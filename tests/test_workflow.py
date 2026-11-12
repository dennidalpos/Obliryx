import base64
import io
import json
import secrets
import tempfile
import unittest
from contextlib import closing, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import dkim
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from obliryx.analysis import analyze_email, https_url, severity
from obliryx.cli import evidence_details, import_eml, parser, run, unsubscribe
from obliryx.mail_import import find_original, mbox_messages, scan_mail, watch_eml
from obliryx.one_click import submit, verify_message
from obliryx.store import Store

MESSAGE = (
    b"From: News <newsletter@example.invalid>\r\n"
    b"To: reader@example.invalid\r\n"
    b"Subject: Newsletter sintetica\r\n"
    b"List-Id: <news.example.invalid>\r\n"
    b"List-Unsubscribe: <https://mail.example.invalid/out?token=synthetic>\r\n"
    b"List-Unsubscribe-Post: List-Unsubscribe=One-Click\r\n"
    b"\r\nSynthetic body\r\n"
)
TEST_PHRASE = secrets.token_hex(16)
MBOX_SEPARATOR = b"From newsletter@example.invalid Thu Nov 12 14:00:00 2026\n"


class LocalWorkflow(unittest.TestCase):
    def test_controller_review_requires_public_match_and_preserves_declared_sender(self):
        with tempfile.TemporaryDirectory() as tmp:
            with closing(Store(Path(tmp) / "vault.sqlite3", TEST_PHRASE)) as store:
                finding_id, _ = store.save(analyze_email(MESSAGE), b"eml\x00" + MESSAGE)
                args = parser().parse_args(["identify", finding_id])
                inputs = ["Example News", "https://example.invalid/privacy", "Informativa della lista Example News"]
                with (patch("builtins.input", side_effect=[*inputs, "CONFERMO"]),
                      patch("obliryx.cli.inspect_page", return_value=(False, [])), redirect_stdout(io.StringIO())):
                    with self.assertRaisesRegex(ValueError, "denominazione non compare"):
                        run(store, args)
                self.assertNotIn("controller_reviews", store.get(finding_id))
                with (patch("builtins.input", side_effect=[*inputs, "CONFERMO", "CONFERMO"]),
                      patch("obliryx.cli.inspect_page", return_value=(True, [])) as inspect,
                      redirect_stdout(io.StringIO())):
                    run(store, args)
                    inspect.assert_called_once_with("https://example.invalid/privacy", "Example News")
                updated = store.get(finding_id)
                self.assertEqual(updated["sender"], "newsletter@example.invalid")
                [review] = updated["controller_reviews"]
                self.assertEqual(review["name"], "Example News")
                self.assertEqual(review["source_url"], "https://example.invalid/privacy")
                self.assertEqual(review["association"], "Informativa della lista Example News")
                self.assertEqual(updated["routes"], analyze_email(MESSAGE)["routes"])

    def test_discovered_route_keeps_purchase_high_until_confirmed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with closing(Store(Path(tmp) / "vault.sqlite3", TEST_PHRASE)) as store:
                finding = analyze_email(b"Subject: Newsletter\r\n\r\nSynthetic")
                finding["acquisition"] = "acquisto_documentato"
                finding_id, _ = store.save(finding, b"synthetic-actor")
                route = {"kind": "unsubscribe_candidate", "value": "https://example.invalid/leave",
                         "source_url": "https://example.invalid/"}
                cli = parser()
                with (patch("builtins.input", side_effect=["https://example.invalid/", "CONFERMO"]),
                      patch("obliryx.cli.discover_routes", return_value=[route]) as discover,
                      redirect_stdout(io.StringIO())):
                    run(store, cli.parse_args(["find-routes", finding_id]))
                    discover.assert_called_once_with("https://example.invalid/")
                self.assertEqual(store.add_routes(finding_id, [route]), 0)
                self.assertEqual(severity(store.get(finding_id))[0], "alta")
                with patch("builtins.input", return_value="CONFERMO"), redirect_stdout(io.StringIO()):
                    run(store, cli.parse_args(["confirm-route", finding_id, "1"]))
                confirmed = store.get(finding_id)
                self.assertEqual(severity(confirmed)[0], "media")
                self.assertEqual(confirmed["routes"][0]["kind"], "unsubscribe_candidate")
                self.assertEqual(confirmed["routes"][0]["source_url"], "https://example.invalid/")

    def test_mail_scan_enriches_existing_review_and_omits_matching_subject(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            eml = folder / "newsletter.eml"
            raw = MESSAGE.replace(b"Newsletter sintetica", b"Newsletter DOC-EXAMPLE-721")
            raw = raw.replace(b"Synthetic body", b"Documento: doc-example-721.")
            eml.write_bytes(raw)
            with closing(Store(folder / "vault.sqlite3", TEST_PHRASE)) as store:
                existing_id, _ = store.save(analyze_email(raw), b"eml\x00" + raw)
                store.update(existing_id, enrollment="non_riconosciuta", evidence="Nota precedente")
                with (patch("obliryx.cli.getpass.getpass", return_value="DOC-EXAMPLE-721"),
                      redirect_stdout(io.StringIO()) as output):
                    self.assertEqual(run(store, parser().parse_args(["scan-mail", str(eml), "documento"])), 0)
                self.assertEqual(json.loads(output.getvalue())["aggiornati"], 1)
                finding = store.get(existing_id)
                self.assertEqual(finding["mail_matches"], {"documento": ["corpo_testuale", "oggetto"]})
                self.assertEqual(finding["enrollment"], "non_riconosciuta")
                self.assertEqual(finding["evidence"], "Nota precedente")
                self.assertEqual(severity(finding)[0], "alta")
                self.assertNotIn("doc-example-721", json.dumps(finding).lower())
                self.assertEqual(scan_mail(store, eml, "documento", "DOC-EXAMPLE-721")["duplicati"], 1)

    def test_mail_scan_excludes_recipient_headers_and_hidden_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            html = (b"From: author@example.invalid\nTo: reader@example.invalid\nSubject: Ciao\n"
                    b"Content-Type: text/html\n\n<script>reader@example.invalid</script>"
                    b"<p>other+reader@example.invalid</p>")
            (folder / "no-match.eml").write_bytes(html)
            (folder / "match.eml").write_bytes(html + b"<p>Scrivi a READER@example.invalid.</p>")
            with closing(Store(folder / "vault.sqlite3", TEST_PHRASE)) as store:
                counts = scan_mail(store, folder, "email", "reader@example.invalid")
                self.assertEqual(counts, {"importati": 1, "aggiornati": 0, "duplicati": 0,
                                          "senza_corrispondenze": 1, "errori": 0})
                [(_, finding)] = list(store.all())
                self.assertEqual(finding["mail_matches"], {"email": ["corpo_html"]})
                self.assertEqual(finding["indicators"], [])
                with redirect_stdout(io.StringIO()) as output:
                    run(store, parser().parse_args(["campaigns"]))
                self.assertEqual(json.loads(output.getvalue()), [])

    def test_mbox_import_groups_campaign_and_preserves_existing_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            inbox = folder / "inbox.mbox"
            first = MESSAGE.replace(b"\r\n", b"\n")
            second = first.replace(b"token=synthetic", b"token=second")
            personal = b"From: friend@example.invalid\nSubject: Ciao\n\nMessaggio personale\n"
            raw_inbox = b"".join(MBOX_SEPARATOR + message + b"\n" for message in (first, second, personal))
            inbox.write_bytes(raw_inbox)
            with closing(Store(folder / "test.sqlite3", TEST_PHRASE)) as store:
                legacy_id, _ = store.save(analyze_email(MESSAGE), b"eml\x00" + MESSAGE)
                store.update(legacy_id, enrollment="non_riconosciuta")
                cli = parser()
                with redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(run(store, cli.parse_args(["import-mbox", str(inbox)])), 0)
                counts = json.loads(output.getvalue())
                self.assertEqual(counts, {"importati": 1, "duplicati": 1, "senza_indicatori": 1, "errori": 0})
                self.assertEqual(find_original(store, legacy_id, inbox), first)
                with redirect_stdout(io.StringIO()) as output:
                    self.assertEqual(run(store, cli.parse_args(["campaigns"])), 0)
                [campaign] = json.loads(output.getvalue())
                self.assertEqual(campaign["messaggi"], 2)
                self.assertEqual(campaign["non_riconosciute"], 1)
                self.assertEqual(campaign["gravita_massima"], "media")
            self.assertEqual(inbox.read_bytes(), raw_inbox)

    def test_mbox_skips_oversized_message_and_keeps_next_message(self):
        with tempfile.TemporaryDirectory() as tmp:
            inbox = Path(tmp) / "inbox.mbox"
            valid = b"Subject: Newsletter\n\n>From synthetic\n"
            long_line = b"X" * 180 + b"From not a separator mid-line\n"
            inbox.write_bytes(MBOX_SEPARATOR + long_line + b"\n" + MBOX_SEPARATOR + valid + b"\n")
            with patch("obliryx.mail_import.MAX_MESSAGE_BYTES", 80):
                self.assertEqual(list(mbox_messages(inbox)), [None, valid])

    def test_watcher_imports_only_after_a_new_file_is_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            file = folder / "newsletter.eml"
            ticks = iter(range(4))

            def advance(_seconds):
                tick = next(ticks, None)
                if tick == 0:
                    file.write_bytes(MESSAGE[:50])
                if tick == 1:
                    file.write_bytes(MESSAGE)
                if tick is None:
                    raise KeyboardInterrupt

            with (closing(Store(folder / "vault.sqlite3", TEST_PHRASE)) as store,
                  closing(watch_eml(store, folder, 1)) as watch,
                  patch("obliryx.mail_import.sleep", side_effect=advance)):
                self.assertEqual(next(watch), {"importati": 1, "duplicati": 0, "senza_indicatori": 0, "errori": 0})
                with self.assertRaises(KeyboardInterrupt):
                    next(watch)
                self.assertEqual(len(list(store.all())), 1)

    def test_import_encryption_review_and_deduplication(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            eml = folder / "newsletter.eml"
            eml.write_bytes(MESSAGE)
            db = folder / "test.sqlite3"
            with closing(Store(db, TEST_PHRASE)) as store, redirect_stdout(io.StringIO()):
                self.assertEqual(import_eml(store, folder), 0)
                self.assertEqual(import_eml(store, eml), 0)
                [(finding_id, finding)] = list(store.all())
                self.assertEqual(finding["enrollment"], "da_verificare")
                self.assertEqual(finding["routes"][0]["kind"], "one_click_candidate")
                store.update(finding_id, enrollment="non_riconosciuta")
                self.assertEqual(severity(store.get(finding_id))[0], "media")
            self.assertNotIn(b"token=synthetic", db.read_bytes())
            self.assertNotIn(b"newsletter@example.invalid", db.read_bytes())
            with self.assertRaisesRegex(ValueError, "Passphrase errata"):
                Store(db, "altra passphrase per prova")
            with closing(Store(db, TEST_PHRASE)) as store:
                self.assertEqual(store.get(finding_id)["enrollment"], "non_riconosciuta")

    def test_documented_purchase_without_unsubscribe_is_high(self):
        finding = analyze_email(b"Subject: Newsletter\r\n\r\nSynthetic")
        finding["acquisition"] = "acquisto_documentato"
        self.assertEqual(severity(finding)[0], "alta")
        finding["acquisition"] = "ignota"
        self.assertEqual(severity(finding)[0], "bassa")

    def test_page_evidence_does_not_count_as_purchase_evidence(self):
        previous = {"acquisition": "ignota", "evidence": "Corrispondenza testuale", "data_types": ["email"]}
        with (patch("builtins.input", side_effect=["", "s", "", ""]), redirect_stdout(io.StringIO()),
              self.assertRaisesRegex(ValueError, "riferimento alla prova")):
            evidence_details(previous)

    def test_untrusted_routes_and_ambiguous_one_click(self):
        self.assertIsNone(https_url("https://example.invalid@other.invalid/out"))
        self.assertIsNone(https_url("https://127.0.0.1/out"))
        self.assertIsNone(https_url("https://example.invalid:444/out"))
        ambiguous = MESSAGE.replace(b"token=synthetic>", b"token=synthetic>, <https://example.invalid/extra>")
        self.assertEqual({item["kind"] for item in analyze_email(ambiguous)["routes"]}, {"web_header"})

    def test_approved_attempt_survives_reopen_and_prevents_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            eml = folder / "message.eml"
            eml.write_bytes(MESSAGE)
            db = folder / "vault.sqlite3"
            finding = analyze_email(MESSAGE)
            with closing(Store(db, TEST_PHRASE)) as store:
                finding_id, _ = store.save(finding, b"eml\x00" + MESSAGE)
                with (patch("obliryx.cli.verify_message"), patch("obliryx.cli.approve"),
                      patch("builtins.input", return_value="reader@example.invalid"),
                      patch("obliryx.cli.resolve_destination", return_value="203.0.113.1"),
                      patch("obliryx.cli.submit", return_value="delivery_unknown") as send,
                      redirect_stdout(io.StringIO())):
                    self.assertEqual(unsubscribe(store, finding_id, finding, eml), 1)
                    send.assert_called_once()
                self.assertEqual(store.actions(finding_id)[0]["status"], "delivery_unknown")
            with closing(Store(db, TEST_PHRASE)) as store:
                with self.assertRaisesRegex(ValueError, "già usata"):
                    store.start_action(finding_id, finding["routes"][0]["value"])

    def test_submit_sends_only_rfc8058_body_and_never_follows_redirects(self):
        with patch("obliryx.network.DirectHTTPSConnection") as factory:
            connection = factory.return_value
            connection.getresponse.return_value.status = 302
            status = submit("https://mail.example.invalid/out?token=synthetic", "203.0.113.1")
            self.assertEqual(status, "redirect_unfollowed")
            factory.assert_called_once_with("mail.example.invalid", "203.0.113.1")
            connection.request.assert_called_once_with(
                "POST", "/out?token=synthetic", body=b"List-Unsubscribe=One-Click", headers={
                    "Content-Type": "application/x-www-form-urlencoded", "User-Agent": "Obliryx",
                },
            )


class SignedMessage(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        cls.private_key = key.private_bytes(serialization.Encoding.PEM,
                                           serialization.PrivateFormat.TraditionalOpenSSL,
                                           serialization.NoEncryption())
        public_key = key.public_key().public_bytes(serialization.Encoding.DER,
                                                   serialization.PublicFormat.SubjectPublicKeyInfo)
        cls.dns_record = b"v=DKIM1; k=rsa; p=" + base64.b64encode(public_key)

    def test_real_dkim_signature_and_signed_route(self):
        headers = (b"from", b"to", b"list-unsubscribe", b"list-unsubscribe-post")
        signed = dkim.sign(MESSAGE, b"obliryx", b"example.invalid", self.private_key,
                           include_headers=headers) + MESSAGE
        real_verify = dkim.DKIM.verify

        def verify_locally(verifier, index):
            return real_verify(verifier, index, dnsfunc=lambda *_args, **_kwargs: self.dns_record)

        with patch.object(dkim.DKIM, "verify", verify_locally):
            verify_message(signed, "newsletter@example.invalid", "reader@example.invalid")
            with self.assertRaisesRegex(ValueError, "Firma DKIM"):
                verify_message(signed.replace(b"token=synthetic", b"token=tampered"),
                               "newsletter@example.invalid", "reader@example.invalid")
            with self.assertRaisesRegex(ValueError, "destinatario"):
                verify_message(signed, "newsletter@example.invalid", "other@example.invalid")

    def test_signed_message_from_mbox_reaches_approved_one_click(self):
        signed = dkim.sign(MESSAGE, b"obliryx", b"example.invalid", self.private_key,
                           include_headers=(b"from", b"to", b"list-unsubscribe", b"list-unsubscribe-post")) + MESSAGE
        real_verify = dkim.DKIM.verify

        def verify_locally(verifier, index):
            return real_verify(verifier, index, dnsfunc=lambda *_args, **_kwargs: self.dns_record)

        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            inbox = folder / "inbox.mbox"
            inbox.write_bytes(MBOX_SEPARATOR + signed.replace(b"\r\n", b"\n") + b"\n")
            with (closing(Store(folder / "vault.sqlite3", TEST_PHRASE)) as store,
                  patch.object(dkim.DKIM, "verify", verify_locally),
                  patch("obliryx.cli.resolve_destination", return_value="203.0.113.1"),
                  patch("obliryx.cli.submit", return_value="accepted") as send,
                  patch("builtins.input", side_effect=["reader@example.invalid", "CONFERMO"]),
                  redirect_stdout(io.StringIO())):
                cli = parser()
                self.assertEqual(run(store, cli.parse_args(["import-mbox", str(inbox)])), 0)
                [(finding_id, _)] = list(store.all())
                self.assertEqual(run(store, cli.parse_args(["unsubscribe", finding_id, str(inbox)])), 0)
                send.assert_called_once_with("https://mail.example.invalid/out?token=synthetic", "203.0.113.1")
                self.assertEqual(store.actions(finding_id)[0]["status"], "accepted")


if __name__ == "__main__":
    unittest.main()
