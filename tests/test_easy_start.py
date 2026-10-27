"""ID-free start integration tests: real isolated SQLite, mocked Antigravity."""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from re_harness import autonomy, core, easy_start as start, quota_watchdog as wd


class OneCommandStartupTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.harness=self.root/".re_harness_mvp"
        self.watcher=self.root/".re_harness"/"quota-watchdog.json"
        self.prompt=self.root/"prompt.md"
        self.prompt.write_text("Resume bound project and emit marker", encoding="utf8")
        with core.database(self.harness) as db:
            autonomy.migrate(db)

    def state(self):
        return wd.load(self.watcher)

    def projects(self):
        with sqlite3.connect(self.harness/"state.sqlite3") as db:
            return db.execute("SELECT id,goal,status FROM auto_projects").fetchall()

    def output(self, state="CONTINUE", cid="new-conversation-11111111"):
        return {"code":0,"data":{"status":"SUCCESS","conversation_id":cid,
                 "response":"RE_DRAGON_RUN_STATE "+json.dumps(
                     {"state":state,"note":"Saved"})},"stderr":""}

    def test_first_start_creates_single_production_goal_with_no_ids(self):
        info=start.bootstrap(self.root)
        self.assertTrue(info["project_created"])
        self.assertEqual(info["conversation"],"new dedicated headless session")
        self.assertEqual(len(self.projects()),1)
        self.assertEqual(self.state()["project_id"],info["project_id"])
        self.assertTrue(self.state()["bootstrap_new_conversation"])
        self.assertIsNone(self.state()["conversation_id"])

    def test_repeated_starts_reuse_project_and_conversation(self):
        one=start.bootstrap(self.root)
        st=self.state()
        st["conversation_id"]="dedicated-session-12345678"
        st.pop("bootstrap_new_conversation")
        wd.save(self.watcher,st)
        two=start.bootstrap(self.root)
        self.assertEqual(two["project_id"],one["project_id"])
        self.assertEqual(two["conversation"],"pinned")
        self.assertFalse(two["project_created"])
        self.assertEqual(len(self.projects()),1)

    def test_two_accepted_pilots_not_reused_as_production(self):
        with core.database(self.harness) as db:
            for i in range(2):
                pid=autonomy.start(db,"PILOT: synthetic testing "+str(i),
                                  "Offline unit tests")["project_id"]
                db.execute("UPDATE auto_projects SET status='ACCEPTED' WHERE id=?",(pid,))
            db.commit()
        info=start.bootstrap(self.root)
        self.assertEqual(len(self.projects()),3)
        self.assertEqual(info["project_id"],
                         [p[0] for p in self.projects() if p[1].startswith(start.TITLE)][0])

    def test_fake_ids_cleared_only_when_both_exact_placeholders(self):
        wd.save(self.watcher,{"status":"NEEDS_USER","project_id":"PROJECT_ID",
                               "conversation_id":"CONVERSATION_ID",
                               "last_reason":"Pinned project_id not found",
                               "attempts":0,"quota_hits":0,"next_at":0})
        info=start.bootstrap(self.root)
        self.assertEqual(self.state()["status"],"READY")
        self.assertEqual(self.state()["project_id"],info["project_id"])
        self.assertIsNone(self.state()["conversation_id"])

    def test_real_needs_user_stop_cannot_be_bypassed_by_start(self):
        start.bootstrap(self.root)
        st=self.state()
        st.update(status="NEEDS_USER",last_reason="Authorization required")
        wd.save(self.watcher,st)
        with self.assertRaisesRegex(start.SetupError,"Resolve the blocker"):
            start.bootstrap(self.root)

    def test_conflicting_real_project_binding_is_not_overwritten(self):
        st=wd.load(self.watcher)
        st["project_id"]="real-other-1234"
        wd.save(self.watcher,st)
        with self.assertRaisesRegex(start.SetupError,"Pinned watchdog project_id"):
            start.bootstrap(self.root)

    def test_accepted_goal_is_not_duplicated_after_completion(self):
        first=start.bootstrap(self.root)
        with sqlite3.connect(self.harness/"state.sqlite3") as db:
            db.execute("UPDATE auto_projects SET status='ACCEPTED' WHERE id=?",
                       (first["project_id"],))
        with self.assertRaisesRegex(start.SetupError,"ACCEPTED"):
            start.bootstrap(self.root)
        self.assertEqual(len(self.projects()),1)

    def test_resume_prefers_pinned_active_project_over_old_accepted_goal(self):
        with core.database(self.harness) as db:
            old = autonomy.start(db, start.GOAL, start.ACCEPTANCE)["project_id"]
            db.execute("UPDATE auto_projects SET status='ACCEPTED' WHERE id=?", (old,))
            target = autonomy.start(
                db, "RS-UH-PROD-V1: Android client charter",
                "Complete eight verified gates"
            )["project_id"]
        state = wd.load(self.watcher)
        state.update(status="READY", project_id=target,
                     conversation_id="production-session-123456789")
        wd.save(self.watcher, state)
        info = start.bootstrap(self.root)
        self.assertEqual(info["project_id"], target)
        self.assertFalse(info["project_created"])
        self.assertEqual(self.state()["conversation_id"],
                         "production-session-123456789")
        self.assertEqual(len(self.projects()), 2)

    def test_pinned_missing_project_does_not_silently_fall_back(self):
        with core.database(self.harness) as db:
            autonomy.start(db, start.GOAL, start.ACCEPTANCE)
        state = wd.load(self.watcher)
        state["project_id"] = "missing-pinned-project"
        wd.save(self.watcher, state)
        with self.assertRaisesRegex(start.SetupError, "Pinned watchdog project_id"):
            start.bootstrap(self.root)

    def test_unpinned_start_selects_active_project_when_older_accepted_exists(self):
        with core.database(self.harness) as db:
            old = autonomy.start(db, start.GOAL, start.ACCEPTANCE)["project_id"]
            db.execute("UPDATE auto_projects SET status='ACCEPTED' WHERE id=?", (old,))
            active = autonomy.start(db, start.TITLE + " v1 active", "Verified")["project_id"]
        # No pinned project in state
        info = start.bootstrap(self.root)
        self.assertEqual(info["project_id"], active)
        self.assertFalse(info["project_created"])

    def test_first_headless_turn_pins_cli_returned_session(self):
        setup=start.bootstrap(self.root)
        seen=[]
        def runner(workspace,prompt,cid,**kwargs):
            seen.append((cid,prompt))
            return self.output()
        result=wd.once(self.root,self.watcher,self.prompt,runner=runner,
                       clock=1000,harness_state_dir=self.harness)
        self.assertEqual(result["status"],"CONTINUE")
        self.assertIsNone(seen[0][0])
        self.assertIn(setup["project_id"],seen[0][1])
        self.assertEqual(result["conversation_id"],"new-conversation-11111111")
        self.assertNotIn("bootstrap_new_conversation",result)
        result2=wd.once(self.root,self.watcher,self.prompt,runner=runner,
                        clock=1031,harness_state_dir=self.harness)
        self.assertEqual(result2["status"],"CONTINUE")
        self.assertEqual(seen[1][0],"new-conversation-11111111")

    def test_bootstrap_quota_pause_without_pretending_old_pilot(self):
        start.bootstrap(self.root)
        calls=[]
        def runner(*args,**kwargs):
            calls.append(args[2])
            return {"code":3,"data":{"status":"ERROR",
                    "error":"RESOURCE_EXHAUSTED Resets in 1m"},"stderr":""}
        result=wd.once(self.root,self.watcher,self.prompt,clock=1000,
                       runner=runner,harness_state_dir=self.harness)
        self.assertEqual(result["status"],"WAIT_QUOTA")
        self.assertEqual(result["next_at"],1120)
        self.assertTrue(result["bootstrap_new_conversation"])
        wd.once(self.root,self.watcher,self.prompt,clock=1119,
                runner=runner,harness_state_dir=self.harness)
        self.assertEqual(len(calls),1)

    def test_no_conversation_flag_for_new_unbound_cli_process(self):
        class FakeProcess:
            def __init__(self, argv, **kwargs):
                self.argv=argv
                self.returncode=0
            def communicate(self,timeout=None):
                return (json.dumps({"status":"SUCCESS","conversation_id":"new-12345678",
                                    "response":"done"}),"")
        with patch("re_harness.quota_watchdog.subprocess.Popen",
                   side_effect=lambda argv,**kw:FakeProcess(argv,**kw)) as mocked:
            result=wd.invoke(self.root,"hello",None)
        args=mocked.call_args.args[0]
        self.assertNotIn("--continue",args)
        self.assertNotIn("--conversation",args)
        self.assertEqual(result["data"]["conversation_id"],"new-12345678")


if __name__=="__main__":
    unittest.main()
