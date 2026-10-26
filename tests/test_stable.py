"""Regression tests for stable engine using actual subprocess mock REA."""
from __future__ import annotations
import json
import os
import stat
import tempfile
import time
import unittest
from pathlib import Path
from re_harness import core, stable, mcp

class StableTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.state = self.base / "state"
        self.binary = self.base / "fixture.so"
        self.binary.write_bytes(b"\x7fELF" + b"\x01"*32)
        self.rea = self.base / "mock_rea"
        self.rea.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys, time\n"
            "cmd = sys.argv[1]\n"
            "if os.environ.get('MOCK_SLEEP'): time.sleep(float(os.environ['MOCK_SLEEP']))\n"
            "if os.environ.get('MOCK_FAIL') == cmd:\n"
            " print(json.dumps({'error': {'message':'mock error'}}))\n"
            " sys.exit(0)\n"
            "if cmd == 'function':\n"
            " out={'normalized_result': {'name':'root', 'calls':"
            " [{'target':'function_B'}, {'target':'function_C'}]}}\n"
            "else:\n"
            " out={'normalized_result': {'functions':"
            " [{'name':'CProtocolManager','address':'0x1000'}]}}\n"
            "print(json.dumps(out))\n", encoding="utf-8")
        self.rea.chmod(self.rea.stat().st_mode | stat.S_IXUSR)
        self.workflow = self.base / "workflow.json"
        self.workflow.write_text(json.dumps({"steps": [
            {"key":"inspect","operation":"inspect"},
            {"key":"lookup","operation":"search","selector":"CProtocolManager",
             "depends_on":["inspect"]}]}), encoding="utf-8")
        self.db = core.database(self.state)
        self.addCleanup(self.db.close)
        stable.migrate(self.db)

    def plan(self):
        return core.create_plan(self.db,self.binary,self.workflow,rea_bin=str(self.rea))

    def test_full_workflow_and_integrity(self):
        run = self.plan()
        reply = stable.work(self.db,self.state,run,steps=20)
        self.assertEqual(reply["status"],"completed")
        self.assertEqual(reply["executed"],2)
        self.assertTrue(Path(reply["report"]).is_file())
        self.assertTrue(core.validate(self.db,self.state,run)["ready_for_review"])
        self.assertEqual(core.validate(self.db,self.state,run)["checks"][-1]["result"],
                         "REVIEW_REQUIRED")
        self.assertTrue(stable.observations(self.db,run)["items"])

    def test_resume_skips_completed(self):
        run=self.plan()
        first=stable.work(self.db,self.state,run,steps=1)
        self.assertEqual(first["status"],"paused")
        final=stable.work(self.db,self.state,run,steps=20)
        self.assertEqual(final["status"],"completed")
        self.assertEqual([t["attempts"] for t in core.get_tasks(self.db,run)],[1,1])

    def test_binary_identity(self):
        run=self.plan()
        self.binary.write_bytes(b"changed")
        with self.assertRaisesRegex(ValueError,"SHA-256"):
            stable.work(self.db,self.state,run)

    def test_verified_claim_requires_source(self):
        run=self.plan()
        stable.work(self.db,self.state,run,steps=20)
        core.add_claim(self.db,run,"Unproven claim","VERIFIED","inspect")
        self.assertEqual(core.validate(self.db,self.state,run)["checks"][3]["result"],
                         "FAIL")

    def test_tampering_detected(self):
        run=self.plan()
        stable.work(self.db,self.state,run,steps=20)
        task=core.get_tasks(self.db,run)[0]
        artifact=core.latest_artifact(self.db,task["id"])
        (self.state/artifact["stdout_path"]).write_text("{}")
        self.assertEqual(core.validate(self.db,self.state,run)["checks"][2]["result"],
                         "FAIL")

    def test_json_failure_even_if_process_exits_zero(self):
        run=self.plan()
        os.environ["MOCK_FAIL"]="inspect"
        self.addCleanup(os.environ.pop,"MOCK_FAIL",None)
        result=stable.work(self.db,self.state,run,steps=1,retries=0)
        self.assertEqual(result["status"],"failed")
        self.assertEqual(core.get_tasks(self.db,run)[0]["exit_code"],65)

    def test_retry_budget_and_cooldown(self):
        run=self.plan()
        os.environ["MOCK_FAIL"]="inspect"
        self.addCleanup(os.environ.pop,"MOCK_FAIL",None)
        stable.work(self.db,self.state,run,steps=1,retries=1)
        step=core.get_tasks(self.db,run)[0]
        self.assertGreater(step["retry_after"],time.time())
        with self.db:
            self.db.execute("UPDATE tasks SET retry_after=0 WHERE id=?",(step["id"],))
        second=stable.work(self.db,self.state,run,steps=1,retries=1)
        self.assertEqual(second["status"],"failed")
        self.assertEqual(core.get_tasks(self.db,run)[0]["attempts"],2)

    def test_exclusive_worker_lease(self):
        run=self.plan()
        a=stable.claim(self.db,run,"agent-A",lease_seconds=600)
        self.assertIsNotNone(a)
        with core.database(self.state) as db2:
            stable.migrate(db2)
            self.assertIsNone(stable.claim(db2,run,"agent-B",lease_seconds=600))

    def test_recover_dead_worker(self):
        run=self.plan()
        stable.claim(self.db,run,"dead",lease_seconds=1)
        with self.db:
            self.db.execute("UPDATE tasks SET lease_until=0,pid=NULL WHERE run_id=?",(run,))
            self.db.execute("UPDATE engine_slots SET lease_until=0,pid=NULL")
        result=stable.recover(self.db,run)
        self.assertEqual(result["recovered"],["inspect"])
        self.assertEqual(core.get_tasks(self.db,run)[0]["status"],"failed")

    def test_recovery_does_not_steal_live_process(self):
        run=self.plan()
        stable.claim(self.db,run,"live",lease_seconds=1)
        pid=os.getpid()
        with self.db:
            self.db.execute(
                "UPDATE tasks SET lease_until=0,pid=?,pid_start=? WHERE run_id=?",
                (pid,stable.proc_start(pid),run))
        result=stable.recover(self.db,run)
        self.assertEqual(result["recovered"],[])
        self.assertIn("inspect",result["blocked_live_processes"])

    def test_call_graph_is_bounded(self):
        run=self.plan()
        stable.work(self.db,self.state,run,steps=20)
        stable.add_graph(self.db,run,"root",depth=1,max_nodes=3)
        reply=stable.work(self.db,self.state,run,steps=20)
        self.assertEqual(reply["status"],"completed")
        graph=stable.graph(self.db,run)
        self.assertEqual({r["selector"] for r in graph["nodes"]},
                         {"root","function_B","function_C"})

    def test_mcp_connection_and_tools(self):
        listed=mcp.process({"jsonrpc":"2.0","id":1,"method":"tools/list"},self.state)
        self.assertIn("harness_worker",[x["name"] for x in listed["result"]["tools"]])
        response=mcp.process({
            "jsonrpc":"2.0","id":2,"method":"tools/call",
            "params":{"name":"harness_create_plan","arguments":{
                "binary_path":str(self.binary),"workflow_path":str(self.workflow)}}},
            self.state)
        self.assertFalse(response["result"]["isError"])
        run=json.loads(response["result"]["content"][0]["text"])["run_id"]
        self.assertIsNotNone(core.get_run(self.db,run))

    def test_invalid_workflow_dependency(self):
        path=self.base/"bad.json"
        path.write_text(json.dumps({"steps":[{"key":"a","operation":"inspect",
                                              "depends_on":["missing"]}]}))
        with self.assertRaises(ValueError):
            core.create_plan(self.db,self.binary,path,rea_bin=str(self.rea))

    def test_timeout_terminates_child_and_saves_failed_attempt(self):
        run=self.plan()
        os.environ["MOCK_SLEEP"]="15"
        self.addCleanup(os.environ.pop,"MOCK_SLEEP",None)
        result=stable.work(self.db,self.state,run,steps=1,timeout=1,retries=0)
        self.assertEqual(result["status"],"failed")
        task=core.get_tasks(self.db,run)[0]
        self.assertEqual(task["exit_code"],124)
        self.assertIsNotNone(core.latest_artifact(self.db,task["id"]))

    def test_concurrent_workers_do_not_repeat_a_task(self):
        import threading
        run=self.plan()
        os.environ["MOCK_SLEEP"]="0.25"
        self.addCleanup(os.environ.pop,"MOCK_SLEEP",None)
        barrier=threading.Barrier(2)
        errors=[]
        def worker():
            try:
                with core.database(self.state) as db:
                    barrier.wait(timeout=5)
                    stable.work(db,self.state,run,steps=3,capacity=1)
            except Exception as exc:
                errors.append(repr(exc))
        threads=[threading.Thread(target=worker) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=15)
        self.assertFalse(errors,errors)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual([t["attempts"] for t in core.get_tasks(self.db,run)],[1,1])

    def test_stdio_mcp_round_trip(self):
        import subprocess
        import sys
        queries=[
            {"jsonrpc":"2.0","id":1,"method":"initialize",
             "params":{"protocolVersion":"2025-03-26","capabilities":{}}},
            {"jsonrpc":"2.0","id":2,"method":"tools/list"},
            {"jsonrpc":"2.0","id":3,"method":"tools/call",
             "params":{"name":"harness_list_runs","arguments":{}}}
        ]
        result=subprocess.run([sys.executable,"-m","re_harness.mcp","--state-dir",
                               str(self.state)],input="\n".join(map(json.dumps,queries))+"\n",
                              text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        replies=[json.loads(line) for line in result.stdout.splitlines()]
        self.assertEqual([item["id"] for item in replies],[1,2,3])
        self.assertFalse(replies[-1]["result"]["isError"])

if __name__=="__main__":
    unittest.main()
