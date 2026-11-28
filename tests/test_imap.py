import base64
import io
import json
import secrets
import socket
import socketserver
import tempfile
import threading
import unittest
from contextlib import closing, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import dkim
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from obliryx.analysis import MAX_MESSAGE_BYTES, analyze_email
from obliryx.cli import parser, run
from obliryx.imap_source import BoundedIMAP, fetch_message
from obliryx.store import Store
from test_web_forms import tls_contexts
from test_workflow import MESSAGE

HOST = "imap.example.invalid"
USER = "reader@example.invalid"


class ImapTests(unittest.TestCase):
    def test_fetch_rejects_truncation_and_wrong_uid(self):
        with patch("obliryx.imap_source.BoundedIMAP") as factory:
            client = factory.return_value
            client.uid.return_value = ("OK", [(b"1 (BODY[]<0> {4}", b"test"), b" UID 10 RFC822.SIZE 6)"])
            self.assertIsNone(fetch_message(client, 10))
            client.uid.return_value = ("OK", [(b"1 (BODY[]<0> {4}", b"test"), b" UID 11 RFC822.SIZE 4)"])
            self.assertIsNone(fetch_message(client, 10))

    def test_import_and_unsubscribe_via_read_only_imap_tls(self):
        signer = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        signing_key = signer.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.TraditionalOpenSSL,
                                          serialization.NoEncryption())
        dns_key = signer.public_key().public_bytes(serialization.Encoding.DER,
                                                  serialization.PublicFormat.SubjectPublicKeyInfo)
        signed = dkim.sign(MESSAGE, b"obliryx", b"example.invalid", signing_key,
                           include_headers=(b"from", b"to", b"list-unsubscribe", b"list-unsubscribe-post")) + MESSAGE
        command_log = []
        token_responses = []
        validity = 5

        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                self.wfile.write(b"* OK Synthetic IMAP ready\r\n")
                while line := self.rfile.readline():
                    tag, command, *args = line.rstrip().split(b" ")
                    command_log.append((command, b" ".join(args)))
                    if command == b"CAPABILITY":
                        self.wfile.write(b"* CAPABILITY IMAP4rev1 AUTH=XOAUTH2\r\n")
                    elif command == b"AUTHENTICATE":
                        self.wfile.write(b"+ \r\n")
                        token_responses.append(base64.b64decode(self.rfile.readline().strip()))
                    elif command == b"EXAMINE":
                        self.wfile.write(b"* 2 EXISTS\r\n")
                        self.wfile.write(f"* OK [UIDVALIDITY {validity}] IDs\r\n".encode())
                    elif command == b"FETCH":
                        self.wfile.write(f"* 1 FETCH (UID 10 RFC822.SIZE {len(signed)})\r\n".encode())
                        self.wfile.write(f"* 2 FETCH (UID 20 RFC822.SIZE {MAX_MESSAGE_BYTES + 1})\r\n".encode())
                    elif command == b"UID":
                        self.wfile.write(f"* 1 FETCH (BODY[]<0> {{{len(signed)}}}\r\n".encode())
                        self.wfile.write(signed)
                        self.wfile.write(f" UID 10 RFC822.SIZE {len(signed)})\r\n".encode())
                    elif command == b"LOGOUT":
                        self.wfile.write(b"* BYE Closed\r\n")
                    elif command != b"LOGIN":
                        self.wfile.write(tag + b" BAD Unexpected command\r\n")
                        continue
                    self.wfile.write(tag + b" OK Done\r\n")
                    if command == b"LOGOUT":
                        break

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            server_context, client_context = tls_contexts(folder, HOST)
            with socketserver.ThreadingTCPServer(("127.0.0.1", 0), Handler) as server:
                server.socket = server_context.wrap_socket(server.socket, server_side=True)
                thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
                thread.start()
                lookup = socket.getaddrinfo
                verify = dkim.DKIM.verify

                def connect(host, **kwargs):
                    return BoundedIMAP(host, server.server_address[1], ssl_context=client_context, timeout=kwargs["timeout"])

                def verify_locally(verifier, index):
                    return verify(verifier, index, dnsfunc=lambda *_args, **_kwargs: b"v=DKIM1; p=" + base64.b64encode(dns_key))

                def resolve(host, *args, **kwargs):
                    return lookup("127.0.0.1" if host == HOST else host, *args, **kwargs)

                credential = secrets.token_hex(20)
                try:
                    with (closing(Store(folder / "archive.sqlite3", secrets.token_hex(16))) as store,
                          patch("obliryx.imap_source.BoundedIMAP", side_effect=connect),
                          patch("socket.getaddrinfo", side_effect=resolve),
                          patch.object(dkim.DKIM, "verify", verify_locally),
                          patch("obliryx.services.resolve_destination", return_value="203.0.113.1"),
                          patch("obliryx.services.submit", return_value="accepted") as send):
                        finding_id, _ = store.save(analyze_email(signed), b"eml\x00" + signed)
                        store.update(finding_id, enrollment="non_riconosciuta")
                        cli = parser()
                        with (patch("builtins.input", return_value="CONFERMO"),
                              patch("obliryx.cli.getpass.getpass", side_effect=[USER, credential]),
                              redirect_stdout(io.StringIO()) as output):
                            self.assertEqual(run(store, cli.parse_args(["import-imap", HOST, "--limit", "2"])), 1)
                        report = output.getvalue()
                        _, start = json.JSONDecoder().raw_decode(report)
                        self.assertEqual(json.loads(report[start:]), {
                            "importati": 0, "duplicati": 1, "senza_indicatori": 0, "errori": 1,
                        })
                        finding = store.get(finding_id)
                        self.assertEqual(finding["enrollment"], "non_riconosciuta")
                        self.assertEqual(finding["imap_sources"], [{"host": HOST, "user": USER, "mailbox": "INBOX",
                                                                  "uid_validity": 5, "uid": 10}])
                        self.assertNotIn(credential, json.dumps(finding))
                        with (patch("builtins.input", return_value="CONFERMO"),
                              patch("obliryx.cli.getpass.getpass", side_effect=[USER, "Synthetic body", credential]),
                              redirect_stdout(io.StringIO())):
                            self.assertEqual(run(store, cli.parse_args([
                                "import-imap", HOST, "--limit", "2", "--match", "documento",
                            ])), 1)
                        self.assertEqual(store.get(finding_id)["mail_matches"], {"documento": ["corpo_testuale"]})
                        args = cli.parse_args(["unsubscribe-imap", finding_id, "--auth", "xoauth2"])
                        with (patch("builtins.input", side_effect=["CONFERMO", USER, "CONFERMO"]),
                              patch("obliryx.cli.getpass.getpass", return_value=credential), redirect_stdout(io.StringIO())):
                            self.assertEqual(run(store, args), 0)
                        send.assert_called_once()
                        self.assertEqual(token_responses, [f"user={USER}\x01auth=Bearer {credential}\x01\x01".encode()])
                        validity = 6
                        with (patch("builtins.input", return_value="CONFERMO"),
                              patch("obliryx.cli.getpass.getpass", return_value=credential), redirect_stdout(io.StringIO())):
                            with self.assertRaisesRegex(ValueError, "cartella IMAP è cambiata"):
                                run(store, args)
                        send.assert_called_once()
                finally:
                    server.shutdown()
                    thread.join(timeout=5)
        self.assertEqual({command for command, _ in command_log},
                         {b"CAPABILITY", b"LOGIN", b"AUTHENTICATE", b"EXAMINE", b"FETCH", b"UID", b"LOGOUT"})
        self.assertEqual([args for command, args in command_log if command == b"UID"],
                         [f"FETCH 10 (UID RFC822.SIZE BODY.PEEK[]<0.{MAX_MESSAGE_BYTES + 1}>)".encode()] * 3)
        self.assertNotIn(b"Synthetic body", b"\n".join(args for _, args in command_log))
