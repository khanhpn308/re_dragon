"""Offline transition gates: blocked source never bypassed by unaudited requests."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from re_harness import autonomy,core,scheduler

class BlockedReworkTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.db=core.database(Path(self.tmp.name))
        self.addCleanup(self.db.close)
        self.host=patch("re_harness.scheduler.read_host",
            return_value=scheduler.Host(8,16384,0.0))
        self.host.start()
        self.addCleanup(self.host.stop)
        autonomy.migrate(self.db)
        self.pid=autonomy.start(self.db,"E2E source repair",
                             "Independent evidence required")["project_id"]
        autonomy.plan(self.db,self.pid,[
          {"key":"preflight","title":"Earlier accepted gate","kind":"AUDIT",
           "acceptance":"Real evidence","depends_on":[]},
          {"key":"p3b","title":"Onboard hero","kind":"IMPLEMENT",
           "acceptance":"Physical summon and team","depends_on":["preflight"]},
        ])
        with self.db:
            self.db.execute("UPDATE auto_tasks SET status='VERIFIED' WHERE project_id=? AND task_key='preflight'",(self.pid,))
            self.db.execute("UPDATE auto_tasks SET status='BLOCKED',tries=3 WHERE project_id=? AND task_key='p3b'",(self.pid,))
            self.db.execute("UPDATE auto_projects SET status='BLOCKED' WHERE id=?",(self.pid,))

    def test_prepare_does_not_unblock(self):
        r=autonomy.prepare_blocked_rework_audit(
            self.db,self.pid,"p3b","Implement source-grounded gacha wire",
            ["docs/production/P3B_HERO_ONBOARDING_PREFLIGHT_BLOCKED_REPORT.md"])
        self.assertEqual(r["source_status"],"BLOCKED")
        self.assertEqual(autonomy._task(self.db,self.pid,"p3b")["status"],"BLOCKED")
        self.assertEqual(autonomy.project(self.db,self.pid)["status"],"ACTIVE")
        with self.assertRaisesRegex(ValueError,"VERIFIED"):
            autonomy.reopen_blocked_after_audit(self.db,self.pid,"p3b",r["audit_task"],"pretend fixed")
        self.assertEqual(autonomy._task(self.db,self.pid,"preflight")["status"],"VERIFIED")

    def test_verified_review_required_and_preserved(self):
        r=autonomy.prepare_blocked_rework_audit(
            self.db,self.pid,"p3b","Offline contract tests",
            ["docs/production/P3B_HERO_ONBOARDING_PREFLIGHT_BLOCKED_REPORT.md"])
        with self.db:
            self.db.execute(
              "UPDATE auto_tasks SET status='VERIFIED',producer='agent',"
              "reviewer='reviewer',producer_session='session-a',"
              "reviewer_session='session-b',review_note='Checked primary evidence',"
              "evidence_json=? WHERE project_id=? AND task_key=?",
              (json.dumps(["client-logcat","source-code"]),self.pid,r["audit_task"]))
        out=autonomy.reopen_blocked_after_audit(
            self.db,self.pid,"p3b",r["audit_task"],"Backend fix independently audited")
        self.assertEqual(out["status"],"REWORK")
        self.assertEqual(autonomy._task(self.db,self.pid,"p3b")["tries"],0)
        self.assertEqual(autonomy._task(self.db,self.pid,"preflight")["status"],"VERIFIED")
        count=self.db.execute(
            "SELECT count(*) FROM auto_events WHERE project_id=? AND event='BLOCKED_REOPENED_FOR_REWORK'",
            (self.pid,)).fetchone()[0]
        self.assertEqual(count,1)
