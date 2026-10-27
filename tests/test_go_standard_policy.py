"""Contract tests for the v1.1 documentation quality gate (offline)."""
from __future__ import annotations

from pathlib import Path
import shutil
import tempfile
import unittest

from scripts.check_go_standard import expand_rule_refs, validate

ROOT = Path(__file__).resolve().parents[1]
POLICY = [
    "GO_GAME_SERVER_RULE_REGISTRY_V1_1.md",
    "GO_GAME_SERVER_AGENT_STANDARD_V1_1.md",
    "GO_GAME_SERVER_RULE_MATRIX_V1_1.md",
    "GO_GAME_SERVER_AGENT_STANDARD_V1.md",
]


class GoStandardPolicyTests(unittest.TestCase):
    def test_live_policy_is_consistent(self):
        self.assertEqual(validate(ROOT), [])

    def test_inclusive_rule_expansion(self):
        self.assertEqual(expand_rule_refs("GO-001..003, DB-GAME-002"), {
            "GO-001", "GO-002", "GO-003", "DB-GAME-002"
        })

    def test_rejects_backwards_range(self):
        with self.assertRaises(ValueError):
            expand_rule_refs("GO-007..003")

    def _scratch(self):
        temp = tempfile.TemporaryDirectory()
        root = Path(temp.name)
        (root / "docs" / "production").mkdir(parents=True)
        for p in POLICY:
            shutil.copy2(ROOT / "docs" / "production" / p, root / "docs" / "production" / p)
        shutil.copy2(ROOT / "AGENTS.md", root / "AGENTS.md")
        self.addCleanup(temp.cleanup)
        return root

    def test_missing_row_is_fatal(self):
        root = self._scratch()
        p = root / "docs/production/GO_GAME_SERVER_RULE_REGISTRY_V1_1.md"
        content = p.read_text()
        content = "\n".join(l for l in content.split("\n") if not l.startswith("| GO-001 |"))
        p.write_text(content)
        self.assertTrue(any("148 unique" in e for e in validate(root)))

    def test_excluded_rule_cannot_leak_to_matrix(self):
        root = self._scratch()
        p = root / "docs/production/GO_GAME_SERVER_RULE_MATRIX_V1_1.md"
        content = p.read_text()
        content = content.replace("TCP-001..005, PERF-GAME-002, SEC-GAME-002",
                                  "TCP-001..005, MQ-001, PERF-GAME-002, SEC-GAME-002")
        p.write_text(content)
        self.assertTrue(any("excluded matrix rule MQ-001" in e for e in validate(root)))

    def test_unknown_rule_cannot_leak_to_matrix(self):
        root = self._scratch()
        p = root / "docs/production/GO_GAME_SERVER_RULE_MATRIX_V1_1.md"
        content = p.read_text().replace(
            "TCP-001..005, PERF-GAME-002, SEC-GAME-002",
            "TCP-001..005, UNKNOWN-999, PERF-GAME-002, SEC-GAME-002")
        p.write_text(content)
        self.assertTrue(any("unknown matrix rule UNKNOWN-999" in e for e in validate(root)))


if __name__ == "__main__":
    unittest.main()
