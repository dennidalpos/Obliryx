"""Five-stage orchestration. Identifiers and batch approvals live only in memory."""
import copy
import json
import threading
import time
import uuid
from urllib.parse import quote, urlsplit

from .broker_catalog import load_catalog
from .browser_procedures import QUALIFIED_PROCEDURES
from .free_sources import FreeSources, FreeSourceError
from .web_discovery import (FIELDS, SEARCH_HOME, candidate_links, identifiers, match_page,
                            masked, public_url, queries, search_access)
from .store import now
from .windows_secret import application_password


class PrivacyWorkflow:
    def __init__(self, api, *, browser_factory=None, access=search_access, procedures=None, free_sources=None):
        self.api = api
        self.browser_factory = browser_factory
        self.access = access
        self.procedures = dict(QUALIFIED_PROCEDURES if procedures is None else procedures)
        self.free_sources = FreeSources() if free_sources is None else free_sources
        self._mutex = threading.RLock()
        self._cancel = threading.Event()
        self._answer_ready = threading.Event()
        self._answer = None
        self._browser = None
        self._values = {}
        self._items = []
        self._plan = None
        self._epoch = 0
        self._active = False
        self._state = self._empty()

    @staticmethod
    def _empty():
        return dict(phase="input", busy=False, message="", sources=[], items=[], operations=[],
                    assistance=None, history=[], error=None, processed=0, total=0)

    def snapshot(self):
        with self._mutex:
            return copy.deepcopy(self._state)

    def _update(self, **values):
        with self._mutex:
            if not self._cancel.is_set():
                self._state.update(values)

    def open(self):
        with self._mutex:
            if self._active:
                raise ValueError("Completa o annulla l’attività corrente.")
        target = self.api._directory / "desktop-history.sqlite3"
        if not self.api._unlocked:
            password = application_password(self.api._directory)
            result = self.api.unlock(str(target), password, not target.exists(), password)
            password = None
            if not result["ok"]:
                raise ValueError(result["error"])
        elif self.api._path != target.resolve():
            raise ValueError("Chiudi l’archivio precedente prima di tornare al percorso guidato.")
        self._cancel.clear()

        def history():
            return [{"id": key, "title": row.get("title", "Riscontro"),
                     "checked_at": row.get("checked_at"), "status": row.get("status"),
                     "actions": self.api._store.actions(key) + row.get("workflow_operations", [])}
                    for key, row in self.api._store.all() if row.get("source") == "web_workflow"][:100]
        self._update(history=self.api._submit(history).result())
        return self.snapshot()

    def _check(self):
        if self._cancel.is_set() or not self.api._unlocked:
            raise ValueError("Attività annullata. Un invio già iniziato non può essere richiamato.")

    def _get_browser(self):
        self._check()
        if self._browser is None:
            if self.browser_factory is None:
                raise ValueError("Browser integrato non disponibile. Riavvia l’app desktop.")
            self._browser = self.browser_factory()
            if self._cancel.is_set():
                self._browser.close()
                self._browser = None
                self._check()
        return self._browser

    def _launch(self, phase, function):
        with self._mutex, self.api._mutex:
            if self._active or self.api._state["status"] == "running" or not self.api._unlocked:
                raise ValueError("Attendi la fine dell’attività corrente o riapri la sessione.")
            self._cancel.clear()
            self._active = True
            self._state.update(phase=phase, busy=True, error=None, assistance=None)
            epoch = self._epoch

        def run():
            try:
                function()
            except Exception:
                with self._mutex:
                    if epoch == self._epoch:
                        self._state.update(error="Attività interrotta o fonte non disponibile. Gli invii incerti non saranno ripetuti.",
                                           phase="results" if phase == "analysis" else "done")
            finally:
                with self._mutex:
                    self._active = False
                    if epoch == self._epoch:
                        self._state.update(busy=False, assistance=None)
                if self._browser:
                    self._browser.suspend()
        self.api._submit(run)

    def analyze(self, values):
        values = identifiers(values)
        with self._mutex:
            if self._active:
                raise ValueError("Un’analisi è già in corso.")
            self._values = values
            self._items = []
            self._plan = None
            self._state.update(items=[], sources=[], operations=[], processed=0,
                               total=len(queries(values)) + len(self.free_sources.specs(values)))
        self._launch("analysis", self._analyze)
        return {"started": True}

    def _publish_items(self):
        self._update(items=copy.deepcopy(self._items))

    def _save(self, item):
        # No searched identifier, page text, snippets or form values in history.
        record = {"source": "web_workflow", "title": item["title"], "url": item["url"],
                  "checked_at": item.get("checked_at", now()), "status": item["status"],
                  "matches": item.get("matches", [])}
        record_id, _ = self.api._store.save(record, ("web-workflow:" + item["url"]).encode())
        self.api._store.update(record_id, **record)
        return record_id

    def _analyze(self):
        self._check()
        access = self.access()
        sources = []
        seen = set()
        for index, query in enumerate(queries(self._values)):
            self._check()
            source = {"id": uuid.uuid4().hex, "title": "DuckDuckGo · " + query["label"],
                      "masked": query["masked"], "url": query["url"], "external": True, **access}
            sources.append(source)
            self._update(sources=copy.deepcopy(sources), processed=index,
                         message="Verifica della fonte di ricerca · " + query["label"])
            if access["status"] != "available":
                continue
            try:
                browser = self._get_browser()
                snapshot = browser.navigate(query["url"], self._cancel)
                if snapshot.get("challenge") or snapshot.get("password"):
                    source.update(status="blocked", reason="Verifica richiesta. La ricerca è in coda per l’assistenza.")
                    continue
                links = candidate_links(snapshot.get("links", []))
                source.update(status="complete" if links else "incomplete",
                              reason="Pagine candidate da verificare." if links else "Nessuna pagina candidata leggibile; copertura non accertata.")
                for url in links:
                    self._check()
                    if url in seen:
                        continue
                    seen.add(url)
                    self._update(message="Verifica della pagina · " + urlsplit(url).netloc)
                    self._inspect_url(url)
            except (ValueError, OSError):
                source.update(status="unavailable", reason="Fonte non verificabile in questa sessione.")
            finally:
                self._update(sources=copy.deepcopy(sources))
        for spec in self.free_sources.specs(self._values):
            self._check()
            source = {"id":uuid.uuid4().hex, "title":spec["title"], "masked":spec["masked"],
                      "url":spec["url"], "external":True, "status":"searching", "reason":"Consultazione dell’interfaccia pubblica gratuita."}
            sources.append(source)
            self._update(sources=copy.deepcopy(sources), message="Ricerca · " + spec["title"])
            try:
                result = self.free_sources.search(spec, self._cancel)
                source.update(status=result["status"], reason=result["reason"])
                for url in result["links"]:
                    self._check()
                    if url in seen:
                        continue
                    if len(seen) >= 20:
                        source.update(status="incomplete",reason="Raggiunto il limite di 20 pagine per sessione. Raffina i dati di ricerca.")
                        break
                    seen.add(url)
                    self._update(message="Verifica della pagina · " + urlsplit(url).netloc)
                    self._inspect_url(url)
            except (ValueError, OSError) as exc:
                source.update(status="unavailable",reason=str(exc) if isinstance(exc, FreeSourceError) else "Fonte non verificabile in questa sessione.")
            finally:
                self._update(sources=copy.deepcopy(sources),processed=len(sources))
        for row in load_catalog()["procedures"]:
            self._check()
            if not set(row["countries"]) & {"IT", "EU"}:
                continue
            channel = row["channel"]
            adapter = self.procedures.get(row["id"])
            self._items.append({"id": uuid.uuid4().hex, "kind": "broker", "title": row["controller"],
                "url": row["source"], "status": "holding_unknown", "matches": [], "checked_at": row["reviewed_on"],
                "procedure": row["id"], "action": row["action"], "effect": channel["effect"],
                "channel": copy.deepcopy(channel), "mode": "automatic" if adapter else "manual",
                "reason": "La scheda descrive una procedura; non prova il possesso dei tuoi dati.",
                "browser_only": row["action"] == "opt_out_pubblicitario"})
        self._publish_items()
        self._update(phase="results", processed=len(sources), message="Analisi terminata. Controlla la copertura prima di scegliere le azioni.")

    def _inspect_url(self, url):
        public_url(url)
        item = {"id": uuid.uuid4().hex, "kind": "presence", "title": urlsplit(url).netloc,
                "url": url, "action": "verifica_alla_fonte", "effect": "Apri la fonte e verifica il contatto ufficiale per richiedere la rimozione.",
                "mode": "manual", "checked_at": now()}
        try:
            page = self._get_browser().navigate(url, self._cancel)
            item.update(match_page(page, self._values))
        except (ValueError, OSError):
            item.update(status="unavailable", matches=[], reason="Pagina non verificabile.")
        with self._mutex:
            self._check()
            item["record_id"] = self._save(item)
            existing = next((row for row in self._items if row["kind"] == "presence" and row["url"] == url), None)
            if existing:
                item["id"] = existing["id"]
                existing.update(item)
            else:
                self._items.append(item)
            self._publish_items()

    def inspect_url(self, url):
        if not self._values:
            raise ValueError("Inserisci prima i dati per il confronto.")
        url = public_url(url)
        def inspect():
            self._inspect_url(url)
            self._update(phase="results")
        self._plan = None
        self._launch("analysis", inspect)
        return {"started": True}

    def plan(self, selected):
        with self._mutex:
            if self._state["busy"] or not isinstance(selected, list) or not selected or len(set(selected)) != len(selected):
                raise ValueError("Seleziona almeno un risultato e attendi la fine dell’analisi.")
            by_id = {item["id"]: item for item in self._items}
            if any(not isinstance(key, str) or key not in by_id for key in selected):
                raise ValueError("La selezione non è più valida.")
            actions = []
            for key in selected:
                item = by_id[key]
                adapter = self.procedures.get(item.get("procedure"))
                required = [category for _, category in adapter.fields] if adapter else []
                if any(category not in self._values for category in required):
                    adapter = None
                channel = item.get("channel", {"kind": "web", "destination": item["url"]})
                actions.append({"id": key, "title": item["title"], "url": item["url"],
                    "destination": adapter.submit_url if adapter else channel["destination"],
                    "channel": channel["kind"], "effect": item["effect"],
                    "mode": "automatic" if adapter else "manual", "browser_only": item.get("browser_only", False),
                    "fields": {FIELDS[category]: self._values[category] for category in required} if adapter else {},
                    "version": adapter.version if adapter else None, "status": "pending"})
            actions.sort(key=lambda item: item["mode"] != "automatic")
            token = uuid.uuid4().hex
            self._plan = {"id": token, "created": time.monotonic(), "actions": actions, "used": False}
            self._update(phase="approval")
            return {"id": token, "actions": copy.deepcopy(actions)}

    def execute(self, plan_id):
        with self._mutex:
            plan = self._plan
            if (self._state["busy"] or not plan or plan["id"] != plan_id or plan["used"]
                    or time.monotonic() - plan["created"] > 300):
                raise ValueError("Riepilogo scaduto o già usato. Seleziona di nuovo le azioni.")
            plan["used"] = True
            self._update(operations=copy.deepcopy(plan["actions"]))
        self._launch("execution", self._execute)
        return {"started": True}

    def _operation(self, key, **changes):
        with self._mutex:
            if self._cancel.is_set():
                return
            for operation in self._state["operations"]:
                if operation["id"] == key:
                    operation.update(changes)

    def edit_selection(self):
        with self._mutex:
            if self._active:
                raise ValueError("Attendi la fine dell’attività corrente.")
            self._plan = None
            self._state["phase"] = "results"
        return None

    def _wait_assistance(self, request):
        self._answer_ready.clear()
        self._answer = None
        request["request_id"] = uuid.uuid4().hex
        self._update(assistance=request, message="Completa la verifica nel browser integrato, poi continua.")
        while not self._answer_ready.wait(.15):
            self._check()
        self._check()
        answer = self._answer
        self._update(assistance=None)
        return answer

    def _execute(self):
        pending = []
        by_id = {item["id"]: item for item in self._items}
        for operation in copy.deepcopy(self._state["operations"]):
            self._check()
            item = by_id[operation["id"]]
            adapter = self.procedures.get(item.get("procedure")) if operation["mode"] == "automatic" else None
            if adapter is None:
                pending.append(operation)
                continue
            self._operation(operation["id"], status="checking")
            try:
                page = self._get_browser().navigate(adapter.page_url, self._cancel)
                contract = self._browser.inspect(adapter)
                if page.get("challenge") or page.get("password") or (isinstance(contract, dict) and contract.get("challenge")):
                    self._operation(operation["id"], status="queued_verification")
                    pending.append(operation)
                elif not adapter.accepts(contract):
                    self._operation(operation["id"], status="approval_invalidated", reason="La procedura è cambiata. Serve una nuova revisione e approvazione.")
                else:
                    self._submit_operation(operation, item, adapter)
            except (ValueError, OSError):
                current = next(row for row in self.snapshot()["operations"] if row["id"] == operation["id"])
                if current["status"] not in {"delivery_unknown", "accepted"}:
                    self._operation(operation["id"], status="unavailable", reason="Procedura o registro non disponibili. Controlla lo storico prima di ripetere un invio.")
        for operation in pending:
            self._check()
            item = by_id[operation["id"]]
            self._operation(operation["id"], status="awaiting_user")
            # Email and browser-cookie preferences stay direct links, not fake automation.
            if operation["channel"] == "email" or operation["browser_only"]:
                self._operation(operation["id"], status="manual", reason="Usa la bozza email o il browser abituale per questa procedura.")
                continue
            try:
                self._get_browser().assist(operation["url"], self._cancel)
                answer = self._wait_assistance({"id": operation["id"], "title": operation["title"],
                    "domain": urlsplit(operation["url"]).netloc, "url": operation["url"]})
                self._browser.suspend()
                if answer == "skip":
                    self._operation(operation["id"], status="skipped")
                    continue
                adapter = self.procedures.get(item.get("procedure")) if operation["mode"] == "automatic" else None
                if adapter:
                    if adapter.accepts(self._browser.inspect(adapter)):
                        self._submit_operation(operation, item, adapter)
                    else:
                        self._operation(operation["id"], status="approval_invalidated", reason="Stato o campi inattesi. L’approvazione non è più valida.")
                else:
                    self._operation(operation["id"], status="manual_review", reason="Passaggio manuale concluso; invio e rimozione non verificati dall’app.")
            except (ValueError, OSError):
                self._operation(operation["id"], status="unavailable", reason="Browser non disponibile; usa il collegamento diretto.")
        self._update(phase="done", message="Operazioni terminate. Un invio accettato non dimostra la rimozione dei dati.")
        for operation in self.snapshot()["operations"]:
            if operation["mode"] == "manual":
                record_id = self._save(by_id[operation["id"]])
                record = self.api._store.get(record_id)
                events = record.get("workflow_operations", [])
                events.append({"status":operation["status"], "when":now()})
                self.api._store.update(record_id, workflow_operations=events[-100:])

    def _submit_operation(self, operation, item, adapter):
        if (operation["destination"] != adapter.submit_url or operation["version"] != adapter.version
                or not adapter.accepts(self._browser.inspect(adapter))):
            self._operation(operation["id"], status="approval_invalidated")
            return
        record_id = item.get("record_id") or self._save(item)
        store = self.api._store
        finding = store.get(record_id)
        checkpoint = store.review_action(record_id, finding)
        self._check()
        # Reserve before browser execution; the encrypted approval includes exact fields.
        action_id = store.start_action(record_id, "browser:" + adapter.identifier + ":" + adapter.submit_url,
            form_address=json.dumps({category: self._values[category] for _, category in adapter.fields}, sort_keys=True),
            form_page=adapter.page_url, preview={**operation, "fields": {key: masked(value) for key, value in operation["fields"].items()}},
            reviewed_checkpoint=checkpoint, reviewed_finding=finding)
        self._operation(operation["id"], status="delivery_unknown")
        status = "delivery_unknown"
        try:
            if self._browser.submit(adapter, self._values) == "submitted":
                page = self._browser.completion(adapter)
                if adapter.completed(page):
                    status = "accepted"
        except Exception:
            # Reservation has happened: errors must remain uncertain, never 'not sent'.
            status = "delivery_unknown"
        finally:
            try:
                store.finish_action(action_id, status)
            finally:
                self._operation(operation["id"], status=status, removal_verified=False)

    def respond(self, request_id, answer):
        with self._mutex:
            request = self._state["assistance"]
            if (not request or request["request_id"] != request_id or self._answer_ready.is_set()
                    or answer not in {"continue", "skip"}):
                raise ValueError("Verifica scaduta o risposta non valida.")
            self._answer = answer
            self._answer_ready.set()
        return None

    def cancel(self, *, clear=False):
        browser = None
        with self._mutex:
            self._cancel.set()
            self._answer_ready.set()
            self._plan = None
            if clear:
                self._epoch += 1
                self._values.clear()
                self._items.clear()
                self._state = self._empty()
                browser, self._browser = self._browser, None
        if browser:
            browser.close()
        elif self._browser:
            self._browser.suspend()

    def close(self):
        self.cancel(clear=True)

    def link(self, identifier):
        """Only backend-owned links can be opened; never accept a URL from bridge input."""
        with self._mutex:
            source = next((row for row in self._state["sources"] if row["id"] == identifier), None)
            item = next((row for row in self._items if row["id"] == identifier), None)
            if source:
                url = source["url"]
            elif item:
                channel = item.get("channel", {})
                if channel.get("kind") == "email":
                    destination = channel["destination"]
                    body = "Buongiorno,\nvorrei esercitare la seguente richiesta: " + item["effect"] + "\n\nCordiali saluti"
                    url = "mailto:" + quote(destination, safe="@") + "?subject=" + quote("Richiesta privacy") + "&body=" + quote(body)
                else:
                    url = public_url(channel.get("destination", item["url"]))
            else:
                raise ValueError("Collegamento non più disponibile.")
        import webbrowser
        webbrowser.open(url)
        return None
