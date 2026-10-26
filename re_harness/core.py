"""MVP orchestration: local REA commands, durable tasks, evidence and review gates.

No untrusted shell execution. This module does not contact the game server.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE = ROOT / ".re_harness_mvp"
DEFAULT_WORKFLOW = ROOT / "workflows" / "network-handshake.json"
OPERATIONS = {"inspect", "search", "function", "decompile"}
ASSESSMENTS = {"VERIFIED", "INFERRED", "UNKNOWN"}


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def as_dict(record):
    return dict(record) if record is not None else None


def database(state=DEFAULT_STATE):
    state = Path(state).expanduser().resolve()
    state.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(state / "state.sqlite3", timeout=30)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,
            binary_path TEXT NOT NULL,
            binary_sha256 TEXT NOT NULL,
            workflow TEXT NOT NULL,
            provider TEXT NOT NULL,
            rea_bin TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES runs(id),
            ordinal INTEGER NOT NULL,
            key TEXT NOT NULL,
            operation TEXT NOT NULL,
            selector TEXT,
            dependencies TEXT NOT NULL,
            status TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            exit_code INTEGER,
            error TEXT,
            updated_at TEXT NOT NULL,
            UNIQUE(run_id, ordinal),
            UNIQUE(run_id, key)
        );
        CREATE TABLE IF NOT EXISTS artifacts (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL REFERENCES tasks(id),
            attempt INTEGER NOT NULL,
            stdout_path TEXT NOT NULL,
            stderr_path TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            bytes INTEGER NOT NULL,
            rea_evidence_id TEXT,
            exit_code INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            UNIQUE(task_id, attempt)
        );
        CREATE TABLE IF NOT EXISTS claims (
            id TEXT PRIMARY KEY,
            run_id TEXT NOT NULL REFERENCES runs(id),
            assessment TEXT NOT NULL,
            statement TEXT NOT NULL,
            task_key TEXT,
            symbol TEXT,
            address TEXT,
            rationale TEXT,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL REFERENCES runs(id),
            event TEXT NOT NULL,
            details_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
    """)
    return db


def event(db, run_id, name, details=None):
    db.execute(
        "INSERT INTO events (run_id, event, details_json, created_at) VALUES (?, ?, ?, ?)",
        (run_id, name, json.dumps(details or {}, ensure_ascii=False), now()),
    )


def get_run(db, run_id):
    run = db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    if run is None:
        raise ValueError("Unknown run_id: " + run_id)
    return run


def get_tasks(db, run_id):
    return db.execute(
        "SELECT * FROM tasks WHERE run_id=? ORDER BY ordinal", (run_id,)
    ).fetchall()


def latest_artifact(db, task_id):
    return db.execute(
        "SELECT * FROM artifacts WHERE task_id=? ORDER BY attempt DESC LIMIT 1",
        (task_id,),
    ).fetchone()


def load_workflow(path):
    source = Path(path).expanduser().resolve()
    definition = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(definition, dict) or not isinstance(definition.get("steps"), list):
        raise ValueError("Workflow must contain an array named steps")
    if not definition["steps"]:
        raise ValueError("Workflow has no steps")
    known = set()
    for item in definition["steps"]:
        if not isinstance(item, dict):
            raise ValueError("Each workflow step must be an object")
        key, op = item.get("key"), item.get("operation")
        selector, deps = item.get("selector"), item.get("depends_on", [])
        if not isinstance(key, str) or not key or key in known:
            raise ValueError("Workflow step keys must be unique, nonempty strings")
        if op not in OPERATIONS:
            raise ValueError("Unsupported REA operation: " + str(op))
        if (op == "inspect" and selector is not None) or (
            op != "inspect" and (not isinstance(selector, str) or not selector)
        ):
            raise ValueError("Invalid selector for step " + key)
        if not isinstance(deps, list) or any(d not in known for d in deps):
            raise ValueError("Dependencies must reference earlier step keys: " + key)
        known.add(key)
    return definition, source


