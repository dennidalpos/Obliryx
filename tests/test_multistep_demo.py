import io
import tempfile
import threading
import unittest
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.util import find_spec
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qsl

from obliryx.cli import main
from test_web_forms import tls_contexts


COOKIE = "obliryx_demo=fixture_session_01"
PREPARE_TOKEN = "fixture_prepare_01"
CONFIRM_TOKEN = "fixture_confirm_01"
REQUEST_ID = "fixture_request_01"
EMAIL = "reader@example.invalid"
PREPARE = f"""
<img src="/demo/unapproved-resource"><iframe src="/demo/unapproved-frame"></iframe>
<script>fetch('/demo/unapproved-script')</script>
<form id="newsletter" method="post" action="/demo/signup">
  <input name="email" type="email"><button>Iscriviti</button>
</form>
<form id="demo-prepare" method="post" action="/demo/prepare" data-procedure="obliryx-demo-v1" data-effect="prepare">
  <input name="email" type="email"><input name="csrf" type="hidden" value="{PREPARE_TOKEN}">
  <button>Prepara</button>
</form>
"""
CONFIRM = f"""
<form id="demo-confirm" method="post" action="/demo/confirm" data-procedure="obliryx-demo-v1" data-effect="confirm">
  <input name="request_id" type="hidden" value="{REQUEST_ID}">
  <input name="csrf" type="hidden" value="{CONFIRM_TOKEN}">
  <button>Conferma</button>
</form>
"""


@contextmanager
def controlled_site(folder, *, prepare=PREPARE, confirm=CONFIRM, redirect=False):
    requests = []
    ca = folder / "ca.pem"
    tls, _ = tls_contexts(folder, "localhost", ca_file=ca)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def reply(self, status, *, html="", headers=()):
            content = html.encode()
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            for name, value in headers:
                self.send_header(name, value)
            self.end_headers()
            self.wfile.write(content)

        def do_GET(self):
            requests.append(("GET", self.path, self.headers.get("Cookie"), []))
            if self.path == "/demo/start":
                markup = prepare.replace("/demo/unapproved-", f"https://localhost:{self.server.server_port}/demo/unapproved-")
                self.reply(200, html=markup, headers=(
                    ("Set-Cookie", f"{COOKIE}; Secure; HttpOnly; SameSite=Strict; Path=/demo/"),
                ))
            else:
                self.reply(404)

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            fields = parse_qsl(body.decode(), strict_parsing=True)
            cookie = self.headers.get("Cookie")
            requests.append(("POST", self.path, cookie, fields))
            if cookie != COOKIE:
                self.reply(403)
            elif self.path == "/demo/prepare" and fields == [("email", EMAIL), ("csrf", PREPARE_TOKEN)]:
                if redirect:
                    self.reply(307, headers=(("Location", "/demo/unapproved-redirect"),))
                else:
                    self.reply(200, html=confirm)
            elif self.path == "/demo/confirm" and fields == [("request_id", REQUEST_ID), ("csrf", CONFIRM_TOKEN)]:
                self.reply(204)
            else:
                self.reply(400)

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as server:
        server.socket = tls.wrap_socket(server.socket, server_side=True)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
        thread.start()
        try:
            yield server.server_port, ca, requests
        finally:
            server.shutdown()
            thread.join(timeout=5)


@unittest.skipUnless(find_spec("playwright"), "requires the demo extra and Chromium")
class MultistepDemoTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(self.enterContext(tempfile.TemporaryDirectory()))

    def invoke(self, port, ca, *choices):
        output = io.StringIO()
        with (patch("sys.argv", ["obliryx", "multistep-demo", "--port", str(port), "--ca", str(ca)]),
              patch("sys.stdin.isatty", return_value=True),
              patch("builtins.input", side_effect=choices) as confirm,
              patch("obliryx.cli.Store", side_effect=AssertionError("archive opened")),
              redirect_stdout(output), redirect_stderr(output)):
            status = main()
        return status, output.getvalue(), confirm.call_count

    def test_tls_session_and_two_explicit_posts(self):
        with controlled_site(self.folder) as (port, ca, requests):
            status, output, approvals = self.invoke(port, ca, "CONFERMO", "CONFERMO", "CONFERMO")
        self.assertEqual(status, 0, output)
        self.assertEqual(approvals, 3)
        self.assertEqual(requests, [
            ("GET", "/demo/start", None, []),
            ("POST", "/demo/prepare", COOKIE, [("email", EMAIL), ("csrf", PREPARE_TOKEN)]),
            ("POST", "/demo/confirm", COOKIE, [("request_id", REQUEST_ID), ("csrf", CONFIRM_TOKEN)]),
        ])
        for value in (COOKIE, PREPARE_TOKEN, CONFIRM_TOKEN, REQUEST_ID):
            self.assertNotIn(value, output)
        self.assertIn('"stato": "confermata"', output)

    def test_declined_confirmation_stops_before_second_post(self):
        with controlled_site(self.folder) as (port, ca, requests):
            status, output, approvals = self.invoke(port, ca, "CONFERMO", "CONFERMO", "NO")
        self.assertEqual((status, approvals), (1, 3))
        self.assertIn("annullata", output)
        self.assertEqual([item[1] for item in requests], ["/demo/start", "/demo/prepare"])

        changed = CONFIRM.replace('name="request_id"', 'name="unexpected"')
        with controlled_site(self.folder, confirm=changed) as (port, ca, requests):
            status, output, approvals = self.invoke(port, ca, "CONFERMO", "CONFERMO")
        self.assertEqual((status, approvals), (1, 2))
        self.assertIn("revisionata", output)
        self.assertEqual([item[1] for item in requests], ["/demo/start", "/demo/prepare"])

    def test_changed_form_or_assisted_step_stops_before_any_post(self):
        cases = (
            (PREPARE.replace('action="/demo/prepare"', 'action="https://outside.invalid/"'), "revisionata"),
            (PREPARE.replace('data-effect="prepare"', 'data-effect="signup"'), "revisionata"),
            (PREPARE.replace('<button>Prepara</button>', '<input name="extra"><button>Prepara</button>'), "revisionata"),
            ('<p data-assistance="captcha">Verifica assistita</p>', "assistito"),
            (PREPARE.replace('id="demo-prepare"', 'id="signup"'), "revisionata"),
        )
        for markup, error in cases:
            with self.subTest(error=error, markup=markup):
                with controlled_site(self.folder, prepare=markup) as (port, ca, requests):
                    status, output, approvals = self.invoke(port, ca, "CONFERMO")
                self.assertEqual((status, approvals), (1, 1))
                self.assertIn(error, output)
                self.assertEqual(requests, [("GET", "/demo/start", None, [])])

    def test_post_redirect_is_not_followed(self):
        with controlled_site(self.folder, redirect=True) as (port, ca, requests):
            status, output, approvals = self.invoke(port, ca, "CONFERMO", "CONFERMO")
        self.assertEqual((status, approvals), (1, 2))
        self.assertIn("HTTP 307", output)
        self.assertEqual([item[1] for item in requests], ["/demo/start", "/demo/prepare"])

    def test_wrong_ca_fails_before_any_http_request(self):
        other = self.folder / "other"
        other.mkdir()
        wrong_ca = other / "ca.pem"
        tls_contexts(other, "localhost", ca_file=wrong_ca)
        with controlled_site(self.folder) as (port, _ca, requests):
            status, output, approvals = self.invoke(port, wrong_ca, "CONFERMO")
        self.assertEqual((status, approvals), (1, 1))
        self.assertIn("HTTPS demo interrotto", output)
        self.assertEqual(requests, [])
