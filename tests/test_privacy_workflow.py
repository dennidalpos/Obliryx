import json
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from obliryx.browser_procedures import BrowserProcedure
from obliryx.desktop import DesktopAPI
from obliryx.privacy_workflow import PrivacyWorkflow
from obliryx.web_discovery import candidate_links, identifiers, match_page, queries, search_access
from obliryx.windows_secret import application_password
from obliryx.free_sources import FreeSources, FreeSourceError

EMAIL = "reader@example.invalid"
PAGE = "https://privacy.example.invalid/request"
SUBMIT = "https://privacy.example.invalid/done"
ADAPTER = BrowserProcedure("synthetic-request", "1", PAGE, SUBMIT, "privacy", "send",
                           (("email", "email"),), "receipt", "Request received", "Richiesta sintetica")


def contract(adapter=ADAPTER, **changes):
    return {"page": adapter.page_url, "action": adapter.submit_url, "method": "post",
            "fields": [{"name": "email", "type": "email"}], "challenge": False,
            "button": adapter.button_id, **changes}


def broker(identifier="synthetic-request", source=PAGE):
    return {"id": identifier, "controller": "Broker sintetico", "countries": ["IT"],
            "source": source, "action": "cancellazione", "reviewed_on": "2026-11-13",
            "channel": {"kind": "web", "destination": source, "effect": "Richiesta sintetica"}}


class FakeBrowser:
    def __init__(self):
        self.pages = {}
        self.calls = []
        self.contract = contract()
        self.completion_result = {"url": SUBMIT, "completion_id": "receipt", "completion_text": "Request received"}
        self.submit_error = False

    def navigate(self, url, cancelled=None):
        self.calls.append(("navigate", url))
        return self.pages.get(url, {"url": url, "text": "", "links": [], "challenge": False})

    def inspect(self, adapter):
        return self.contract

    def submit(self, adapter, values):
        self.calls.append(("submit", adapter.identifier))
        if self.submit_error:
            raise TimeoutError()
        return "submitted"

    def completion(self, adapter):
        return self.completion_result

    def assist(self, url, cancelled=None):
        self.calls.append(("assist", url))
        return self.navigate(url, cancelled)

    def suspend(self):
        pass

    def show(self):
        pass

    def close(self):
        pass


class NoFreeSources:
    def specs(self, _values):
        return []


class DiscoveryTests(unittest.TestCase):
    def test_validation_queries_and_ambiguity(self):
        with self.assertRaises(ValueError):
            identifiers({"city": "Roma"})
        with self.assertRaises(ValueError):
            identifiers({"email": "invalid"})
        with self.assertRaises(ValueError):
            identifiers({"name": "bad\nvalue"})
        rows = queries(identifiers({"email": EMAIL, "name": "Nome Sintetico", "city": "Roma"}))
        self.assertEqual(len(rows), 2)
        self.assertNotIn(EMAIL, rows[0]["masked"])
        self.assertIn("Roma", rows[1]["url"])
        observed = match_page({"text": "Nome Sintetico"}, {"name": "Nome Sintetico"})
        self.assertEqual(observed["status"], "observed")
        self.assertIn("verificare", observed["identity"])
        self.assertEqual(match_page({"text": "other"}, {"email": EMAIL})["status"], "not_observed")

    def test_challenge_is_not_evidence_and_snippets_are_not_matched(self):
        row = match_page({"text": EMAIL, "challenge": True}, {"email": EMAIL})
        self.assertEqual(row["status"], "blocked")
        self.assertEqual(row["matches"], [])
        self.assertEqual(match_page({"text": "", "snippet": EMAIL}, {"email": EMAIL})["status"], "not_observed")
        self.assertEqual(match_page({"text": "x" + EMAIL + "x"}, {"email": EMAIL})["status"], "not_observed")
        self.assertEqual(match_page({"text": "prefix." + EMAIL}, {"email": EMAIL})["status"], "not_observed")
        self.assertEqual(match_page({"text": "123 another field 456"}, {"phone": "123456"})["status"], "not_observed")
        self.assertEqual(match_page({"text": "+39 (012) 345-6789"}, {"phone": "+390123456789"})["status"], "observed")
        self.assertEqual(match_page({"text": "", "settled":False}, {"email": EMAIL})["status"], "unavailable")

    def test_links_are_bounded_unique_https_and_engine_links_are_removed(self):
        rows = [{"url": "https://example.invalid/a#one"}, {"url": "https://example.invalid/a#two"},
                {"url": "javascript:alert(1)"}, {"url": "https://duckduckgo.com/?q=a"},
                {"url": "https://duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.invalid%2Fb"}]
        self.assertEqual(candidate_links(rows), ["https://example.invalid/a", "https://example.invalid/b"])

    def test_reviewed_embedding_policy_blocks_before_any_search_request(self):
        def forbidden(_):
            self.fail("A prohibited source must not be contacted")
        self.assertEqual(search_access(forbidden)["status"], "unavailable")

    def test_exact_contract_rejects_added_fields_new_destinations_and_captcha(self):
        self.assertTrue(ADAPTER.accepts(contract()))
        for changed in [contract(action="https://other.invalid/submit"), contract(challenge=True),
                        contract(fields=[{"name": "email", "type": "email"}, {"name": "document", "type": "text"}])]:
            self.assertFalse(ADAPTER.accepts(changed))
        self.assertFalse(ADAPTER.completed({"url": SUBMIT, "text": "Request received"}))


