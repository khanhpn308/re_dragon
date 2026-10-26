#!/usr/bin/env python3
"""REA reverse-engineering harness prototype: persistent jobs and evidence.

Python standard library only. All REA analysis is delegated to the local CLI.
No APK/ELF bytes are uploaded or committed by this program.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path


PROJECT = Path(__file__).resolve().parent.parent
DEFAULT_STATE = PROJECT / ".re_harness"
DEFAULT_QUERIES = ("CProtocolManager", "Conexao")


def utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def connect(state: Path) -> sqlite3.Connection:
    state.mkdir(parents=True, exist_ok=True)
    database = sqlite3.connect(state / "state.sqlite3")
    database.row_factory = sqlite3.Row
    database.execute("PRAGMA foreign_keys=ON")
    database.executescript(
        """
        CREATE TABLE IF NOT EXISTS runs (
            id TEXT PRIMARY KEY,
            binary_path TEXT NOT NULL,
            binary_sha256 TEXT NOT NULL,
            provider TEXT NOT NULL,
            rea_executable TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS steps (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL REFERENCES runs(id),
            ordinal INTEGER NOT NULL,
            operation TEXT NOT NULL,
            selector TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            exit_code INTEGER,
            started_at TEXT,
            ended_at TEXT,
            error_message TEXT,
            UNIQUE(run_id, ordinal)
        );
        CREATE TABLE IF NOT EXISTS evidence (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            step_id INTEGER NOT NULL UNIQUE REFERENCES steps(id),
            command_json TEXT NOT NULL,
            output_path TEXT NOT NULL,
            stderr_path TEXT NOT NULL,
            stdout_sha256 TEXT NOT NULL,
            stdout_bytes INTEGER NOT NULL,
            rea_evidence_id TEXT,
            created_at TEXT NOT NULL
        );
        """
    )
    return database


def plan(database: sqlite3.Connection, binary: Path, provider: str,
         rea: str, queries: list[str], function: str | None) -> str:
    if not binary.is_file():
        raise ValueError(f"Binary not found: {binary}")
    run_id = uuid.uuid4().hex[:12]
    now = utc()
    steps: list[tuple[str, str | None]] = [("inspect", None)]
    steps.extend(("search", q) for q in queries)
    if function:
        steps.extend((("function", function), ("decompile", function)))
    with database:
        database.execute(
            "INSERT INTO runs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (run_id, str(binary), digest(binary), provider, rea,
             "pending", now, now),
        )
        database.executemany(
            "INSERT INTO steps (run_id, ordinal, operation, selector, status)"
            " VALUES (?, ?, ?, ?, 'pending')",
            [(run_id, i + 1, name, selector)
             for i, (name, selector) in enumerate(steps)],
        )
    return run_id


def command_for(run: sqlite3.Row, step: sqlite3.Row) -> list[str]:
    command = [run["rea_executable"], step["operation"], run["binary_path"]]
    selector = step["selector"]
    if step["operation"] == "search":
        command.extend([f"--pattern={selector}", "--kind", "procedures"])
    elif step["operation"] in ("function", "decompile"):
        command.append(f"--procedure={selector}")
    command.extend(["--provider", run["provider"], "--json"])
    return command


def evidence_id_of(path: Path) -> str | None:
    # The complete raw output stays on disk. Do not load giant native dossiers.
    if path.stat().st_size > 16 * 1024 * 1024:
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError, OSError):
        return None
    if isinstance(record, dict):
        value = record.get("evidence_id")
        if isinstance(value, str):
            return value
        result = record.get("result")
        if isinstance(result, dict) and isinstance(result.get("evidence_id"), str):
            return result["evidence_id"]
    return None


def write_report(database: sqlite3.Connection, state: Path,
                 run_id: str) -> Path:
    run = database.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    if run is None:
        raise ValueError(f"Unknown run: {run_id}")
    steps = database.execute(
        "SELECT s.*, e.command_json, e.output_path, e.stderr_path, "
        "e.stdout_sha256, e.stdout_bytes, e.rea_evidence_id "
        "FROM steps s LEFT JOIN evidence e ON e.step_id=s.id "
        "WHERE s.run_id=? ORDER BY s.ordinal", (run_id,),
    ).fetchall()
    lines = [
        f"# REA Investigation — {run_id}",
        "",
        f"- Status: **{run['status']}**",
        f"- Binary: \`{Path(run['binary_path']).name}\` (local only)",
        f"- SHA-256: \`{run['binary_sha256']}\`",
        f"- Provider: \`{run['provider']}\`",
        f"- Started: {run['created_at']}",
        f"- Updated: {run['updated_at']}",
        "",
        "## Execution record",
        "",
        "| # | Operation | Selector | Status | Exit |",
        "|---|---|---|---|---|",
    ]
    for s in steps:
        selector = (s["selector"] or "—").replace("|", "\\|").replace("\n", " ")
        lines.append(
            f"| {s['ordinal']} | {s['operation']} | {selector} | "
            f"{s['status']} | {s['exit_code'] if s['exit_code'] is not None else '—'} |"
        )
    lines += ["", "## Evidence files", ""]
    for s in steps:
        if s["output_path"]:
            lines += [
                f"### Step {s['ordinal']}: {s['operation']}",
                f"- Raw JSON: \`{s['output_path']}\`",
                f"- Standard error: \`{s['stderr_path']}\`",
                f"- SHA-256: \`{s['stdout_sha256']}\`",
                f"- Bytes: {s['stdout_bytes']}",
                f"- REA evidence ID: \`{s['rea_evidence_id'] or 'not extracted'}\`",
                "",
            ]
        elif s["error_message"]:
            lines += [f"- Step {s['ordinal']}: {s['error_message']}", ""]
    lines += [
        "## Interpretation boundary",
        "",
        "A successful tool invocation does **not** establish that every discovered",
        "symbol, inferred call edge, packet format, or runtime behavior is verified.",
        "Inspect the retained REA JSON, coverage, and limitations before assigning",
        "VERIFIED / INFERRED / UNKNOWN to technical claims.",
        "",
        "This prototype does not contact the game's production server.",
        "",
    ]
    report = state / "reports" / f"{run_id}.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("\n".join(lines), encoding="utf-8")
    return report


def execute(database: sqlite3.Connection, state: Path, run_id: str,
            timeout: int | None) -> int:
    run = database.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    if run is None:
        raise ValueError(f"Unknown run: {run_id}")
    binary = Path(run["binary_path"])
    if not binary.is_file() or digest(binary) != run["binary_sha256"]:
        raise ValueError("Binary is absent or SHA-256 changed; refusing to resume")
    if shutil.which(run["rea_executable"]) is None:
        raise ValueError(f"REA executable not found: {run['rea_executable']}")
    evidence_dir = state / "evidence" / run_id
    evidence_dir.mkdir(parents=True, exist_ok=True)
    with database:
        database.execute(
            "UPDATE runs SET status='running', updated_at=? WHERE id=?",
            (utc(), run_id),
        )
    pending = database.execute(
        "SELECT * FROM steps WHERE run_id=? AND status!='completed' "
        "ORDER BY ordinal", (run_id,),
    ).fetchall()
    for step in pending:
        command = command_for(run, step)
        prefix = evidence_dir / f"{step['ordinal']:02d}_{step['operation']}"
        out_path = Path(str(prefix) + ".json")
        err_path = Path(str(prefix) + ".stderr.txt")
        print(f"[{run_id}] {step['ordinal']}: {step['operation']} "
              f"{step['selector'] or ''}", flush=True)
        with database:
            database.execute(
                "UPDATE steps SET status='running', started_at=?, "
                "ended_at=NULL, error_message=NULL WHERE id=?",
                (utc(), step["id"]),
            )
        exit_code = 1
        reason = None
        with out_path.open("wb") as stdout, err_path.open("wb") as stderr:
            try:
                completed = subprocess.run(
                    command, stdout=stdout, stderr=stderr,
                    check=False, timeout=timeout,
                )
                exit_code = completed.returncode
            except subprocess.TimeoutExpired:
                exit_code = 124
                reason = f"Command exceeded {timeout} seconds"
            except OSError as exc:
                exit_code = 127
                reason = f"Could not launch REA: {exc}"
        size = out_path.stat().st_size
        with database:
            database.execute("DELETE FROM evidence WHERE step_id=?", (step["id"],))
            database.execute(
                "INSERT INTO evidence (step_id, command_json, output_path, "
                "stderr_path, stdout_sha256, stdout_bytes, rea_evidence_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    step["id"], json.dumps(command), str(out_path.relative_to(state)),
                    str(err_path.relative_to(state)), digest(out_path),
                    size, evidence_id_of(out_path), utc(),
                ),
            )
            database.execute(
                "UPDATE steps SET status=?, exit_code=?, ended_at=?, "
                "error_message=? WHERE id=?",
                ("completed" if exit_code == 0 else "failed",
                 exit_code, utc(), reason, step["id"]),
            )
            database.execute(
                "UPDATE runs SET status=?, updated_at=? WHERE id=?",
                ("running" if exit_code == 0 else "failed", utc(), run_id),
            )
        report = write_report(database, state, run_id)
        if exit_code != 0:
            print(f"FAILED exit={exit_code}; stderr={err_path}", file=sys.stderr)
            print(f"Checkpoint preserved. Report: {report}", file=sys.stderr)
            return 1
    with database:
        database.execute(
            "UPDATE runs SET status='completed', updated_at=? WHERE id=?",
            (utc(), run_id),
        )
    print(f"Completed. Report: {write_report(database, state, run_id)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Local REA investigation harness with SQLite checkpoints"
    )
    parser.add_argument("--state-dir", type=Path, default=DEFAULT_STATE)
    sub = parser.add_subparsers(dest="action", required=True)
    run = sub.add_parser("run", help="Plan and execute a new investigation")
    run.add_argument("--binary", type=Path, required=True)
    run.add_argument("--query", action="append", default=[],
                     help="Procedure search pattern; repeatable")
    run.add_argument("--function", help="Exact symbol/address for function dossier")
    run.add_argument("--provider", default="ghidra")
    run.add_argument("--rea", default="rea", help="REA CLI executable")
    run.add_argument("--timeout", type=int, default=1800)
    resume = sub.add_parser("resume", help="Resume pending/failed steps")
    resume.add_argument("--run-id", required=True)
    resume.add_argument("--timeout", type=int, default=1800)
    status = sub.add_parser("status", help="List runs or show a run")
    status.add_argument("--run-id")
    report = sub.add_parser("report", help="Regenerate a Markdown report")
    report.add_argument("--run-id", required=True)
    args = parser.parse_args()
    state = args.state_dir.expanduser().resolve()
    try:
        with connect(state) as database:
            if args.action == "run":
                queries = args.query if args.query else list(DEFAULT_QUERIES)
                run_id = plan(
                    database, args.binary.expanduser().resolve(),
                    args.provider, args.rea, queries, args.function,
                )
                print(f"Created run: {run_id}")
                return execute(database, state, run_id, args.timeout)
            if args.action == "resume":
                return execute(database, state, args.run_id, args.timeout)
            if args.action == "report":
                print(write_report(database, state, args.run_id))
                return 0
            if args.action == "status":
                if args.run_id:
                    rows = database.execute(
                        "SELECT ordinal, operation, selector, status, exit_code "
                        "FROM steps WHERE run_id=? ORDER BY ordinal", (args.run_id,)
                    ).fetchall()
                    for row in rows:
                        print(dict(row))
                    if not rows:
                        raise ValueError(f"Unknown run: {args.run_id}")
                else:
                    rows = database.execute(
                        "SELECT id, status, binary_path, updated_at "
                        "FROM runs ORDER BY created_at DESC"
                    ).fetchall()
                    for row in rows:
                        print(dict(row))
                return 0
    except (ValueError, sqlite3.Error, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
