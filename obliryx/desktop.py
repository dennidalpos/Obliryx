"""Desktop application boundary. All SQLite work belongs to one worker thread.

No web server or command interpreter is exposed. Pending questions are held only
in memory and are invalidated by cancellation, expiry, locking and process exit.
"""
import copy
import os
import queue
import sqlite3
import threading
import time
import uuid
from concurrent.futures import Future
from pathlib import Path

from . import services
from .analysis import severity
from .broker_catalog import catalog_view
from .cli import data_directory, parser
from .desktop_schema import OPERATIONS, POSITIONAL
from .interaction import using
from .mail_import import collect, eml_snapshot, read_eml
from .store import Store


class Cancelled(Exception):
    pass


class DesktopInteraction:
    def __init__(self, api, generation):
        self.api = api
        self.generation = generation
        self.cancelled = threading.Event()
        self.answer_ready = threading.Event()
        self.answer = None
        self.expires = 0

    def check(self):
        if self.cancelled.is_set() or self.generation != self.api._generation or not self.api._unlocked:
            raise Cancelled()

    def begin_effect(self):
        # Linearization point: once admitted, an already-started POST may finish.
        # Lock/cancel prevents every subsequent effect; a timeout is never retried.
        with self.api._mutex:
            self.check()
            self.api._state["phase"] = "Invio in corso: l’annullamento non può richiamarlo."

    def _request(self, kind, label, preview=None, secret=False):
        self.check()
        request_id = uuid.uuid4().hex
        self.answer_ready.clear()
        self.answer = None
        self.expires = time.monotonic() + 300
        with self.api._mutex:
            self.api._state["request"] = dict(id=request_id, kind=kind, label=label,
                                                preview=preview, secret=secret)
            self.api._state["phase"] = "In attesa della tua verifica"
        try:
            while not self.answer_ready.wait(.15):
                self.check()
                if time.monotonic() >= self.expires:
                    raise ValueError("Anteprima scaduta. Avvia nuovamente l’operazione.")
            self.check()
            if time.monotonic() >= self.expires:
                raise ValueError("Anteprima scaduta. Avvia nuovamente l’operazione.")
            answer, self.answer = self.answer, None
            return answer
        finally:
            with self.api._mutex:
                self.api._state["request"] = None

    def ask(self, label, secret=False):
        return self._request("field", label, secret=secret)

    def approve(self, value, message):
        if self._request("approval", message, copy.deepcopy(value)) != "CONFERMO":
            raise Cancelled()

    def emit(self, value):
        self.check()
        with self.api._mutex:
            self.api._state["result"] = copy.deepcopy(value)

    def notify(self, message):
        with self.api._mutex:
            self.api._state["phase"] = message


def safe(method):
    def call(self, *args, **kwargs):
        try:
            return {"ok": True, "value": method(self, *args, **kwargs)}
        except Cancelled:
            return {"ok": False, "error": "Operazione annullata."}
        except ValueError as exc:
            return {"ok": False, "error": str(exc)}
        except (OSError, sqlite3.Error):
            return {"ok": False, "error": "Accesso al file, all’archivio o alla rete non riuscito. Verifica il percorso e riprova."}
        except Exception:
            # Never return tracebacks, credentials, provider responses or raw exceptions.
            return {"ok": False, "error": "Operazione non riuscita. Blocca e riapri l’archivio prima di riprovare."}
    return call


