"""Tests for reading a finished report back.

The case that matters is the one that used to be impossible: the job record is
gone, which is what every restart produces, and the report has to come from S3.
"""

import os
import sys
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient

import app as app_module
from app import JobStatus

JOB_ID = "054a0b3a-66ad-49d2-8bd9-5d4b6cafc289"
BODY = "# A finished report\n\nwith contents.\n"


def _client_error(code):
    from botocore.exceptions import ClientError

    return ClientError({"Error": {"Code": code, "Message": code}}, "GetObject")


class TestReportRetrieval(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app_module.app)
        app_module.JOBS.clear()
        app_module.REPORTS.clear()

    def tearDown(self):
        app_module.JOBS.clear()
        app_module.REPORTS.clear()

    def _done_job(self):
        app_module.JOBS[JOB_ID] = {
            "job_id": JOB_ID,
            "status": JobStatus.DONE,
            "query": "q",
            "created_at": "2026-09-10T00:00:00+00:00",
            "finished_at": "2026-09-10T00:06:00+00:00",
            "report_key": f"reports/{JOB_ID}.md",
            "error": None,
        }

    # ── memory ───────────────────────────────────────────────────────

    def test_memory_is_used_when_present(self):
        self._done_job()
        app_module.REPORTS[JOB_ID] = BODY
        with patch.object(app_module, "_load_report_from_s3") as from_s3:
            r = self.client.get(f"/jobs/{JOB_ID}/report")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.text, BODY)
        from_s3.assert_not_called()

    # ── S3 fallback ──────────────────────────────────────────────────

    def test_report_is_served_after_the_job_record_is_gone(self):
        """The restart case. This is what the old ordering made unreachable."""
        with patch.object(app_module, "_load_report_from_s3", return_value=BODY):
            r = self.client.get(f"/jobs/{JOB_ID}/report")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.text, BODY)

    def test_missing_from_both_is_404(self):
        with patch.object(app_module, "_load_report_from_s3", return_value=None):
            r = self.client.get(f"/jobs/{JOB_ID}/report")
        self.assertEqual(r.status_code, 404)

    def test_unfinished_job_is_409_and_does_not_touch_s3(self):
        self._done_job()
        app_module.JOBS[JOB_ID]["status"] = JobStatus.RUNNING
        with patch.object(app_module, "_load_report_from_s3") as from_s3:
            r = self.client.get(f"/jobs/{JOB_ID}/report")
        self.assertEqual(r.status_code, 409)
        from_s3.assert_not_called()

    # ── the S3 loader itself ─────────────────────────────────────────

    def test_loader_returns_none_when_s3_is_disabled(self):
        with patch.object(app_module, "_s3", return_value=None):
            self.assertIsNone(app_module._load_report_from_s3(JOB_ID))

    def test_loader_rejects_a_job_id_that_is_not_a_uuid(self):
        """The id becomes part of an S3 key, so only the issued shape is used."""
        s3 = MagicMock()
        with patch.object(app_module, "_s3", return_value=s3):
            self.assertIsNone(app_module._load_report_from_s3("../../etc/passwd"))
        s3.get_object.assert_not_called()

    def test_loader_reads_the_conventional_key(self):
        s3 = MagicMock()
        s3.get_object.return_value = {"Body": MagicMock(read=lambda: BODY.encode())}
        with patch.object(app_module, "_s3", return_value=s3):
            result = app_module._load_report_from_s3(JOB_ID)
        self.assertEqual(result, BODY)
        self.assertEqual(s3.get_object.call_args.kwargs["Key"], f"reports/{JOB_ID}.md")

    def test_loader_returns_none_on_no_such_key(self):
        s3 = MagicMock()
        s3.get_object.side_effect = _client_error("NoSuchKey")
        with patch.object(app_module, "_s3", return_value=s3):
            self.assertIsNone(app_module._load_report_from_s3(JOB_ID))

    def test_loader_reraises_an_access_denied(self):
        """A permissions problem is not a missing report and must not look like one."""
        s3 = MagicMock()
        s3.get_object.side_effect = _client_error("AccessDenied")
        from botocore.exceptions import ClientError

        with patch.object(app_module, "_s3", return_value=s3):
            with self.assertRaises(ClientError):
                app_module._load_report_from_s3(JOB_ID)

    def test_write_and_read_agree_on_the_key(self):
        self.assertEqual(app_module._report_key(JOB_ID), f"reports/{JOB_ID}.md")


if __name__ == "__main__":
    unittest.main(verbosity=2)