class CredentialTests(unittest.TestCase):
    def test_credential_is_sealed_reused_and_never_regenerated_over_a_database(self):
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            seal = lambda data: bytes(b ^ 91 for b in data)
            first = application_password(directory, protect=seal, unprotect=seal)
            self.assertNotIn(first.encode(), (directory / "desktop-key.dpapi").read_bytes())
            self.assertEqual(first, application_password(directory, protect=seal, unprotect=seal))
        with tempfile.TemporaryDirectory() as folder:
            directory = Path(folder)
            (directory / "desktop-history.sqlite3").write_bytes(b"existing")
            with self.assertRaises(ValueError):
                application_password(directory, protect=seal, unprotect=seal)
            self.assertFalse((directory / "desktop-key.dpapi").exists())


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.api = DesktopAPI(self.directory)
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(self.api._close)
        self.browser = FakeBrowser()
        self.workflow = PrivacyWorkflow(self.api, browser_factory=lambda: self.browser,
                access=lambda: {"status": "unavailable", "reason": "Synthetic unavailable source"},
                procedures={ADAPTER.identifier: ADAPTER}, free_sources=NoFreeSources())
        self.api._workflow = self.workflow
        self.patches = [patch('obliryx.privacy_workflow.application_password', return_value='synthetic-password-123456'),
                        patch('obliryx.privacy_workflow.public_url', side_effect=lambda url: url),
                        patch('obliryx.privacy_workflow.load_catalog', return_value={"procedures": [broker(), broker('manual-request', 'https://manual.example.invalid/request')]})]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        self.assertTrue(self.api.workflow_open()["ok"])

    def wait(self, predicate, seconds=5):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            state = self.api.workflow_status()["value"]
            if predicate(state):
                return state
            time.sleep(.01)
        self.fail(str(state))

    def analyze(self):
        result = self.api.workflow_analyze({"email": EMAIL})
        self.assertTrue(result["ok"], result)
        return self.wait(lambda s: not s["busy"])

    def test_unavailable_sources_do_not_fabricate_presence_and_no_identifiers_are_persisted(self):
        state = self.analyze()
        self.assertEqual(state["phase"], "results")
        self.assertEqual(len(state["items"]), 2)
        self.assertTrue(all(row["kind"] == "broker" and row["status"] == "holding_unknown" for row in state["items"]))
        self.assertFalse(any(call[0] == "navigate" for call in self.browser.calls))
        self.assertNotIn(EMAIL.encode(), (self.directory / "desktop-history.sqlite3").read_bytes())

    def test_automatic_actions_finish_before_assistance_and_approval_is_single_use(self):
        state = self.analyze()
        plan = self.api.workflow_plan([row["id"] for row in reversed(state["items"])])["value"]
        self.assertEqual(plan["actions"][0]["mode"], "automatic")
        self.assertEqual(plan["actions"][0]["fields"], {"Email": EMAIL})
        self.assertTrue(self.api.workflow_execute(plan["id"])["ok"])
        assisted = self.wait(lambda s: s["assistance"] is not None)
        self.assertEqual(assisted["operations"][0]["status"], "accepted")
        self.assertLess(next(i for i,c in enumerate(self.browser.calls) if c[0]=='submit'), next(i for i,c in enumerate(self.browser.calls) if c[0]=='assist'))
        self.assertFalse(self.api.workflow_execute(plan["id"])["ok"])
        request = assisted["assistance"]["request_id"]
        self.assertTrue(self.api.workflow_respond(request, "skip")["ok"])
        self.assertFalse(self.api.workflow_respond(request, "continue")["ok"])
        done = self.wait(lambda s: not s["busy"])
        self.assertEqual(done["operations"][1]["status"], "skipped")
        # Approval at rest contains masks, never searched values.
        def approvals():
            return [self.api._store._open(row['id'], row['approval']) for row in self.api._store.db.execute('SELECT id, approval FROM actions')]
        self.assertNotIn(EMAIL, json.dumps(self.api._submit(approvals).result()))

    def test_changed_contract_never_submits(self):
        self.browser.contract = contract(action='https://changed.example.invalid/')
        state = self.analyze()
        plan = self.api.workflow_plan([state['items'][0]['id']])['value']
        self.api.workflow_execute(plan['id'])
        done = self.wait(lambda s:not s['busy'])
        self.assertEqual(done['operations'][0]['status'], 'approval_invalidated')
        self.assertFalse(any(c[0]=='submit' for c in self.browser.calls))

    def test_captcha_is_deferred_then_resume_revalidates_contract(self):
        self.browser.pages[PAGE] = {'url':PAGE, 'challenge':True, 'text':''}
        state = self.analyze()
        plan = self.api.workflow_plan([state['items'][0]['id']])['value']
        self.api.workflow_execute(plan['id'])
        assisted = self.wait(lambda s:bool(s['assistance']))
        self.assertFalse(any(c[0]=='submit' for c in self.browser.calls))
        self.browser.pages[PAGE]['challenge'] = False
        self.api.workflow_respond(assisted['assistance']['request_id'], 'continue')
        done = self.wait(lambda s:not s['busy'])
        self.assertEqual(done['operations'][0]['status'], 'accepted')

    def test_timeout_is_durable_and_a_new_plan_cannot_resubmit(self):
        self.browser.submit_error = True
        state = self.analyze()
        selected = [state['items'][0]['id']]
        plan = self.api.workflow_plan(selected)['value']
        self.api.workflow_execute(plan['id'])
        done = self.wait(lambda s:not s['busy'])
        self.assertEqual(done['operations'][0]['status'], 'delivery_unknown')
        plan = self.api.workflow_plan(selected)['value']
        self.api.workflow_execute(plan['id'])
        self.wait(lambda s:not s['busy'])
        self.assertEqual(len([c for c in self.browser.calls if c[0]=='submit']), 1)

    def test_lock_revokes_assistance_and_clears_identifiers_and_approvals(self):
        state = self.analyze()
        plan = self.api.workflow_plan([state['items'][1]['id']])['value']
        self.api.workflow_execute(plan['id'])
        assisted = self.wait(lambda s:bool(s['assistance']))
        self.api.lock()
        self.assertFalse(self.api.workflow_respond(assisted['assistance']['request_id'], 'continue')['ok'])
        self.assertEqual(self.workflow._values, {})
        self.assertIsNone(self.workflow._plan)
        self.assertEqual(self.api.workflow_status()['value']['items'], [])

    def test_expired_preview_and_unknown_selection(self):
        state = self.analyze()
        self.assertFalse(self.api.workflow_plan(['unknown'])['ok'])
        plan = self.api.workflow_plan([state['items'][0]['id']])['value']
        self.workflow._plan['created'] = 0
        self.assertFalse(self.api.workflow_execute(plan['id'])['ok'])

    def test_editing_selection_invalidates_the_old_approval(self):
        state = self.analyze()
        plan = self.api.workflow_plan([state['items'][0]['id']])['value']
        self.assertTrue(self.api.workflow_edit_selection()['ok'])
        self.assertEqual(self.workflow.snapshot()['phase'],'results')
        self.assertFalse(self.api.workflow_execute(plan['id'])['ok'])

    def test_discovery_visits_and_deduplicates_pages_instead_of_using_snippets(self):
        self.workflow.access = lambda:{'status':'available', 'reason':'Synthetic permitted source'}
        query = queries({'email':EMAIL})[0]['url']
        self.browser.pages[query] = {'url':query, 'text':EMAIL, 'links':[{'url':PAGE}, {'url':PAGE}]}
        self.browser.pages[PAGE] = {'url':PAGE, 'text':EMAIL, 'links':[]}
        state = self.analyze()
        presences = [r for r in state['items'] if r['kind']=='presence']
        self.assertEqual(len(presences), 1)
        self.assertEqual(presences[0]['status'], 'observed')
        self.assertEqual(len([c for c in self.browser.calls if c==('navigate',PAGE)]), 1)
        self.assertNotIn(EMAIL, json.dumps(presences))

    def test_free_api_results_are_candidates_until_the_actual_page_is_checked(self):
        calls = []
        def request(host, path):
            calls.append((host,path))
            return {'items':[{'login':'synthetic-user'}],'total_count':1} if host=='api.github.com' else {'query':{'search':[]}}
        self.workflow.free_sources = FreeSources(request=request)
        self.browser.pages['https://github.com/synthetic-user'] = {'url':'https://github.com/synthetic-user','text':EMAIL}
        state = self.analyze()
        self.assertEqual(len(calls),2)
        self.assertEqual(len([s for s in state['sources'] if s['status']=='complete']),2)
        self.assertTrue(any(row['status']=='observed' for row in state['items']))
        self.api.workflow_inspect('https://github.com/synthetic-user')
        repeated = self.wait(lambda s:not s['busy'])
        self.assertEqual(len([row for row in repeated['items'] if row['kind']=='presence']),1)
        self.api.lock()
        reopened = self.api.workflow_open()
        self.assertTrue(reopened['ok'],reopened)
        self.assertEqual(len(reopened['value']['history']),1)
        self.assertEqual(self.workflow._values,{})


