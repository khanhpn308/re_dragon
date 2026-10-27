"""Tests for Telegram Incident Control commands and lifecycle controls."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from re_harness import (
    autonomy,
    core,
    incidents,
    quota_watchdog,
    telegram_bridge,
    telegram_control,
)


class TelegramIncidentControlTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.workspace = Path(self.temp_dir.name)
        self.watch_dir = self.workspace / ".re_harness"
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self.harness_dir = self.workspace / ".re_harness_mvp"
        with core.database(self.harness_dir) as db:
            autonomy.migrate(db)

    def test_incidents_text_formatting(self):
        # Empty case
        self.assertIn("No incidents recorded", telegram_bridge.incidents_text(self.workspace))

        # Add an incident
        inc, _ = incidents.create_or_update_incident(
            self.workspace,
            project_id="test-proj-1",
            category="MISSING_MARKER",
            error_message="CLI turn omitted marker",
            severity="WARNING",
        )

        text = telegram_bridge.incidents_text(self.workspace)
        self.assertIn(inc["id"], text)
        self.assertIn("MISSING_MARKER", text)
        self.assertIn("OPEN", text)

    def test_incident_detail_text(self):
        inc, _ = incidents.create_or_update_incident(
            self.workspace,
            project_id="test-proj-2",
            category="AGENT_CRASH",
            error_message="Non-zero exit code 1",
            severity="ERROR",
        )
        detail = telegram_bridge.incident_detail_text(self.workspace, inc["id"])
        self.assertIn(inc["id"], detail)
        self.assertIn("AGENT_CRASH", detail)
        self.assertIn("/retry " + inc["id"], detail)

        # Missing incident
        missing = telegram_bridge.incident_detail_text(self.workspace, "INC-missing")
        self.assertIn("not found", missing)

    def test_pause_and_resume_watchdog(self):
        state_file = self.watch_dir / "quota-watchdog.json"
        with core.database(self.harness_dir) as db:
            pid = autonomy.start(db, "Production Goal", "Acceptance gates")["project_id"]

        quota_watchdog.save(
            state_file,
            {"status": "CONTINUE", "project_id": pid, "conversation_id": "c-1234"},
        )

        # Pause
        pause_msg = telegram_bridge.pause_watchdog(self.workspace)
        self.assertIn("paused", pause_msg.lower())
        st = quota_watchdog.load(state_file)
        self.assertEqual(st["status"], "PAUSED")

        # Second pause is idempotent
        pause_again = telegram_bridge.pause_watchdog(self.workspace)
        self.assertIn("already PAUSED", pause_again)

        # Resume
        resume_msg = telegram_bridge.resume_watchdog(self.workspace, db_dir=self.harness_dir)
        self.assertIn("resumed", resume_msg.lower())
        st2 = quota_watchdog.load(state_file)
        self.assertEqual(st2["status"], "READY")

    def test_retry_incident_safety_check(self):
        with core.database(self.harness_dir) as db:
            pid = autonomy.start(db, "Production Goal", "Acceptance gates")["project_id"]

        state_file = self.watch_dir / "quota-watchdog.json"
        quota_watchdog.save(
            state_file,
            {"status": "NEEDS_USER", "project_id": pid, "conversation_id": "c-1234"},
        )

        inc, _ = incidents.create_or_update_incident(
            self.workspace,
            project_id=pid,
            category="MISSING_MARKER",
            error_message="Omitted marker",
        )

        # Retry should succeed since project is ACTIVE
        res = telegram_bridge.retry_incident(self.workspace, inc["id"], db_dir=self.harness_dir)
        self.assertIn("Safe retry confirmed", res)
        st = quota_watchdog.load(state_file)
        self.assertEqual(st["status"], "READY")

        # If project is ACCEPTED, retry must fail safety check
        with core.database(self.harness_dir) as db:
            db.execute("UPDATE auto_projects SET status='ACCEPTED' WHERE id=?", (pid,))

        inc2, _ = incidents.create_or_update_incident(
            self.workspace,
            project_id=pid,
            category="MISSING_MARKER",
            error_message="Omitted marker after accept",
        )
        res_fail = telegram_bridge.retry_incident(self.workspace, inc2["id"], db_dir=self.harness_dir)
        self.assertIn("safety check failed", res_fail.lower())


if __name__ == "__main__":
    unittest.main()
