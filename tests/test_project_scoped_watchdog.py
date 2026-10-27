"""Regression: a newly pinned PLANNING goal must not inherit an ACCEPTED predecessor."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from re_harness import autonomy, core, quota_watchdog as q, quota_guard


class ProjectScopedWatchdogTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.db_path=self.root/".re_harness_mvp"
        self.state=self.root/".re_harness"/"quota-watchdog.json"
        self.prompt=self.root/"watchdog.md"
        self.prompt.write_text(
            "Only use the project pinned by the supervisor. No hardcoded titles.",
            encoding="utf8")
        with core.database(self.db_path) as db:
            autonomy.migrate(db)
            old=autonomy.start(db,"OLD: ReturnSaiyan accepted edition",
                               "Old acceptance is unrelated")
            self.old=old["project_id"]
            autonomy.plan(db,self.old,[{
                "key":"old-finished","title":"Prior project result",
                "acceptance":"Independent review completed",
                "kind":"DOCUMENT","resource_class":"LIGHT",
                "targets":[],"depends_on":[],
            }])
            db.execute("UPDATE auto_tasks SET status='VERIFIED' WHERE project_id=?",
                       (self.old,))
            db.execute("UPDATE auto_projects SET status='ACCEPTED' WHERE id=?",
                       (self.old,))
            db.commit()
            new=autonomy.start(db,"TEST: Telegram lifecycle pilot, different goal",
                               "Create a bounded DAG in the NEW project only")
            self.new=new["project_id"]
        state=q.load(self.state)
        state.update(project_id=self.new,conversation_id=None,
                     bootstrap_new_conversation=True)
        q.save(self.state,state)

    @staticmethod
    def response(kind="CONTINUE"):
        return {"code":0,"data":{
            "status":"SUCCESS","conversation_id":"new-session-123456789",
            "response":"RE_DRAGON_RUN_STATE "+json.dumps({
                "state":kind,"note":"Turn saved"})},"stderr":""}

    def test_injects_new_charter_and_initial_plan_instruction(self):
        seen=[]
        def fake_runner(workspace,prompt,conv,**kwargs):
            seen.append((prompt,conv))
            return self.response()
        result=q.once(self.root,self.state,self.prompt,clock=1000,
                      runner=fake_runner,harness_state_dir=self.db_path)
        self.assertEqual(result["status"],"CONTINUE")
        self.assertEqual(result["project_id"],self.new)
        self.assertEqual(seen[0][1],None)
        prompt=seen[0][0]
        self.assertIn(self.new,prompt)
        self.assertIn("TEST: Telegram lifecycle pilot",prompt)
        self.assertIn("Create a bounded DAG in the NEW project only",prompt)
        self.assertIn("MANDATORY FIRST ACTION FOR PLANNING",prompt)
        self.assertIn("harness_auto_plan",prompt)
        self.assertNotIn("OLD: ReturnSaiyan",prompt)
        self.assertNotIn(self.old,prompt)
        self.assertEqual(result["planning_no_progress_turns"],1)
        self.assertEqual(quota_guard.inspect(self.db_path,self.new)["project_status"],
                         "PLANNING")

    def test_old_accepted_does_not_mark_new_project_complete(self):
        result=q.once(self.root,self.state,self.prompt,clock=1000,
                      runner=lambda *a,**k:self.response("COMPLETE"),
                      harness_state_dir=self.db_path)
        self.assertEqual(result["status"],"NEEDS_USER")
        self.assertIn("without verified Harness acceptance",result["last_reason"])
        self.assertEqual(quota_guard.inspect(self.db_path,self.old)["project_status"],
                         "ACCEPTED")
        self.assertEqual(quota_guard.inspect(self.db_path,self.new)["project_status"],
                         "PLANNING")

    def test_successful_plan_is_persisted_in_new_project_not_old(self):
        def planning_runner(workspace,prompt,conv,**kwargs):
            with core.database(self.db_path) as db:
                autonomy.plan(db,self.new,[{
                    "key":"pilot-protocol-check",
                    "title":"Verify project-bound planning loop",
                    "acceptance":"Task exists and review gate remains open",
                    "kind":"DOCUMENT","resource_class":"LIGHT",
                    "targets":[],"depends_on":[],
                }])
            return self.response()
        result=q.once(self.root,self.state,self.prompt,clock=1000,
                      runner=planning_runner,harness_state_dir=self.db_path)
        self.assertEqual(result["status"],"CONTINUE")
        self.assertEqual(result.get("planning_no_progress_turns"),0)
        self.assertEqual(quota_guard.inspect(self.db_path,self.new)["project_status"],
                         "ACTIVE")
        with core.database(self.db_path) as db:
            self.assertEqual([r["task_key"] for r in autonomy.tasks(db,self.new)],
                             ["pilot-protocol-check"])
            self.assertEqual([r["task_key"] for r in autonomy.tasks(db,self.old)],
                             ["old-finished"])

    def test_three_successful_unplanned_turns_require_user_instead_of_loop(self):
        for idx,now in enumerate((1000,1040,1080),start=1):
            result=q.once(self.root,self.state,self.prompt,clock=now,
                          runner=lambda *a,**k:self.response(),
                          harness_state_dir=self.db_path)
            self.assertEqual(result["planning_no_progress_turns"],idx)
        self.assertEqual(result["status"],"NEEDS_USER")
        self.assertIn("0 SQLite tasks after 3",result["last_reason"])
        q.once(self.root,self.state,self.prompt,clock=2000,
               runner=lambda *a,**k:self.fail("must not call Agent after stop"),
               harness_state_dir=self.db_path)

    def test_wrong_explicit_project_id_refused(self):
        s=q.load(self.state)
        s["project_id"]="does-not-exist"
        q.save(self.state,s)
        result=q.once(self.root,self.state,self.prompt,clock=1000,
                      runner=lambda *a,**k:self.fail("must not run"),
                      harness_state_dir=self.db_path)
        self.assertEqual(result["status"],"NEEDS_USER")
        self.assertIn("Pinned project_id not found",result["last_reason"])

    def test_template_is_generic(self):
        doc=(Path(__file__).resolve().parent.parent/
             "docs"/"QUOTA_WATCHDOG_TURN.md").read_text(encoding="utf8")
        self.assertNotIn("returnsaiyan",doc.lower())
        self.assertIn("harness_auto_plan",doc)
        self.assertIn("PLANNING",doc)


if __name__=="__main__":
    unittest.main()
