import io
import json
import unittest
from unittest.mock import MagicMock, patch
from urllib.error import URLError

import bloom_draft_queue_precheck as precheck


def last_line(text):
    return json.loads(text.strip().splitlines()[-1])


class DecideTests(unittest.TestCase):
    def test_empty_queue_skips_the_agent(self):
        out = precheck.decide(lambda: 0)
        self.assertEqual(last_line(out), {"wakeAgent": False})

    def test_pending_requests_wake_the_agent(self):
        out = precheck.decide(lambda: 2)
        self.assertEqual(last_line(out), {"wakeAgent": True, "pending": 2})

    def test_api_failure_skips_the_agent_and_reports_error(self):
        def boom():
            raise RuntimeError("HTTP 500")

        out = precheck.decide(boom)
        self.assertEqual(last_line(out), {"wakeAgent": False})
        self.assertIn("HTTP 500", out)


class ConfigTests(unittest.TestCase):
    def test_requires_https_origin_and_token(self):
        with self.assertRaises(ValueError):
            precheck.config({"BLOOM_API_URL": "http://x.com", "BLOOM_CONTENT_API_TOKEN": "t"})
        with self.assertRaises(ValueError):
            precheck.config({"BLOOM_API_URL": "https://x.com/api", "BLOOM_CONTENT_API_TOKEN": "t"})
        with self.assertRaises(ValueError):
            precheck.config({"BLOOM_API_URL": "https://x.com", "BLOOM_CONTENT_API_TOKEN": ""})

    def test_returns_origin_without_trailing_slash(self):
        url, token = precheck.config({"BLOOM_API_URL": "https://x.com/", "BLOOM_CONTENT_API_TOKEN": " t "})
        self.assertEqual((url, token), ("https://x.com", "t"))

    def test_failure_output_never_contains_the_token(self):
        env = {"BLOOM_API_URL": "https://x.com", "BLOOM_CONTENT_API_TOKEN": "secret-token"}
        with patch("urllib.request.urlopen", side_effect=URLError("connection refused")):
            out = precheck.decide(lambda: precheck.fetch_pending(env))
        self.assertIn("connection refused", out)
        self.assertNotIn("secret-token", out)


class FetchPendingTests(unittest.TestCase):
    ENV = {"BLOOM_API_URL": "https://x.com", "BLOOM_CONTENT_API_TOKEN": "secret-token"}

    def test_calls_pending_endpoint_with_token_and_user_agent(self):
        response = MagicMock()
        response.__enter__.return_value = io.BytesIO(b'{"pending": 4}')
        with patch("urllib.request.urlopen", return_value=response) as urlopen:
            count = precheck.fetch_pending(self.ENV)
        request = urlopen.call_args.args[0]
        self.assertEqual(count, 4)
        self.assertEqual(request.full_url, "https://x.com/api/v1/viralbarato/editorial/draft-requests/pending")
        self.assertEqual(request.get_header("Authorization"), "Bearer secret-token")
        self.assertTrue(request.get_header("User-agent").startswith("Mozilla/"))
        self.assertEqual(urlopen.call_args.kwargs["timeout"], precheck.TIMEOUT_SECONDS)


if __name__ == "__main__":
    unittest.main()
