"""Quota watchdog integration: real SQLite checkpoints, fake CLI, no model calls."""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from re_harness import quota_guard as g, quota_watchdog as q


class WatchdogSafetyTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.watch_state=self.root/".re_harness"/"quota-watchdog.json"
        self.harness=self.root/".re_harness_mvp"
        self.harness.mkdir()
        self.prompt=self.root/"prompt.md"
        self.prompt.write_text("Resume current goal and emit RE_DRAGON_RUN_STATE",encoding="utf8")
        with sqlite3.connect(self.harness/"state.sqlite3") as db:
            db.executescript("""
              CREATE TABLE auto_projects (
                id TEXT PRIMARY KEY,goal TEXT,acceptance TEXT,status TEXT,updated_at TEXT
              );
              CREATE TABLE auto_tasks (
                project_id TEXT,task_key TEXT,status TEXT
              );
            """)
            db.execute("INSERT INTO auto_projects VALUES(?,?,?,?,?)",
                       ("return-12345678","ReturnSaiyan Unified Heroes","Verified all original and Global heroes","ACTIVE","2026-10-27"))
            db.execute("INSERT INTO auto_tasks VALUES(?,?,?)",
                       ("return-12345678","assets","PENDING"))
        q.save(self.watch_state,{**q.load(self.watch_state),
                                "conversation_id":"conversation-12345678"})

    def update_project(self,status,task_status=None):
        with sqlite3.connect(self.harness/"state.sqlite3") as db:
            db.execute("UPDATE auto_projects SET status=?",(status,))
            if task_status is not None:
                db.execute("UPDATE auto_tasks SET status=?",(task_status,))

    def result(self,state="CONTINUE",conv="conversation-12345678"):
        return {"code":0,"data":{"status":"SUCCESS","conversation_id":conv,
               "response":"RE_DRAGON_RUN_STATE "+
               json.dumps({"state":state,"note":"checkpoint"})},"stderr":""}

    def test_binds_active_project_and_pins_conversation(self):
        seen=[]
        def runner(workspace,prompt,conv,**kwargs):
            seen.append((prompt,conv))
            return self.result()
        res=q.once(self.root,self.watch_state,self.prompt,runner=runner,
                   clock=100,harness_state_dir=self.harness)
        self.assertEqual(res["status"],"CONTINUE")
        self.assertEqual(res["project_id"],"return-12345678")
        self.assertEqual(seen[0][1],"conversation-12345678")
        self.assertIn("return-12345678",seen[0][0])
        self.assertIn("do not create or switch projects",seen[0][0])

    def test_wrong_conversation_must_stop(self):
        r=q.once(self.root,self.watch_state,self.prompt,clock=100,
                 runner=lambda *a,**k:self.result(conv="intruder-12345678"),
                 harness_state_dir=self.harness)
        self.assertEqual(r["status"],"NEEDS_USER")
        self.assertIn("different conversation",r["last_reason"])
        q.once(self.root,self.watch_state,self.prompt,clock=100000,
               runner=lambda *a,**kw:self.fail("must not auto-resume"),
               harness_state_dir=self.harness)

    def test_completion_requires_verified_checkpoint(self):
        r=q.once(self.root,self.watch_state,self.prompt,clock=100,
                 runner=lambda *a,**k:self.result("COMPLETE"),
                 harness_state_dir=self.harness)
        self.assertEqual(r["status"],"NEEDS_USER")
        self.assertIn("without verified",r["last_reason"])

    def test_project_accepted_is_terminal_without_model_call(self):
        # A real watcher has already pinned this project before it finishes.
        pinned=q.load(self.watch_state)
        pinned["project_id"]="return-12345678"
        q.save(self.watch_state,pinned)
        self.update_project("ACCEPTED","VERIFIED")
        r=q.once(self.root,self.watch_state,self.prompt,clock=100,
                 runner=lambda *a,**k:self.fail("should not invoke agy"),
                 harness_state_dir=self.harness)
        self.assertEqual(r["status"],"COMPLETE")

    def test_project_blocked_stops_unattended_run(self):
        self.update_project("BLOCKED")
        r=q.once(self.root,self.watch_state,self.prompt,clock=100,
                 runner=lambda *a,**k:self.fail("should not run"),
                 harness_state_dir=self.harness)
        self.assertEqual(r["status"],"NEEDS_USER")

    def test_bad_project_count_aborts_instead_of_guessing(self):
        with sqlite3.connect(self.harness/"state.sqlite3") as db:
            db.execute("INSERT INTO auto_projects VALUES(?,?,?,?,?)",
                       ("other-87654321","Another project","Check another goal separately","ACTIVE","2026-10-27"))
        res=q.once(self.root,self.watch_state,self.prompt,clock=100,
                   runner=lambda *a,**k:self.fail("ambiguous project"),
                   harness_state_dir=self.harness)
        self.assertEqual(res["status"],"NEEDS_USER")
        self.assertIn("Exactly one active",res["last_reason"])

    def test_pinned_project_ignores_other_active_projects(self):
        with sqlite3.connect(self.harness/"state.sqlite3") as db:
            db.execute("INSERT INTO auto_projects VALUES(?,?,?,?,?)",
                       ("other-87654321","Another project","Check another goal separately","ACTIVE","2026-10-27"))
        state=q.load(self.watch_state)
        state["project_id"]="return-12345678"
        q.save(self.watch_state,state)
        res=q.once(self.root,self.watch_state,self.prompt,clock=100,
                   runner=lambda *a,**k:self.result(),
                   harness_state_dir=self.harness)
        self.assertEqual(res["status"],"CONTINUE")

    def test_quota_wait_then_resume_exact_session(self):
        calls=[]
        queue=[
            {"code":3,"data":{"status":"ERROR","error":"RESOURCE_EXHAUSTED Resets in 2m"},
             "stderr":""},
            self.result("YIELD")]
        def runner(w,p,c,**kw):
            calls.append(c)
            return queue.pop(0)
        a=q.once(self.root,self.watch_state,self.prompt,runner=runner,
                 clock=1000,harness_state_dir=self.harness)
        self.assertEqual(a["status"],"WAIT_QUOTA")
        self.assertEqual(a["next_at"],1180)
        q.once(self.root,self.watch_state,self.prompt,runner=runner,
               clock=1179,harness_state_dir=self.harness)
        self.assertEqual(len(calls),1)
        b=q.once(self.root,self.watch_state,self.prompt,runner=runner,
                 clock=1181,harness_state_dir=self.harness)
        self.assertEqual(b["status"],"YIELD")
        self.assertEqual(calls,["conversation-12345678"]*2)

    def test_unknown_reset_poll_is_15_minutes(self):
        x=q.evaluate({"code":3,"data":{"status":"ERROR",
            "error":"RESOURCE_EXHAUSTED"},"stderr":""},
            q.load(self.watch_state),1000)
        self.assertEqual(x["next_at"],1900)

    def test_network_retry_budget_exhausted(self):
        prior=q.load(self.watch_state)
        for i in range(1,5):
            prior=q.evaluate({"code":1,"data":{"status":"ERROR",
                "error":"ECONNRESET: connection reset by peer"},"stderr":""},prior,1000+i*60)
            self.assertEqual(prior["status"],"WAIT_RETRY" if i<=3 else "ERROR")
        self.assertEqual(prior["transient_failures"],4)
        self.assertEqual(prior["next_at"],0)

    def test_permission_soft_denial_never_retries(self):
        r=q.evaluate({"code":0,"data":{"status":"SUCCESS",
             "response":'RE_DRAGON_RUN_STATE {"state":"CONTINUE"}'},
             "stderr":"tool soft-denied: needs approval"},q.load(self.watch_state),1000)
        self.assertEqual(r["status"],"NEEDS_USER")

    def test_failure_does_not_switch_conversation(self):
        prior=q.load(self.watch_state)
        outcome={"code":3,"data":{"status":"ERROR",
                "conversation_id":"different-9999999",
                "error":"RESOURCE_EXHAUSTED"},"stderr":""}
        r=q.evaluate(outcome,prior,1000)
        self.assertEqual(r["status"],"NEEDS_USER")
        self.assertEqual(r["conversation_id"],"conversation-12345678")

    def test_guard_missing_checkpoint(self):
        with self.assertRaisesRegex(g.ProjectGateError,"missing"):
            g.inspect(self.root/"absent","return-12345678")

    def test_complete_requires_verified_not_just_accepted(self):
        self.update_project("ACCEPTED","PENDING")
        info=g.inspect(self.harness,"return-12345678")
        self.assertFalse(g.actual_completion(info))


if __name__=="__main__":
    unittest.main()
