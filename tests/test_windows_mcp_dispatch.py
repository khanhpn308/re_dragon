"""MCP dispatch tests with synthetic Win32 observations; no real GUI calls."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from re_harness import autonomy, core, mcp, scheduler


class LeasedWindowsWorkerMCPTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name) / "state"
        with core.database(self.state) as db:
            autonomy.migrate(db)
            self.pid = autonomy.start(
                db, "Survey authorized Windows client",
                "Real menu interactions with independently reviewed evidence",
            )["project_id"]
            autonomy.plan(db, self.pid, [
                {"key": "survey-win", "title": "Observe one game menu",
                 "acceptance": "Before/after screenshot + user action + log",
                 "kind": "TEST", "depends_on": []}
            ])
            with patch("re_harness.scheduler.read_host",
                       return_value=scheduler.Host(8, 16384, 0.0)):
                self.claim = autonomy.tick(db, self.pid, "android-agent",
                                           "session-one", role="executor")
        self.assertEqual(self.claim["decision"], "EXECUTE")
        self.args = {
            "project_id": self.pid, "task_key": "survey-win",
            "agent_id": "android-agent", "claim_token": self.claim["claim_token"],
            "action": "probe",
        }

    def test_claimed_task_dispatch_returns_observed_not_verified(self):
        observed = {
            "schema": "re-dragon.windows-worker.v1", "status": "OBSERVED",
            "pid": 9099, "action": "probe",
            "evidence_status": "AGENT_OBSERVED", "acceptance_status": "NOT_VERIFIED",
        }
        with patch("re_harness.mcp.windows_worker_dispatch.run_once",
                   return_value=observed) as worker:
            outcome = mcp.call_tool("harness_windows_survey", self.args, self.state)
        worker.assert_called_once()
        self.assertEqual(outcome["status"], "OBSERVED")
        with core.database(self.state) as db:
            self.assertEqual(autonomy._task(db, self.pid, "survey-win")["status"],
                             "RUNNING")
            events = [r[0] for r in db.execute(
                "SELECT event FROM auto_events WHERE project_id=?", (self.pid,))]
            self.assertIn("WINDOWS_SURVEY_STARTED", events)
            self.assertIn("WINDOWS_SURVEY_OBSERVED", events)
            self.assertLess(events.index("WINDOWS_SURVEY_STARTED"),
                            events.index("WINDOWS_SURVEY_OBSERVED"))

    def test_blocked_click_marks_whether_input_was_dispatched(self):
        blocked = {
            "status": "BLOCKED", "action": "click",
            "error": "FOREGROUND_BUSY: input NOT dispatched",
            "input_dispatched": False, "foreground_pid": 5678,
        }
        params = dict(self.args, action="click", x=10, y=20)
        with patch("re_harness.mcp.windows_worker_dispatch.run_once",
                   return_value=blocked):
            output = mcp.call_tool("harness_windows_survey", params, self.state)
        self.assertEqual(output["status"], "BLOCKED")
        with core.database(self.state) as db:
            row = db.execute(
                "SELECT details FROM auto_events WHERE project_id=? "
                "AND task_key=? AND event='WINDOWS_SURVEY_BLOCKED' "
                "ORDER BY id DESC LIMIT 1", (self.pid, "survey-win")
            ).fetchone()
            import json
            details = json.loads(row[0])
            self.assertIs(details["input_dispatched"], False)
            self.assertEqual(details["foreground_pid"], 5678)

    def test_stolen_lease_prevents_windows_action(self):
        invalid = dict(self.args, claim_token="bad")
        with patch("re_harness.mcp.windows_worker_dispatch.run_once") as worker:
            with self.assertRaises(ValueError):
                mcp.call_tool("harness_windows_survey", invalid, self.state)
            worker.assert_not_called()

    def test_project_final_review_prevents_new_windows_actions(self):
        with core.database(self.state) as db:
            with db:
                db.execute("UPDATE auto_projects SET status='READY_FOR_FINAL_REVIEW'"
                           " WHERE id=?", (self.pid,))
        with patch("re_harness.mcp.windows_worker_dispatch.run_once") as worker:
            with self.assertRaisesRegex(ValueError, "ACTIVE"):
                mcp.call_tool("harness_windows_survey", self.args, self.state)
            worker.assert_not_called()


if __name__ == "__main__":
    unittest.main()
