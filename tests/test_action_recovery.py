import io
import json
import multiprocessing
import os
import sqlite3
import tempfile
import unittest
from contextlib import closing, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from obliryx.analysis import analyze_email
from obliryx.cli import execute_one_click, main, parser, run
from obliryx.store import Store, derive_key
from test_web_forms import EMAIL, FORM, PAGE
from test_workflow import MESSAGE


TEST_PHRASE = "synthetic archive fixture phrase"
SECOND_PHRASE = "another synthetic passphrase"
ROUTE = analyze_email(MESSAGE)["routes"][0]["value"]


def reserve_in_process(path, finding_id, gate, results):
    with closing(Store(path, TEST_PHRASE)) as store:
        gate.wait(timeout=15)
        try:
            store.start_action(finding_id, ROUTE)
        except ValueError as exc:
            results.put(str(exc))
        else:
            results.put("reserved")


def interrupt_in_process(path, finding_id, url, receipt):
    def submit(destination, _ip):
        if receipt is not None:
            receipt.write_text(destination, encoding="utf-8")
        os._exit(9)

    with (closing(Store(path, TEST_PHRASE)) as store, patch("obliryx.services.verify_message"),
          patch("obliryx.services.approve"), patch("builtins.input", return_value=EMAIL),
          patch("obliryx.services.resolve_destination", return_value="203.0.113.1"),
          patch("obliryx.services.submit", side_effect=submit)):
        execute_one_click(store, finding_id, store.get(finding_id), MESSAGE, url)


class ActionRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.db = self.folder / "vault.sqlite3"
        self.store = self.enterContext(closing(Store(self.db, TEST_PHRASE)))
        self.finding = analyze_email(MESSAGE)
        self.finding_id, _ = self.store.save(self.finding, b"synthetic-finding")
        self.parse = parser().parse_args

    def test_crash_before_and_after_post_preserves_unknown_and_blocks_retries(self):
        context = multiprocessing.get_context("spawn")
        receipt = self.folder / "received-post.txt"
        for boundary in ("before", "after"):
            with self.subTest(boundary=boundary):
                url = ROUTE + "&boundary=" + boundary
                worker = context.Process(target=interrupt_in_process, args=(
                    self.db, self.finding_id, url, receipt if boundary == "after" else None,
                ))
                worker.start()
                try:
                    worker.join(timeout=15)
                    self.assertEqual(worker.exitcode, 9)
                finally:
                    if worker.is_alive():
                        worker.terminate()
                        worker.join(timeout=5)
                    worker.close()
                with (patch("obliryx.services.verify_message"), patch("obliryx.services.approve"),
                      patch("builtins.input", return_value=EMAIL),
                      patch("obliryx.services.resolve_destination", return_value="203.0.113.1"),
                      patch("obliryx.services.submit") as send,
                      closing(Store(self.db, TEST_PHRASE)) as reopened):
                    self.assertEqual(reopened.actions(self.finding_id)[-1]["status"], "delivery_unknown")
                    with self.assertRaisesRegex(ValueError, "già usata"):
                        execute_one_click(reopened, self.finding_id, self.finding, MESSAGE, url)
                    send.assert_not_called()
                if boundary == "after":
                    self.assertEqual(receipt.read_text(encoding="utf-8"), url)
                else:
                    self.assertFalse(receipt.exists())
        self.assertEqual(len(self.store.action_status()["tentativi"]), 2)

    def test_two_processes_reserve_once(self):
        context = multiprocessing.get_context("spawn")
        gate = context.Barrier(2)
        results = context.Queue()
        workers = [context.Process(target=reserve_in_process, args=(self.db, self.finding_id, gate, results))
                   for _ in range(2)]
        for worker in workers:
            worker.start()
        try:
            replies = [results.get(timeout=20) for _ in workers]
            self.assertEqual(replies.count("reserved"), 1)
            self.assertTrue(any("già usata" in reply for reply in replies))
            self.assertEqual(len(self.store.actions(self.finding_id)), 1)
        finally:
            for worker in workers:
                worker.join(timeout=5)
                if worker.is_alive():
                    worker.terminate()
                    worker.join(timeout=5)
                worker.close()
            results.close()
            results.join_thread()

    def test_pause_from_cli_revokes_preview_even_if_resumed(self):
        with closing(Store(self.db, TEST_PHRASE)) as other, redirect_stdout(io.StringIO()):
            def change_pause(_preview, _prompt):
                run(other, self.parse(["action-pause"]))
                self.assertTrue(other.action_status()["sospeso"])
                other.set_actions_paused(False)

            with (patch("obliryx.services.verify_message"),
                  patch("obliryx.services.approve", side_effect=change_pause),
                  patch("builtins.input", return_value=EMAIL),
                  patch("obliryx.services.resolve_destination", return_value="203.0.113.1"),
                  patch("obliryx.services.submit") as send):
                with self.assertRaisesRegex(ValueError, "nuova anteprima"):
                    execute_one_click(self.store, self.finding_id, self.finding, MESSAGE, ROUTE)
                send.assert_not_called()
        self.assertEqual(self.store.actions(self.finding_id), [])

    def test_missing_ledger_requires_review_and_seeds_prior_deduplication(self):
        action_id = self.store.start_action(self.finding_id, ROUTE)
        pending_copy = self.folder / "while-post-pending.sqlite3"
        self.store.backup_to(pending_copy)
        self.store.finish_action(action_id, "accepted")
        with closing(Store(pending_copy, TEST_PHRASE)) as pending:
            self.assertEqual(pending.action_status()["stato"], "da_riconciliare")
            self.assertEqual(pending.action_status()["tentativi"][0]["status"], "accepted")
            with self.assertRaisesRegex(ValueError, "action-reconcile"):
                pending.start_action(self.finding_id, ROUTE + "&other=1")
        with closing(Store(self.db, TEST_PHRASE, ledger_dir=self.folder / "other-device")) as moved:
            self.assertEqual(moved.action_status()["stato"], "registro_mancante")
            with self.assertRaisesRegex(ValueError, "action-reconcile"):
                moved.start_action(self.finding_id, ROUTE + "&other=1")
            with patch("builtins.input", return_value="NO"), redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(ValueError, "annullata"):
                    run(moved, self.parse(["action-reconcile"]))
            self.assertEqual(moved.action_status()["stato"], "registro_mancante")
            with patch("builtins.input", return_value="CONFERMO"), redirect_stdout(io.StringIO()):
                run(moved, self.parse(["action-reconcile"]))
            self.assertEqual(moved.action_status()["stato"], "allineato")
            with self.assertRaisesRegex(ValueError, "già usata"):
                moved.start_action(self.finding_id, ROUTE)
            moved.start_action(self.finding_id, ROUTE + "&other=1")

    def test_form_changes_after_confirmation_require_a_new_preview(self):
        self.finding["routes"] = [{"kind": "web_manual", "value": PAGE}]
        self.store.update(self.finding_id, routes=self.finding["routes"])
        for old, new in ((b"/privacy/submit", b"/privacy/other"), (b"weekly", b"daily"),
                         (b"Disiscriviti", b"Unsubscribe")):
            with (self.subTest(new=new), patch("builtins.input", return_value="CONFERMO"),
                  patch("obliryx.cli.getpass.getpass", return_value=EMAIL),
                  patch("obliryx.services.resolve_destination", return_value="203.0.113.1"),
                  patch("obliryx.services.fetch_html", side_effect=[FORM.decode(), FORM.replace(old, new).decode()]),
                  patch("obliryx.services.post_form") as send, redirect_stdout(io.StringIO())):
                with self.assertRaisesRegex(ValueError, "procedura è cambiata"):
                    run(self.store, self.parse(["form-unsubscribe", self.finding_id, "1"]))
                send.assert_not_called()
        self.assertEqual(self.store.actions(self.finding_id), [])

    def test_cli_backup_export_restore_and_rotate(self):
        backup = self.folder / "copy.sqlite3"
        export = self.folder / "findings.json"
        recovery = self.folder / "recovered"
        recovery.mkdir()
        restored = recovery / "vault.sqlite3"
        self.store.update(self.finding_id, evidence="synthetic-private-note")
        guard = self.folder / "user-profile"

        def cli(db, command, *parameters, password=TEST_PHRASE, confirm="CONFERMO", new=()):
            output = io.StringIO()
            with (patch.dict(os.environ, {"LOCALAPPDATA": str(guard)}),
                  patch("sys.argv", ["obliryx", "--db", str(db), command, *map(str, parameters)]),
                  patch("sys.stdin.isatty", return_value=True),
                  patch("obliryx.cli.getpass.getpass", side_effect=(password, *new)),
                  patch("builtins.input", return_value=confirm),
                  redirect_stdout(output), redirect_stderr(output)):
                return main(), output.getvalue()

        def success(*args, **kwargs):
            status, output = cli(*args, **kwargs)
            self.assertEqual(status, 0, output)
            self.assertNotIn(TEST_PHRASE, output)
            self.assertNotIn(SECOND_PHRASE, output)

        self.assertEqual(cli(self.db, "backup", backup, confirm="NO")[0], 1)
        self.assertFalse(backup.exists())
        success(self.db, "backup", backup)
        original_backup = backup.read_bytes()
        self.assertNotIn(b"token=synthetic", original_backup)
        self.assertNotIn(b"synthetic-private-note", original_backup)
        self.assertEqual(cli(self.db, "backup", backup)[0], 1)
        success(self.db, "export", export)
        exported = export.read_text(encoding="utf-8")
        self.assertEqual(json.loads(exported)["riscontri"][0]["id"], self.finding_id)
        self.assertNotIn("synthetic-private-note", exported)
        self.assertNotIn("token=synthetic", exported)
        if os.name != "nt":
            self.assertEqual(export.stat().st_mode & 0o777, 0o600)
            self.assertEqual(backup.stat().st_mode & 0o777, 0o600)
        self.assertEqual(cli(backup, "restore", restored, password=SECOND_PHRASE)[0], 1)
        self.assertFalse(restored.exists())
        success(backup, "restore", restored)
        self.assertEqual(backup.read_bytes(), original_backup)
        success(self.db, "rotate-passphrase", new=(SECOND_PHRASE, SECOND_PHRASE))
        self.assertEqual(cli(self.db, "list")[0], 1)
        success(self.db, "list", password=SECOND_PHRASE)
        with (closing(Store(self.db, SECOND_PHRASE)) as rotated,
              closing(Store(restored, TEST_PHRASE, readonly=True)) as recovered):
            self.assertEqual(rotated.get(self.finding_id), recovered.get(self.finding_id))
            self.assertTrue(rotated.matches(self.finding_id, b"synthetic-finding"))
            self.assertEqual(rotated.ledger_path, self.store.ledger_path)

    def test_rotation_keeps_existing_action_fingerprints_for_legacy_archive(self):
        legacy = self.folder / "legacy.sqlite3"
        salt = os.urandom(16)
        self.store._set_key(derive_key(TEST_PHRASE, salt))
        verifier = self.store._seal("vault", {"version": 1})
        finding = self.store._seal(self.finding_id, self.finding)
        fingerprint = self.store._fingerprint(b"one-click", ROUTE.encode())
        with closing(sqlite3.connect(legacy)) as db, db:
            db.executescript("""
                CREATE TABLE vault (id INTEGER PRIMARY KEY, salt BLOB NOT NULL, verifier BLOB NOT NULL);
                CREATE TABLE findings (id TEXT PRIMARY KEY, fingerprint BLOB NOT NULL UNIQUE, payload BLOB NOT NULL);
                CREATE TABLE actions (id TEXT PRIMARY KEY, finding_id TEXT NOT NULL, fingerprint BLOB NOT NULL UNIQUE,
                    status TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT);
            """)
            db.execute("INSERT INTO vault VALUES (1, ?, ?)", (salt, verifier))
            db.execute("INSERT INTO findings VALUES (?, ?, ?)", (self.finding_id, b"legacy", finding))
            db.execute("INSERT INTO actions VALUES ('old', ?, ?, 'accepted', 'test', 'test')",
                       (self.finding_id, fingerprint))
        with closing(Store(legacy, TEST_PHRASE)) as store:
            self.assertEqual(store.get(self.finding_id), self.finding)
            store.reconcile_actions(store.action_status())
            store.rotate_password(SECOND_PHRASE)
        with closing(Store(legacy, SECOND_PHRASE)) as rotated:
            self.assertEqual(rotated.get(self.finding_id), self.finding)
            with self.assertRaisesRegex(ValueError, "già usata"):
                rotated.start_action(self.finding_id, ROUTE)
