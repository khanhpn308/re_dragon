"""Live agent telemetry + authorized Telegram command ingress tests (fully offline)."""
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from re_harness import (
    autonomy,core,quota_watchdog as qw,runtime_state,telegram_bridge as tg,
    telegram_inbox
)


class RuntimeStatusTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.state=self.root/".re_harness"/"quota-watchdog.json"
        qw.save(self.state,qw.load(self.state))
        docs=self.root/"docs"
        docs.mkdir()
        (docs/"QUOTA_WATCHDOG_TURN.md").write_text("test prompt",encoding="utf8")

    def test_live_pid_and_heartbeat_overlay(self):
        path=self.root/".re_harness"/"agent-runtime.json"
        with runtime_state.AgentHeartbeat(path,os.getpid(),interval=.01):
            snap=runtime_state.snapshot(path)
            self.assertIsNotNone(snap)
            self.assertEqual(snap["state"],"AGENT_RUNNING")
            self.assertEqual(snap["pid"],os.getpid())
            self.assertFalse(snap["heartbeat_is_progress_proof"])
            self.assertGreaterEqual(snap["elapsed_seconds"],0)
        self.assertIsNone(runtime_state.snapshot(path))

    def test_pid_reuse_and_stale_record_not_reported_running(self):
        path=self.root/".re_harness"/"agent-runtime.json"
        runtime_state._atomic(path,{"state":"AGENT_RUNNING",
             "pid":os.getpid(),"proc_start":"invalid-old-process",
             "started_at":1,"heartbeat_at":2})
        self.assertIsNone(runtime_state.snapshot(path))

    def test_status_is_live_without_changing_persisted_watchdog_state(self):
        path=self.root/".re_harness"/"agent-runtime.json"
        with runtime_state.AgentHeartbeat(path,os.getpid(),interval=.02):
            with patch("sys.argv",["watchdog","status","--workspace",str(self.root)]):
                from io import StringIO
                import contextlib,json
                output=StringIO()
                with contextlib.redirect_stdout(output):
                    qw.main()
                status=json.loads(output.getvalue())
                self.assertEqual(status["status"],"AGENT_RUNNING")
                self.assertEqual(status["checkpoint_status"],"READY")
                self.assertIn("elapsed_seconds",status["agent"])
                self.assertEqual(qw.load(self.state)["status"],"READY")


class TelegramInboxTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory()
        self.addCleanup(t.cleanup)
        self.root=Path(t.name)
        self.state=self.root/".re_harness"/"quota-watchdog.json"
        self.dbdir=self.root/".re_harness_mvp"
        self.prompt=self.root/"prompt.md"
        self.prompt.write_text("Resume approved goal",encoding="utf8")
        with core.database(self.dbdir) as db:
            autonomy.migrate(db)
            self.pid=autonomy.start(db,"ReturnSaiyan test goal","Verify evidence")["project_id"]
        s=qw.load(self.state)
        s.update(project_id=self.pid,conversation_id="valid-session-12345678")
        qw.save(self.state,s)

    def test_private_owner_only(self):
        self.assertTrue(tg.allowed(123,123,"private",123))
        self.assertFalse(tg.allowed(456,123,"private",123))
        self.assertFalse(tg.allowed(123,123,"group",123))
        self.assertFalse(tg.allowed(123,456,"private",123))

    def test_enqueue_deduplicate_and_bounded_input(self):
        rid,new=tg.submit_task(self.root,42,123,123,"Map hero animation")
        self.assertTrue(new)
        rid2,new2=tg.submit_task(self.root,42,123,123,"Map hero animation")
        self.assertEqual(rid,rid2)
        self.assertFalse(new2)
        self.assertEqual(len(telegram_inbox.queued(self.root,self.pid)),1)
        with self.assertRaises(ValueError):
            tg.submit_task(self.root,43,123,123,"x"*901)

    def test_bounded_agent_turn_forwards_inbox_only_after_success(self):
        rid,_=tg.submit_task(self.root,31,123,123,"Map Global actor 1065")
        seen=[]
        def runner(w,p,c,**kwargs):
            seen.append(p)
            return {"code":0,"data":{"status":"SUCCESS","conversation_id":c,
                     "response":'RE_DRAGON_RUN_STATE {"state":"CONTINUE","note":"work ongoing"}'},
                    "stderr":""}
        output=qw.once(self.root,self.state,self.prompt,runner=runner,
                        clock=100,harness_state_dir=self.dbdir)
        self.assertEqual(output["status"],"CONTINUE")
        self.assertIn("Map Global actor 1065",seen[0])
        self.assertIn('"id": '+str(rid),seen[0])
        self.assertEqual(telegram_inbox.summary(self.root,self.pid),{"FORWARDED":1})

    def test_quota_exhaustion_keeps_inbox_queued(self):
        tg.submit_task(self.root,31,123,123,"Check Global hero id")
        def quota(*a,**k):
            return {"code":3,"data":{"status":"ERROR","error":"RESOURCE_EXHAUSTED"},
                    "stderr":""}
        result=qw.once(self.root,self.state,self.prompt,runner=quota,
                        clock=100,harness_state_dir=self.dbdir)
        self.assertEqual(result["status"],"WAIT_QUOTA")
        self.assertEqual(telegram_inbox.summary(self.root,self.pid),{"QUEUED":1})

    def test_project_closed_rejects_remote_task(self):
        with sqlite3.connect(self.dbdir/"state.sqlite3") as db:
            db.execute("UPDATE auto_projects SET status='ACCEPTED' WHERE id=?",
                       (self.pid,))
        with self.assertRaisesRegex(ValueError,"not active"):
            tg.submit_task(self.root,33,123,123,"change acceptance")

    def test_memory_resource_wait_notifies_once_without_spam(self):
        state=qw.load(self.state)
        state.update(status="WAIT",last_reason="binary-hero-mapping waiting for "
                     "sufficient memory headroom (available: 2205 MB)")
        qw.save(self.state,state)
        key,message=tg.notification_signature(self.root)
        self.assertIn("WAIT_RESOURCE",key)
        self.assertIn("memory headroom",message)

    def test_significant_notifications_exclude_raw_user_content(self):
        tg.submit_task(self.root,44,123,123,"secret not for notification")
        s=qw.load(self.state)
        s.update(status="WAIT_QUOTA",quota_hits=1,last_reason="provider limit")
        qw.save(self.state,s)
        key,msg=tg.notification_signature(self.root)
        self.assertIn("WAIT_QUOTA",key)
        self.assertNotIn("secret",msg)
        self.assertIn("RE Dragon",msg)


if __name__=="__main__":
    unittest.main()
