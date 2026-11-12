import hashlib
import hmac
import json
import os
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def now():
    return datetime.now(UTC).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path, password: str):
        if len(password) < 12:
            raise ValueError("Usa una passphrase di almeno 12 caratteri.")
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        try:
            with self.db:
                self.db.execute("PRAGMA foreign_keys = ON")
                self.db.executescript("""
                    CREATE TABLE IF NOT EXISTS vault (
                        id INTEGER PRIMARY KEY CHECK (id = 1), salt BLOB NOT NULL,
                        verifier BLOB NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS findings (
                        id TEXT PRIMARY KEY, fingerprint BLOB NOT NULL UNIQUE,
                        payload BLOB NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS actions (
                        id TEXT PRIMARY KEY, finding_id TEXT NOT NULL REFERENCES findings(id),
                        fingerprint BLOB NOT NULL UNIQUE, status TEXT NOT NULL,
                        started_at TEXT NOT NULL, finished_at TEXT,
                        kind TEXT NOT NULL DEFAULT 'one_click'
                    );
                """)
                self.db.execute("BEGIN IMMEDIATE")
                if "kind" not in {column["name"] for column in self.db.execute("PRAGMA table_info(actions)")}:
                    self.db.execute("ALTER TABLE actions ADD COLUMN kind TEXT NOT NULL DEFAULT 'one_click'")
                row = self.db.execute("SELECT salt, verifier FROM vault WHERE id = 1").fetchone()
                salt = row["salt"] if row else os.urandom(16)
                key = hashlib.scrypt(password.encode(), salt=salt, n=2**16, r=8, p=1,
                                     dklen=64, maxmem=128 * 1024 * 1024)
                self.cipher = AESGCM(key[:32])
                self.mac_key = key[32:]
                if row:
                    self._open("vault", row["verifier"])
                else:
                    self.db.execute("INSERT INTO vault VALUES (1, ?, ?)",
                                    (salt, self._seal("vault", {"version": 1})))
        except BaseException:
            self.close()
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

    def start_action(self, finding_id, route, *, form_address=None, form_page=None):
        action_id = str(uuid4())
        if form_address is None:
            kind = "one_click"
            fingerprint = self._fingerprint(b"one-click", route.encode())
        else:
            kind = "web_form"
            logical_action = json.dumps([form_page, route, form_address.casefold()]).encode()
            fingerprint = self._fingerprint(b"web-form", logical_action)
        with self.db:
            cursor = self.db.execute(
                "INSERT INTO actions (id, finding_id, fingerprint, status, started_at, kind) "
                "VALUES (?, ?, ?, 'delivery_unknown', ?, ?) ON CONFLICT(fingerprint) DO NOTHING",
                (action_id, finding_id, fingerprint, now(), kind),
            )
            if cursor.rowcount != 1:
                raise ValueError("Destinazione già usata o con esito incerto. Verifica la lista prima di agire.")
        return action_id

    def finish_action(self, action_id, status):
        with self.db:
            self.db.execute("UPDATE actions SET status = ?, finished_at = ? WHERE id = ?",
                            (status, now(), action_id))

    def actions(self, finding_id):
        return [dict(row) for row in self.db.execute(
            "SELECT id, kind, status, started_at, finished_at FROM actions WHERE finding_id = ? ORDER BY rowid",
            (finding_id,),
        )]
