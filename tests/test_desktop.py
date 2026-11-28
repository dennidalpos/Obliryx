import json
import secrets
import tempfile
import time
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import urlopen

from obliryx.analysis import analyze_email
from obliryx.desktop import DesktopAPI
from obliryx.desktop_host import asset_server
from obliryx.store import Store

PHRASE = secrets.token_hex(16)
EMAIL = 'reader@example.invalid'
MESSAGE = (b'From: News <news@example.invalid>\r\nTo: reader@example.invalid\r\n'
           b'Subject: Newsletter sintetica\r\nList-Id: <news.example.invalid>\r\n'
           b'List-Unsubscribe: <https://example.invalid/leave?token=synthetic>\r\n'
           b'List-Unsubscribe-Post: List-Unsubscribe=One-Click\r\n\r\nSynthetic body')


class DesktopTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name)
        self.api = DesktopAPI(self.folder)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(self.api._close)
        self.path = self.folder / 'archivio sintetico.sqlite3'
        self.assertTrue(self.api.unlock(str(self.path), PHRASE, True, PHRASE)['ok'])

    def wait(self, predicate, timeout=5):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            state = self.api.status()['value']['job']
            if predicate(state):
                return state
            time.sleep(.01)
        self.fail('Desktop activity did not reach expected state')

    def answer(self, job, value):
        state = self.wait(lambda s: s['request'] is not None)
        self.assertTrue(self.api.respond(job, state['request']['id'], value)['ok'])
        return state['request']['id']

    def seed(self):
        with closing(Store(self.path, PHRASE, ledger_dir=self.folder / 'action-state')) as store:
            return store.save(analyze_email(MESSAGE), b'eml\x00' + MESSAGE)[0]

    def test_named_operations_reject_unknown_and_unexpected_inputs(self):
        self.assertFalse(self.api.start('multistep-demo', {})['ok'])
        self.assertFalse(self.api.start('import-eml', {'path':'x', 'command':'export'})['ok'])
        self.assertFalse(self.api.start('check-breach', {'method':'other'})['ok'])
        self.assertFalse(self.api.findings(-1, 10)['ok'])

    def test_create_never_overwrites_and_wrong_password_does_not_unlock(self):
        self.api.lock()
        self.assertFalse(self.api.unlock(str(self.path), PHRASE, True, PHRASE)['ok'])
        self.assertFalse(self.api.unlock(str(self.path), secrets.token_hex(16))['ok'])
        self.assertFalse(self.api.status()['value']['unlocked'])
        self.assertTrue(self.api.unlock(str(self.path), PHRASE)['ok'])

    def test_import_counts_and_single_worker_access(self):
        source = self.folder / 'newsletter.eml'
        source.write_bytes(MESSAGE)
        self.api.start('import-eml', {'path':str(source)})
        state = self.wait(lambda s:s['status'] != 'running')
        self.assertEqual(state['result']['importati'], 1)
        findings = self.api.findings()['value']
        self.assertEqual(findings['total'], 1)
        self.assertEqual(findings['items'][0]['enrollment'], 'da_verificare')

    def test_confirmation_is_single_use_and_cancellation_never_posts(self):
        finding = self.seed()
        source = self.folder / 'original.eml'
        source.write_bytes(MESSAGE)
        with (patch('obliryx.services.verify_message'), patch('obliryx.services.submit') as send):
            job = self.api.start('unsubscribe', {'id':finding, 'source':str(source)})['value']['id']
            self.answer(job, EMAIL)
            state = self.wait(lambda s:s['request'] and s['request']['kind']=='approval')
            request = state['request']['id']
            self.api.cancel(job)
            self.assertFalse(self.api.respond(job, request, 'CONFERMO')['ok'])
            self.wait(lambda s:s['status'] != 'running')
            send.assert_not_called()

    def test_two_responses_and_concurrent_jobs_cannot_duplicate_post(self):
        finding = self.seed()
        source = self.folder / 'original.eml'
        source.write_bytes(MESSAGE)
        with (patch('obliryx.services.verify_message'), patch('obliryx.services.resolve_destination', return_value='203.0.113.1'),
              patch('obliryx.services.submit', return_value='accepted') as send):
            job = self.api.start('unsubscribe', {'id':finding, 'source':str(source)})['value']['id']
            self.assertFalse(self.api.start('action-pause')['ok'])
            self.answer(job, EMAIL)
            request = self.answer(job, 'CONFERMO')
            self.assertFalse(self.api.respond(job, request, 'CONFERMO')['ok'])
            state = self.wait(lambda s:s['status'] != 'running')
            self.assertEqual(state['status'], 'completed', state)
            self.assertEqual(state['result']['stato'], 'accepted')
            self.assertFalse(state['result']['rimozione_verificata'])
            send.assert_called_once()
            # Repeating the operation still passes through durable deduplication.
            job = self.api.start('unsubscribe', {'id':finding, 'source':str(source)})['value']['id']
            self.answer(job, EMAIL)
            self.answer(job, 'CONFERMO')
            self.assertEqual(self.wait(lambda s:s['status'] != 'running')['status'], 'failed')
            send.assert_called_once()

    def test_lock_discards_preview_and_pending_secret_and_keeps_archive(self):
        self.seed()
        job = self.api.start('check-page', {'category':'email'})['value']['id']
        self.wait(lambda s:s['request'] is not None)
        self.api.lock()
        self.assertFalse(self.api.respond(job, 'stale', EMAIL)['ok'])
        state = self.api.status()['value']
        self.assertFalse(state['unlocked'])
        self.assertIsNone(state['job']['result'])
        self.assertTrue(self.path.exists())

    def test_polling_does_not_extend_idle_session(self):
        self.api._clock = lambda: 1000
        self.api._last_activity = 100
        self.api.status()
        self.api.bootstrap()
        self.api._expire_idle()
        self.assertFalse(self.api.status()['value']['unlocked'])

    def test_cancel_monitor_and_import_error_recovery(self):
        job = self.api.start('watch-eml', {'path':str(self.folder), 'interval':'1'})['value']['id']
        self.api.cancel(job)
        self.assertEqual(self.wait(lambda s:s['status'] != 'running')['status'], 'cancelled')
        self.api.start('import-eml', {'path':str(self.folder / 'missing.eml')})
        self.assertEqual(self.wait(lambda s:s['status'] != 'running')['status'], 'failed')
        self.assertEqual(self.api.findings()['value']['total'], 0)

    def test_expiry_and_external_pause_revoke_preview(self):
        finding = self.seed()
        source = self.folder / 'original.eml'
        source.write_bytes(MESSAGE)
        with (patch('obliryx.services.verify_message'), patch('obliryx.services.resolve_destination', return_value='203.0.113.1'),
              patch('obliryx.services.submit') as send):
            job = self.api.start('unsubscribe', {'id':finding, 'source':str(source)})['value']['id']
            self.answer(job, EMAIL)
            state = self.wait(lambda s:s['request'] and s['request']['kind']=='approval')
            with closing(Store(self.path, PHRASE, ledger_dir=self.folder / 'action-state')) as other:
                other.set_actions_paused(True)
                other.set_actions_paused(False)
            self.api.respond(job, state['request']['id'], 'CONFERMO')
            self.assertEqual(self.wait(lambda s:s['status'] != 'running')['status'], 'failed')
            send.assert_not_called()
            job = self.api.start('action-resume')['value']['id']
            state = self.wait(lambda s:s['request'] is not None)
            self.api._interaction.expires = 0
            self.assertFalse(self.api.respond(job, state['request']['id'], 'CONFERMO')['ok'])
            self.assertEqual(self.wait(lambda s:s['status'] != 'running')['status'], 'failed')

    def test_backup_restore_and_reconciliation_keep_deduplication(self):
        self.seed()
        backup = self.folder / 'backup.sqlite3'
        job = self.api.start('backup', {'destination':str(backup)})['value']['id']
        self.answer(job, 'CONFERMO')
        self.assertEqual(self.wait(lambda s:s['status'] != 'running')['status'], 'completed')
        self.assertTrue(backup.exists())
        self.assertFalse((self.folder / 'backup-action-state').exists())

    def test_asset_server_has_no_directory_listing_or_traversal(self):
        assets = self.folder / 'assets'
        assets.mkdir()
        (assets / 'index.html').write_text('synthetic', encoding='utf-8')
        (self.folder / 'secret.txt').write_text('not public', encoding='utf-8')
        with asset_server(assets) as url:
            with urlopen(url) as response:
                self.assertEqual(response.read(), b'synthetic')
                self.assertIn("connect-src 'none'", response.headers['Content-Security-Policy'])
            for path in ['../secret.txt', '%2e%2e/secret.txt', 'other.sqlite3', 'assets/']:
                with self.assertRaises(HTTPError):
                    urlopen(url.rsplit('/', 1)[0] + '/' + path)


if __name__ == '__main__':
    unittest.main()
