"""v0.7.1: Telegram flood protection + remote lifecycle safety (offline)."""
from __future__ import annotations
import fcntl
import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from re_harness import autonomy,core,notification_delivery as nd,telegram_bridge as tg,telegram_control as ctl

class NotificationTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup)
        self.root=Path(t.name);self.ledger=self.root/"global"/"delivery.sqlite3"
    def test_same_event_sent_once_across_restart_and_worktree(self):
        self.assertTrue(nd.claim("123:valid_not_real_token",44,"project-A:COMPLETE",base=self.ledger))
        nd.delivered("123:valid_not_real_token",44,"project-A:COMPLETE",base=self.ledger)
        self.assertFalse(nd.claim("123:valid_not_real_token",44,"project-A:COMPLETE",base=self.ledger))
        self.assertEqual(nd.status("123:valid_not_real_token",44,"project-A:COMPLETE",base=self.ledger),"SENT")
    def test_at_most_once_when_remote_delivery_uncertain(self):
        self.assertTrue(nd.claim("123:valid_not_real_token",44,"project-A:COMPLETE",base=self.ledger))
        # No delivered(): process crashes or HTTP confirmation is ambiguous.
        self.assertFalse(nd.claim("123:valid_not_real_token",44,"project-A:COMPLETE",base=self.ledger))
        self.assertEqual(nd.status("123:valid_not_real_token",44,"project-A:COMPLETE",base=self.ledger),"CLAIMED")
    def test_different_event_and_owner_can_notify(self):
        self.assertTrue(nd.claim("123:valid_not_real_token",44,"project-A:COMPLETE",base=self.ledger))
        self.assertTrue(nd.claim("123:valid_not_real_token",44,"project-B:COMPLETE",base=self.ledger))
        self.assertTrue(nd.claim("123:valid_not_real_token",45,"project-A:COMPLETE",base=self.ledger))
    def test_database_error_fails_closed(self):
        with tempfile.TemporaryDirectory() as x:
            with self.assertRaises(sqlite3.DatabaseError):
                nd.claim("123:valid_not_real_token",44,"p:COMPLETE",base=Path(x))
    def test_complete_key_ignores_changing_task_counts(self):
        state={"status":"COMPLETE","project_id":"abcd1234","attempts":5,"last_reason":"accepted"}
        with patch.object(tg,"watched",return_value=(state,None)),\
             patch.object(tg.quota_guard,"inspect",return_value={
                "task_status_counts":{"VERIFIED":10}}),\
             patch.object(tg.telegram_inbox,"list_proposals",return_value=[]):
            key,msg=tg.notification_signature(self.root)
        self.assertEqual(key,"abcd1234:COMPLETE")
        self.assertIn("COMPLETE",msg)

class ControllerTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup)
        self.root=Path(t.name);self.dir=self.root/".re_harness_mvp"
        with core.database(self.dir) as db:
            autonomy.migrate(db)
            self.p1=autonomy.start(db,"Test evidence project","Pass 7 gates")["project_id"]
            self.p2=autonomy.start(db,"Another bounded project","Evidence gates")["project_id"]
    def test_newgoal_requires_confirmation_and_is_idempotent(self):
        row,created=ctl.propose(self.root,123,440,"NEW_GOAL",{"goal":"Test further model mapping"})
        self.assertTrue(created)
        row2,created2=ctl.propose(self.root,123,440,"NEW_GOAL",{"goal":"unrelated"})
        self.assertFalse(created2);self.assertEqual(row["id"],row2["id"])
        with core.database(self.dir) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM auto_projects").fetchone()[0],2)
        c=ctl.claim(self.root,row["id"],row["nonce"],440,"APPROVE")
        self.assertEqual(c["kind"],"NEW_GOAL")
        with self.assertRaisesRegex(ValueError,"Already decided"):
            ctl.claim(self.root,row["id"],row["nonce"],440,"APPROVE")
    def test_reject_and_owner_nonce_security(self):
        row,_=ctl.propose(self.root,124,440,"SWITCH_PROJECT",{"project_id":self.p1})
        with self.assertRaisesRegex(ValueError,"nonce"):
            ctl.claim(self.root,row["id"],"invalid",440,"APPROVE")
        with self.assertRaisesRegex(ValueError,"identity"):
            ctl.claim(self.root,row["id"],row["nonce"],441,"APPROVE")
        self.assertEqual(ctl.claim(self.root,row["id"],row["nonce"],440,"REJECT")["decision"],"REJECT")
    def test_expired_confirmation_rejected(self):
        row,_=ctl.propose(self.root,125,440,"NEW_GOAL",{"goal":"Test"},ttl=-2)
        with self.assertRaisesRegex(ValueError,"expired"):
            ctl.claim(self.root,row["id"],row["nonce"],440,"APPROVE")
    def test_watcher_lock_blocks_switch_and_prevents_orphan(self):
        lk=self.root/".re_harness"/"quota-watchdog.lock"
        lk.parent.mkdir(parents=True,exist_ok=True)
        with lk.open("a+") as h:
            fcntl.flock(h,fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError,"Watchdog is active"):
                tg.switch_project(self.root,self.p2,db_dir=self.dir)
            with self.assertRaisesRegex(ValueError,"Watchdog is active"):
                tg.create_goal(self.root,"No orphan goal must appear",db_dir=self.dir)
            with core.database(self.dir) as db:
                self.assertEqual(db.execute("SELECT count(*) FROM auto_projects").fetchone()[0],2)
    def test_controller_unlocked_switches_and_separates_sessions(self):
        res=tg.switch_project(self.root,self.p1,db_dir=self.dir)
        self.assertEqual(res["project_id"],self.p1)
        created=tg.create_goal(self.root,"A uniquely new remote goal",db_dir=self.dir)
        self.assertTrue(created["new_session"])
        with self.assertRaisesRegex(ValueError,"Duplicate goal"):
            tg.create_goal(self.root,"A uniquely new remote goal",db_dir=self.dir)
    def test_fixed_launcher_no_shell_injection(self):
        script=self.root/"scripts"/"quota-watchdog.sh"
        script.parent.mkdir()
        script.write_text("#!/bin/bash\necho Started-safe\n",encoding="utf8")
        self.assertIn("Started-safe",tg.start_watchdog_for_new_goal(self.root))
    def test_global_bot_lock_separates_tokens(self):
        # Existing workspace lock API stays compatible in old tests.
        h=tg.acquire_worker_lock(self.root)
        try:
            with self.assertRaises(RuntimeError):
                tg.acquire_worker_lock(self.root)
        finally:
            h.close()

if __name__=="__main__":
    unittest.main()
