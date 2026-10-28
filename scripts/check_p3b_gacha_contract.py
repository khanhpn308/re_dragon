#!/usr/bin/env python3
"""P3b source-only audit. Never claims physical Android gameplay PASS."""
import argparse
import json
import re
from pathlib import Path

def has_swallowed_rpc(source):
    match = re.search(r'func\s+\(h\s+\*AuthHandler\)\s+handleSkillCast\b.*?(?=\nfunc\s|\Z)', source, re.S)
    if match is None:
        return False
    return bool(re.search(
        r'if\s+strings\.Contains\s*\(\s*str\s*,\s*":"\s*\).*?client command RPC received.*?return\s+nil',
        match.group(0), re.S))

def inspect(root):
    base = root / "game-server/internal/session"
    handler = base / "handler.go"
    opcodes = root / "game-server/internal/protocol/opcodes.go"
    blocked_report = root / "docs/production/P3B_HERO_ONBOARDING_PREFLIGHT_BLOCKED_REPORT.md"
    contract = root / "docs/production/P3B_GACHA_S2C_CONTRACT.md"
    wire_test = base / "gacha_wire_test.go"
    required = [handler, opcodes, blocked_report]
    missing = [str(x.relative_to(root)) for x in required if not x.is_file()]
    checks = {}
    if not missing:
        code = handler.read_text(encoding="utf8")
        op = opcodes.read_text(encoding="utf8")
        checks = {
            "drawCard_not_swallowed_by_generic_RPC": not has_swallowed_rpc(code),
            "source_cited_client_S2C_contract_present": contract.is_file() and contract.stat().st_size > 0,
            "targeted_packet_wire_test_present": wire_test.is_file() and wire_test.stat().st_size > 0,
            "opcode_0x20_preserved_as_movement": bool(re.search(r"OpcodeEntityMoveSync\s+byte\s*=\s*0x20\b", op)),
        }
    status = "SOURCE_GATE_PASS_ANDROID_NOT_RUN" if checks and all(checks.values()) else "BLOCKED"
    return {
        "status": status, "checks": checks, "missing_sources": missing,
        "android_e2e": "NOT_RUN", "independent_visual_review": "NOT_RUN",
        "lua_mType_causality": "UNVERIFIED",
        "notes": "CI cannot replace genuine client Lua/S2C tracing or physical Android verification.",
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", type=Path, default=Path("."))
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--fail-closed", action="store_true")
    opts = ap.parse_args()
    result = inspect(opts.repo.resolve())
    opts.out_dir.mkdir(parents=True, exist_ok=True)
    (opts.out_dir / "p3b_gacha_contract.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf8")
    lines = ["# P3b Gacha S2C contract audit", "", "**"+result["status"]+"**", "",
             "| Source check | Result |", "|---|---|"]
    for k, ok in result["checks"].items():
        lines.append("| "+k+" | "+("PASS" if ok else "BLOCKED")+" |")
    lines += ["", "**Android E2E: NOT_RUN. Visual review: NOT_RUN.**", "",
              "This check cannot establish the original Lua callback and S2C response.",
              "Do not assume the mType=nil exception was caused by absent Go S2C.",
              "Never invent a gacha opcode or grant heroes directly into a live account.",
              ""]
    md = "\n".join(lines)
    (opts.out_dir / "p3b_gacha_contract.md").write_text(md, encoding="utf8")
    print(md)
    return 2 if opts.fail_closed and result["status"] == "BLOCKED" else 0

if __name__ == "__main__":
    raise SystemExit(main())
