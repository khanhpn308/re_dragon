#!/usr/bin/env python3
"""Offline consistency gate for RE Dragon Go Standard v1.1.

This checks DOCUMENT integrity and applicability, not Go build correctness.
No third-party network connections, source mutations, or dependency installation.
"""
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import re
import sys

SOURCE_COUNTS = {
    "GGS": 14, "GB": 10, "AR": 8, "GO": 14, "CT": 9,
    "MQ": 12, "SC": 8, "DB": 10, "RT": 11, "OB": 12,
    "SE": 9, "TS": 11, "QG": 8, "AI": 12,
}
DECISION_COUNTS = {"ADOPT": 86, "ADAPT": 26, "EXCLUDE": 36}
EXCLUDED = {
    *[f"CT-{i:03d}" for i in range(1, 10)],
    *[f"MQ-{i:03d}" for i in range(1, 13)],
    *[f"SC-{i:03d}" for i in range(1, 9)],
    "AR-005", "OB-005", "SE-005",
    "TS-004", "TS-005", "TS-006", "QG-008",
}
GAME_PREFIX_COUNTS = {
    "TCP": 5, "AUTH": 2, "DOMAIN": 3, "DB-GAME": 2,
    "SEC-GAME": 1, "E2E-GAME": 2, "GOV-GAME": 1,
}
EXTRA_PREFIX_COUNTS = {
    "PERF-GAME": 2, "DB-GAME": 3, "OPS-GAME": 1,
    "SEC-GAME": 1, "E2E-GAME": 1, "GOV-GAME": 1,
}
REGISTRY_ROW = re.compile(r"^\| (?P<id>[A-Z]+-\d{3}) \| (?P<decision>ADOPT|ADAPT|EXCLUDE) \| (?P<rest>.*) \|$")
GAME_ROW = re.compile(r"^\| (?P<id>(?:TCP|AUTH|DOMAIN|DB-GAME|SEC-GAME|E2E-GAME|GOV-GAME)-\d{3}) \|")
EXTRA_ROW = re.compile(r"^\| (?P<id>(?:PERF-GAME|DB-GAME|OPS-GAME|SEC-GAME|E2E-GAME|GOV-GAME)-\d{3}) \|")
RANGE = re.compile(r"(?<![\w-])([A-Z][A-Z-]*-)(\d{3})(?:\.\.(\d{3}))?")
TASK_ROW = re.compile(r"^\| (?:H0 /|S[1-6] /|Startup/CI /|Telemetry/security /)")


def expand_rule_refs(text: str) -> set[str]:
    """Inclusive same-family short ranges, e.g. GO-001..014."""
    found: set[str] = set()
    for m in RANGE.finditer(text):
        prefix, start, end = m.group(1), int(m.group(2)), m.group(3)
        stop = int(end) if end is not None else start
        if stop < start or stop - start > 300:
            raise ValueError(f"bad rule reference {m.group(0)}")
        found.update(f"{prefix}{i:03d}" for i in range(start, stop + 1))
    return found


