"""Tests for credential redaction.

The cases here are drawn from a real failure: a Gemini 429 whose message
contained the request URL, and the URL carried the API key as a query
parameter.
"""

import unittest

from redaction import PLACEHOLDER, redact


class TestRedact(unittest.TestCase):

    def test_key_query_parameter_is_removed(self):
        text = (
            "Client error '429 Too Many Requests' for url "
            "'https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-2.0-flash:generateContent?key=AIzaSyExampleKeyValue1234567'"
        )
        out = redact(text)
        self.assertNotIn("AIzaSyExampleKeyValue1234567", out)
        self.assertIn(PLACEHOLDER, out)

    def test_url_structure_survives(self):
        """The URL should stay readable so the error is still diagnosable."""
        text = "https://example.com/v1/models:generate?key=AIzaSyAbcdefghijklmnopqrstu"
        out = redact(text)
        self.assertIn("https://example.com/v1/models:generate?key=", out)
        self.assertNotIn("AIzaSyAbcdefghijklmnopqrstu", out)

    def test_api_key_variants(self):
        for param in ("api_key", "api-key", "apikey", "access_token", "token"):
            with self.subTest(param=param):
                out = redact(f"https://x.test/v1?{param}=supersecretvalue123456")
                self.assertNotIn("supersecretvalue123456", out)

    def test_second_parameter_is_removed(self):
        out = redact("https://x.test/v1?model=flash&key=AIzaSyAbcdefghijklmnopqrstu")
        self.assertIn("model=flash", out)
        self.assertNotIn("AIzaSyAbcdefghijklmnopqrstu", out)

    def test_bearer_token(self):
        out = redact("Authorization: Bearer abcdef123456ghijkl")
        self.assertNotIn("abcdef123456ghijkl", out)
        self.assertIn("Authorization: Bearer", out)

    def test_bare_google_key(self):
        out = redact("the key AIzaSyAbcdefghijklmnopqrstuvwx appeared in a log line")
        self.assertNotIn("AIzaSyAbcdefghijklmnopqrstuvwx", out)

    def test_bare_openai_key(self):
        out = redact("sk-abcdefghijklmnopqrstuvwxyz0123")
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz0123", out)

    def test_ordinary_text_is_untouched(self):
        text = "job 9e52e58e failed after 2 searches and 4 page reads"
        self.assertEqual(redact(text), text)

    def test_empty_and_none_safe(self):
        self.assertEqual(redact(""), "")
        self.assertIsNone(redact(None))


if __name__ == "__main__":
    unittest.main()
