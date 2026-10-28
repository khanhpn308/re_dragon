import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from re_harness import autonomy,core,functional_slices as fs,mcp,scheduler

SHA="5e0aefcbf1b23aa2dc74e95b22aee90c17011a4814193b8b61d305747a668c0f"
def contract():
    return {"feature_id":"P3B-GACHA",
            "objective":"Recover original mType Lua callback and S2C wire evidence",
            "binary_sha256":SHA,"entrypoints":["drawCard:open:1"],
            "targets":["lua:mType","native:opcode25"],
            "questions":["Where does mType get assigned?","What is x1 wish command?"],
            "artifacts":["docs/P3B_S2C_TRACE.md"],
            "acceptance":["Primary function address","Source-backed packet layout or unknown"],
            "budget":{"max_rea_calls":2,"max_functions":2,"max_xref_depth":1,
                      "max_output_chars":1200}}

class SliceGateTests(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory();self.addCleanup(tmp.cleanup)
        self.db=core.database(Path(tmp.name));self.addCleanup(self.db.close)
        p=patch("re_harness.scheduler.read_host",return_value=scheduler.Host(8,16384,0))
        p.start();self.addCleanup(p.stop)
        autonomy.migrate(self.db)
        self.pid=autonomy.start(self.db,"Verify Gacha client source",
                               "Source-backed callback evidence")["project_id"]
        autonomy.plan(self.db,self.pid,[{"key":"draw","title":"Targeted native/Lua trace",
                    "kind":"ANALYZE","acceptance":"Source-grounded S2C evidence",
                    "targets":["lua:mType","native:opcode25"]}])
        fs.define(self.db,self.pid,"draw",contract())
        self.claim=autonomy.tick(self.db,self.pid,"exec","session-A")
        self.token=self.claim["claim_token"]
    def reserve(self,target="lua:mType"):
        return fs.reserve(self.db,self.pid,"draw","exec",self.token,"xref",target,1)["ticket"]
    def record(self,ticket,fid="lua:mType",confidence="VERIFIED"):
        return fs.receipt(self.db,self.pid,"draw","exec",self.token,ticket,fid,
                          "REA:proof-source",102,"a"*64,confidence)
    def test_budget_without_elapsed_time(self):
        a=self.reserve()
        with self.assertRaisesRegex(ValueError,"previous REA receipt"):
            self.reserve()
        self.record(a)
        self.record(self.reserve("native:opcode25"),"native:opcode25")
        with self.assertRaisesRegex(ValueError,"REA_CALL_BUDGET_EXHAUSTED"):
            self.reserve()
        self.assertIsNone(fs.status(self.db,self.pid,"draw")["wall_clock_deadline"])
    def test_submission_fail_closed(self):
        with self.assertRaisesRegex(ValueError,"complete REA receipts"):
            autonomy.submit(self.db,self.pid,"draw","exec",self.token,"fake",
                            ["REA:proof-source"],["docs/P3B_S2C_TRACE.md"],[])
        self.record(self.reserve())
        with self.assertRaisesRegex(ValueError,"declared slice artifacts"):
            autonomy.submit(self.db,self.pid,"draw","exec",self.token,"missing",
                            ["REA:proof-source"],[],[])
        v=autonomy.submit(self.db,self.pid,"draw","exec",self.token,"evidence",
                          ["REA:proof-source"],["docs/P3B_S2C_TRACE.md"],[])
        self.assertEqual(v["status"],"SUBMITTED")
    def test_unknown_cannot_be_submitted_and_can_checkpoint(self):
        self.record(self.reserve(),confidence="UNKNOWN")
        with self.assertRaisesRegex(ValueError,"VERIFIED"):
            autonomy.submit(self.db,self.pid,"draw","exec",self.token,"no proof",
                            ["REA:proof-source"],["docs/P3B_S2C_TRACE.md"],[])
        v=fs.checkpoint_split(self.db,self.pid,"draw","exec",self.token,
                              "Missing Lua callback in current binary",["REA:proof-source"])
        self.assertEqual(v["status"],"SPLIT_REQUIRED")
        self.assertEqual(autonomy.tick(self.db,self.pid,"exec","session-B")["decision"],"DECOMPOSE")
    def test_scope_and_output_rejects(self):
        with self.assertRaisesRegex(ValueError,"outside frozen"):
            self.reserve("not:in-scope")
        t=self.reserve()
        with self.assertRaisesRegex(ValueError,"exceeds bounded context"):
            fs.receipt(self.db,self.pid,"draw","exec",self.token,t,"lua:mType",
                       "REA:proof-source",1201,"a"*64,"VERIFIED")
        self.record(t)
    def test_invalid_contract_and_mcp_registration(self):
        c=contract(); c["budget"]["max_rea_calls"]=100
        with self.assertRaisesRegex(ValueError,"max_rea_calls"):
            fs.validate_contract(c)
        names={t["name"] for t in mcp.TOOLS}
        self.assertTrue({"harness_slice_define","harness_slice_reserve",
                         "harness_slice_receipt","harness_slice_status",
                         "harness_slice_checkpoint_split"}<=names)
