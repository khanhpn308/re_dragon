"""v0.5 orchestrator regression: real SQLite, local state, no Ghidra network."""
from __future__ import annotations

import json
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from re_harness import core, autonomy, mcp


class AutonomousHarnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state=Path(self.tmp.name)/"state"
        self.binary=Path(self.tmp.name)/"test.so"
        self.binary.write_bytes(b"\x7fELF"+b"\x00"*32)
        self.db=core.database(self.state)
        self.addCleanup(self.db.close)
        autonomy.migrate(self.db)

    def goal(self):
        return autonomy.start(self.db,"Restore offline protocol",
                              "Evidence-backed codec and parser with passing CI",
                              binary_path=str(self.binary))["project_id"]

    def seed(self,pid):
        return autonomy.plan(self.db,pid,[
            {"key":"discovery","title":"Inspect ELF and find packet functions",
             "kind":"ANALYZE","acceptance":"Symbol + address + provenance",
             "priority":30,"depends_on":[]},
            {"key":"codec","title":"Build codec with independent tests",
             "kind":"IMPLEMENT","acceptance":"Offline vectors pass",
             "priority":20,"depends_on":["discovery"]},
        ])

    def claim(self,pid,actor="exec",role="executor",session="session-A",limit=80):
        return autonomy.tick(self.db,pid,actor,session,role,max_turns=limit)

    def finish(self,pid,task,producer="exec",reviewer="review-agent"):
        if isinstance(task,str):
            result=self.claim(pid,producer)
            self.assertEqual(result["task_key"],task)
            task=result
        autonomy.submit(self.db,pid,task["task_key"],producer,
                        task["claim_token"],"Reviewed assembly and code",
                        ["REA:raw-evidence-1"],["docs/analysis.md"],["test:passed"])
        review=self.claim(pid,reviewer,"reviewer")
        self.assertEqual(review["decision"],"REVIEW")
        self.assertEqual(review["task_key"],task["task_key"])
        return autonomy.review(self.db,pid,review["task_key"],reviewer,
                    review["claim_token"],"APPROVE",
                    "Independently inspected source, not just generated tests",
                    ["REA:raw-evidence-1"])

    def test_full_goal_loop_without_human_phase_prompts(self):
        pid=self.goal()
        self.assertEqual(self.claim(pid)["decision"],"PLAN")
        self.seed(pid)
        first=self.claim(pid)
        self.assertEqual(first["decision"],"EXECUTE")
        self.assertEqual(first["task_key"],"discovery")
        self.finish(pid,first)
        second=self.claim(pid)
        self.assertEqual(second["task_key"],"codec")
        self.finish(pid,second)
        decision=self.claim(pid)
        self.assertEqual(decision["decision"],"FINAL_REVIEW")
        accepted=autonomy.final_review(self.db,pid,"external-owner","ACCEPT",
                                        "Accepted relative to explicitly bounded offline scope")
        self.assertEqual(accepted["status"],"ACCEPTED")
        self.assertEqual(self.claim(pid)["decision"],"ACCEPTED")

    def test_same_actor_cannot_review_own_submission(self):
        pid=self.goal()
        self.seed(pid)
        t=self.claim(pid)
        autonomy.submit(self.db,pid,t["task_key"],"exec",t["claim_token"],
             "Code inspected",["source:1"],[],["offline pytest passed"])
        own=self.claim(pid,"exec","reviewer")
        self.assertNotEqual(own["decision"],"REVIEW")
        external=self.claim(pid,"review-agent","reviewer")
        self.assertEqual(external["decision"],"REVIEW")

    def test_plan_rejects_dependency_cycle(self):
        pid=self.goal()
        with self.assertRaisesRegex(ValueError,"cycle"):
            autonomy.plan(self.db,pid,[
                {"key":"a","title":"Task A","acceptance":"A",
                 "depends_on":["b"]},
                {"key":"b","title":"Task B","acceptance":"B",
                 "depends_on":["a"]},
            ])
        self.assertEqual(autonomy.snapshot(self.db,pid)["tasks"],[])

    def test_dag_blocks_downstream_until_review(self):
        pid=self.goal()
        self.seed(pid)
        claimed=self.claim(pid)
        self.assertEqual(claimed["task_key"],"discovery")
        self.assertEqual(self.claim(pid,"other")["decision"],"WAIT")
        autonomy.submit(self.db,pid,"discovery","exec",
                        claimed["claim_token"],"Done",["source:1"],[],[])
        self.assertEqual(self.claim(pid,"other")["decision"],"WAIT")
        self.finish_review_only(pid,"discovery")
        self.assertEqual(self.claim(pid,"other")["task_key"],"codec")

    def finish_review_only(self,pid,key,verdict="APPROVE"):
        review=self.claim(pid,"review-agent","reviewer")
        self.assertEqual(review["task_key"],key)
        return autonomy.review(self.db,pid,key,"review-agent",
            review["claim_token"],verdict,"Primary source inspected",
            ["evidence:1"] if verdict=="APPROVE" else [])

    def test_reject_requires_rework_and_no_auto_verified(self):
        pid=self.goal()
        self.seed(pid)
        t=self.claim(pid)
        autonomy.submit(self.db,pid,t["task_key"],"exec",t["claim_token"],
               "Model tests passed",["self-generated-test"],[],[])
        outcome=self.finish_review_only(pid,"discovery",verdict="REJECT")
        self.assertEqual(outcome["status"],"REWORK")
        self.assertEqual(self.claim(pid)["task_key"],"discovery")

    def test_expired_lease_reclaim(self):
        pid=self.goal()
        self.seed(pid)
        a=self.claim(pid)
        with self.db:
            self.db.execute(
                "UPDATE auto_tasks SET lease_until=0 WHERE project_id=? "
                "AND task_key=?",(pid,a["task_key"]))
        b=self.claim(pid,"new-worker")
        self.assertEqual(b["task_key"],"discovery")
        self.assertNotEqual(b["claim_token"],a["claim_token"])
        with self.assertRaisesRegex(ValueError,"token mismatch"):
            autonomy.submit(self.db,pid,"discovery","exec",
                            a["claim_token"],"stale",["x"],[],[])

    def test_session_turn_budget_forces_yield(self):
        pid=self.goal()
        self.seed(pid)
        self.assertEqual(self.claim(pid,limit=1)["decision"],"EXECUTE")
        self.assertEqual(self.claim(pid,limit=1)["decision"],"YIELD")
        self.assertEqual(self.claim(pid,session="session-B")["decision"],"WAIT")

    def test_bad_submission_requires_evidence_or_artifact(self):
        pid=self.goal()
        self.seed(pid)
        claim=self.claim(pid)
        with self.assertRaisesRegex(ValueError,"requires evidence"):
            autonomy.submit(self.db,pid,"discovery","exec",
                            claim["claim_token"],"No provenance",[],[],[])

    def test_independent_reviewer_must_list_checked_primary_sources(self):
        pid=self.goal()
        self.seed(pid)
        first=self.claim(pid)
        autonomy.submit(self.db,pid,"discovery","exec",first["claim_token"],
                        "Done",["source:one"],[],[])
        r=self.claim(pid,"review-agent","reviewer")
        with self.assertRaisesRegex(ValueError,"requires inspected"):
            autonomy.review(self.db,pid,"discovery","review-agent",
                            r["claim_token"],"APPROVE","No direct review",[])
        self.assertEqual(
            autonomy.review(self.db,pid,"discovery","review-agent",
                            r["claim_token"],"APPROVE","Checked bytes",
                            ["source:one"])["status"],"VERIFIED")

    def test_detect_contradiction_invalidate_dependents_and_replan(self):
        pid=self.goal()
        self.seed(pid)
        self.finish(pid,"discovery")
        self.finish(pid,"codec")
        issue=autonomy.report_issue(self.db,pid,"discovery",
              "Manifest differs from ARM64 branch parser",["elf:0x7efabc"])
        self.assertTrue(issue["created"])
        self.assertIn("codec",issue["invalidated"])
        states={x["key"]:x["status"] for x in autonomy.snapshot(self.db,pid)["tasks"]}
        self.assertEqual(states["discovery"],"DISPUTED")
        self.assertEqual(states["codec"],"REWORK")
        audit=self.claim(pid)
        self.assertEqual(audit["task_key"],issue["audit_task_key"])
        self.finish(pid,audit)
        result=autonomy.resolve_issue(self.db,pid,"discovery",
                   issue["audit_task_key"],"Confirmed parsing mismatch")
        self.assertEqual(result["status"],"REWORK")
        self.assertEqual(self.claim(pid)["task_key"],"discovery")
        duplicate=autonomy.report_issue(self.db,pid,"discovery",
              "Manifest differs from ARM64 branch parser",["elf:0x7efabc"])
        self.assertFalse(duplicate["created"])

    def test_final_acceptance_cannot_skip_any_task_review(self):
        pid=self.goal()
        self.seed(pid)
        with self.assertRaisesRegex(ValueError,"independent review"):
            autonomy.final_review(self.db,pid,"review-agent","ACCEPT","not ready")

    def test_stop_then_resume_preserves_backlog(self):
        pid=self.goal()
        self.seed(pid)
        before=autonomy.snapshot(self.db,pid)["tasks"]
        autonomy.pause(self.db,pid,"User stopped workflow")
        self.assertEqual(self.claim(pid)["decision"],"STOPPED")
        self.assertEqual(autonomy.resume(self.db,pid,"Continue local only")["status"],"ACTIVE")
        self.assertEqual(len(before),len(autonomy.snapshot(self.db,pid)["tasks"]))

    def test_wrong_binary_identity_prevents_acceptance(self):
        pid=self.goal()
        self.seed(pid)
        self.finish(pid,"discovery")
        self.finish(pid,"codec")
        self.assertEqual(self.claim(pid)["decision"],"FINAL_REVIEW")
        self.binary.write_bytes(b"modified")
        with self.assertRaisesRegex(ValueError,"binary changed"):
            autonomy.final_review(self.db,pid,"reviewer","ACCEPT","should fail")

    def test_double_claim_prevented_across_sqlite_connections(self):
        pid=self.goal()
        self.seed(pid)
        first=self.claim(pid)
        with core.database(self.state) as other:
            result=autonomy.tick(other,pid,"second","session-b")
        self.assertEqual(result["decision"],"WAIT")
        self.assertNotEqual(first["claim_token"],result.get("claim_token"))

    def test_mcp_tools_exposed_and_work(self):
        names={x["name"] for x in mcp.TOOLS}
        for name in ("harness_auto_start","harness_auto_plan",
            "harness_auto_tick","harness_auto_submit","harness_auto_review",
            "harness_auto_issue","harness_auto_resolve_issue",
            "harness_auto_status","harness_auto_resume"):
            self.assertIn(name,names)
        response=mcp.process({"jsonrpc":"2.0","id":3,"method":"tools/call",
            "params":{"name":"harness_auto_start","arguments":{
                "goal":"Recover offline protocol",
                "acceptance":"Static evidence and passing tests",
                "binary_path":str(self.binary)}}},self.state)
        self.assertFalse(response["result"]["isError"])
        pid=json.loads(response["result"]["content"][0]["text"])["project_id"]
        self.assertEqual(autonomy.snapshot(self.db,pid)["project"]["status"],"PLANNING")


    def test_reconnect_agent_lists_existing_active_goal(self):
        pid=self.goal()
        self.seed(pid)
        found=autonomy.list_projects(self.db)
        self.assertEqual(found["recommended_project_id"],pid)
        self.assertTrue(any(p["id"]==pid for p in found["projects"]))

    def test_checkpoint_task_detail_retains_evidence_without_lease_secret(self):
        pid=self.goal()
        self.seed(pid)
        claim=self.claim(pid)
        autonomy.submit(self.db,pid,claim["task_key"],"exec",
             claim["claim_token"],"Found ELF function",
             ["REA:0x702abc"],["docs/native.md"],["pytest pass"])
        found=autonomy.task_detail(self.db,pid,claim["task_key"])["task"]
        self.assertEqual(found["evidence_json"],["REA:0x702abc"])
        self.assertEqual(found["verification_json"],["pytest pass"])
        self.assertNotIn("lease_token",found)

    def test_blocked_task_requires_authorized_claim(self):
        pid=self.goal()
        self.seed(pid)
        first=self.claim(pid)
        with self.assertRaisesRegex(ValueError,"ownership token"):
            autonomy.block_task(self.db,pid,"discovery","exec","wrong","network denied")
        blocked=autonomy.block_task(self.db,pid,"discovery","exec",
                 first["claim_token"],"Original ELF not accessible")
        self.assertEqual(blocked["status"],"BLOCKED")
        self.assertEqual(self.claim(pid)["decision"],"BLOCKED")

    def test_local_report_contains_accepted_goal_and_evidence_disclaimer(self):
        pid=self.goal()
        self.seed(pid)
        result=autonomy.export_report(self.db,self.state,pid)
        report=Path(result["report"])
        self.assertTrue(report.is_file())
        self.assertIn("Restore offline protocol",report.read_text())
        self.assertIn("not cryptographically authenticated",report.read_text())

if __name__=="__main__":
    unittest.main()
