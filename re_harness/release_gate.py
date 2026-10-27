"""Owner-controlled, transactional V2 Go v1.1 Backaudit release gate.

This module does not run agents or modify V1. --check never writes anything.
--apply requires local PAUSED Watchdog, stopped supervisor and a matching active
project, then atomically inserts one AUDIT task and adds it to Final GO deps.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess

from . import autonomy, core, scheduler

AUDIT_KEY = "v2-go-v1-1-backaudit"
FINAL_KEY = "final-fullstack-release-audit"
GO_RULE_SHA = "49ed4166f42ad80f8e8627418ce8f558c6e05869"
PREREQUISITES = (
    "s1-tcp-protocol-server",
    "s2-auth-and-session",
    "s3-game-state-and-heroes",
    "s4-gameplay-authoritative",
    "s5-postgres-persistence",
)
AUDIT_TITLE = "Independent Go Standard v1.1 retrospective audit and remediation"
AUDIT_ACCEPTANCE = (
    "Scope: current local (including untracked) V2 game-server source for S1-S5 "
    "and T01-T04. Apply rulebook docs/production/GO_GAME_SERVER_AGENT_STANDARD_V1_1.md, "
    "RULE_REGISTRY and RULE_MATRIX at commit " + GO_RULE_SHA + ". "
    "Produce per-rule PASS/FAIL/NOT_RUN with file:line primary evidence and independent "
    "review; check actual CI (not docs-only PASS), protocol, auth, goroutines, SQL "
    "transactions, idempotency, race conditions, migrations and security. "
    "Any FAIL requires bounded remediation and regression with separately reviewed "
    "evidence BEFORE this audit may be VERIFIED. Preserve previous S1-S5 VERIFIED "
    "history and T01-T04 REVIEWING; no replay or fabricated approvals. "
    "If remediation cannot be enforced as dependencies/children, mark BLOCKED or "
    "NEEDS_USER; never mark this audit VERIFIED nor Final GO. Never touch V1."
)


def _operator_guard(root: Path, project_id: str, *, check_tmux: bool = True) -> None:
    path = root / ".re_harness" / "quota-watchdog.json"
    if not path.is_file():
        raise ValueError("Watchdog state missing; fail closed")
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("status") != "PAUSED" or state.get("project_id") != project_id:
        raise ValueError("Project must be pinned and PAUSED (do not resume)")
    if check_tmux:
        exe = shutil.which("tmux")
        if exe is None:
            raise ValueError("tmux unavailable; cannot prove Watchdog stopped")
        res = subprocess.run(
            [exe, "has-session", "-t", "re-dragon-quota-watchdog"],
            check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=5,
        )
        if res.returncode != 1:
            raise ValueError("Watchdog active or tmux check inconclusive")


def _inspect(db: sqlite3.Connection, project_id: str):
    proj = db.execute("SELECT status FROM auto_projects WHERE id=?", (project_id,)).fetchone()
    if proj is None or proj["status"] != "ACTIVE":
        raise ValueError("Only an ACTIVE project may receive this release gate")

    release = db.execute(
        "SELECT * FROM auto_tasks WHERE project_id=? AND task_key=?",
        (project_id, FINAL_KEY),
    ).fetchone()
    if release is None or release["status"] != "PENDING" or release["owner"] is not None:
        raise ValueError("Final Release task missing, claimed, or not PENDING")
    dependencies = json.loads(release["dependencies"])
    if not isinstance(dependencies, list) or not {"s6-android-go-e2e",
                                                  "t10-t11-migration-and-pitr"}.issubset(dependencies):
        raise ValueError("Final Release dependency charter differs; fail closed")

    tasks = db.execute("SELECT task_key,status,dependencies FROM auto_tasks WHERE project_id=?",
                       (project_id,)).fetchall()
    statuses = {r["task_key"]: r["status"] for r in tasks}
    for key in PREREQUISITES:
        if statuses.get(key) != "VERIFIED":
            raise ValueError(f"Prerequisite {key} must be VERIFIED; got {statuses.get(key)}")
    audit = db.execute(
        "SELECT * FROM auto_tasks WHERE project_id=? AND task_key=?",
        (project_id, AUDIT_KEY),
    ).fetchone()
    if audit is None and AUDIT_KEY in dependencies:
        raise ValueError("Dangling release dependency: audit task missing")
    if audit is not None:
        if (audit["kind"] != "AUDIT"
                or json.loads(audit["dependencies"]) != list(PREREQUISITES)
                or GO_RULE_SHA not in audit["acceptance"]
                or AUDIT_KEY not in dependencies):
            raise ValueError("Existing audit has incompatible scope/dependencies")
        return {"result": "ALREADY_INSTALLED", "project_id": project_id,
                "audit": AUDIT_KEY, "audit_status": audit["status"],
                "final_dependencies": dependencies}

    if AUDIT_KEY in dependencies:
        raise ValueError("Release points to missing audit")
    if len(dependencies) >= 25:
        raise ValueError("Final task dependency budget exceeded")
    if len(tasks) >= autonomy.MAX_TASKS:
        raise ValueError("Project task budget exceeded")
    previous = {r["task_key"]: json.loads(r["dependencies"]) for r in tasks}
    candidate = {
        "key": AUDIT_KEY, "kind": "AUDIT", "title": AUDIT_TITLE,
        "acceptance": AUDIT_ACCEPTANCE, "priority": 95,
        "depends_on": list(PREREQUISITES), "resource_class": "CPU",
        "targets": [],
    }
    validated = autonomy._validate_batch([candidate], previous)
    return {"result": "PENDING_INSTALL", "project_id": project_id,
            "audit": AUDIT_KEY, "candidate": validated[0],
            "final_dependencies": dependencies + [AUDIT_KEY]}


def execute(root: Path, project_id: str, *, apply: bool = False,
            check_tmux: bool = True):
    root = root.expanduser().resolve()
    if not root.is_dir():
        raise ValueError("Repository directory not found")
    _operator_guard(root, project_id, check_tmux=check_tmux)
    path = root / ".re_harness_mvp" / "state.sqlite3"
    if not path.is_file():
        raise ValueError("Existing Harness DB missing; refusing to create one")

    if not apply:
        # Strictly read-only: never run schema migration on --check.
        db = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    else:
        db = sqlite3.connect(path, timeout=5)
    db.row_factory = sqlite3.Row
    try:
        if apply:
            db.execute("BEGIN IMMEDIATE")
            # Re-check operator pause immediately after obtaining write lease.
            _operator_guard(root, project_id, check_tmux=check_tmux)
        result = _inspect(db, project_id)
        if apply and result["result"] == "PENDING_INSTALL":
            info = result.pop("candidate")
            task_id = autonomy.ident()
            db.execute(
                "INSERT INTO auto_tasks(id,project_id,task_key,title,acceptance,kind,"
                "priority,dependencies,status,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (task_id, project_id, AUDIT_KEY, AUDIT_TITLE, AUDIT_ACCEPTANCE,
                 "AUDIT", 95, json.dumps(list(PREREQUISITES)), "PENDING", core.now()),
            )
            scheduler.attach(db, task_id, "AUDIT", "CPU", [])
            db.execute(
                "UPDATE auto_tasks SET dependencies=?,updated_at=? WHERE project_id=? AND task_key=?",
                (json.dumps(result["final_dependencies"]), core.now(), project_id, FINAL_KEY),
            )
            autonomy.event(db, project_id, AUDIT_KEY, "GO_BACKAUDIT_GATE_INSTALLED",
                           {"addendum_sha": GO_RULE_SHA, "release": FINAL_KEY,
                            "prerequisite_count": len(PREREQUISITES)})
            verified = _inspect(db, project_id)
            if verified["result"] != "ALREADY_INSTALLED":
                raise RuntimeError("Post-write gate verification failed")
            result = verified
            result["result"] = "INSTALLED"
        elif apply:
            result["result"] = "ALREADY_INSTALLED"
        else:
            result.pop("candidate", None)
        if apply:
            db.commit()
        return result
    except Exception:
        if apply:
            db.rollback()
        raise
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--project", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    try:
        result = execute(args.root, args.project, apply=args.apply)
    except (ValueError, RuntimeError, OSError, sqlite3.Error, json.JSONDecodeError) as exc:
        parser.exit(2, f"STOP: {exc}\n")
    print(json.dumps(result, indent=2))
    if not args.apply:
        print("READ ONLY. Apply requires explicit --apply while project is PAUSED.")
    else:
        print("DAG gate installed; Watchdog remains PAUSED. Check SQLite before /resume.")


if __name__ == "__main__":
    main()
