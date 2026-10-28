import tempfile
import unittest
from pathlib import Path
from scripts.check_p3b_gacha_contract import has_swallowed_rpc, inspect

STUB = '''
func (h *AuthHandler) handleSkillCast(conn *tcp.ClientConn, pkt *protocol.Packet) error {
 if strings.Contains(str, ":") || strings.HasPrefix(str,"drawCard") {
  h.logger.Info("client command RPC received", slog.String("cmd",str))
  return nil
 }
 return conn.SendPacket(pw)
}
'''

class P3bContractAuditTest(unittest.TestCase):
    def test_generic_rpc_swallow_detected(self):
        self.assertTrue(has_swallowed_rpc(STUB))

    def test_source_gate_cannot_prove_android(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = {
                "game-server/internal/session/handler.go": STUB,
                "game-server/internal/protocol/opcodes.go": "const (OpcodeEntityMoveSync byte = 0x20)",
                "docs/production/P3B_HERO_ONBOARDING_PREFLIGHT_BLOCKED_REPORT.md": "BLOCKED",
            }
            for name, value in paths.items():
                p = root / name
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(value, encoding="utf8")
            found = inspect(root)
            self.assertEqual(found["status"], "BLOCKED")
            self.assertEqual(found["android_e2e"], "NOT_RUN")

    def test_missing_sources_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(inspect(Path(tmp))["status"], "BLOCKED")