def create_plan(db, binary, workflow=DEFAULT_WORKFLOW, provider="ghidra", rea_bin="rea"):
    binary = Path(binary).expanduser().resolve()
    if not binary.is_file():
        raise ValueError("Native binary not found: " + str(binary))
    if provider not in {"ghidra", "hopper", "ida"}:
        raise ValueError("Provider must be ghidra, hopper or ida")
    if not rea_bin or any(c.isspace() for c in rea_bin):
        raise ValueError("Invalid REA executable")
    definition, source = load_workflow(workflow)
    run_id, stamp = uuid.uuid4().hex[:12], now()
    with db:
        db.execute(
            "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, 'planned', ?, ?)",
            (run_id, str(binary), sha256(binary), str(source), provider,
             rea_bin, stamp, stamp),
        )
        for index, spec in enumerate(definition["steps"], start=1):
            db.execute(
                "INSERT INTO tasks (id, run_id, ordinal, key, operation, selector, "
                "dependencies, status, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)",
                (uuid.uuid4().hex, run_id, index, spec["key"], spec["operation"],
                 spec.get("selector"), json.dumps(spec.get("depends_on", [])), stamp),
            )
        event(db, run_id, "planned", {"steps": len(definition["steps"])})
    return run_id


def append_function(db, run_id, procedure):
    if not isinstance(procedure, str) or not procedure.strip() or len(procedure) > 2048:
        raise ValueError("Expected exact procedure name or address")
    get_run(db, run_id)
    with db:
        ordinal = db.execute(
            "SELECT COALESCE(MAX(ordinal), 0) FROM tasks WHERE run_id=?", (run_id,)
        ).fetchone()[0]
        keys = []
        for op in ("function", "decompile"):
            ordinal += 1
            key = "manual-" + str(ordinal)
            db.execute(
                "INSERT INTO tasks (id, run_id, ordinal, key, operation, selector, "
                "dependencies, status, updated_at) VALUES (?, ?, ?, ?, ?, ?, '[]', 'pending', ?)",
                (uuid.uuid4().hex, run_id, ordinal, key, op, procedure, now()),
            )
            keys.append(key)
        db.execute("UPDATE runs SET status='planned', updated_at=? WHERE id=?", (now(), run_id))
        event(db, run_id, "function_queued", {"selector": procedure, "task_keys": keys})
    return keys


def build_command(run, task):
    cmd = [run["rea_bin"], task["operation"], run["binary_path"]]
    if task["operation"] == "search":
        cmd += ["--pattern=" + task["selector"], "--kind", "procedures"]
    if task["operation"] in {"function", "decompile"}:
        cmd += ["--procedure=" + task["selector"]]
    return cmd + ["--provider", run["provider"], "--json"]


def extract_evidence_id(path):
    # REA may return large dossiers; keep full raw JSON on disk regardless.
    if Path(path).stat().st_size > 16 * 1024 * 1024:
        return None
    try:
        record = json.loads(Path(path).read_text(encoding="utf-8"))
        if isinstance(record, dict):
            if isinstance(record.get("evidence_id"), str):
                return record["evidence_id"]
            inner = record.get("result")
            if isinstance(inner, dict) and isinstance(inner.get("evidence_id"), str):
                return inner["evidence_id"]
    except (OSError, UnicodeError, ValueError):
        pass
    return None


@contextmanager
def exclusive(state, run_id):
    locks = state / "locks"
    locks.mkdir(parents=True, exist_ok=True)
    with (locks / (run_id + ".lock")).open("a+") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Another process is executing this run") from exc
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)


