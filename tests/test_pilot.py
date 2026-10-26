"""P0 autonomy pilot evaluator unit tests. Simulated agents, not live Antigravity."""
import tempfile
import unittest
from pathlib import Path
from re_harness import core, autonomy, pilot, mcp


class PilotEvaluationTest(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.state=Path(temp.name)
        self.db=core.database(self.state)
        self.addCleanup(self.db.close)
        self.pid=autonomy.start(self.db,
              "PILOT: evaluate bounded automatic review loop",
              "Reject defective fixture, repair, then continue")["project_id"]
        autonomy.plan(self.db,self.pid,[
          {"key":"inspect-and-repair-fixture","title":"Audit canary",
           "kind":"IMPLEMENT","acceptance":"Reject and fix endian mismatch",
           "priority":20,"depends_on":[]},
          {"key":"continuation","title":"Continue without user prompt",
           "kind":"DOCUMENT","acceptance":"Verified continuation",
           "priority":10,"depends_on":["inspect-and-repair-fixture"]},
        ])

    def claim(self,role="executor",session="exec-session",actor="exec"):
        return autonomy.tick(self.db,self.pid,actor,session,role)

    def submit(self,claim,summary):
        return autonomy.submit(self.db,self.pid,claim["task_key"],"exec",
           claim["claim_token"],summary,["pilot/SPEC.md"],
           ["pilot/buggy_decoder.py"],["offline test recorded"])

    def review(self,key,verdict):
        r=self.claim("reviewer","reviewer-session","real-reviewer")
        self.assertEqual(r["decision"],"REVIEW")
        self.assertEqual(r["task_key"],key)
        return autonomy.review(self.db,self.pid,key,"real-reviewer",
               r["claim_token"],verdict,"Independent oracle check",
               ["pilot/SPEC.md"])

    def test_pilot_controller_pass_but_real_subagent_unattested(self):
        first=self.claim()
        self.assertEqual(first["task_key"],"inspect-and-repair-fixture")
        self.submit(first,"Buggy fixture intentionally submitted for review")
        self.assertEqual(self.review(first["task_key"],"REJECT")["status"],"REWORK")
        repair=self.claim()
        self.assertEqual(repair["task_key"],"inspect-and-repair-fixture")
        self.submit(repair,"Corrected fixture, oracle passed")
        self.assertEqual(self.review(repair["task_key"],"APPROVE")["status"],"VERIFIED")
        second=self.claim()
        self.assertEqual(second["task_key"],"continuation")
        self.submit(second,"Handoff generated without extra prompt")
        self.review(second["task_key"],"APPROVE")
        verdict=pilot.evaluate(self.db,self.pid)
        self.assertEqual(verdict["controller_gate"],"PASS")
        self.assertEqual(verdict["real_antigravity_subagent_gate"],"UNVERIFIED")
        self.assertEqual(verdict["overall"],"PENDING_HOST_VERIFICATION")
        self.assertTrue(all(verdict["controller_checks"].values()))
        self.assertIn("harness_pilot_evaluate",{x["name"] for x in mcp.TOOLS})

    def test_no_go_without_real_reviewed_continuation(self):
        first=self.claim()
        self.submit(first,"Buggy fixture")
        result=pilot.evaluate(self.db,self.pid)
        self.assertEqual(result["overall"],"NO_GO")
        self.assertFalse(result["controller_checks"]["review_rejected_initial_defect"])

    def test_not_allowed_to_use_real_project_as_pilot(self):
        normal=autonomy.start(self.db,"Actual game project","Analyze native")["project_id"]
        with self.assertRaisesRegex(ValueError,"isolated PILOT"):
            pilot.evaluate(self.db,normal)


if __name__=="__main__":
    unittest.main()
