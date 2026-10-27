"""Offline tests for S6 client-preflight DAG gate, isolated from V1/live DB."""
from __future__ import annotations
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from re_harness import autonomy, core, s6_preflight_gate as gate


class S6ClientGateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / ".re_harness").mkdir()
        self.dbpath = self.root / ".re_harness_mvp"
        self.pids = (
            "g-client-server-contract",
            "s4-gameplay-authoritative",
            "s5-postgres-persistence",
            "v2-go-v1-1-backaudit",
        )
        with core.database(self.dbpath) as db:
            autonomy.migrate(db)
            self.pid = autonomy.start(db, "V2 simulated Go gameplay",
                                     "Independent E2E required")["project_id"]
            items = [
                {"key":key,"title":key,"kind":"TEST","priority":10,
                 "acceptance":"Offline test", "depends_on":[]}
                for key in self.pids
            ] + [
                {"key":gate.S6_KEY,"title":"Android E2E","kind":"TEST",
                 "priority":60,"acceptance":"E2E on private Go server",
                 "depends_on":list(self.pids[:3])},
                {"key":gate.FINAL_KEY,"title":"Final release","kind":"AUDIT",
                 "priority":5,"acceptance":"GO only after independent E2E",
                 "depends_on":[gate.S6_KEY,self.pids[3]]},
            ]
            autonomy.plan(db,self.pid,items)
            with db:
                for key in self.pids:
                    db.execute(
                        "UPDATE auto_tasks SET status='VERIFIED' "
                        "WHERE project_id=? AND task_key=?",(self.pid,key))
        self.state=self.root / ".re_harness" / "quota-watchdog.json"
        self.state.write_text(json.dumps(
            {"status":"PAUSED","project_id":self.pid}
        ))
        self.before=self.snapshot()

    def snapshot(self):
        with core.database(self.dbpath) as db:
            return [(r["task_key"],r["status"],r["dependencies"]) for r in
                    db.execute("SELECT task_key,status,dependencies FROM auto_tasks "
                               "WHERE project_id=? ORDER BY task_key",(self.pid,))]
    def call(self,apply=False):
        return gate.execute(self.root,self.pid,apply=apply,check_tmux=False)

    def test_check_is_strictly_read_only(self):
        result=self.call()
        self.assertEqual(result["result"],"PENDING_INSTALL")
        self.assertEqual(self.before,self.snapshot())
        self.assertIn(gate.PREFLIGHT_KEY,result["s6_dependencies"])
        self.assertIn(gate.PREFLIGHT_KEY,result["final_dependencies"])

    def test_atomic_install_and_idempotence(self):
        self.assertEqual(self.call(apply=True)["result"],"INSTALLED")
        self.assertEqual(self.call(apply=True)["result"],"ALREADY_INSTALLED")
        with core.database(self.dbpath) as db:
            audit=db.execute("SELECT * FROM auto_tasks WHERE project_id=? AND task_key=?",
                             (self.pid,gate.PREFLIGHT_KEY)).fetchone()
            s6=db.execute("SELECT * FROM auto_tasks WHERE project_id=? AND task_key=?",
                          (self.pid,gate.S6_KEY)).fetchone()
            final=db.execute("SELECT * FROM auto_tasks WHERE project_id=? AND task_key=?",
                             (self.pid,gate.FINAL_KEY)).fetchone()
            self.assertEqual(audit["status"],"PENDING")
            self.assertEqual(audit["kind"],"AUDIT")
            self.assertEqual(json.loads(audit["dependencies"]),list(self.pids[:3]))
            self.assertIn(gate.PREFLIGHT_KEY,json.loads(s6["dependencies"]))
            self.assertIn(gate.PREFLIGHT_KEY,json.loads(final["dependencies"]))
            self.assertEqual(s6["status"],"PENDING")
            self.assertEqual(final["status"],"PENDING")
            self.assertIsNotNone(db.execute(
                "SELECT task_id FROM auto_resource_specs WHERE task_id=?",
                (audit["id"],)).fetchone())
            self.assertEqual(db.execute(
                "SELECT count(*) FROM auto_events WHERE project_id=? "
                "AND event='S6_PREFLIGHT_GATE_INSTALLED'",(self.pid,)).fetchone()[0],1)
        self.assertEqual(json.loads(self.state.read_text())["status"],"PAUSED")

    def test_reject_non_paused(self):
        self.state.write_text(json.dumps({"status":"READY","project_id":self.pid}))
        with self.assertRaisesRegex(ValueError,"PAUSED"):
            self.call(apply=True)
        self.assertEqual(self.before,self.snapshot())

    def test_reject_wrong_project(self):
        with self.assertRaisesRegex(ValueError,"PAUSED"):
            gate.execute(self.root,"unrelated",apply=True,check_tmux=False)
        self.assertEqual(self.before,self.snapshot())

    def test_reject_s6_claimed(self):
        with core.database(self.dbpath) as db:
            with db:
                db.execute("UPDATE auto_tasks SET status='RUNNING',owner='fake' "
                           "WHERE project_id=? AND task_key=?", (self.pid,gate.S6_KEY))
        after=self.snapshot()
        with self.assertRaisesRegex(ValueError,"PENDING"):
            self.call(apply=True)
        self.assertEqual(after,self.snapshot())

    def test_reject_prior_s6_partial_artifact(self):
        with core.database(self.dbpath) as db:
            with db:
                db.execute("UPDATE auto_tasks SET artifacts_json='[\"state.json\"]' "
                           "WHERE project_id=? AND task_key=?",(self.pid,gate.S6_KEY))
        after=self.snapshot()
        with self.assertRaisesRegex(ValueError,"prior evidence"):
            self.call(apply=True)
        self.assertEqual(after,self.snapshot())

    def test_rollback_on_resource_attach_failure(self):
        with patch("re_harness.s6_preflight_gate.scheduler.attach",
                   side_effect=RuntimeError("injected fault")):
            with self.assertRaisesRegex(RuntimeError,"injected fault"):
                self.call(apply=True)
        self.assertEqual(self.before,self.snapshot())
        with core.database(self.dbpath) as db:
            self.assertEqual(db.execute(
                "SELECT count(*) FROM auto_events WHERE project_id=? "
                "AND event='S6_PREFLIGHT_GATE_INSTALLED'",
                (self.pid,)).fetchone()[0],0)

    def test_reject_incompatible_preexisting_gate(self):
        self.call(apply=True)
        with core.database(self.dbpath) as db:
            with db:
                db.execute("UPDATE auto_tasks SET acceptance='untrusted' "
                           "WHERE project_id=? AND task_key=?",(self.pid,gate.PREFLIGHT_KEY))
        with self.assertRaisesRegex(ValueError,"differs"):
            self.call(apply=True)

    def test_reject_missing_required_dependency(self):
        with core.database(self.dbpath) as db:
            with db:
                db.execute("UPDATE auto_tasks SET dependencies='[]' "
                           "WHERE project_id=? AND task_key=?",(self.pid,gate.S6_KEY))
        with self.assertRaisesRegex(ValueError,"prerequisites differ"):
            self.call(apply=True)

    def test_reject_live_agent_even_if_paused(self):
        with patch("re_harness.s6_preflight_gate.runtime_state.snapshot",
                   return_value={"pid":999,"state":"AGENT_RUNNING"}):
            with self.assertRaisesRegex(ValueError,"Agent process still active"):
                self.call(apply=True)


if __name__=="__main__":
    unittest.main()