class FreeSourceTests(unittest.TestCase):
    def test_only_relevant_identifiers_are_sent_and_search_queries_are_encoded(self):
        specs = FreeSources().specs({'email':EMAIL,'phone':'+39 0123456789','name':'Nome Sintetico','city':'Roma'})
        self.assertEqual(len([s for s in specs if s['provider']=='github']),2)
        self.assertTrue(all('api-key' not in s['path'] for s in specs))
        self.assertTrue(any('location' in s['path'] and 'Roma' in s['path'] for s in specs))
        self.assertFalse(any('0123456789' in s['path'] for s in specs if s['provider']=='github'))

    def test_api_results_are_bounded_and_remote_urls_are_not_trusted(self):
        source = FreeSources(request=lambda *_:{'items':[{'login':'synthetic-user','html_url':'https://hostile.invalid/'}], 'total_count':9,'incomplete_results':False})
        result = source.search(source.specs({'email':EMAIL})[0],threading.Event())
        self.assertEqual(result['status'],'incomplete')
        self.assertEqual(result['links'],['https://github.com/synthetic-user'])

    def test_rate_wait_is_cancellable_and_errors_do_not_become_empty_success(self):
        source = FreeSources(request=lambda *_:{'unexpected':'shape'})
        spec = source.specs({'email':EMAIL})[0]
        with self.assertRaises(FreeSourceError):
            source.search(spec,threading.Event())
        cancelled=threading.Event()
        cancelled.set()
        with self.assertRaises(FreeSourceError):
            source.search(spec,cancelled)


if __name__ == '__main__':
    unittest.main()
