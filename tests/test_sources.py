import hashlib
import unittest
from email.message import Message
from unittest.mock import patch

from obliryx.providers import breach_matches, search_web
from obliryx.site import discover_routes, inspect_page


class SourceTests(unittest.TestCase):
    def test_discover_routes_fetches_only_informational_source(self):
        with (patch("obliryx.site.resolve_destination", return_value="203.0.113.1"),
              patch("obliryx.site.DirectHTTPSConnection") as connection):
            client = connection.return_value
            response = client.getresponse.return_value
            response.status = 200
            response.headers = Message()
            response.headers["Content-Type"] = "text/html"
            response.read.return_value = b'<a href="https://elsewhere.invalid/out">Disiscrizione</a>'
            self.assertEqual(discover_routes("https://example.invalid/privacy"), [
                {"kind": "unsubscribe_candidate", "value": "https://elsewhere.invalid/out",
                 "source_url": "https://example.invalid/privacy"},
            ])
            client.request.assert_called_once_with("GET", "/privacy", headers={
                "User-Agent": "Obliryx", "Accept": "text/html",
            })
            with self.assertRaisesRegex(ValueError, "parametri personali"):
                discover_routes("https://example.invalid/out?token=synthetic")
            client.request.assert_called_once()
    def test_hibp_prefix_filters_out_other_addresses(self):
        email = "reader@example.invalid"
        digest = hashlib.sha1(email.encode()).hexdigest().upper()
        with patch("obliryx.providers.request_json", return_value=[
            {"hashSuffix": "F" * 34, "websites": ["ThirdParty"]},
            {"hashSuffix": digest[6:], "websites": ["Own"]},
        ]) as request:
            self.assertEqual(breach_matches(email, "synthetic", "prefisso"), [{"Name": "Own"}])
            self.assertTrue(request.call_args.args[1].endswith("/" + digest[:6]))
            self.assertNotIn(email, request.call_args.args[1])

    def test_provider_permission_error_does_not_retry_with_direct_lookup(self):
        with patch("obliryx.providers.request_json", side_effect=ValueError("HTTP 403")) as request:
            with self.assertRaisesRegex(ValueError, "403"):
                breach_matches("reader@example.invalid", "synthetic", "prefisso")
            request.assert_called_once()

    def test_brave_result_uses_only_https_and_displays_no_snippet(self):
        with patch("obliryx.providers.request_json", return_value={"web": {"results": [
            {"title": "Fonte", "url": "https://example.invalid/page", "description": "PII"},
            {"title": "HTTP", "url": "http://example.invalid/page"},
        ]}}):
            self.assertEqual(search_web("reader@example.invalid", "synthetic"),
                             [{"titolo": "Fonte", "url": "https://example.invalid/page"}])

    def test_page_matches_only_visible_text_and_lists_candidates_without_following(self):
        with (patch("obliryx.site.resolve_destination", return_value="203.0.113.1"),
              patch("obliryx.site.DirectHTTPSConnection") as connection):
            client = connection.return_value
            response = client.getresponse.return_value
            response.status = 200
            response.headers = Message()
            response.headers["Content-Type"] = "text/html; charset=utf-8"
            response.read.return_value = (
                b"<script>hidden@example.invalid</script><p>reader@example.invalid</p>"
                b'<a href="/privacy">Privacy</a><a href="/out">Disiscrizione</a>'
            )
            found, routes = inspect_page("https://example.invalid/list", "reader@example.invalid")
            self.assertTrue(found)
            self.assertEqual([item["kind"] for item in routes], ["privacy_candidate", "unsubscribe_candidate"])
            client.request.assert_called_once_with("GET", "/list", headers={"User-Agent": "Obliryx", "Accept": "text/html"})
            self.assertFalse(inspect_page("https://example.invalid/list", "hidden@example.invalid")[0])


if __name__ == "__main__":
    unittest.main()
