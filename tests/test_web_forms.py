import io
import secrets
import sqlite3
import ssl
import tempfile
import threading
import unittest
from contextlib import closing, redirect_stdout
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qsl

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from obliryx.analysis import analyze_email
from obliryx.cli import parser, run
from obliryx.network import DirectHTTPSConnection
from obliryx.store import Store
from obliryx.web_forms import discover_unsubscribe_form

HOST = "form.example.invalid"
PAGE = f"https://{HOST}/privacy/leave"
EMAIL = "reader+demo@example.invalid"
FORM = (b'<form method="post" action="/privacy/submit">'
        b'<input type="email" name="address" required>'
        b'<input type="hidden" name="list" value="weekly">'
        b'<button name="action" value="remove">Disiscriviti</button></form>')


def tls_contexts(folder, host=HOST, *, ca_file=None):
    current = datetime.now(UTC)
    issuer = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Obliryx Test CA")])
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, host)])
    ca_key = ec.generate_private_key(ec.SECP256R1())
    leaf_key = ec.generate_private_key(ec.SECP256R1())

    def certificate(name, key):
        return (x509.CertificateBuilder().subject_name(name).issuer_name(issuer).public_key(key.public_key())
                .serial_number(x509.random_serial_number()).not_valid_before(current - timedelta(minutes=5))
                .not_valid_after(current + timedelta(hours=1)))

    ca = (certificate(issuer, ca_key).add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .add_extension(x509.KeyUsage(False, False, False, False, False, True, True, None, None), critical=True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
          .sign(ca_key, hashes.SHA256()))
    leaf = (certificate(subject, leaf_key).add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.SubjectAlternativeName([x509.DNSName(host)]), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256()))
    cert_file = folder / "test-server.pem"
    key_file = folder / "test-server-key.pem"
    cert_file.write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
    ca_pem = ca.public_bytes(serialization.Encoding.PEM)
    if ca_file is not None:
        ca_file.write_bytes(ca_pem)
    key_file.write_bytes(leaf_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                               serialization.NoEncryption()))
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(cert_file, key_file)
    return server_context, ssl.create_default_context(cadata=ca_pem.decode())


class UnsubscribeFormTests(unittest.TestCase):
    def test_rejects_wrong_destination_and_unsupported_forms(self):
        replacements = (
            (b'/privacy/submit', b'https://other.example.invalid/submit'),
            (b'Disiscriviti', b'Iscriviti'),
            (b'method="post"', b'method="get"'),
            (b'<button name=', b'<button formaction="/subscribe" name='),
            (b'</button>', b'</button><input name="extra" type="checkbox">'),
            (b'</button>', b'</button><input name="second" type="email">'),
        )
        for old, new in replacements:
            with self.subTest(old=old, new=new), self.assertRaisesRegex(ValueError, "non individuato"):
                discover_unsubscribe_form(PAGE, FORM.replace(old, new).decode())
        with self.assertRaisesRegex(ValueError, "non individuato"):
            discover_unsubscribe_form(PAGE, (FORM + FORM).decode())

    def test_existing_action_schema_is_migrated(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "old.sqlite3"
            with closing(sqlite3.connect(path)) as db, db:
                db.execute("CREATE TABLE actions (id TEXT PRIMARY KEY, finding_id TEXT NOT NULL, "
                           "fingerprint BLOB NOT NULL UNIQUE, status TEXT NOT NULL, "
                           "started_at TEXT NOT NULL, finished_at TEXT)")
                db.execute("INSERT INTO actions VALUES ('old', 'finding', X'01', 'accepted', 'synthetic', NULL)")
            with closing(Store(path, secrets.token_hex(16))) as store:
                [action] = store.actions("finding")
                self.assertEqual((action["id"], action["kind"], action["status"]), ("old", "one_click", "accepted"))

    def test_preview_and_submit_over_controlled_tls(self):
        requests = []

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_GET(self):
                requests.append(("GET", self.path))
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(FORM)))
                self.end_headers()
                self.wfile.write(FORM)

            def do_POST(self):
                payload = self.rfile.read(int(self.headers["Content-Length"]))
                requests.append(("POST", self.path, parse_qsl(payload.decode()), self.headers.get("Cookie")))
                self.send_response(303)
                self.send_header("Location", "/unexpected")
                self.end_headers()

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
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
                    with (closing(Store(folder / "vault.sqlite3", secrets.token_hex(16))) as store,
                          patch("obliryx.services.resolve_destination", return_value="127.0.0.1"),
                          patch("obliryx.site.DirectHTTPSConnection", side_effect=connect),
                          patch("obliryx.network.DirectHTTPSConnection", side_effect=connect),
                          patch("obliryx.cli.getpass.getpass", return_value=EMAIL),
                          redirect_stdout(io.StringIO()) as output):
                        finding = analyze_email(b"Subject: Newsletter\n\nSynthetic")
                        finding["routes"] = [{"kind": "web_header", "value": PAGE}]
                        finding_id, _ = store.save(finding, b"synthetic-form-finding")
                        args = parser().parse_args(["form-unsubscribe", finding_id, "1"])
                        with self.assertRaisesRegex(ValueError, "confirm-route"):
                            run(store, args)
                        self.assertEqual(requests, [])
                        with patch("builtins.input", return_value="CONFERMO"):
                            run(store, parser().parse_args(["confirm-route", finding_id, "1"]))
                        with patch("builtins.input", side_effect=["CONFERMO", "NO"]):
                            with self.assertRaisesRegex(ValueError, "annullata"):
                                run(store, args)
                        self.assertEqual(requests, [("GET", "/privacy/leave")])
                        with patch("builtins.input", return_value="CONFERMO"):
                            self.assertEqual(run(store, args), 1)
                            with self.assertRaisesRegex(ValueError, "già usata"):
                                run(store, args)
                        [post] = [request for request in requests if request[0] == "POST"]
                        self.assertEqual(post, ("POST", "/privacy/submit", [
                            ("address", EMAIL), ("list", "weekly"), ("action", "remove"),
                        ], None))
                        self.assertNotIn(("GET", "/unexpected"), requests)
                        self.assertIn(EMAIL, output.getvalue())
                        [action] = store.actions(finding_id)
                        self.assertEqual((action["kind"], action["status"]), ("web_form", "redirect_unfollowed"))
                finally:
                    server.shutdown()
                    thread.join(timeout=5)
