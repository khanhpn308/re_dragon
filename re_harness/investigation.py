"""Agent-owned reverse-engineering investigations, persisted behind Harness MCP.

The LLM Agent is the only planner and REA MCP caller. This module stores
provenance, explicit uncertainty and checkpoint state, without invoking REA.
Python's job is persistence, input validation and mechanically checkable gates.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from pathlib import Path

from . import core

STATUSES = {"planned", "in_progress", "blocked", "ready_for_review", "closed"}
ASSESSMENTS = {"VERIFIED", "INFERRED", "UNKNOWN"}
MILESTONES = {"pending", "in_progress", "done", "blocked"}
SAFE_TOOL = re.compile(r"^[a-zA-Z0-9_.:/-]{2,128}$")


def _uuid():
    return uuid.uuid4().hex[:16]


def _value(value, label, limit=4000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{label} must be a nonempty string <= {limit} characters")
    return value.strip()


def _details(value, label="details"):
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 100:
        raise ValueError(f"{label} must be a list of no more than 100 strings")
    return [_value(x, label, 3000) for x in value]


def migrate(db):
    db.executescript("""
      CREATE TABLE IF NOT EXISTS investigations (
        id TEXT PRIMARY KEY,
        goal TEXT NOT NULL,
        binary_path TEXT,
        binary_sha256 TEXT,
        agent TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS investigation_steps (
        id TEXT PRIMARY KEY,
        investigation_id TEXT NOT NULL REFERENCES investigations(id),
        ordinal INTEGER NOT NULL,
        title TEXT NOT NULL,
        acceptance TEXT NOT NULL,
        status TEXT NOT NULL,
        note TEXT,
        updated_at TEXT NOT NULL,
        UNIQUE(investigation_id, ordinal)
      );
      CREATE TABLE IF NOT EXISTS rea_observations (
        id TEXT PRIMARY KEY,
        investigation_id TEXT NOT NULL REFERENCES investigations(id),
        step_id TEXT REFERENCES investigation_steps(id),
        tool TEXT NOT NULL,
        rea_evidence_id TEXT,
        target_sha256 TEXT,
        summary TEXT NOT NULL,
        limitations_json TEXT NOT NULL,
        receipt_status TEXT NOT NULL,
        created_at TEXT NOT NULL
      );
      CREATE UNIQUE INDEX IF NOT EXISTS ux_rea_receipt
        ON rea_observations(investigation_id, tool, rea_evidence_id)
        WHERE rea_evidence_id IS NOT NULL;
      CREATE TABLE IF NOT EXISTS investigation_findings (
        id TEXT PRIMARY KEY,
        investigation_id TEXT NOT NULL REFERENCES investigations(id),
        statement TEXT NOT NULL,
        assessment TEXT NOT NULL,
        symbol TEXT,
        address TEXT,
        rationale TEXT NOT NULL,
        observation_ids_json TEXT NOT NULL,
        created_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS investigation_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        investigation_id TEXT NOT NULL,
        kind TEXT NOT NULL,
        details_json TEXT NOT NULL,
        created_at TEXT NOT NULL
      );
    """)
    db.commit()


def _event(db, ident, name, data=None):
    db.execute(
        "INSERT INTO investigation_events(investigation_id,kind,details_json,created_at)"
        " VALUES(?,?,?,?)",
        (ident, name, json.dumps(data or {}, ensure_ascii=False), core.now()),
    )


def _get(db, ident):
    investigation = db.execute(
        "SELECT * FROM investigations WHERE id=?", (ident,)
    ).fetchone()
    if investigation is None:
        raise ValueError("Unknown investigation_id")
    return investigation


def _ensure_active(row):
    if row["status"] == "closed":
        raise ValueError("Investigation is closed; create a new investigation for new work")


def _local_target(binary_path):
    if binary_path is None:
        return None, None
    path = Path(_value(binary_path, "binary_path", 4096)).expanduser().resolve()
    if not path.is_file():
        raise ValueError("Selected local binary does not exist")
    if path.suffix.lower() not in {".so", ".elf", ".apk", ".xapk", ".dex", ".bin"}:
        raise ValueError("Expected a local binary/archive input")
    return str(path), core.sha256(path)


def begin(db, goal, agent="codex-or-antigravity", binary_path=None):
    """Create a research objective; Agent must author the plan via set_plan."""
    migrate(db)
    goal = _value(goal, "goal", 12000)
    agent = _value(agent, "agent", 150)
    binary, digest = _local_target(binary_path)
    ident = _uuid()
    stamp = core.now()
    with db:
        db.execute(
            "INSERT INTO investigations VALUES(?,?,?,?,?,?,?,?)",
            (ident, goal, binary, digest, agent, "planned", stamp, stamp),
        )
        _event(db, ident, "created", {"binary": Path(binary).name if binary else None})
    return {"investigation_id": ident, "status": "planned",
            "binary_sha256": digest, "needs_agent_plan": True,
            "next_tool": "harness_set_investigation_plan"}


def set_plan(db, ident, steps):
    row = _get(db, ident)
    _ensure_active(row)
    if not isinstance(steps, list) or not 1 <= len(steps) <= 20:
        raise ValueError("Agent plan must have 1–20 ordered steps")
    validated = []
    for entry in steps:
        if not isinstance(entry, dict):
            raise ValueError("Plan step must be an object")
        title = _value(entry.get("title"), "step title", 240)
        acceptance = _value(entry.get("acceptance"), "acceptance criterion", 1200)
        validated.append((title, acceptance))
    current = db.execute(
        "SELECT COUNT(*) FROM investigation_steps WHERE investigation_id=?",
        (ident,),
    ).fetchone()[0]
    if current:
        raise ValueError("Plan already exists; use milestone updates instead")
    with db:
        for i, (title, acceptance) in enumerate(validated, start=1):
            db.execute(
                "INSERT INTO investigation_steps VALUES(?,?,?,?,?,?,?,?)",
                (_uuid(), ident, i, title, acceptance, "pending", None, core.now()),
            )
        db.execute(
            "UPDATE investigations SET status='in_progress',updated_at=? WHERE id=?",
            (core.now(), ident),
        )
        _event(db, ident, "agent_plan_set", {"step_count": len(validated)})
    return {"investigation_id": ident, "status": "in_progress",
            "milestones": len(validated), "decision_owner": "Codex/Antigravity"}


def _step(db, ident, ordinal):
    if not isinstance(ordinal, int) or isinstance(ordinal, bool) or ordinal < 1:
        raise ValueError("step must be a positive integer")
    result = db.execute(
        "SELECT * FROM investigation_steps "
        "WHERE investigation_id=? AND ordinal=?",
        (ident, ordinal),
    ).fetchone()
    if result is None:
        raise ValueError("Unknown step in this investigation")
    return result


def set_step(db, ident, ordinal, status, note=None):
    row = _get(db, ident)
    _ensure_active(row)
    milestone = _step(db, ident, ordinal)
    if status not in MILESTONES:
        raise ValueError("Invalid milestone state")
    if status == "done" and not db.execute(
        "SELECT 1 FROM rea_observations WHERE investigation_id=? AND step_id=?",
        (ident, milestone["id"]),
    ).fetchone():
        raise ValueError("A completed milestone must reference at least one REA observation")
    if note is not None and (not isinstance(note, str) or len(note) > 3000):
        raise ValueError("Note must be a string <= 3000 characters")
    with db:
        db.execute(
            "UPDATE investigation_steps SET status=?,note=?,updated_at=? WHERE id=?",
            (status, note, core.now(), milestone["id"]),
        )
        db.execute(
            "UPDATE investigations SET status=?,updated_at=? WHERE id=?",
            ("blocked" if status == "blocked" else "in_progress", core.now(), ident),
        )
        _event(db, ident, "milestone_updated", {"step": ordinal, "status": status})
    return {"step": ordinal, "status": status}


def record_rea(db, ident, tool, summary, evidence_id=None,
               step=None, limitations=None, target_sha256=None):
    """Store an Agent-provided REA MCP receipt. Never claim we authenticated it."""
    row = _get(db, ident)
    _ensure_active(row)
    if not isinstance(tool, str) or not SAFE_TOOL.fullmatch(tool):
        raise ValueError("Invalid REA MCP tool identifier")
    summary = _value(summary, "summary", 12000)
    evidence_id = _value(evidence_id, "evidence_id", 200) if evidence_id else None
    if target_sha256 is not None and not re.fullmatch(r"[0-9a-fA-F]{64}", target_sha256):
        raise ValueError("target_sha256 must be 64 hex digits")
    if row["binary_sha256"] and target_sha256 and target_sha256.lower() != row["binary_sha256"]:
        raise ValueError("REA result is associated with a different target binary SHA-256")
    caveats = _details(limitations, "limitations")
    step_id = _step(db, ident, step)["id"] if step is not None else None
    if evidence_id:
        prior = db.execute(
            "SELECT id FROM rea_observations "
            "WHERE investigation_id=? AND tool=? AND rea_evidence_id=?",
            (ident, tool, evidence_id),
        ).fetchone()
        if prior:
            return {"observation_id": prior["id"], "duplicate": True}
    observation_id = _uuid()
    with db:
        db.execute(
            "INSERT INTO rea_observations VALUES(?,?,?,?,?,?,?,?,?,?)",
            (observation_id, ident, step_id, tool, evidence_id,
             target_sha256.lower() if target_sha256 else None, summary,
             json.dumps(caveats, ensure_ascii=False),
             "agent_reported_not_authenticated", core.now()),
        )
        db.execute("UPDATE investigations SET updated_at=? WHERE id=?",
                   (core.now(), ident))
        _event(db, ident, "rea_receipt_recorded", {"tool": tool,
                  "observation_id": observation_id, "step": step})
    return {"observation_id": observation_id, "duplicate": False,
            "receipt_status": "agent_reported_not_authenticated",
            "warning": "The harness did not independently authenticate the REA result"}


def record_finding(db, ident, statement, assessment, rationale,
                   observation_ids=None, symbol=None, address=None):
    """Findings always link to observations for VERIFIED; G4 remains human review."""
    row = _get(db, ident)
    _ensure_active(row)
    statement = _value(statement, "statement", 12000)
    rationale = _value(rationale, "rationale", 6000)
    if assessment not in ASSESSMENTS:
        raise ValueError("Invalid finding assessment")
    if symbol is not None:
        symbol = _value(symbol, "symbol", 1000)
    if address is not None:
        address = _value(address, "address", 300)
    refs = observation_ids if observation_ids is not None else []
    if not isinstance(refs, list) or len(refs) > 30 or any(
            not isinstance(i, str) for i in refs):
        raise ValueError("observation_ids must be a list of <=30 identifiers")
    refs = list(dict.fromkeys(refs))
    if refs:
        placeholders = ",".join("?" for _ in refs)
        found = db.execute(
            f"SELECT COUNT(*) FROM rea_observations "
            f"WHERE investigation_id=? AND id IN ({placeholders})",
            (ident, *refs),
        ).fetchone()[0]
        if found != len(refs):
            raise ValueError("All linked observations must belong to this investigation")
    if assessment == "VERIFIED" and (not refs or not (symbol or address)):
        raise ValueError("VERIFIED requires linked REA observation(s) and symbol/address")
    finding_id = _uuid()
    with db:
        db.execute(
            "INSERT INTO investigation_findings VALUES(?,?,?,?,?,?,?,?,?)",
            (finding_id, ident, statement, assessment, symbol, address, rationale,
             json.dumps(refs), core.now()),
        )
        _event(db, ident, "finding_recorded",
               {"finding_id": finding_id, "assessment": assessment})
    return {"finding_id": finding_id, "assessment": assessment,
            "semantic_review": "required"}


def status(db, ident=None):
    migrate(db)
    if ident is None:
        return {"investigations": [dict(x) for x in db.execute(
            "SELECT id,goal,status,agent,updated_at FROM investigations "
            "ORDER BY updated_at DESC LIMIT 40")]}
    row = _get(db, ident)
    steps = [dict(x) for x in db.execute(
        "SELECT ordinal,title,acceptance,status,note "
        "FROM investigation_steps WHERE investigation_id=? ORDER BY ordinal", (ident,),
    )]
    observations = [dict(x) for x in db.execute(
        "SELECT id,tool,rea_evidence_id,summary,limitations_json,receipt_status "
        "FROM rea_observations WHERE investigation_id=? ORDER BY created_at", (ident,),
    )]
    findings = [dict(x) for x in db.execute(
        "SELECT * FROM investigation_findings "
        "WHERE investigation_id=? ORDER BY created_at", (ident,),
    )]
    return {"investigation": dict(row), "milestones": steps,
            "observations": observations, "findings": findings,
            "agent_action": "Review evidence, decide next REA MCP call or close with caveats"}


def review(db, ident):
    row = _get(db, ident)
    steps = db.execute(
        "SELECT status FROM investigation_steps WHERE investigation_id=?",
        (ident,),
    ).fetchall()
    facts = db.execute(
        "SELECT assessment FROM investigation_findings WHERE investigation_id=?",
        (ident,),
    ).fetchall()
    receipts = db.execute(
        "SELECT receipt_status,rea_evidence_id FROM rea_observations "
        "WHERE investigation_id=?", (ident,),
    ).fetchall()
    binary_ok = bool(row["binary_sha256"] and row["binary_path"]) and (
        Path(row["binary_path"]).is_file() and
        core.sha256(row["binary_path"]) == row["binary_sha256"]
    )
    checks = [
        {"gate": "A0_TARGET_IDENTITY", "state": "PASS" if binary_ok else "FAIL"},
        {"gate": "A1_PLAN", "state": "PASS" if steps else "FAIL"},
        {"gate": "A2_MILESTONES", "state": "PASS" if steps and all(
            s["status"] == "done" for s in steps) else "FAIL"},
        {"gate": "A3_REA_RECEIPTS", "state": "PASS" if receipts else "FAIL"},
        {"gate": "A4_FINDINGS", "state": "PASS" if facts else "FAIL"},
        {"gate": "A5_EXTERNAL_EVIDENCE_AUTHENTICITY", "state": "UNVERIFIED",
         "note": "Receipt metadata was supplied by the AI Agent, not cryptographically"
                 " authenticated against the REA MCP session"},
        {"gate": "A6_SEMANTIC_REVIEW", "state": "REVIEW_REQUIRED"},
    ]
    return {
        "investigation_id": ident, "checks": checks,
        "ready_for_review": all(x["state"] == "PASS" for x in checks[:5]),
        "meaning": "Workflow completeness only; NOT proof of protocol correctness",
    }


def report(db, state, ident):
    record = status(db, ident)
    evaluation = review(db, ident)
    state = Path(state).expanduser().resolve()
    outdir = state / "agent_reports"
    outdir.mkdir(parents=True, exist_ok=True)
    path = outdir / (ident + ".md")
    lines = [
        "# RE Dragon Agent Investigation — " + ident, "",
        "**Goal:** " + record["investigation"]["goal"], "",
        "**Agent:** " + record["investigation"]["agent"], "",
        "**Status:** " + record["investigation"]["status"], "",
        "## Milestones", "",
    ]
    for step in record["milestones"]:
        lines.append(f"- {step['ordinal']}. {step['title']} — {step['status']}")
        lines.append("  - Acceptance: " + step["acceptance"])
        if step["note"]:
            lines.append("  - Notes: " + step["note"])
    lines += ["", "## REA MCP observation receipts", ""]
    for receipt in record["observations"]:
        lines.append("- " + receipt["id"] + " [" + receipt["tool"] + "]: " +
                     receipt["summary"].replace("\n", " "))
        lines.append("  - REA Evidence ID: " +
                     (receipt["rea_evidence_id"] or "unavailable"))
        lines.append("  - Limitations: " + receipt["limitations_json"])
        lines.append("  - Trust: " + receipt["receipt_status"])
    lines += ["", "## Findings", ""]
    for finding in record["findings"]:
        lines.append("- **" + finding["assessment"] + "** " + finding["statement"])
        lines.append("  - Symbol/address: " +
                     str(finding["symbol"] or finding["address"] or "unknown"))
        lines.append("  - Observation links: " + finding["observation_ids_json"])
        lines.append("  - Rationale: " + finding["rationale"])
    lines += ["", "## Gates", ""]
    for entry in evaluation["checks"]:
        lines.append("- " + entry["gate"] + ": " + entry["state"])
    lines += [
        "", "This report stores Agent-provided REA receipts, not independently",
        "authenticated decompiler output. Inspect original REA MCP Evidence",
        "and coverage limitations before a VERIFIED protocol claim is accepted.", "",
    ]
    tmp = path.with_suffix(".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    tmp.replace(path)
    return {"path": str(path), "ready_for_review": evaluation["ready_for_review"]}


def close(db, ident, note):
    row = _get(db, ident)
    _ensure_active(row)
    note = _value(note, "closure note", 6000)
    result = review(db, ident)
    with db:
        db.execute(
            "UPDATE investigations SET status='closed',updated_at=? WHERE id=?",
            (core.now(), ident),
        )
        _event(db, ident, "closed",
               {"ready_for_review": result["ready_for_review"], "note": note})
    return {"investigation_id": ident, "status": "closed",
            "ready_for_review": result["ready_for_review"],
            "semantic_review": "required",
            "closure_note": note}
