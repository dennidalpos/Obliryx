import io
import secrets
import tempfile
import threading
import unittest
from contextlib import closing, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs

from obliryx.cli import page_identity, parser, run
from obliryx.network import DirectHTTPSConnection
from obliryx.store import Store
from test_web_forms import EMAIL, FORM, HOST, tls_contexts

PUBLIC_PAGE = f"https://{HOST}/public"


class RecheckTests(unittest.TestCase):
    def test_real_https_removal_and_recurrence(self):
        requests = []
        phase = "published"

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                requests.append(("GET", self.path))
                if self.path == "/privacy/leave":
                    content = FORM
                elif phase == "login":
                    content = b'<p>Accedi per visualizzare il profilo</p><input type="password">'
                elif phase == "published":
                    content = f'<p>Email: {EMAIL}</p><a href="/privacy/leave">Disiscrizione</a>'.encode()
                else:
                    content = b"<p>Elenco pubblico aggiornato.</p>"
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)

            def do_POST(self):
                nonlocal phase
                requests.append(("POST", self.path))
                payload = parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
                if self.path == "/privacy/submit" and payload.get("address") == [EMAIL]:
                    phase = "removed"
                    self.send_response(204)
                else:
                    self.send_response(400)
                self.end_headers()

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            password = secrets.token_hex(16)
            backup = folder / "before-post.sqlite3"
            restored = folder / "restored.sqlite3"
            server_context, client_context = tls_contexts(folder)
            with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
                server.socket = server_context.wrap_socket(server.socket, server_side=True)
                thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
                thread.start()

                def connect(host, ip):
                    connection = DirectHTTPSConnection(host, ip)
                    connection.port = server.server_port
                    connection._context = client_context
                    return connection

                try:
                    with (closing(Store(folder / "vault.sqlite3", password)) as store,
                          patch("obliryx.site.resolve_destination", return_value="127.0.0.1"),
                          patch("obliryx.cli.resolve_destination", return_value="127.0.0.1"),
                          patch("obliryx.site.DirectHTTPSConnection", side_effect=connect),
                          patch("obliryx.network.DirectHTTPSConnection", side_effect=connect),
                          patch("builtins.input", return_value="CONFERMO"), redirect_stdout(io.StringIO())):
                        cli = parser()
                        with patch("obliryx.cli.getpass.getpass", side_effect=[PUBLIC_PAGE, EMAIL]):
                            self.assertEqual(run(store, cli.parse_args(["check-page", "email"])), 0)
                        [(finding_id, _)] = list(store.all())
                        run(store, cli.parse_args(["confirm-route", finding_id, "1"]))
                        run(store, cli.parse_args(["backup", str(backup)]))
                        args = cli.parse_args(["recheck-page", finding_id])
                        with patch("obliryx.cli.getpass.getpass", return_value="different@example.invalid"):
                            with self.assertRaisesRegex(ValueError, "non coincide"):
                                run(store, args)
                        self.assertEqual(requests, [("GET", "/public")])
                        with patch("obliryx.cli.getpass.getpass", return_value=EMAIL):
                            send = cli.parse_args(["form-unsubscribe", finding_id, "1"])
                            self.assertEqual(run(store, send), 0)
                            [action] = store.actions(finding_id)
                            self.assertEqual(action["status"], "accepted")
                            self.assertNotIn(EMAIL.encode(), store.ledger_path.read_bytes())
                            approval = store.db.execute("SELECT approval FROM actions WHERE id = ?",
                                                        (action["id"],)).fetchone()[0]
                            self.assertIn(["address", EMAIL], store._open(action["id"], approval)["campi"])
                            with closing(Store(backup, password, readonly=True)) as source:
                                run(source, cli.parse_args(["restore", str(restored)]))
                            with closing(Store(restored, password)) as recovered:
                                self.assertEqual(recovered.action_status()["stato"], "da_riconciliare")
                                with self.assertRaisesRegex(ValueError, "action-reconcile"):
                                    run(recovered, send)
                                run(recovered, cli.parse_args(["action-reconcile"]))
                                self.assertEqual(recovered.actions(finding_id)[0]["status"], "accepted")
                                with self.assertRaisesRegex(ValueError, "già usata"):
                                    run(recovered, send)
                            self.assertEqual(run(store, args), 0)
                            phase = "login"
                            self.assertEqual(run(store, args), 1)
                            phase = "published"
                        with patch("obliryx.cli.getpass.getpass", return_value=EMAIL.upper()):
                            self.assertEqual(run(store, args), 0)
                        checks = store.get(finding_id)["web_checks"]
                        self.assertEqual([item["status"] for item in checks], [
                            "dato_osservato", "dato_non_osservato", "non_verificabile", "ricomparsa",
                        ])
                finally:
                    server.shutdown()
                    thread.join(timeout=5)
        self.assertEqual(requests, [("GET", "/public"), ("GET", "/privacy/leave"), ("GET", "/privacy/leave"),
                                   ("POST", "/privacy/submit"), ("GET", "/privacy/leave"),
                                   ("GET", "/privacy/leave"), ("GET", "/public"),
                                   ("GET", "/public"), ("GET", "/public")])

    def test_legacy_finding_without_page_category_can_be_rechecked(self):
        with tempfile.TemporaryDirectory() as tmp:
            with closing(Store(Path(tmp) / "vault.sqlite3", secrets.token_hex(16))) as store:
                finding_id, _ = store.save({"source": "pagina_verificata", "source_url": PUBLIC_PAGE,
                                             "data_types": ["telefono"]}, page_identity(PUBLIC_PAGE, "email", EMAIL.upper()))
                with (patch("obliryx.cli.getpass.getpass", return_value=EMAIL.upper()),
                      patch("builtins.input", return_value="CONFERMO"),
                      patch("obliryx.cli.inspect_page", return_value=(False, [])), redirect_stdout(io.StringIO())):
                    self.assertEqual(run(store, parser().parse_args(["recheck-page", finding_id])), 0)
                self.assertEqual(store.get(finding_id)["web_checks"][0]["status"], "dato_non_osservato")
