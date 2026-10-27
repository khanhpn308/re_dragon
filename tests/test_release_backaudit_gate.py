"""Offline regression tests: V2 Go backaudit release gate.

Run against isolated temp SQLite. Never touches real RE Dragon workspace.
"""
from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from re_harness import autonomy, core, release_gate, scheduler


class BackauditGateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / ".re_harness").mkdir()
        self.db_dir = self.root / ".re_harness_mvp"
        with core.database(self.db_dir) as db:
            autonomy.migrate(db)
            self.pid = autonomy.start(db, "Isolated V2 goal", "End-to-end accepted")["project_id"]
            specs = []
            for key in (*release_gate.PREREQUISITES, "s6-android-go-e2e",
                        "t10-t11-migration-and-pitr", release_gate.FINAL_KEY):
                specs.append({
                    "key": key,
                    "title": f"Simulated {key}",
                    "kind": "TEST", "acceptance": "Isolated simulation",
                    "priority": 10,
                    "depends_on": (["s6-android-go-e2e", "t10-t11-migration-and-pitr"]
                                   if key == release_gate.FINAL_KEY else []),
                })
            autonomy.plan(db, self.pid, specs)
            with db:
                for key in release_gate.PREREQUISITES:
                    db.execute(
                        "UPDATE auto_tasks SET status='VERIFIED' WHERE project_id=? AND task_key=?",
                        (self.pid, key),
                    )
        self.state_path = self.root / ".re_harness" / "quota-watchdog.json"
        self.state_path.write_text(json.dumps({"project_id": self.pid, "status": "PAUSED"}))
        self.original = self.snapshot()

    def snapshot(self):
        with core.database(self.db_dir) as db:
            rows = db.execute(
                "SELECT task_key,status,dependencies FROM auto_tasks "
                "WHERE project_id=? ORDER BY task_key", (self.pid,),
            ).fetchall()
            return [(x["task_key"], x["status"], x["dependencies"]) for x in rows]

    def run_gate(self, *, apply=False):
        return release_gate.execute(self.root, self.pid, apply=apply, check_tmux=False)

    def test_read_only_dry_run_does_not_change_database(self):
        output = self.run_gate()
        self.assertEqual(output["result"], "PENDING_INSTALL")
        self.assertEqual(self.snapshot(), self.original)

    def test_install_gate_and_idempotent_second_call(self):
        output = self.run_gate(apply=True)
        self.assertEqual(output["result"], "INSTALLED")
        self.assertEqual(self.run_gate(apply=True)["result"], "ALREADY_INSTALLED")
        self.assertEqual(self.run_gate()["result"], "ALREADY_INSTALLED")
        with core.database(self.db_dir) as db:
            audit = db.execute(
                "SELECT * FROM auto_tasks WHERE project_id=? AND task_key=?",
                (self.pid, release_gate.AUDIT_KEY),
            ).fetchone()
            final = db.execute(
                "SELECT * FROM auto_tasks WHERE project_id=? AND task_key=?",
                (self.pid, release_gate.FINAL_KEY),
            ).fetchone()
            self.assertEqual(audit["status"], "PENDING")
            self.assertEqual(audit["kind"], "AUDIT")
            self.assertEqual(json.loads(audit["dependencies"]), list(release_gate.PREREQUISITES))
            self.assertIn(release_gate.GO_RULE_SHA, audit["acceptance"])
            self.assertIn(release_gate.AUDIT_KEY, json.loads(final["dependencies"]))
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM auto_tasks WHERE project_id=? AND task_key=?",
                (self.pid, release_gate.AUDIT_KEY),
            ).fetchone()[0], 1)
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM auto_events WHERE project_id=? "
                "AND event='GO_BACKAUDIT_GATE_INSTALLED'",
                (self.pid,),
            ).fetchone()[0], 1)
            self.assertIsNotNone(db.execute(
                "SELECT task_id FROM auto_resource_specs WHERE task_id=?", (audit["id"],),
            ).fetchone())
        self.assertEqual(json.loads(self.state_path.read_text())["status"], "PAUSED")
        for key in release_gate.PREREQUISITES:
            self.assertIn((key, "VERIFIED", "[]"), self.snapshot())

    def test_reject_unpaused_without_modification(self):
        self.state_path.write_text(json.dumps({"project_id": self.pid, "status": "READY"}))
        with self.assertRaisesRegex(ValueError, "PAUSED"):
            self.run_gate(apply=True)
        self.assertEqual(self.snapshot(), self.original)

    def test_reject_other_project(self):
        with self.assertRaisesRegex(ValueError, "PAUSED"):
            release_gate.execute(self.root, "wrong", apply=True, check_tmux=False)
        self.assertEqual(self.snapshot(), self.original)

    def test_reject_final_task_claimed_or_accepted(self):
        with core.database(self.db_dir) as db:
            with db:
                db.execute("UPDATE auto_tasks SET status='RUNNING' WHERE project_id=? "
                           "AND task_key=?", (self.pid, release_gate.FINAL_KEY))
        with self.assertRaisesRegex(ValueError, "not PENDING"):
            self.run_gate(apply=True)

    def test_reject_unverified_prerequisite(self):
        with core.database(self.db_dir) as db:
            with db:
                db.execute("UPDATE auto_tasks SET status='REWORK' "
                           "WHERE project_id=? AND task_key=?",
                           (self.pid, release_gate.PREREQUISITES[0]))
        with self.assertRaisesRegex(ValueError, "must be VERIFIED"):
            self.run_gate(apply=True)
        self.assertEqual(len(self.snapshot()), len(self.original))

    def test_rollback_on_resource_attach_failure(self):
        with patch("re_harness.release_gate.scheduler.attach",
                   side_effect=RuntimeError("Injected failure")):
            with self.assertRaisesRegex(RuntimeError, "Injected failure"):
                self.run_gate(apply=True)
        self.assertEqual(self.snapshot(), self.original)
        with core.database(self.db_dir) as db:
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM auto_events WHERE event='GO_BACKAUDIT_GATE_INSTALLED'"
            ).fetchone()[0], 0)

    def test_reject_conflicting_audit_does_not_silently_overwrite(self):
        self.run_gate(apply=True)
        with core.database(self.db_dir) as db:
            with db:
                db.execute(
                    "UPDATE auto_tasks SET acceptance='unrelated goal' "
                    "WHERE project_id=? AND task_key=?",
                    (self.pid, release_gate.AUDIT_KEY),
                )
        with self.assertRaisesRegex(ValueError, "incompatible"):
            self.run_gate(apply=True)


if __name__ == "__main__":
    unittest.main()
