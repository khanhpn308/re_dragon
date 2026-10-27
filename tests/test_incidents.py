"""Unit tests for Incident Journal and Redaction in re_harness.incidents."""
from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

from re_harness import incidents


class IncidentJournalTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.workspace = Path(self.temp_dir.name)

    def test_redaction_strips_tokens_and_api_keys(self):
        raw = (
            "Failed Telegram delivery: bot token 123456789:ABCdefGHIjklMNOpqrSTUvwxYZ_1234567 "
            "with key AIzaSyD9uG8_X1z5V3p1N4m2Q9w8E7r6T5y4U3i and "
            "sk-1234567890abcdef1234567890abcdef and password=SuperSecret123!"
        )
        redacted = incidents.redact_sensitive(raw)
        self.assertNotIn("123456789:ABCdef", redacted)
        self.assertIn("[REDACTED_BOT_TOKEN]", redacted)
        self.assertNotIn("AIzaSyD9uG8", redacted)
        self.assertIn("[REDACTED_API_KEY]", redacted)
        self.assertNotIn("SuperSecret123!", redacted)
        self.assertIn("password=[REDACTED]", redacted)

    def test_create_and_query_incident(self):
        inc, is_new = incidents.create_or_update_incident(
            self.workspace,
            project_id="test-proj-1",
            category="MISSING_MARKER",
            error_message="CLI turn exited 0 but emitted no RE_DRAGON_RUN_STATE marker",
            severity="WARNING",
            task_id="T-001",
            details={"pid": 9999},
        )
        self.assertTrue(is_new)
        self.assertTrue(inc["id"].startswith("INC-"))
        self.assertEqual(inc["category"], "MISSING_MARKER")
        self.assertEqual(inc["status"], "OPEN")
        self.assertEqual(inc["occurrence_count"], 1)

        listed = incidents.list_incidents(self.workspace, project_id="test-proj-1")
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["id"], inc["id"])

        fetched = incidents.get_incident(self.workspace, inc["id"])
        self.assertIsNotNone(fetched)
        self.assertEqual(len(fetched["events"]), 1)
        self.assertEqual(fetched["events"][0]["event_type"], "CREATED")

    def test_deduplication_within_window(self):
        inc1, is_new1 = incidents.create_or_update_incident(
            self.workspace,
            project_id="test-proj-2",
            category="NETWORK_TRANSIENT",
            error_message="Connection reset by peer ECONNRESET",
            now=1000.0,
        )
        self.assertTrue(is_new1)

        # 60 seconds later, same project and category
        inc2, is_new2 = incidents.create_or_update_incident(
            self.workspace,
            project_id="test-proj-2",
            category="NETWORK_TRANSIENT",
            error_message="Connection reset by peer ECONNRESET second time",
            now=1060.0,
        )
        self.assertFalse(is_new2)
        self.assertEqual(inc1["id"], inc2["id"])
        self.assertEqual(inc2["occurrence_count"], 2)

        # Verify event recorded
        fetched = incidents.get_incident(self.workspace, inc1["id"])
        self.assertEqual(len(fetched["events"]), 2)
        self.assertEqual(fetched["events"][1]["event_type"], "OCCURRENCE_BUMP")

    def test_recovery_attempts_and_resolution(self):
        inc, _ = incidents.create_or_update_incident(
            self.workspace,
            project_id="test-proj-3",
            category="SQLITE_LOCK",
            error_message="database is locked",
            max_retries=2,
            now=1000.0,
        )
        # Attempt 1 fails
        updated = incidents.record_recovery_attempt(
            self.workspace, inc["id"], success=False, note="DB busy retry 1", now=1010.0
        )
        self.assertEqual(updated["status"], "INVESTIGATING")
        self.assertEqual(updated["recovery_attempts"], 1)

        # Attempt 2 fails -> exhausts budget
        updated2 = incidents.record_recovery_attempt(
            self.workspace, inc["id"], success=False, note="DB busy retry 2", now=1020.0
        )
        self.assertEqual(updated2["status"], "FAILED_UNRECOVERABLE")
        self.assertEqual(updated2["recovery_attempts"], 2)

        # Manual resolution
        res = incidents.resolve_incident(
            self.workspace, inc["id"], notes="Operator released lock", now=1030.0
        )
        self.assertTrue(res)
        final = incidents.get_incident(self.workspace, inc["id"])
        self.assertEqual(final["status"], "RESOLVED")
        self.assertEqual(final["resolution_notes"], "Operator released lock")


if __name__ == "__main__":
    unittest.main()
