"""Agent-first v0.4 regression tests (no native binary execution)."""
from __future__ import annotations
import json
import tempfile
import unittest
from pathlib import Path

from re_harness import core, investigation, mcp

class AgentOrchestrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name) / "state"
        self.binary = Path(self.tmp.name) / "libaos_jogo.so"
        self.binary.write_bytes(b"\x7fELF" + b"\x99"*40)
        self.db = core.database(self.state)
        self.addCleanup(self.db.close)
        investigation.migrate(self.db)

    def begin(self):
        return investigation.begin(self.db,
            "Trace TCP handshake key derivation and opcode dispatch",
            agent="codex", binary_path=str(self.binary))["investigation_id"]

    def plan(self, ident):
        return investigation.set_plan(self.db, ident, [
            {"title": "Discover entrypoints",
             "acceptance": "Identify exact symbols and addresses"},
            {"title": "Trace receive path",
             "acceptance": "Preserve function-level evidence and uncertainties"},
        ])

    def test_full_agent_workflow_and_gates(self):
        ident = self.begin()
        self.plan(ident)
        receipt = investigation.record_rea(
            self.db, ident, "analyze_function", "Receive logic candidate",
            evidence_id="ev_fixture0123", step=1,
            limitations=["Unresolved virtual calls"],
            target_sha256=core.sha256(self.binary))
        self.assertEqual(receipt["receipt_status"],
                         "agent_reported_not_authenticated")
        oid=receipt["observation_id"]
        self.assertFalse(receipt["duplicate"])
        investigation.set_step(self.db, ident, 1, "done", "Needs semantic review")
        next_receipt=investigation.record_rea(
            self.db, ident, "procedure_callees", "Callees seen via Ghidra",
            step=2, limitations=["Static only"])
        investigation.set_step(self.db, ident, 2, "done")
        finding=investigation.record_finding(
            self.db, ident, "Observed a native receive path",
            "VERIFIED", "Assembly and Ghidra pseudocode are aligned",
            observation_ids=[oid], symbol="aos::Conexao")
        self.assertEqual(finding["semantic_review"], "required")
        checks=investigation.review(self.db, ident)
        self.assertTrue(checks["ready_for_review"])
        self.assertEqual(checks["checks"][5]["state"], "UNVERIFIED")
        self.assertEqual(checks["checks"][6]["state"], "REVIEW_REQUIRED")
        report=investigation.report(self.db, self.state, ident)
        self.assertTrue(Path(report["path"]).is_file())
        closed=investigation.close(self.db, ident, "Further runtime tests unknown")
        self.assertEqual(closed["status"], "closed")

    def test_no_done_without_attached_observation(self):
        ident=self.begin()
        self.plan(ident)
        with self.assertRaisesRegex(ValueError, "at least one REA observation"):
            investigation.set_step(self.db, ident, 1, "done")

    def test_verified_requires_provenance(self):
        ident=self.begin()
        self.plan(ident)
        with self.assertRaisesRegex(ValueError, "VERIFIED requires"):
            investigation.record_finding(
                self.db, ident, "Speculative opcode", "VERIFIED",
                "Symbol looked plausible", symbol="someFunction")
        receipt=investigation.record_rea(
            self.db, ident, "search_procedures", "Candidate", step=1)
        with self.assertRaisesRegex(ValueError, "belong to this investigation"):
            investigation.record_finding(
                self.db, ident, "Speculative opcode", "VERIFIED",
                "No exact provenance", observation_ids=["made_up"],
                symbol="someFunction")
        self.assertTrue(receipt["observation_id"])

    def test_target_digest_mismatch_is_rejected(self):
        ident=self.begin()
        with self.assertRaisesRegex(ValueError, "different target"):
            investigation.record_rea(
                self.db, ident, "analyze_function", "Mismatched binary",
                target_sha256="0"*64)

    def test_duplicate_receipt_is_idempotent(self):
        ident=self.begin()
        self.plan(ident)
        first=investigation.record_rea(
            self.db, ident, "open_binary", "ELF loaded",
            evidence_id="ev_fixture_01", step=1)
        second=investigation.record_rea(
            self.db, ident, "open_binary", "ELF loaded again",
            evidence_id="ev_fixture_01", step=1)
        self.assertTrue(second["duplicate"])
        self.assertEqual(first["observation_id"],second["observation_id"])

    def test_preserves_legacy_tasks_and_state(self):
        ident=self.begin()
        self.plan(ident)
        investigation.migrate(self.db)
        self.assertEqual(investigation.status(self.db,ident)["investigation"]["id"],
                         ident)
        self.assertIsNotNone(self.db.execute(
            "SELECT name FROM sqlite_master WHERE name='tasks'").fetchone())

    def test_mcp_agent_first_protocol(self):
        names={x["name"] for x in mcp.TOOLS}
        for required in ("harness_begin_investigation",
                         "harness_set_investigation_plan",
                         "harness_record_rea_observation",
                         "harness_record_finding",
                         "harness_investigation_review",
                         "harness_investigation_report"):
            self.assertIn(required,names)
        request={"jsonrpc":"2.0","id":44,"method":"tools/call",
                 "params":{"name":"harness_begin_investigation",
                           "arguments":{"goal":"Map opcode dispatch",
                                        "binary_path":str(self.binary)}}}
        reply=mcp.process(request,self.state)
        self.assertFalse(reply["result"]["isError"])
        ident=json.loads(reply["result"]["content"][0]["text"])["investigation_id"]
        self.assertTrue(investigation.status(self.db,ident)["investigation"])

    def test_cannot_write_to_closed_investigation(self):
        ident=self.begin()
        investigation.close(self.db, ident, "No supporting material")
        with self.assertRaisesRegex(ValueError,"closed"):
            investigation.record_rea(self.db,ident,"open_binary","late receipt")
        with self.assertRaisesRegex(ValueError,"closed"):
            investigation.set_plan(self.db,ident,[{
                "title":"Late","acceptance":"Should fail"}])

    def test_plan_requires_agent_authored_acceptance(self):
        ident=self.begin()
        with self.assertRaisesRegex(ValueError,"acceptance"):
            investigation.set_plan(self.db,ident,[{"title":"Guess"}])

    def test_target_changes_cause_failed_review_gate(self):
        ident=self.begin()
        self.plan(ident)
        self.binary.write_bytes(b"changed")
        output=investigation.review(self.db,ident)
        self.assertEqual(output["checks"][0]["state"],"FAIL")
        self.assertFalse(output["ready_for_review"])

    def test_unbound_target_never_passes_identity_gate(self):
        ident=investigation.begin(
            self.db, "Investigate unknown client binary without a selected ELF"
        )["investigation_id"]
        investigation.set_plan(self.db, ident, [
            {"title": "Find input", "acceptance": "Identify the exact binary"}
        ])
        verdict=investigation.review(self.db, ident)
        self.assertEqual(verdict["checks"][0]["state"], "FAIL")
        self.assertFalse(verdict["ready_for_review"])

if __name__=="__main__":
    unittest.main()
