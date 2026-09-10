"""Tests for the API key gate.

The important cases are the two that are easy to get wrong: /health must stay
open or App Runner kills the container, and an unset API_KEY must leave the
service usable so local runs and CI need no configuration.
"""

import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

import app as app_module

KEY = "test-key-abc123"


class TestApiKeyGate(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app_module.app)
        self.payload = {"query": "a valid research question"}

    # ── key configured ───────────────────────────────────────────────

    def test_request_without_key_is_rejected(self):
        with patch.dict(os.environ, {"API_KEY": KEY}):
            r = self.client.post("/research", json=self.payload)
        self.assertEqual(r.status_code, 401)

    def test_request_with_wrong_key_is_rejected(self):
        with patch.dict(os.environ, {"API_KEY": KEY}):
            r = self.client.post(
                "/research", json=self.payload, headers={"X-API-Key": "wrong"}
            )
        self.assertEqual(r.status_code, 401)

    def test_reading_a_job_requires_the_key(self):
        with patch.dict(os.environ, {"API_KEY": KEY}):
            r = self.client.get("/jobs/does-not-exist")
        self.assertEqual(r.status_code, 401)

    def test_reading_a_report_requires_the_key(self):
        with patch.dict(os.environ, {"API_KEY": KEY}):
            r = self.client.get("/jobs/does-not-exist/report")
        self.assertEqual(r.status_code, 401)

    def test_correct_key_is_accepted(self):
        """Auth passes; the crew itself is stubbed so no model call is made."""
        with patch.dict(os.environ, {"API_KEY": KEY}), \
             patch.object(app_module, "_execute"):
            r = self.client.post(
                "/research", json=self.payload, headers={"X-API-Key": KEY}
            )
        self.assertEqual(r.status_code, 202)
        self.assertIn("job_id", r.json())

    def test_auth_runs_before_the_404(self):
        """A wrong key on a missing job must not reveal that it is missing."""
        with patch.dict(os.environ, {"API_KEY": KEY}):
            r = self.client.get("/jobs/does-not-exist", headers={"X-API-Key": "wrong"})
        self.assertEqual(r.status_code, 401)

    # ── health stays open ────────────────────────────────────────────

    def test_health_needs_no_key(self):
        """App Runner polls /health; a 401 there gets the container killed."""
        with patch.dict(os.environ, {"API_KEY": KEY}):
            r = self.client.get("/health")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "ok")

    def test_docs_need_no_key(self):
        with patch.dict(os.environ, {"API_KEY": KEY}):
            r = self.client.get("/docs")
        self.assertEqual(r.status_code, 200)

    # ── key not configured ───────────────────────────────────────────

    def test_unset_key_leaves_the_service_open(self):
        env = {k: v for k, v in os.environ.items() if k != "API_KEY"}
        with patch.dict(os.environ, env, clear=True), \
             patch.object(app_module, "_execute"):
            r = self.client.post("/research", json=self.payload)
        self.assertEqual(r.status_code, 202)

    def test_empty_key_leaves_the_service_open(self):
        with patch.dict(os.environ, {"API_KEY": ""}), \
             patch.object(app_module, "_execute"):
            r = self.client.post("/research", json=self.payload)
        self.assertEqual(r.status_code, 202)

    # ── the scheme is advertised ─────────────────────────────────────

    def test_openapi_declares_the_security_scheme(self):
        """Without this, /docs shows no Authorize button to paste a key into."""
        schemes = self.client.get("/openapi.json").json()["components"][
            "securitySchemes"
        ]
        self.assertIn("APIKeyHeader", schemes)
        self.assertEqual(schemes["APIKeyHeader"]["name"], "X-API-Key")


if __name__ == "__main__":
    unittest.main(verbosity=2)
