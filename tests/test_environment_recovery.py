"""Offline fault-injection for S6 Android environment recovery."""
from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from re_harness import autonomy, core, environment_recovery as env


class AndroidEnvironmentRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.dbdir = self.root / ".re_harness_mvp"
        (self.root / ".re_harness").mkdir()
        with core.database(self.dbdir) as db:
            autonomy.migrate(db)
            self.pid=autonomy.start(db,"Test isolated Android E2E","Must review E2E")["project_id"]
            autonomy.plan(db,self.pid,[{
                "key": "s1-tcp-protocol-server", "title": "Go server ready",
                "kind": "TEST", "acceptance": "Verified", "priority": 20,
                "depends_on": [],
            }, {
                "key": env.TARGET, "title": "Android E2E",
                "kind": "TEST", "acceptance": "Android client plays via own Go server",
                "priority": 10, "depends_on": ["s1-tcp-protocol-server"]
            }])
            with db:
                db.execute("UPDATE auto_tasks SET status='VERIFIED' WHERE project_id=? "
                           "AND task_key='s1-tcp-protocol-server'",(self.pid,))
                db.execute(
                    "UPDATE auto_tasks SET status='BLOCKED',tries=1,review_note=? "
                    "WHERE project_id=? AND task_key=?",
                    ("No local adb binary or Android test device/emulator available",
                     self.pid,env.TARGET),
                )
        self.state=self.root/".re_harness/quota-watchdog.json"
        self.state.write_text(json.dumps({"project_id":self.pid,"status":"PAUSED"}))
        self.ready_device=lambda: {"serial":"test1234","model":env.MODEL}
        self.ready_apk=lambda root: {
            "path":env.APK,"sha256":"a"*64,"note":"format/hash only"
        }

    def check(self,apply=False,automatic=False):
        return env.recover(self.root,self.pid,apply=apply,automatic=automatic,
                           adb_probe=self.ready_device,apk_probe=self.ready_apk)

    def task(self):
        db=sqlite3.connect(self.dbdir/"state.sqlite3")
        try:
            return db.execute("SELECT status,tries,review_note FROM auto_tasks "
                              "WHERE project_id=? AND task_key=?", (self.pid,env.TARGET)).fetchone()
        finally:
            db.close()

    def test_read_only_check_and_idempotent_apply(self):
        self.assertEqual(self.check()["result"],"READY_TO_REQUEUE")
        self.assertEqual(self.task()[0],"BLOCKED")
        self.assertEqual(self.check(apply=True)["result"],"REQUEUED")
        self.assertEqual(self.task()[0],"PENDING")
        self.assertEqual(self.task()[1],1)
        self.assertEqual(self.check(apply=True)["result"],"NO_MATCHING_BLOCKED_TASK")
        with core.database(self.dbdir) as db:
            row=db.execute("SELECT event,details FROM auto_events WHERE project_id=? "
                           "AND event='ENVIRONMENT_RECOVERED'",(self.pid,)).fetchall()
        self.assertEqual(len(row),1)
        self.assertIn("original_reason",json.loads(row[0]["details"]))
        self.assertEqual(json.loads(self.state.read_text())["status"],"PAUSED")

    def test_auto_only_during_active_watchdog(self):
        with self.assertRaisesRegex(env.NotReady,"stopped"):
            self.check(apply=True,automatic=True)
        self.state.write_text(json.dumps({"project_id":self.pid,"status":"CONTINUE"}))
        self.assertEqual(self.check(apply=True,automatic=True)["result"],"REQUEUED")

    def test_no_recovery_for_other_blocker(self):
        with core.database(self.dbdir) as db:
            with db:
                db.execute("UPDATE auto_tasks SET review_note='server credential missing' "
                           "WHERE project_id=? AND task_key=?",(self.pid,env.TARGET))
        with self.assertRaisesRegex(env.NotReady,"different reason"):
            self.check(apply=True)
        self.assertEqual(self.task()[0],"BLOCKED")

    def test_no_recovery_when_attempt_exhausted(self):
        with core.database(self.dbdir) as db:
            with db:
                db.execute("UPDATE auto_tasks SET tries=? WHERE project_id=? AND task_key=?",
                           (autonomy.MAX_ATTEMPTS,self.pid,env.TARGET))
        with self.assertRaisesRegex(env.NotReady,"budget"):
            self.check(apply=True)

    def test_no_recovery_on_bad_apk_or_usb(self):
        bad=lambda root: (_ for _ in ()).throw(env.NotReady("APK absent"))
        response=env.recover(self.root,self.pid,apply=True,
                             adb_probe=self.ready_device,apk_probe=bad)
        self.assertEqual(response["result"],"NOT_READY")
        self.assertEqual(self.task()[0],"BLOCKED")
        bad_adb=lambda: (_ for _ in ()).throw(env.NotReady("No authorized device"))
        response=env.recover(self.root,self.pid,apply=True,
                             adb_probe=bad_adb,apk_probe=self.ready_apk)
        self.assertEqual(response["result"],"NOT_READY")
        self.assertEqual(self.task()[0],"BLOCKED")

    def test_no_recovery_when_agent_running(self):
        with patch("re_harness.environment_recovery.runtime_state.snapshot",
                   return_value={"pid":123}):
            with self.assertRaisesRegex(env.NotReady,"Agent currently running"):
                self.check(apply=True)
        self.assertEqual(self.task()[0],"BLOCKED")

    def test_transaction_rollback_on_event_failure(self):
        with patch("re_harness.environment_recovery.autonomy.event",
                   side_effect=RuntimeError("fault injected")):
            with self.assertRaisesRegex(RuntimeError,"fault injected"):
                self.check(apply=True)
        self.assertEqual(self.task()[0],"BLOCKED")

    def test_apk_probe_checks_local_archive(self):
        path=self.root/env.APK
        path.parent.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(path,"w") as z:
            z.writestr("AndroidManifest.xml",b"nonempty")
            z.writestr("classes.dex",b"dex\n")
        item=env._apk_probe(self.root)
        self.assertEqual(len(item["sha256"]),64)
        self.assertIn("NOT certified",item["note"])
        with self.assertRaisesRegex(env.NotReady,"outside repository"):
            env._apk_probe(self.root,"../another.apk")

    def test_adb_probe_requires_single_authorized_model(self):
        class R:
            def __init__(self,stdout="",code=0):
                self.stdout=stdout
                self.returncode=code
        def run(cmd,timeout=8):
            if cmd[-2:]==["devices","-l"]:
                return R("List of devices attached\nabc12345 device product:a model:RMX3461\n")
            if cmd[-1]=="get-state":
                return R("device\n")
            if cmd[-1]=="ro.product.model":
                return R(env.MODEL+"\n")
            return R(code=1)
        with patch("re_harness.environment_recovery.shutil.which",return_value="/usr/bin/adb"):
            result=env._adb_probe(run=run)
        self.assertEqual(result["model"],env.MODEL)


if __name__=="__main__":
    unittest.main()
