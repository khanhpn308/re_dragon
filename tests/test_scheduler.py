"""v0.6 scheduler: deterministic host fixtures, real SQLite and atomic MCP claims."""
from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from re_harness import autonomy, core, mcp, scheduler


class ResourceControllerTest(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.state=Path(tmp.name)/"state"
        self.db=core.database(self.state)
        self.addCleanup(self.db.close)
        self.host=patch("re_harness.scheduler.read_host",
                        return_value=scheduler.Host(8,16384,0.0))
        self.host.start()
        self.addCleanup(self.host.stop)
        autonomy.migrate(self.db)

    def project(self):
        return autonomy.start(self.db,"Offline bounded test goal",
                              "Verified evidence and review")["project_id"]

    def plan(self,pid,entries):
        return autonomy.plan(self.db,pid,entries)

    def item(self,key,kind="ANALYZE",priority=10,targets=None,resource=None,deps=None):
        return {"key":key,"title":"Inspect "+key,"kind":kind,"priority":priority,
                "acceptance":"Primary evidence for "+key,
                "resource_class":resource or ("GHIDRA_HEAVY" if kind=="ANALYZE" else "LIGHT"),
                "targets":targets or [],"depends_on":deps or []}

    def claim(self,pid,who="executor",session="executor-session",role="executor"):
        return autonomy.tick(self.db,pid,who,session,role)

    def submit_review(self,pid,claim):
        autonomy.submit(self.db,pid,claim["task_key"],"executor",
               claim["claim_token"],"Independent evidence",["src:elf"],
               ["report.md"],["offline test passed"])
        review=self.claim(pid,"reviewer","reviewer-session","reviewer")
        self.assertEqual(review["decision"],"REVIEW")
        self.assertEqual(review["task_key"],claim["task_key"])
        return autonomy.review(self.db,pid,claim["task_key"],"reviewer",
                               review["claim_token"],"APPROVE",
                               "Inspected disassembly source directly",["src:elf"])

    def test_resource_class_and_atomic_reservation(self):
        pid=self.project()
        self.plan(pid,[self.item("a",priority=30),
                       self.item("b",priority=20),
                       self.item("c",kind="DOCUMENT",priority=10)])
        first=self.claim(pid)
        self.assertEqual(first["task_key"],"a")
        self.assertEqual(first["resource_class"],"GHIDRA_HEAVY")
        second=self.claim(pid,"worker-2","worker-2-session")
        self.assertEqual(second["task_key"],"c")
        self.assertEqual(second["resource_class"],"LIGHT")
        third=self.claim(pid,"worker-3","worker-3-session")
        self.assertEqual(third["decision"],"WAIT")
        self.assertEqual(third["resource_wait"][0]["reason"],
                         "ghidra_exclusive_slot")
        self.assertEqual(len(scheduler.running(self.db)),2)

    def test_heavy_slot_is_global_across_projects(self):
        first=self.project()
        second=self.project()
        self.plan(first,[self.item("ghidra_a")])
        self.plan(second,[self.item("ghidra_b")])
        self.assertEqual(self.claim(first)["decision"],"EXECUTE")
        denied=self.claim(second,who="other",session="other-session")
        self.assertEqual(denied["decision"],"WAIT")
        self.assertEqual(denied["resource_wait"][0]["reason"],
                         "ghidra_exclusive_slot")

    def test_low_memory_defers_heavy_but_executes_light(self):
        pid=self.project()
        self.plan(pid,[self.item("heavy",priority=20),
                       self.item("docs",kind="DOCUMENT",priority=10)])
        with patch("re_harness.scheduler.read_host",
                   return_value=scheduler.Host(8,600,0.0)):
            self.assertEqual(self.claim(pid)["task_key"],"docs")
        statuses={x["key"]:x["status"] for x in autonomy.snapshot(self.db,pid)["tasks"]}
        self.assertEqual(statuses["heavy"],"PENDING")

    def test_ghidra_slot_released_after_submission_but_reserved_for_review(self):
        pid=self.project()
        self.plan(pid,[self.item("heavy"),self.item("next",priority=2)])
        first=self.claim(pid)
        autonomy.submit(self.db,pid,first["task_key"],"executor",
                        first["claim_token"],"Source evidence",["src:elf"],[],[])
        reviewer=self.claim(pid,"reviewer","reviewer-session","reviewer")
        self.assertEqual(reviewer["decision"],"REVIEW")
        self.assertEqual(self.claim(pid,"executor2","exec2-session")["decision"],"WAIT")
        autonomy.review(self.db,pid,reviewer["task_key"],"reviewer",
                        reviewer["claim_token"],"APPROVE","Reviewed ELF",
                        ["src:elf"])
        self.assertEqual(self.claim(pid,"executor2","exec2-session")["task_key"],"next")

    def test_adaptive_controller_bounds_and_failures(self):
        pid=self.project()
        self.plan(pid,[self.item("sample",kind="TEST")])
        first=scheduler.ensure_policy(self.db,pid)
        self.assertEqual(first["concurrency"],2)
        for _ in range(3):
            outcome=scheduler.feedback(self.db,pid,"sample","PASS")
        self.assertEqual(outcome["concurrency"],3)
        outcome=scheduler.feedback(self.db,pid,"sample","TIMEOUT")
        self.assertEqual(outcome["concurrency"],1)
        for _ in range(30):
            outcome=scheduler.feedback(self.db,pid,"sample","PASS")
        self.assertEqual(outcome["concurrency"],4)
        outcome=scheduler.feedback(self.db,pid,"sample","REJECT")
        self.assertEqual(outcome["concurrency"],3)

    def test_scoped_timeout_automatically_halves_without_extending_deadline(self):
        pid=self.project()
        targets=["0x01","0x10","0x20","0x21"]
        self.plan(pid,[self.item("opcode-study",targets=targets)])
        first=self.claim(pid)
        done=autonomy.report_timeout(self.db,pid,"opcode-study","executor",
                                     first["claim_token"],"Ghidra startup timeout")
        self.assertEqual(done["status"],"WAIT_CHILDREN")
        self.assertEqual(done["adaptive"]["concurrency"],1)
        self.assertEqual(len(done["children"]),2)
        subset=[scheduler.spec_for(self.db,autonomy._task(self.db,pid,k))["targets"]
                for k in done["children"]]
        self.assertEqual([["0x01","0x10"],["0x20","0x21"]],subset)
        for key in done["children"]:
            next_task=self.claim(pid)
            self.assertEqual(next_task["task_key"],key)
            self.submit_review(pid,next_task)
        parent=self.claim(pid)
        self.assertEqual(parent["task_key"],"opcode-study")
        self.assertEqual(parent["kind"],"DOCUMENT")
        self.assertEqual(parent["resource_class"],"LIGHT")
        self.assertEqual(parent["decision"],"EXECUTE")
        # Integration still requires executor and independent reviewer
        self.submit_review(pid,parent)
        self.assertEqual(self.claim(pid)["decision"],"FINAL_REVIEW")

    def test_manual_decomposition_requires_grounded_nonoverlapping_scopes(self):
        pid=self.project()
        self.plan(pid,[self.item("opaque")])
        task=self.claim(pid)
        timeout=autonomy.report_timeout(self.db,pid,"opaque","executor",
                         task["claim_token"],"Need isolated symbols")
        self.assertEqual(timeout["decision"],"DECOMPOSE")
        claim=self.claim(pid)
        self.assertEqual(claim["decision"],"DECOMPOSE")
        bad=[{"key":"one","title":"First","acceptance":"Evidence","targets":["func-A"]},
             {"key":"two","title":"Second","acceptance":"Evidence","targets":["func-A"]}]
        with self.assertRaisesRegex(ValueError,"overlap"):
            autonomy.split_task(self.db,pid,"opaque","executor",claim["claim_token"],
                                bad,"Static symbol evidence")
        good=[{"key":"one","title":"First","acceptance":"Evidence","targets":["func-A"]},
              {"key":"two","title":"Second","acceptance":"Evidence","targets":["func-B"]}]
        result=autonomy.split_task(self.db,pid,"opaque","executor",
                                  claim["claim_token"],good,"Static symbol evidence")
        self.assertEqual(result["status"],"WAIT_CHILDREN")
        self.assertEqual(set(result["children"]),{"one","two"})

    def test_wrong_token_cannot_inject_split(self):
        pid=self.project()
        self.plan(pid,[self.item("opaque")])
        task=self.claim(pid)
        autonomy.report_timeout(self.db,pid,"opaque","executor",
                                task["claim_token"],"Bottleneck")
        claim=self.claim(pid)
        with self.assertRaisesRegex(ValueError,"ownership token"):
            autonomy.split_task(self.db,pid,"opaque","executor","wrong",
                [{"key":"one","title":"One","acceptance":"A","targets":["a"]},
                 {"key":"two","title":"Two","acceptance":"B","targets":["b"]}],
                "Scope verified")

    def test_atomic_single_scope_timeout_blocks_without_infinite_recursion(self):
        pid=self.project()
        self.plan(pid,[self.item("atomic",targets=["0x01"])])
        task=self.claim(pid)
        r=autonomy.report_timeout(self.db,pid,"atomic","executor",
                                  task["claim_token"],"One function still times out")
        self.assertEqual(r["status"],"BLOCKED")
        self.assertEqual(self.claim(pid)["decision"],"BLOCKED")

    def test_full_project_resource_cap_and_policy_status(self):
        pid=self.project()
        self.plan(pid,[self.item("a",kind="IMPLEMENT")])
        state=autonomy.resource_config(self.db,pid,1)
        self.assertEqual(state["policy"]["max_concurrency"],1)
        self.assertEqual(state["policy"]["concurrency"],1)
        self.assertEqual(state["ghidra_exclusivity_limit"],1)
        with self.assertRaisesRegex(ValueError,"exceeds"):
            autonomy.resource_config(self.db,pid,5)

    def test_invalid_resource_class_and_cycles_are_rejected(self):
        pid=self.project()
        with self.assertRaisesRegex(ValueError,"resource_class"):
            self.plan(pid,[self.item("bad",resource="ALL_GHIDRA")])
        self.assertEqual(autonomy.snapshot(self.db,pid)["tasks"],[])

    def test_existing_unannotated_v05_tasks_fail_closed_as_heavy_analysis(self):
        pid=self.project()
        self.plan(pid,[{"key":"legacy","title":"Legacy analysis",
                        "acceptance":"Evidence","kind":"ANALYZE"}])
        info=scheduler.spec_for(self.db,autonomy._task(self.db,pid,"legacy"))
        self.assertEqual(info["profile"],"GHIDRA_HEAVY")

    def test_mcp_v06_tools_list_and_capacity_response(self):
        expected={"harness_auto_resources","harness_auto_timeout",
                  "harness_auto_split","harness_auto_resource_config"}
        self.assertTrue(expected.issubset({t["name"] for t in mcp.TOOLS}))
        pid=self.project()
        state=autonomy.resource_status(self.db,pid)
        self.assertEqual(state["host"]["logical_cpus"],8)
        self.assertEqual(state["resource_mode"],
                         "advisory_reservation_no_os_enforcement")


if __name__=="__main__":
    unittest.main()
