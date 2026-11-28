import hashlib
import hmac
import json
import os
import sqlite3
from contextlib import closing, contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def now():
    return datetime.now(UTC).isoformat(timespec="seconds")


ACTION_COLUMNS = "id, finding_id, fingerprint, status, started_at, finished_at, kind, approval"
RECONCILE_REQUIRED = "Invii sospesi: esegui action-status e poi action-reconcile dopo la verifica."


def open_private(path, *, exclusive=False):
    flags = os.O_CREAT | os.O_RDWR | (os.O_EXCL if exclusive else 0)
    return os.open(path, flags, 0o600)


def derive_key(password, salt):
    return hashlib.scrypt(password.encode(), salt=salt, n=2**16, r=8, p=1,
                          dklen=64, maxmem=128 * 1024 * 1024)


def wrap_key(password, salt, key):
    nonce = os.urandom(12)
    wrapper = AESGCM(derive_key(password, salt)[:32])
    return nonce + wrapper.encrypt(nonce, key, b"obliryx-vault-key-v2")


class Store:
    def __init__(self, path: Path, password: str, *, ledger_dir=None, readonly=False):
        if len(password) < 12:
            raise ValueError("Usa una passphrase di almeno 12 caratteri.")
        if not readonly:
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.close(open_private(path))
        self.db = sqlite3.connect(path.resolve().as_uri() + ("?mode=ro" if readonly else "?mode=rw"), uri=True)
        self.db.row_factory = sqlite3.Row
        try:
            if readonly:
                row = self.db.execute("SELECT * FROM vault WHERE id = 1").fetchone()
                if row is None:
                    raise ValueError("Il file non contiene un archivio Obliryx.")
                self._unlock(row, password)
                return
            with self.db:
                self.db.execute("PRAGMA foreign_keys = ON")
                self.db.executescript("""
                    CREATE TABLE IF NOT EXISTS vault (
                        id INTEGER PRIMARY KEY CHECK (id = 1), salt BLOB NOT NULL,
                        verifier BLOB NOT NULL, key_format INTEGER NOT NULL DEFAULT 1,
                        action_checkpoint TEXT
                    );
                    CREATE TABLE IF NOT EXISTS findings (
                        id TEXT PRIMARY KEY, fingerprint BLOB NOT NULL UNIQUE,
                        payload BLOB NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS actions (
                        id TEXT PRIMARY KEY, finding_id TEXT NOT NULL REFERENCES findings(id),
                        fingerprint BLOB NOT NULL UNIQUE, status TEXT NOT NULL,
                        started_at TEXT NOT NULL, finished_at TEXT,
                        kind TEXT NOT NULL DEFAULT 'one_click', approval BLOB
                    );
                """)
                self.db.execute("BEGIN IMMEDIATE")
                row = self.db.execute("SELECT * FROM vault WHERE id = 1").fetchone()
                if row:
                    self._unlock(row, password)
                    checkpoint = None
                else:
                    self._set_key(os.urandom(64))
                    salt = os.urandom(16)
                    self.verifier = wrap_key(password, salt, self.key)
                    checkpoint = uuid4().hex
                self._migrate()
                if row is None:
                    self.db.execute("INSERT INTO vault VALUES (1, ?, ?, 2, ?)",
                                    (salt, self.verifier, checkpoint))
            ledger_dir = ledger_dir if ledger_dir is not None else path.parent / ".obliryx-action-state"
            self.ledger_path = ledger_dir / (self._fingerprint(b"action-ledger", b"").hex() + ".sqlite3")
            if checkpoint is not None:
                with self._ledger(create=True):
                    self.db.execute("INSERT INTO ledger.state VALUES (1, ?, 0)", (checkpoint,))
        except BaseException:
            self.close()
            raise

    def _migrate(self):
        action_columns = {row["name"] for row in self.db.execute("PRAGMA table_info(actions)")}
        if "kind" not in action_columns:
            self.db.execute("ALTER TABLE actions ADD COLUMN kind TEXT NOT NULL DEFAULT 'one_click'")
        if "approval" not in action_columns:
            self.db.execute("ALTER TABLE actions ADD COLUMN approval BLOB")
        vault_columns = {row["name"] for row in self.db.execute("PRAGMA table_info(vault)")}
        if "key_format" not in vault_columns:
            self.db.execute("ALTER TABLE vault ADD COLUMN key_format INTEGER NOT NULL DEFAULT 1")
        if "action_checkpoint" not in vault_columns:
            self.db.execute("ALTER TABLE vault ADD COLUMN action_checkpoint TEXT")

    def _set_key(self, key):
        self.key = key
        self.cipher = AESGCM(key[:32])
        self.mac_key = key[32:]

    def _unlock(self, row, password):
        key = derive_key(password, row["salt"])
        self.verifier = row["verifier"]
        key_format = row["key_format"] if "key_format" in row.keys() else 1
        if key_format == 1:
            self._set_key(key)
            self._open("vault", self.verifier)
        elif key_format == 2:
            try:
                key = AESGCM(key[:32]).decrypt(self.verifier[:12], self.verifier[12:], b"obliryx-vault-key-v2")
            except InvalidTag:
                raise ValueError("Passphrase errata o archivio danneggiato.") from None
            if len(key) != 64:
                raise ValueError("Chiave dell’archivio non valida.")
            self._set_key(key)
        else:
            raise ValueError("Formato della chiave dell’archivio non supportato.")

    def rotate_password(self, password):
        if len(password) < 12:
            raise ValueError("Usa una passphrase di almeno 12 caratteri.")
        salt = os.urandom(16)
        verifier = wrap_key(password, salt, self.key)
        self.db.execute("PRAGMA secure_delete = ON")
        with self.db:
            cursor = self.db.execute("""
                UPDATE vault SET salt = ?, verifier = ?, key_format = 2 WHERE id = 1 AND verifier = ?
            """, (salt, verifier, self.verifier))
            if cursor.rowcount != 1:
                raise ValueError("La passphrase è già cambiata. Riapri l’archivio.")
        self.verifier = verifier

    def backup_to(self, path):
        if [row[0] for row in self.db.execute("PRAGMA quick_check")] != ["ok"]:
            raise ValueError("Il controllo di integrità dell’archivio è fallito.")
        try:
            os.close(open_private(path, exclusive=True))
        except FileExistsError:
            raise ValueError("Il file di destinazione esiste già.") from None
        try:
            with closing(sqlite3.connect(path)) as backup:
                self.db.backup(backup)
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    def export_to(self, path):
        # Keep URL tokens, free-form evidence, mailbox details and approved payloads in the vault.
        keys = ("source", "sender", "controller", "data_types", "acquisition", "enrollment", "outcomes")
        try:
            output = os.fdopen(open_private(path, exclusive=True), "w", encoding="utf-8")
        except FileExistsError:
            raise ValueError("Il file di destinazione esiste già.") from None
        try:
            with output, self.db:
                self.db.execute("BEGIN")
                findings = [{"id": finding_id, **{key: finding[key] for key in keys if key in finding},
                             "azioni": self.actions(finding_id)} for finding_id, finding in self.all()]
                json.dump({"schema": 1, "riscontri": findings}, output, ensure_ascii=False, indent=2)
                output.write("\n")
        except BaseException:
            path.unlink(missing_ok=True)
            raise

    def close(self):
        self.db.close()

    def _seal(self, record_id, value):
        nonce = os.urandom(12)
        payload = json.dumps(value, ensure_ascii=False).encode()
        return nonce + self.cipher.encrypt(nonce, payload, record_id.encode())

    def _open(self, record_id, blob):
        try:
            return json.loads(self.cipher.decrypt(blob[:12], blob[12:], record_id.encode()))
        except InvalidTag:
            raise ValueError("Passphrase errata o archivio danneggiato.") from None

    def _fingerprint(self, namespace, value):
        return hmac.digest(self.mac_key, namespace + b"\x00" + value, "sha256")

    def save(self, finding, identity, *, alternate_identities=()):
        finding_id = str(uuid4())
        fingerprint = self._fingerprint(b"finding", identity)
        with self.db:
            if alternate_identities:
                self.db.execute("BEGIN IMMEDIATE")
                candidates = [self._fingerprint(b"finding", value) for value in alternate_identities]
                placeholders = ",".join("?" for _ in candidates)
                match = self.db.execute(f"SELECT id FROM findings WHERE fingerprint IN ({placeholders})",
                                        candidates).fetchone()
                if match:
                    return match["id"], False
            self.db.execute("INSERT INTO findings VALUES (?, ?, ?) ON CONFLICT(fingerprint) DO NOTHING",
                            (finding_id, fingerprint, self._seal(finding_id, finding)))
            row = self.db.execute("SELECT id FROM findings WHERE fingerprint = ?", (fingerprint,)).fetchone()
        return row["id"], row["id"] == finding_id

    def get(self, finding_id):
        row = self.db.execute("SELECT payload FROM findings WHERE id = ?", (finding_id,)).fetchone()
        if not row:
            raise ValueError("Riscontro inesistente.")
        return self._open(finding_id, row["payload"])

    def matches(self, finding_id, identity):
        fingerprint = self._fingerprint(b"finding", identity)
        return self.db.execute("SELECT 1 FROM findings WHERE id = ? AND fingerprint = ?",
                               (finding_id, fingerprint)).fetchone() is not None

    def all(self):
        with closing(self.db.execute("SELECT id, payload FROM findings ORDER BY rowid DESC")) as cursor:
            for row in cursor:
                yield row["id"], self._open(row["id"], row["payload"])

    def update(self, finding_id, **changes):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            finding = self.get(finding_id)
            finding.update(changes)
            self.db.execute("UPDATE findings SET payload = ? WHERE id = ?",
                            (self._seal(finding_id, finding), finding_id))

    def record_outcome(self, finding_id, status):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            finding = self.get(finding_id)
            finding.setdefault("outcomes", []).append({"status": status, "recorded_at": now(), "source": "utente"})
            self.db.execute("UPDATE findings SET payload = ? WHERE id = ?",
                            (self._seal(finding_id, finding), finding_id))

    def record_controller(self, finding_id, name, url, reason):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            finding = self.get(finding_id)
            review = {"name": name, "source_url": url, "association": reason, "reviewed_at": now()}
            finding.setdefault("controller_reviews", []).append(review)
            self.db.execute("UPDATE findings SET payload = ? WHERE id = ?",
                            (self._seal(finding_id, finding), finding_id))
            return review

    def record_web_check(self, finding_id, observed, reason=None):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            finding = self.get(finding_id)
            checks = finding.setdefault("web_checks", [])
            if observed is None:
                status = "non_verificabile"
            elif observed is False:
                status = "dato_non_osservato"
            else:
                previous = next((item["status"] for item in reversed(checks)
                                 if item["status"] != "non_verificabile"), None)
                status = "ricomparsa" if previous == "dato_non_osservato" else "dato_osservato"
            event = {"status": status, "checked_at": now()}
            if reason:
                event["reason"] = reason
            checks.append(event)
            self.db.execute("UPDATE findings SET payload = ? WHERE id = ?",
                            (self._seal(finding_id, finding), finding_id))
            return event

    def record_mail_match(self, finding_id, category, fields, subject):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            finding = self.get(finding_id)
            matches = finding.setdefault("mail_matches", {})
            merged_fields = sorted(set(matches.get(category, ())) | set(fields))
            categories = sorted(set(finding["data_types"]) | {category})
            subject = subject if "oggetto" in fields else finding["subject"]
            if (matches.get(category) == merged_fields and finding["data_types"] == categories
                    and finding["subject"] == subject):
                return False
            matches[category] = merged_fields
            finding.update(data_types=categories, subject=subject)
            self.db.execute("UPDATE findings SET payload = ? WHERE id = ?",
                            (self._seal(finding_id, finding), finding_id))
            return True

    def add_imap_source(self, finding_id, source):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            finding = self.get(finding_id)
            sources = finding.setdefault("imap_sources", [])
            if source in sources:
                return
            sources.append(source)
            self.db.execute("UPDATE findings SET payload = ? WHERE id = ?",
                            (self._seal(finding_id, finding), finding_id))

    def add_routes(self, finding_id, candidates):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            finding = self.get(finding_id)
            routes = finding["routes"]
            seen = {(route["kind"], route["value"]) for route in routes}
            added = 0
            for candidate in candidates:
                key = (candidate["kind"], candidate["value"])
                if key not in seen:
                    seen.add(key)
                    routes.append(candidate)
                    added += 1
            if added:
                self.db.execute("UPDATE findings SET payload = ? WHERE id = ?",
                                (self._seal(finding_id, finding), finding_id))
            return added

    def confirm_route(self, finding_id, kind, url):
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            finding = self.get(finding_id)
            for route in finding["routes"]:
                if route["kind"] == kind and route["value"] == url:
                    route["confirmed_at"] = now()
                    self.db.execute("UPDATE findings SET payload = ? WHERE id = ?",
                                    (self._seal(finding_id, finding), finding_id))
                    return
            raise ValueError("Il canale da confermare non è più presente.")

    @contextmanager
    def _ledger(self, *, create=False, write=True):
        if create:
            self.ledger_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            os.close(open_private(self.ledger_path))
        if not self.ledger_path.is_file():
            raise ValueError(RECONCILE_REQUIRED)
        self.db.execute("ATTACH DATABASE ? AS ledger", (self.ledger_path.resolve().as_uri() + "?mode=rw",))
        try:
            if write:
                for schema in ("main", "ledger"):
                    if self.db.execute(f"PRAGMA {schema}.journal_mode").fetchone()[0] != "delete":
                        raise ValueError("Per gli invii entrambi i database devono usare il journal SQLite DELETE.")
                    self.db.execute(f"PRAGMA {schema}.synchronous = EXTRA")
            with self.db:
                self.db.execute("BEGIN IMMEDIATE" if write else "BEGIN")
                if create:
                    self.db.execute("""
                        CREATE TABLE IF NOT EXISTS ledger.state (
                            id INTEGER PRIMARY KEY CHECK (id = 1), checkpoint TEXT NOT NULL,
                            paused INTEGER NOT NULL CHECK (paused IN (0, 1))
                        )
                    """)
                    self.db.execute("""
                        CREATE TABLE IF NOT EXISTS ledger.attempts (
                            id TEXT PRIMARY KEY, finding_id TEXT NOT NULL, fingerprint BLOB NOT NULL UNIQUE,
                            status TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT,
                            kind TEXT NOT NULL, approval BLOB
                        )
                    """)
                yield
        finally:
            self.db.execute("DETACH DATABASE ledger")

    def _checkpoint(self):
        return self.db.execute("SELECT action_checkpoint FROM vault WHERE id = 1").fetchone()[0]

    def _ledger_state(self):
        return self.db.execute("SELECT checkpoint, paused FROM ledger.state WHERE id = 1").fetchone()

    def _ready_checkpoint(self):
        state = self._ledger_state()
        if state is None or state["checkpoint"] != self._checkpoint():
            raise ValueError(RECONCILE_REQUIRED)
        if state["paused"]:
            raise ValueError("Invii sospesi. Usa action-resume per riabilitare le nuove approvazioni.")
        return state["checkpoint"]

    def review_action(self, finding_id, finding):
        with self._ledger(write=False):
            checkpoint = self._ready_checkpoint()
            if self.get(finding_id) != finding:
                raise ValueError("Il riscontro è cambiato. Genera una nuova anteprima.")
        return checkpoint

    def _advance_checkpoint(self, previous, *, paused=None):
        checkpoint = uuid4().hex
        if paused is None:
            self.db.execute("UPDATE ledger.state SET checkpoint = ? WHERE id = 1", (checkpoint,))
        else:
            self.db.execute("UPDATE ledger.state SET checkpoint = ?, paused = ? WHERE id = 1", (checkpoint, paused))
        self.db.execute("UPDATE vault SET action_checkpoint = ? WHERE id = 1 AND action_checkpoint IS ?",
                        (checkpoint, previous))

    def set_actions_paused(self, paused):
        with self._ledger():
            state = self._ledger_state()
            if state is None or (not paused and state["checkpoint"] != self._checkpoint()):
                raise ValueError(RECONCILE_REQUIRED)
            if bool(state["paused"]) != paused:
                self._advance_checkpoint(state["checkpoint"], paused=paused)

    def _reconciliation_preview(self, *, has_ledger):
        state = self._ledger_state() if has_ledger else None
        checkpoint = self._checkpoint()
        aligned = bool(state and checkpoint == state["checkpoint"])
        if state:
            attempts = self.db.execute("""
                SELECT id, finding_id, status, kind, started_at, finished_at
                FROM ledger.attempts AS a WHERE a.status = 'delivery_unknown' OR NOT EXISTS (
                    SELECT 1 FROM actions AS local
                    WHERE local.id = a.id AND local.status = a.status AND local.finished_at IS a.finished_at
                )
                UNION ALL
                SELECT id, finding_id, status, kind, started_at, finished_at FROM actions AS local
                WHERE NOT EXISTS (SELECT 1 FROM ledger.attempts WHERE id = local.id)
                ORDER BY started_at, id
            """)
        else:
            attempts = self.db.execute("""
                SELECT id, finding_id, status, kind, started_at, finished_at FROM actions ORDER BY started_at, id
            """)
        return {
            "stato": "allineato" if aligned else ("da_riconciliare" if state else "registro_mancante"),
            "sospeso": not aligned or bool(state["paused"]),
            "pausa_manuale": bool(state and state["paused"]),
            "archivio": checkpoint,
            "registro": state["checkpoint"] if state else None,
            "tentativi": [dict(row) for row in attempts],
        }

    def action_status(self):
        if not self.ledger_path.is_file():
            return self._reconciliation_preview(has_ledger=False)
        with self._ledger(write=False):
            has_schema = self.db.execute(
                "SELECT 1 FROM ledger.sqlite_schema WHERE type = 'table' AND name = 'state'"
            ).fetchone()
            return self._reconciliation_preview(has_ledger=bool(has_schema))

    def reconcile_actions(self, reviewed):
        with self._ledger(create=True):
            if self._reconciliation_preview(has_ledger=True) != reviewed:
                raise ValueError("Il registro è cambiato. Controlla di nuovo gli invii prima di confermare.")
            if self._ledger_state() is None:
                self.db.execute("INSERT INTO ledger.state VALUES (1, ?, 0)", (uuid4().hex,))
            self.db.execute(f"""
                INSERT INTO ledger.attempts ({ACTION_COLUMNS})
                SELECT {ACTION_COLUMNS} FROM actions WHERE true ON CONFLICT(fingerprint) DO NOTHING
            """)
            self.db.execute("""
                UPDATE ledger.attempts AS a SET (status, finished_at) = (
                    SELECT status, finished_at FROM actions WHERE id = a.id
                ) WHERE a.finished_at IS NULL AND EXISTS (
                    SELECT 1 FROM actions WHERE id = a.id AND finished_at IS NOT NULL
                )
            """)
            self.db.execute(f"""
                INSERT INTO actions ({ACTION_COLUMNS})
                SELECT {ACTION_COLUMNS} FROM ledger.attempts
                WHERE finding_id IN (SELECT id FROM findings) ON CONFLICT(fingerprint) DO NOTHING
            """)
            self.db.execute("""
                UPDATE actions AS local SET (status, finished_at) = (
                    SELECT status, finished_at FROM ledger.attempts WHERE id = local.id
                ) WHERE EXISTS (SELECT 1 FROM ledger.attempts WHERE id = local.id)
            """)
            self._advance_checkpoint(self._checkpoint())

    def start_action(self, finding_id, route, *, form_address=None, form_page=None, preview=None,
                     reviewed_checkpoint=None, reviewed_finding=None):
        action_id = str(uuid4())
        if form_address is None:
            kind = "one_click"
            fingerprint = self._fingerprint(b"one-click", route.encode())
        else:
            kind = "web_form"
            logical_action = json.dumps([form_page, route, form_address.casefold()]).encode()
            fingerprint = self._fingerprint(b"web-form", logical_action)
        approval = self._seal(action_id, preview) if preview is not None else None
        with self._ledger():
            checkpoint = self._ready_checkpoint()
            duplicate = self.db.execute("""
                SELECT 1 FROM ledger.attempts WHERE fingerprint = ?
                UNION ALL SELECT 1 FROM actions WHERE fingerprint = ?
            """, (fingerprint, fingerprint)).fetchone()
            if duplicate:
                raise ValueError("Destinazione già usata o con esito incerto. Verifica la lista prima di agire.")
            if reviewed_checkpoint is not None and (
                    checkpoint != reviewed_checkpoint or self.get(finding_id) != reviewed_finding):
                raise ValueError("Il riscontro o il registro è cambiato. Genera una nuova anteprima.")
            values = (action_id, finding_id, fingerprint, "delivery_unknown", now(), None, kind, approval)
            self.db.execute(f"INSERT INTO actions ({ACTION_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", values)
            self.db.execute(f"INSERT INTO ledger.attempts ({ACTION_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)", values)
            self._advance_checkpoint(checkpoint)
        return action_id

    def finish_action(self, action_id, status):
        with self._ledger():
            state = self._ledger_state()
            if state is None:
                raise ValueError(RECONCILE_REQUIRED)
            finished = now()
            cursor = self.db.execute("UPDATE ledger.attempts SET status = ?, finished_at = ? WHERE id = ?",
                                     (status, finished, action_id))
            if cursor.rowcount != 1:
                raise ValueError(RECONCILE_REQUIRED)
            self.db.execute("UPDATE actions SET status = ?, finished_at = ? WHERE id = ?",
                            (status, finished, action_id))
            self._advance_checkpoint(state["checkpoint"])

    def actions(self, finding_id):
        return [dict(row) for row in self.db.execute(
            "SELECT id, kind, status, started_at, finished_at FROM actions WHERE finding_id = ? ORDER BY rowid",
            (finding_id,),
        )]
