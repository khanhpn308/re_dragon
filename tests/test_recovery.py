"""Unit tests for Recovery Engine and Classification in re_harness.recovery."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from re_harness import autonomy, core, recovery


class RecoveryClassificationTests(unittest.TestCase):
    def test_auth_and_permission_denial_classified_critical_fail_closed(self):
        outcome = {
            "code": 0,
            "data": {"status": "SUCCESS", "response": "Tool denied: user permission required to edit file"},
            "stderr": "",
        }
        res = recovery.classify_turn(outcome)
        self.assertEqual(res.category, "AUTH_OR_PERMISSION")
        self.assertEqual(res.severity, "CRITICAL")
        self.assertFalse(res.recoverable)
        self.assertEqual(res.suggested_status, "NEEDS_USER")
        self.assertTrue(res.requires_human)

    def test_quota_exhausted_classified_with_reset_delay(self):
        outcome = {
            "code": 1,
            "data": {"status": "ERROR"},
            "stderr": "RESOURCE_EXHAUSTED: Quota exceeded. Resets in 1h 30m",
        }
        res = recovery.classify_turn(outcome)
        self.assertEqual(res.category, "QUOTA_EXHAUSTED")
        self.assertEqual(res.severity, "INFO")
        self.assertTrue(res.recoverable)
        self.assertEqual(res.suggested_status, "WAIT_QUOTA")
        self.assertAlmostEqual(res.retry_delay, 5400 + 60, delta=1.0)

    def test_ghidra_oom_classified_resource_exhaustion(self):
        outcome = {
            "code": 137,
            "data": {"status": "ERROR"},
            "stderr": "java.lang.OutOfMemoryError: Java heap space during native decompile",
        }
        res = recovery.classify_turn(outcome, current_attempt=1)
        self.assertEqual(res.category, "RESOURCE_EXHAUSTION")
        self.assertEqual(res.severity, "ERROR")
        self.assertTrue(res.recoverable)
        self.assertEqual(res.suggested_status, "WAIT_RETRY")
        self.assertGreaterEqual(res.retry_delay, 60.0)

    def test_sqlite_lock_classified_with_short_backoff(self):
        outcome = {
            "code": 1,
            "data": {"status": "ERROR"},
            "stderr": "sqlite3.OperationalError: database is locked",
        }
        res = recovery.classify_turn(outcome, current_attempt=2)
        self.assertEqual(res.category, "SQLITE_LOCK")
        self.assertEqual(res.severity, "WARNING")
        self.assertTrue(res.recoverable)
        self.assertGreaterEqual(res.retry_delay, 6.0)

    def test_network_transient_classified_with_exponential_backoff(self):
        outcome = {
            "code": 1,
            "data": {"status": "ERROR"},
            "stderr": "Connection reset by peer ECONNRESET",
        }
        res = recovery.classify_turn(outcome, current_attempt=3)
        self.assertEqual(res.category, "NETWORK_TRANSIENT")
        self.assertTrue(res.recoverable)
        self.assertGreaterEqual(res.retry_delay, 120.0)

    def test_timeout_classified_correctly(self):
        outcome = {"code": 124, "data": {}, "stderr": "watchdog process timeout"}
        res = recovery.classify_turn(outcome, current_attempt=1)
        self.assertEqual(res.category, "TIMEOUT")
        self.assertTrue(res.recoverable)
        self.assertEqual(res.suggested_status, "WAIT_RETRY")

    def test_clean_success_with_marker_parsed(self):
        outcome = {
            "code": 0,
            "data": {
                "status": "SUCCESS",
                "response": "Here is what I did...\nRE_DRAGON_RUN_STATE {\"state\":\"CONTINUE\",\"note\":\"Checkpoint 1\"}",
            },
            "stderr": "",
        }
        res = recovery.classify_turn(outcome)
        self.assertEqual(res.category, "SUCCESS_WITH_MARKER")
        self.assertEqual(res.suggested_status, "CONTINUE")
        self.assertEqual(res.error_summary, "Checkpoint 1")

    def test_missing_marker_classified_recoverable(self):
        outcome = {
            "code": 0,
            "data": {"status": "SUCCESS", "response": "Completed task without any marker at all"},
            "stderr": "",
        }
        res = recovery.classify_turn(outcome, current_attempt=1)
        self.assertEqual(res.category, "MISSING_MARKER")
        self.assertTrue(res.recoverable)
        self.assertEqual(res.suggested_status, "WAIT_RETRY")


class PreRetrySafetyTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.workspace = Path(self.temp_dir.name)
        self.harness_dir = self.workspace / ".re_harness_mvp"
        with core.database(self.harness_dir) as db:
            autonomy.migrate(db)

    def test_safety_check_succeeds_on_valid_active_project(self):
        with core.database(self.harness_dir) as db:
            proj = autonomy.start(db, "Production Goal", "Acceptance gates")
            pid = proj["project_id"]

        health = recovery.verify_pre_retry_safety(
            self.workspace, pid, self.harness_dir, previous_pid=None
        )
        self.assertTrue(health["safe_to_retry"])
        self.assertEqual(health["project_id"], pid)

    def test_safety_check_fails_closed_on_accepted_project(self):
        with core.database(self.harness_dir) as db:
            proj = autonomy.start(db, "Accepted Goal", "Acceptance gates")
            pid = proj["project_id"]
            db.execute("UPDATE auto_projects SET status='ACCEPTED' WHERE id=?", (pid,))

        with self.assertRaises(recovery.SafetyCheckError) as ctx:
            recovery.verify_pre_retry_safety(
                self.workspace, pid, self.harness_dir, previous_pid=None
            )
        self.assertIn("cannot auto-retry a non-active project", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