def execute(db, state, run_id, max_steps=None, retries=1, timeout=1800):
    state = Path(state).expanduser().resolve()
    if max_steps is not None and max_steps < 1:
        raise ValueError("max_steps must be positive")
    if retries < 0 or retries > 5 or timeout < 1:
        raise ValueError("Invalid retries or timeout")
    with exclusive(state, run_id):
        run = get_run(db, run_id)
        binary = Path(run["binary_path"])
        if not binary.is_file() or sha256(binary) != run["binary_sha256"]:
            raise ValueError("Binary missing or changed since planning (SHA-256 mismatch)")
        if shutil.which(run["rea_bin"]) is None:
            raise ValueError("REA executable not available: " + run["rea_bin"])
        tasks = get_tasks(db, run_id)
        completed = {t["key"] for t in tasks if t["status"] == "completed"}
        performed = 0
        failure = None
        with db:
            db.execute("UPDATE runs SET status='running', updated_at=? WHERE id=?", (now(), run_id))
        for task in tasks:
            if task["status"] == "completed":
                continue
            if max_steps is not None and performed >= max_steps:
                break
            deps = json.loads(task["dependencies"])
            if not all(dep in completed for dep in deps):
                failure = "Dependencies incomplete for " + task["key"]
                break
            performed += 1
            command = build_command(run, task)
            for _ in range(retries + 1):
                attempt = db.execute(
                    "SELECT attempts FROM tasks WHERE id=?", (task["id"],)
                ).fetchone()[0] + 1
                folder = state / "evidence" / run_id
                folder.mkdir(parents=True, exist_ok=True)
                stem = str(task["ordinal"]).zfill(2) + "_attempt_" + str(attempt)
                stdout_path, stderr_path = folder / (stem + ".json"), folder / (stem + ".stderr.txt")
                with db:
                    db.execute(
                        "UPDATE tasks SET status='running', attempts=?, error=NULL, updated_at=? "
                        "WHERE id=?", (attempt, now(), task["id"]),
                    )
                    event(db, run_id, "task_started", {"key": task["key"], "attempt": attempt})
                code, err = 127, None
                with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
                    try:
                        result = subprocess.run(
                            command, stdout=stdout, stderr=stderr,
                            timeout=timeout, check=False,
                        )
                        code = result.returncode
                    except subprocess.TimeoutExpired:
                        code, err = 124, "REA operation timed out"
                    except OSError as exc:
                        code, err = 127, "REA launch failed: " + str(exc)
                evidence_id = extract_evidence_id(stdout_path)
                # The raw response is never discarded, including failed attempts.
                with db:
                    db.execute(
                        "INSERT INTO artifacts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (uuid.uuid4().hex, task["id"], attempt,
                         str(stdout_path.relative_to(state)),
                         str(stderr_path.relative_to(state)),
                         sha256(stdout_path), stdout_path.stat().st_size,
                         evidence_id, code, now()),
                    )
                    db.execute(
                        "UPDATE tasks SET status=?, exit_code=?, error=?, updated_at=? WHERE id=?",
                        ("completed" if code == 0 else "failed", code, err, now(), task["id"]),
                    )
                    event(db, run_id, "task_finished", {
                        "key": task["key"], "attempt": attempt, "exit_code": code,
                    })
                if code == 0:
                    completed.add(task["key"])
                    break
                failure = task["key"] + " exited " + str(code)
            if task["key"] not in completed:
                break
            failure = None
        latest = get_tasks(db, run_id)
        if failure:
            status = "failed"
        elif all(t["status"] == "completed" or t["key"] in completed for t in latest):
            status = "completed"
        else:
            status = "paused"
        with db:
            db.execute("UPDATE runs SET status=?, updated_at=? WHERE id=?",
                       (status, now(), run_id))
            event(db, run_id, "execution_finished", {
                "status": status, "steps_executed": performed, "failure": failure,
            })
        report = render_report(db, state, run_id)
        return {"run_id": run_id, "status": status, "steps_executed": performed,
                "failure": failure, "report": str(report)}


def add_claim(db, run_id, statement, assessment="INFERRED",
              task_key=None, symbol=None, address=None, rationale=None):
    get_run(db, run_id)
    if assessment not in ASSESSMENTS:
        raise ValueError("assessment must be VERIFIED, INFERRED or UNKNOWN")
    if not isinstance(statement, str) or not statement.strip():
        raise ValueError("Claim statement is required")
    if task_key is not None and db.execute(
        "SELECT id FROM tasks WHERE run_id=? AND key=?", (run_id, task_key)
    ).fetchone() is None:
        raise ValueError("Unknown task_key in selected run")
    claim_id = uuid.uuid4().hex[:12]
    with db:
        db.execute(
            "INSERT INTO claims VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (claim_id, run_id, assessment, statement.strip(),
             task_key, symbol, address, rationale, now()),
        )
        event(db, run_id, "claim_added", {
            "claim_id": claim_id, "assessment": assessment,
        })
    return claim_id


def validate(db, state, run_id):
    run = get_run(db, run_id)
    state = Path(state).expanduser().resolve()
    binary = Path(run["binary_path"])
    checks = []
    checks.append({
        "gate": "G0_BINARY_IDENTITY",
        "result": "PASS" if binary.is_file() and sha256(binary) == run["binary_sha256"] else "FAIL",
        "note": "Local binary exists and its SHA-256 matches the original plan",
    })
    tasks = get_tasks(db, run_id)
    checks.append({
        "gate": "G1_TASK_EXECUTION",
        "result": "PASS" if tasks and all(t["status"] == "completed" for t in tasks) else "FAIL",
        "note": "All scheduled tasks completed with exit code zero",
    })
    evidence_good = True
    for task in tasks:
        if task["status"] != "completed":
            continue
        art = latest_artifact(db, task["id"])
        if not art:
            evidence_good = False
            break
        path = state / art["stdout_path"]
        if not path.is_file() or sha256(path) != art["sha256"] or art["exit_code"] != 0:
            evidence_good = False
            break
    checks.append({
        "gate": "G2_EVIDENCE_INTEGRITY",
        "result": "PASS" if evidence_good else "FAIL",
        "note": "Completed task outputs are present and retain their recorded SHA-256",
    })
    claims = db.execute("SELECT * FROM claims WHERE run_id=?", (run_id,)).fetchall()
    traceable = True
    for claim in claims:
        if claim["assessment"] != "VERIFIED":
            continue
        if not (claim["task_key"] and (claim["symbol"] or claim["address"])
                and claim["rationale"]):
            traceable = False
            break
        linked = next((t for t in tasks if t["key"] == claim["task_key"]), None)
        if not linked or linked["status"] != "completed" or not latest_artifact(db, linked["id"]):
            traceable = False
            break
    checks.append({
        "gate": "G3_CLAIM_PROVENANCE",
        "result": "PASS" if traceable else "FAIL",
        "note": "VERIFIED-labelled claims require a completed evidence task, "
                "symbol/address and rationale",
    })
    checks.append({
        "gate": "G4_SEMANTIC_REVIEW",
        "result": "REVIEW_REQUIRED",
        "note": "Tool success and hashes do not prove a protocol interpretation",
    })
    return {"run_id": run_id, "checks": checks,
            "ready_for_review": all(c["result"] == "PASS" for c in checks[:4])}