def validate(root: Path) -> list[str]:
    folder = root / "docs" / "production"
    files = {
        "registry": folder / "GO_GAME_SERVER_RULE_REGISTRY_V1_1.md",
        "standard": folder / "GO_GAME_SERVER_AGENT_STANDARD_V1_1.md",
        "matrix": folder / "GO_GAME_SERVER_RULE_MATRIX_V1_1.md",
        "v1": folder / "GO_GAME_SERVER_AGENT_STANDARD_V1.md",
        "agents": root / "AGENTS.md",
    }
    errors: list[str] = []
    for key, file in files.items():
        if not file.is_file():
            errors.append(f"missing {key}: {file.relative_to(root)}")
    if errors:
        return errors

    registry = files["registry"].read_text(encoding="utf-8")
    standard = files["standard"].read_text(encoding="utf-8")
    matrix = files["matrix"].read_text(encoding="utf-8")
    agents = files["agents"].read_text(encoding="utf-8")

    rows: dict[str, str] = {}
    for line in registry.splitlines():
        m = REGISTRY_ROW.fullmatch(line)
        if not m:
            continue
        ident, status = m.group("id"), m.group("decision")
        if ident in rows:
            errors.append(f"duplicate upstream rule ID {ident}")
        rows[ident] = status
        rest = m.group("rest")
        if status == "EXCLUDE" and "Not applicable" not in rest:
            errors.append(f"excluded rule missing disposition {ident}")
        if status == "ADAPT" and "Upstream" not in rest:
            errors.append(f"adapted rule missing traceable origin {ident}")
    observed = Counter(rows.values())
    if len(rows) != 148:
        errors.append(f"registry must contain 148 unique source IDs, found {len(rows)}")
    for name, number in DECISION_COUNTS.items():
        if observed[name] != number:
            errors.append(f"{name} count {observed[name]} != {number}")
    families = Counter(i.split("-")[0] for i in rows)
    for family, number in SOURCE_COUNTS.items():
        if families[family] != number:
            errors.append(f"{family} source IDs: {families[family]} != {number}")
    if set(rows) & EXCLUDED != EXCLUDED:
        errors.append(f"missing excluded IDs: {sorted(EXCLUDED - set(rows))}")
    for ident in EXCLUDED:
        if rows.get(ident) != "EXCLUDE":
            errors.append(f"upstream domain-specific rule {ident} is not excluded")

    if "source_standard_blob_sha: 7e08b93fdae6f86b61b06fc71837e80ec175aed4" not in registry:
        errors.append("missing immutable LoRa source blob provenance")
    if "status: OWNER_APPROVED_CONTENT_STAGED_FOR_PINNED_V2_ADOPTION" not in standard:
        errors.append("addendum status must be scoped staged approval, not automatic activation")
    if "NOT_RUN_NO_MODULE" not in standard:
        errors.append("missing honest no-Go-module result")
    if "RULE_IDS_APPLICABLE" not in standard:
        errors.append("missing task-level rule evidence record")
    if "V2 Go Standard v1.1" not in agents:
        errors.append("root AGENTS routing to scoped addendum missing")

    section = standard.split("## 2. Core game-server rules", 1)
    if len(section) < 2:
        errors.append("missing carried game-rule table")
        game_ids: set[str] = set()
    else:
        carried = section[1].split("## 3.", 1)[0]
        all_game = [m.group("id") for line in carried.splitlines() if (m := GAME_ROW.match(line))]
        game_ids = set(all_game)
        if len(game_ids) != 16 or len(all_game) != 16:
            errors.append(f"expected 16 unique game baseline rules; found {len(game_ids)}")
        for prefix, count in GAME_PREFIX_COUNTS.items():
            if len([x for x in game_ids if x.startswith(prefix + "-")]) != count:
                errors.append(f"bad baseline game family {prefix}")

    extra = standard.split("## 3. V1.1 clarifications", 1)
    if len(extra) < 2:
        errors.append("missing v1.1 game clarifications")
        extra_ids: set[str] = set()
    else:
        block = extra[1].split("## 4.", 1)[0]
        extra_all = [m.group("id") for line in block.splitlines() if (m := EXTRA_ROW.match(line))]
        extra_ids = set(extra_all)
        if len(extra_ids) != 9 or len(extra_all) != 9:
            errors.append(f"expected 9 distinct additional game rules; found {len(extra_ids)}")
        for prefix, count in EXTRA_PREFIX_COUNTS.items():
            if len([x for x in extra_ids if x.startswith(prefix + "-")]) != count:
                errors.append(f"bad v1.1 game family {prefix}")
    if game_ids & extra_ids:
        errors.append("game rule ID collision between baseline and addendum")

    valid_rules = set(rows) | game_ids | extra_ids
    tasks = [line for line in matrix.splitlines() if TASK_ROW.match(line)]
    if len(tasks) != 9:
        errors.append(f"expected nine task applicability matrix rows, found {len(tasks)}")
    for line in tasks:
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 6:
            errors.append("malformed matrix task row")
            continue
        for ident in expand_rule_refs(parts[2] + " " + parts[3]):
            if ident not in valid_rules:
                errors.append(f"unknown matrix rule {ident} in {parts[1]}")
            elif rows.get(ident) == "EXCLUDE":
                errors.append(f"excluded matrix rule {ident} in {parts[1]}")
    if "GO_GAME_SERVER_RULE_REGISTRY_V1_1.md" not in matrix:
        errors.append("applicability matrix does not link registry")
    if "GO_GAME_SERVER_RULE_MATRIX_V1_1.md" not in standard:
        errors.append("rulebook does not link applicability matrix")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    errors = validate(args.root.resolve())
    if errors:
        for problem in errors:
            print(f"FAIL: {problem}", file=sys.stderr)
        return 1
    print("PASS: rulebook documentation consistency (148 original, 112 active, 36 excluded; 16 baseline game, 9 V1.1 game)")
    print("NOT_RUN: Go build, tests, PostgreSQL, Android E2E, 5000 CCU (documentation validator only)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
