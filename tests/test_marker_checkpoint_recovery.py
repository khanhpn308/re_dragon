"""Fault injection for checkpoint-backed missing-marker recovery.

No real CLI, provider, network, Android, or production SQLite is accessed.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from re_harness import autonomy, core, incidents, quota_watchdog as wd, telegram_bridge


class MarkerRecoveryTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.dbdir = self.root / ".re_harness_mvp"
        self.state = self.root / ".re_harness" / "quota-watchdog.json"
        self.prompt = self.root / "prompt.md"
        self.prompt.write_text("Checkpoint existing project", encoding="utf8")
        with core.database(self.dbdir) as db:
            autonomy.migrate(db)
            self.project_id = autonomy.start(db, "A safe test goal", "Review is mandatory")["project_id"]
        initial = wd.load(self.state)
        initial.update(
            project_id=self.project_id,
            conversation_id="test-pinned-session-12345678",
            status="READY",
        )
        wd.save(self.state, initial)

    def output(self, with_marker=False):
        response = 'RE_DRAGON_RUN_STATE {"state":"CONTINUE"}' if with_marker else "Completed partial work, missing marker"
        return {
            "code": 0,
            "data": {
                "status": "SUCCESS",
                "response": response,
                "conversation_id": "test-pinned-session-12345678",
            },
            "stderr": "",
        }

    def recorded_progress(self, *args, **kwargs):
        with core.database(self.dbdir) as db:
            autonomy.event(db, self.project_id, "test-slice", "SUBMITTED",
                           {"evidence_count": 1})
        return self.output()

    def test_checkpoint_progress_prevents_premature_human_interrupt(self):
        t1 = wd.once(self.root, self.state, self.prompt, clock=1000,
                     runner=self.recorded_progress, harness_state_dir=self.dbdir)
        self.assertEqual(t1["status"], "WAIT_RETRY")
        self.assertEqual(t1["missing_marker_progress_turns"], 1)
        self.assertEqual(t1["missing_marker_recoveries"], 0)
        self.assertIn("durable Harness progress", t1["last_reason"])
        self.assertEqual(t1["next_at"], 1060)

        t2 = wd.once(self.root, self.state, self.prompt, clock=1061,
                     runner=lambda *a, **kw: self.output(),
                     harness_state_dir=self.dbdir)
        self.assertEqual(t2["status"], "WAIT_RETRY")
        self.assertEqual(t2["missing_marker_recoveries"], 1)
        t3 = wd.once(self.root, self.state, self.prompt, clock=1122,
                     runner=lambda *a, **kw: self.output(with_marker=True),
                     harness_state_dir=self.dbdir)
        self.assertEqual(t3["status"], "CONTINUE")
        self.assertEqual(t3["missing_marker_progress_turns"], 0)

    def test_bounded_even_with_fake_repeated_progress(self):
        at = 1000
        for n in range(wd.MAX_PROGRESS_BACKED_MARKERLESS_TURNS):
            out = wd.once(self.root, self.state, self.prompt, clock=at,
                          runner=self.recorded_progress, harness_state_dir=self.dbdir)
            self.assertEqual(out["status"], "WAIT_RETRY")
            at = out["next_at"] + 1
        exhausted = wd.once(self.root, self.state, self.prompt, clock=at,
                            runner=self.recorded_progress, harness_state_dir=self.dbdir)
        self.assertEqual(exhausted["status"], "NEEDS_USER")
        self.assertEqual(exhausted["next_at"], 0)
        inc = incidents.list_incidents(self.root, project_id=self.project_id,
                                        category="MISSING_MARKER")
        self.assertEqual(len(inc), 1)

    def test_claimed_controller_decision_are_not_progress(self):
        def no_real_progress(*a, **kw):
            with core.database(self.dbdir) as db:
                autonomy.event(db, self.project_id, "t01", "CLAIMED", {"role": "reviewer"})
                autonomy.event(db, self.project_id, "t01", "CONTROLLER_DECISION", {"decision": "REVIEW"})
            return self.output()
        t1 = wd.once(self.root, self.state, self.prompt, clock=1000,
                     runner=no_real_progress, harness_state_dir=self.dbdir)
        self.assertEqual(t1["missing_marker_recoveries"], 1)
        self.assertEqual(t1.get("missing_marker_progress_turns", 0), 0)

    def test_pause_during_successful_turn_has_precedence(self):
        def runner(*args, **kwargs):
            wd.pause_operator(self.state, "Paused via Telegram by operator")
            return self.output(with_marker=True)
        final = wd.once(self.root, self.state, self.prompt, clock=1000,
                        runner=runner, harness_state_dir=self.dbdir)
        self.assertEqual(final["status"], "PAUSED")
        self.assertEqual(wd.load(self.state)["status"], "PAUSED")
        self.assertEqual(final["attempts"], 1)
        self.assertEqual(final["last_reason"], "Paused via Telegram by operator")
        calls = []
        wd.once(self.root, self.state, self.prompt, clock=1200,
                runner=lambda *a, **kw: calls.append(True),
                harness_state_dir=self.dbdir)
        self.assertEqual(calls, [])

    def test_pause_during_markerless_turn_has_precedence(self):
        def runner(*args, **kwargs):
            wd.pause_operator(self.state, "Paused via Telegram by operator")
            return self.output()
        final = wd.once(self.root, self.state, self.prompt, clock=1000,
                        runner=runner, harness_state_dir=self.dbdir)
        self.assertEqual(final["status"], "PAUSED")
        self.assertEqual(final["next_at"], 0)

    def test_remote_retry_refused_when_paused(self):
        inc, _ = incidents.create_or_update_incident(
            self.root, self.project_id, "MISSING_MARKER",
            "Missing marker on a test turn", severity="WARNING")
        wd.pause_operator(self.state)
        response = telegram_bridge.retry_incident(self.root, inc["id"], db_dir=self.dbdir)
        self.assertIn("PAUSED", response)
        self.assertEqual(wd.load(self.state)["status"], "PAUSED")
        self.assertEqual(incidents.get_incident(self.root, inc["id"])["recovery_attempts"], 0)


if __name__ == "__main__":
    unittest.main()
