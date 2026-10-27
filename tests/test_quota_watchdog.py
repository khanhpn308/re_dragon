"""Unattended watcher unit tests: synthetic CLI outcomes, no real model calls."""
import json
import tempfile
import unittest
from pathlib import Path
from re_harness import quota_watchdog as q


class QuotaWatchdogTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root=Path(tmp.name)
        self.state=self.root/".re_harness"/"quota-watchdog.json"
        self.prompt=self.root/"prompt.md"
        self.prompt.write_text("Continue existing project with checkpoints",encoding="utf8")

    def output(self,kind="CONTINUE",conv="session-12345678"):
        return {"code":0,"data":{"status":"SUCCESS",
          "conversation_id":conv,
          "response":'Human summary\nRE_DRAGON_RUN_STATE '+
                     json.dumps({"state":kind,"note":"durable checkpoint"})},
          "stderr":""}

    def test_provider_hms_countdown(self):
        self.assertEqual(q.reset_seconds("Resets in 1h1m35s."),3695)
        self.assertEqual(q.reset_seconds("Resets in 2h42m39s."),9759)
        self.assertEqual(q.reset_seconds("Resets in 7m"),420)
        self.assertEqual(q.reset_seconds("Resets in 1d2h"),93600)
        self.assertIsNone(q.reset_seconds("quota exhausted"))

    def test_quota_error_from_stderr_and_scheduled_reset(self):
        prior=q.load(self.state)
        out={"code":3,"data":{},
          "stderr":'AGY_ERROR: {"status":"RESOURCE_EXHAUSTED","error_code":429,'
                   '"short_error":"Individual quota reached. Resets in 1h2m3s."}'}
        res=q.evaluate(out,prior,1000)
        self.assertEqual(res["status"],"WAIT_QUOTA")
        self.assertEqual(res["next_at"],1000+3723+60)
        self.assertEqual(res["quota_hits"],1)

    def test_five_hour_limit_not_assumed_if_countdown_absent(self):
        res=q.evaluate({"code":3,"data":{"status":"ERROR",
          "error":"RESOURCE_EXHAUSTED: Individual quota reached"},
          "stderr":""},q.load(self.state),1000)
        self.assertEqual(res["next_at"],1900)

    def test_followup_turn_resumes_pinned_session(self):
        calls=[]
        def mock_runner(workspace,prompt,conv,**kwargs):
            calls.append(conv)
            return self.output()
        first=q.once(self.root,self.state,self.prompt,clock=5000,runner=mock_runner)
        self.assertEqual(first["status"],"CONTINUE")
        self.assertEqual(first["conversation_id"],"session-12345678")
        self.assertEqual(first["next_at"],5030)
        skipped=q.once(self.root,self.state,self.prompt,clock=5020,runner=mock_runner)
        self.assertEqual(skipped["attempts"],1)
        second=q.once(self.root,self.state,self.prompt,clock=5031,runner=mock_runner)
        self.assertEqual(second["attempts"],2)
        self.assertEqual(calls,[None,"session-12345678"])

    def test_end_to_end_quota_wait_then_resume(self):
        outcomes=[
            {"code":3,"data":{"status":"ERROR",
             "error":"Individual quota reached. Resets in 1m20s."},"stderr":""},
            self.output("YIELD")
        ]
        invoked=[]
        def mock_runner(*a,**kw):
            invoked.append(a)
            return outcomes.pop(0)
        first=q.once(self.root,self.state,self.prompt,clock=1000,runner=mock_runner)
        self.assertEqual(first["status"],"WAIT_QUOTA")
        self.assertEqual(first["next_at"],1140)
        q.once(self.root,self.state,self.prompt,clock=1130,runner=mock_runner)
        self.assertEqual(len(invoked),1)
        resumed=q.once(self.root,self.state,self.prompt,clock=1141,runner=mock_runner)
        self.assertEqual(resumed["status"],"YIELD")
        self.assertEqual(len(invoked),2)

    def test_stop_on_complete(self):
        first=q.once(self.root,self.state,self.prompt,clock=100,
             runner=lambda *a,**kw:self.output("COMPLETE"))
        self.assertEqual(first["status"],"COMPLETE")
        q.once(self.root,self.state,self.prompt,clock=100000,
             runner=lambda *a,**kw:self.fail("Should not restart accepted goal"))

    def test_do_not_resume_on_interactive_permission_error(self):
        res=q.evaluate({"code":2,"data":{"status":"ERROR",
            "error":"permission denied for terminal command"},"stderr":""},
            q.load(self.state),1000)
        self.assertEqual(res["status"],"NEEDS_USER")

    def test_do_not_resume_when_not_authenticated(self):
        res=q.evaluate({"code":1,"data":{},
           "stderr":"authentication required"},q.load(self.state),1000)
        self.assertEqual(res["status"],"NEEDS_USER")

    def test_soft_denied_tool_is_not_progress_even_when_cli_exits_zero(self):
        outcome={"code":0,
                 "data":{"status":"SUCCESS","response":
                      'RE_DRAGON_RUN_STATE {"state":"CONTINUE"}'},
                 "stderr":"Tool command(git) was soft-denied: requires approval"}
        result=q.evaluate(outcome,q.load(self.state),1000)
        self.assertEqual(result["status"],"NEEDS_USER")
        self.assertEqual(result["next_at"],0)

    def test_auto_mode_is_default_when_no_operator_flag(self):
        import inspect
        self.assertEqual(inspect.signature(q.invoke).parameters["mode"].default, "auto")

    def test_unknown_success_fails_closed(self):
        res=q.evaluate({"code":0,"data":{"status":"SUCCESS",
                    "response":"Everything looks fine"},"stderr":""},
                    q.load(self.state),1000)
        self.assertEqual(res["status"],"NEEDS_USER")

    def test_quota_error_is_not_falsely_successful(self):
        res=q.evaluate({"code":0,"data":{"status":"ERROR",
                    "response":"We made progress",
                    "error":"Individual quota reached. Resets in 4h"},"stderr":""},
                    q.load(self.state),1000)
        self.assertEqual(res["status"],"WAIT_QUOTA")

    def test_prompt_malformed_stop(self):
        res=q.evaluate({"code":0,"data":{"status":"SUCCESS",
                    "response":'RE_DRAGON_RUN_STATE {"state":"BOGUS"}'},"stderr":""},
                    q.load(self.state),1000)
        self.assertEqual(res["status"],"NEEDS_USER")

    def test_timeout_needs_operator(self):
        res=q.evaluate({"code":124,"data":{},"stderr":"watchdog process timeout"},
                       q.load(self.state),1000)
        self.assertEqual(res["status"],"NEEDS_USER")

    def test_atomic_persistence(self):
        q.save(self.state,{"status":"READY","next_at":0})
        self.assertEqual(q.load(self.state)["status"],"READY")
        self.assertFalse(self.state.with_suffix(".tmp").exists())

    def test_wait_state_is_bounded(self):
        res=q.evaluate(self.output("WAIT"),q.load(self.state),1000)
        self.assertEqual(res["next_at"],1180)

    def test_agent_summary_cannot_mask_quota_error(self):
        res=q.evaluate({"code":3,"data":{"status":"ERROR",
                "response":'RE_DRAGON_RUN_STATE {"state":"COMPLETE"}',
                "error":"RESOURCE_EXHAUSTED"},"stderr":""},
                q.load(self.state),1000)
        self.assertEqual(res["status"],"WAIT_QUOTA")


if __name__=="__main__":
    unittest.main()