class DesktopAPI:
    def __init__(self, directory=None, clock=time.monotonic):
        self._directory = Path(directory) if directory else data_directory()
        self._clock = clock
        self._mutex = threading.RLock()
        self._queue = queue.Queue()
        self._generation = 0
        self._unlocked = False
        self._store = None
        self._path = None
        self._interaction = None
        self._state = dict(id=None, status="idle", phase="", request=None, result=None, error=None)
        self._last_activity = clock()
        self._window = None
        self._stopped = threading.Event()
        self._thread = threading.Thread(target=self._worker, daemon=True, name="obliryx-vault")
        self._thread.start()
        threading.Thread(target=self._idle_watch, daemon=True, name="obliryx-lock").start()

    def _worker(self):
        while True:
            function, future = self._queue.get()
            if function is None:
                if self._store:
                    self._store.close()
                    self._store = None
                future.set_result(None)
                return
            try:
                future.set_result(function())
            except BaseException as exc:
                future.set_exception(exc)
            finally:
                # Release the last callable/traceback too, including unlock inputs.
                del function, future

    def _submit(self, function):
        future = Future()
        self._queue.put((function, future))
        return future

    def _idle_watch(self):
        while not self._stopped.wait(1):
            self._expire_idle()

    def _expire_idle(self):
        if self._unlocked and self._clock() - self._last_activity >= 900:
            self.lock()

    def _close(self):
        self.lock()
        self._stopped.set()
        future = Future()
        self._queue.put((None, future))
        future.result(timeout=60)

    @safe
    def bootstrap(self):
        return {"version": "0.1.0.dev0", "default_path": str(self._directory / "findings.sqlite3"),
                "operations": [{"id": key, "label": label, "group": group, "fields": fields}
                               for key, (label, group, fields) in OPERATIONS.items()]}

    @safe
    def unlock(self, path, password, create=False, repeated=""):
        if not isinstance(path, str) or not isinstance(password, str):
            raise ValueError("Percorso e passphrase non validi.")
        if len(password) < 12:
            raise ValueError("Usa una passphrase di almeno 12 caratteri.")
        with self._mutex:
            if self._unlocked or self._state["status"] == "running":
                raise ValueError("Blocca prima l’archivio aperto.")
            target = Path(path).resolve()
            if create and (target.exists() or password != repeated):
                raise ValueError("Le passphrase non coincidono oppure il file esiste già. Scegli Apri archivio.")
            if not create and not target.is_file():
                raise ValueError("L’archivio non esiste. Scegli Crea archivio o seleziona un file esistente.")
            generation = self._generation

        def opening():
            with self._mutex:
                if generation != self._generation or self._unlocked:
                    raise Cancelled()
            # Reserve the new filename atomically: never overwrite/open another vault as 'new'.
            reserved = False
            if create:
                target.parent.mkdir(parents=True, exist_ok=True)
                with target.open("xb"):
                    reserved = True
            store = Store(target, password, ledger_dir=self._directory / "action-state")
            with self._mutex:
                if generation != self._generation:
                    store.close()
                    raise Cancelled()
                if self._store:
                    self._store.close()
                self._store, self._path = store, target
                self._unlocked = True
                self._last_activity = self._clock()
                self._state = dict(id=None, status="idle", phase="", request=None, result=None, error=None)
            return {"path": str(target), "created": reserved}
        return self._submit(opening).result()

    @safe
    def lock(self):
        with self._mutex:
            self._generation += 1
            self._unlocked = False
            if self._interaction:
                self._interaction.cancelled.set()
                self._interaction.answer = None
                self._interaction.answer_ready.set()
            self._state = dict(id=None, status="idle", phase="", request=None, result=None, error=None)
        def closing():
            if self._store:
                self._store.close()
                self._store = None
        self._submit(closing)
        return None

    @safe
    def touch(self):
        # Called only for real user keyboard/pointer activity, never by polling.
        self._last_activity = self._clock()

    @safe
    def status(self):
        with self._mutex:
            return {"unlocked": self._unlocked, "path": str(self._path) if self._unlocked else None,
                    "job": copy.deepcopy(self._state)}

    @safe
    def findings(self, offset=0, limit=100):
        if type(offset) is not int or type(limit) is not int or offset < 0 or not 1 <= limit <= 500:
            raise ValueError("Intervallo di lettura non valido.")
        with self._mutex:
            if not self._unlocked or self._state["status"] == "running":
                raise ValueError("Attendi la fine dell’attività o annullala prima di leggere l’archivio.")
            generation = self._generation
        def reading():
            if generation != self._generation or self._store is None:
                raise Cancelled()
            items = [{"id": key, **item, "gravita": severity(item)[0],
                      "motivo": severity(item)[1], "azioni": self._store.actions(key)}
                     for key, item in self._store.all()]
            items.sort(key=lambda item: ({"alta": 0, "media": 1, "bassa": 2}[item["gravita"]], item["id"]))
            return {"items": items[offset:offset + limit], "total": len(items)}
        result = self._submit(reading).result()
        if generation != self._generation:
            raise Cancelled()
        return result

    @safe
    def catalog(self, identifier=None):
        return catalog_view(identifier)

    @safe
    def start(self, operation, parameters=None):
        if operation not in OPERATIONS or not isinstance(parameters, (dict, type(None))):
            raise ValueError("Operazione desktop non valida.")
        parameters = parameters or {}
        _, group, fields = OPERATIONS[operation]
        allowed = {f["key"] for f in fields} | ({"id"} if group == "detail" else set())
        if set(parameters) - allowed:
            raise ValueError("Parametri non previsti per questa operazione.")
        for item in fields:
            value = parameters.get(item["key"], item["default"])
            if not isinstance(value, str) or len(value) > 32768 or (item["required"] and not value):
                raise ValueError("Compila il campo: " + item["label"])
            if item["choices"] and value not in item["choices"]:
                raise ValueError("Scelta non valida: " + item["label"])
            parameters[item["key"]] = value
        if group == "detail":
            try:
                uuid.UUID(parameters.get("id", ""))
            except (ValueError, TypeError, AttributeError):
                raise ValueError("Seleziona un riscontro valido.") from None
        actual = "draft" if operation in {"compose", "draft-route", "compose-route"} else operation
        args = [actual]
        for key in POSITIONAL.get(actual, []):
            if key == "id" or key in parameters:
                value = parameters[key]
                if value.startswith("-"):
                    raise ValueError("Il parametro non può iniziare con un trattino. Usa un percorso assoluto.")
                args.append(value)
        for key, value in parameters.items():
            if key not in POSITIONAL.get(actual, []) and value:
                args.extend(["--" + key, value])
        if operation in {"compose", "compose-route"}:
            args.append("--compose")
        try:
            parsed = parser().parse_args(args)
        except SystemExit:
            raise ValueError("Parametri non validi. Controlla numeri, percorsi e opzioni.") from None
        with self._mutex:
            if not self._unlocked or self._state["status"] == "running":
                raise ValueError("Apri l’archivio e completa o annulla l’attività corrente.")
            job_id = uuid.uuid4().hex
            interaction = DesktopInteraction(self, self._generation)
            self._interaction = interaction
            self._state = dict(id=job_id, status="running", phase="Operazione in corso", request=None, result=None, error=None)
            self._submit(lambda: self._execute(parsed, interaction, job_id))
            return {"id": job_id}

    def _execute(self, args, interaction, job_id):
        status, error = "completed", None
        try:
            with using(interaction):
                interaction.check()
                if args.command == "search-web":
                    services.lookup_web()
                elif args.command == "watch-eml":
                    self._monitor(args, interaction)
                else:
                    services.run(self._store, args)
        except Cancelled:
            status, error = "cancelled", "Operazione annullata. Gli elementi già importati sono conservati; un invio iniziato non può essere richiamato."
        except ValueError as exc:
            status, error = "failed", str(exc)
        except Exception:
            status, error = "failed", "Operazione non riuscita. Verifica file e rete; controlla il registro prima di ripetere un invio."
        finally:
            interaction.answer = None
            with self._mutex:
                if self._state["id"] == job_id:
                    self._state.update(status=status, error=error, request=None,
                                       phase="Attività completata" if status == "completed" else error)
                if self._interaction is interaction:
                    self._interaction = None

    def _monitor(self, args, interaction):
        if not args.path.is_dir() or not 1 <= args.interval <= 3600:
            raise ValueError("Scegli una cartella e un intervallo da 1 a 3600 secondi.")
        previous, processed = eml_snapshot(args.path), {}
        interaction.notify("Monitoraggio attivo durante questa sessione. Arresta per consultare i riscontri.")
        while not interaction.cancelled.wait(args.interval):
            interaction.check()
            snapshot = eml_snapshot(args.path)
            processed = {file: sig for file, sig in processed.items() if file in snapshot}
            for file, signature in sorted(snapshot.items()):
                interaction.check()
                if previous.get(file) != signature or processed.get(file) == signature:
                    continue
                try:
                    raw = read_eml(file)
                    if eml_snapshot(args.path).get(file) != signature:
                        continue
                except (OSError, ValueError):
                    raw = None
                interaction.emit(collect(self._store, [raw]))
                processed[file] = signature
            previous = snapshot
        raise Cancelled()

    @safe
    def respond(self, job_id, request_id, answer):
        if not isinstance(answer, str) or len(answer) > 32768:
            raise ValueError("Risposta non valida.")
        with self._mutex:
            interaction = self._interaction
            request = self._state["request"]
            if not interaction or not request or self._state["id"] != job_id or request["id"] != request_id:
                raise ValueError("Richiesta non più valida. Genera una nuova anteprima.")
            interaction.check()
            if interaction.answer_ready.is_set() or time.monotonic() >= interaction.expires:
                raise ValueError("Risposta già usata o anteprima scaduta.")
            interaction.answer = answer
            self._state["request"] = None
            interaction.answer_ready.set()

    @safe
    def cancel(self, job_id):
        with self._mutex:
            if self._state["id"] != job_id or self._interaction is None:
                return None
            self._interaction.cancelled.set()
            self._interaction.answer = None
            self._interaction.answer_ready.set()

    @safe
    def choose_path(self, mode="open"):
        if mode not in {"open", "save", "folder"} or self._window is None:
            raise ValueError("Selettore non disponibile.")
        import webview
        kind = {"open": webview.FileDialog.OPEN, "save": webview.FileDialog.SAVE, "folder": webview.FileDialog.FOLDER}[mode]
        selected = self._window.create_file_dialog(kind, allow_multiple=False)
        if not selected:
            return None
        return str(selected if isinstance(selected, str) else selected[0])