def status(db, run_id=None):
    if run_id is None:
        return [as_dict(r) for r in db.execute(
            "SELECT id, workflow, status, binary_path, updated_at "
            "FROM runs ORDER BY created_at DESC LIMIT 100"
        )]
    run = get_run(db, run_id)
    return {
        "run": as_dict(run),
        "tasks": [dict(t) for t in get_tasks(db, run_id)],
        "claims": [dict(c) for c in db.execute(
            "SELECT * FROM claims WHERE run_id=? ORDER BY created_at", (run_id,),
        )],
    }


def render_report(db, state, run_id):
    state = Path(state).expanduser().resolve()
    run = get_run(db, run_id)
    tasks = get_tasks(db, run_id)
    verdict = validate(db, state, run_id)
    tick = chr(96)
    lines = [
        "# RE Dragon — MVP investigation " + run_id, "",
        "- Status: **" + run["status"] + "**",
        "- Workflow: " + tick + Path(run["workflow"]).name + tick,
        "- Binary: " + tick + Path(run["binary_path"]).name + tick + " (local only)",
        "- SHA-256: " + tick + run["binary_sha256"] + tick,
        "- Provider: " + run["provider"], "",
        "## Planned tasks", "",
        "| Step | Key | REA operation | Selector | State | Attempts |",
        "|---:|---|---|---|---|---:|",
    ]
    for t in tasks:
        selector = (t["selector"] or "—").replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {t['ordinal']} | {t['key']} | {t['operation']} | {selector} | "
            f"{t['status']} | {t['attempts']} |"
        )
    lines += ["", "## Evidence index", ""]
    for t in tasks:
        art = latest_artifact(db, t["id"])
        if art is not None:
            lines += [
                "- **" + t["key"] + "**: " + tick + art["stdout_path"] + tick
                + " | SHA-256 " + tick + art["sha256"] + tick
                + " | REA evidence ID " + tick + (art["rea_evidence_id"] or "unknown") + tick,
            ]
    lines += ["", "## Claims (agent-authored; not auto-confirmed)", ""]
    claims = db.execute(
        "SELECT * FROM claims WHERE run_id=? ORDER BY created_at, id", (run_id,)
    ).fetchall()
    if not claims:
        lines.append("No claims have been recorded.")
    for claim in claims:
        lines += [
            "- **" + claim["assessment"] + "**: " + claim["statement"].replace("\n", " "),
            "  - Task: " + (claim["task_key"] or "none") +
            " | Symbol: " + (claim["symbol"] or "none") +
            " | Address: " + (claim["address"] or "none"),
            "  - Rationale: " + (claim["rationale"] or "not recorded").replace("\n", " "),
        ]
    lines += ["", "## Validation gates", "",
              "| Gate | Result | Meaning |", "|---|---|---|"]
    for gate in verdict["checks"]:
        lines.append("| " + gate["gate"] + " | " + gate["result"] + " | "
                     + gate["note"].replace("|", "\\|") + " |")
    lines += [
        "", "**Ready for manual review:** " + str(verdict["ready_for_review"]),
        "", "Semantic verification is NOT automated. Coverage gaps, unresolved calls",
        "and runtime-only behavior remain UNKNOWN unless separately supported.",
        "", "All binary and raw REA evidence paths are local-only.", "",
    ]
    folder = state / "reports"
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / (run_id + ".md")
    tmp = folder / (run_id + ".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    os.replace(tmp, dest)
    return dest
