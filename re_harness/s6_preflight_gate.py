"""Owner-controlled transactional S6 V2-client preflight dependency gate.

Use --check (read-only) before --apply (single SQLite transaction).
Never install an APK or contact a remote game server.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3

from . import autonomy, core, release_gate, runtime_state, scheduler

PREFLIGHT_KEY = "s6-client-v2-preflight"
S6_KEY = "s6-android-go-e2e"
FINAL_KEY = "final-fullstack-release-audit"
TITLE = "Independent V2 Android client, endpoint and signing readiness audit"
ACCEPTANCE = (
    "BLOCKING S6 PREFLIGHT: independently verify the exact client APK (SHA-256, "
    "package ID, signing certificate, ABI) and prove it is a V2-ready client "
    "pointing only to the operator-controlled Go Server, not ReturnSaiyan or "
    "other third-party services. Audit source/binary evidence for updater, "
    "bootstrap/login/gameplay endpoint mapping and TCP framing/codec; verify "
    "Go server build, test environment, local PostgreSQL dependencies, adb "
    "authorization and Android device model/OS. Keep the installed Android "
    "app and its data unchanged during this gate: NO adb install/uninstall, "
    "no APK rebuild unless separately planned and reviewed, no production "
    "credentials or third-party network access. If only the V1 release APK "
    "is present, create bounded V2 client build/remediation tasks with "
    "explicit dependencies and independent review, then keep this preflight "
    "unverified until those tasks pass. Record primary evidence and candidate "
    "checksums, reproducible tests and reviewer verdict. Do not equate "
    "format/hash inspection or ADB availability to E2E playability. Never "
    "approve preflight or final release when an essential condition is "
    "unverified; escalate NEEDS_USER or BLOCKED instead."
)


def _guard(root: Path, pid: str, *, check_tmux=True):
    release_gate._operator_guard(root, pid, check_tmux=check_tmux)
    agent = runtime_state.snapshot(root / ".re_harness" / "agent-runtime.json")
    if agent:
        raise ValueError("Agent process still active; fail closed")


def _rows(db, pid):
    pr = db.execute("SELECT status FROM auto_projects WHERE id=?", (pid,)).fetchone()
    if pr is None or pr["status"] != "ACTIVE":
        raise ValueError("Only pinned ACTIVE project is eligible")
    rows = db.execute("SELECT * FROM auto_tasks WHERE project_id=?", (pid,)).fetchall()
    lookup = {r["task_key"]: r for r in rows}
    s6 = lookup.get(S6_KEY)
    final = lookup.get(FINAL_KEY)
    if not s6 or not final:
        raise ValueError("S6 or final release task missing")
    for row in (s6, final):
        if row["status"] != "PENDING" or row["owner"] or row["lease_token"] or row["lease_until"]:
            raise ValueError(f"{row['task_key']} must be PENDING and unleased")
    for row in rows:
        if row["status"] in {"RUNNING", "REVIEWING", "SPLITTING", "SUBMITTED"}:
            raise ValueError("In-flight or submitted task present; reconcile before DAG mutation")
    for field in ("result", "evidence_json", "artifacts_json", "verification_json"):
        val = s6[field]
        if not val:
            continue
        if field == "result" or not isinstance(val, str):
            raise ValueError("S6 prior result/side effects require manual review")
        try:
            if json.loads(val):
                raise ValueError("S6 prior evidence/artifacts require manual review")
        except json.JSONDecodeError as exc:
            raise ValueError("S6 evidence malformed") from exc
    if len(rows) >= autonomy.MAX_TASKS:
        raise ValueError("Harness maximum task limit reached")
    s6deps = json.loads(s6["dependencies"])
    finaldeps = json.loads(final["dependencies"])
    if not isinstance(s6deps, list) or not isinstance(finaldeps, list):
        raise ValueError("Malformed dependency JSON")
    if not {"g-client-server-contract", "s4-gameplay-authoritative",
            "s5-postgres-persistence"}.issubset(s6deps):
        raise ValueError("S6 prerequisites differ from agreed V2 DAG")
    if S6_KEY not in finaldeps or "v2-go-v1-1-backaudit" not in finaldeps:
        raise ValueError("Final release dependencies missing S6 or Go backaudit")
    audit = lookup.get(PREFLIGHT_KEY)
    if audit is not None:
        if (audit["kind"] != "AUDIT" or audit["acceptance"] != ACCEPTANCE
                or json.loads(audit["dependencies"]) != [d for d in s6deps if d != PREFLIGHT_KEY]
                or PREFLIGHT_KEY not in s6deps or PREFLIGHT_KEY not in finaldeps):
            raise ValueError("Existing preflight gate differs: fail closed")
        return {
            "result": "ALREADY_INSTALLED", "project_id": pid,
            "preflight_status": audit["status"],
            "s6_status": s6["status"],
            "s6_dependencies": s6deps,
            "final_dependencies": finaldeps,
        }
    if PREFLIGHT_KEY in s6deps or PREFLIGHT_KEY in finaldeps:
        raise ValueError("Dangling preflight dependency")
    if len(s6deps) >= 25 or len(finaldeps) >= 25:
        raise ValueError("Dependency budget exceeded")
    previous = {r["task_key"]: json.loads(r["dependencies"]) for r in rows}
    candidate = {
        "key": PREFLIGHT_KEY, "title": TITLE, "kind": "AUDIT",
        "acceptance": ACCEPTANCE, "priority": 98,
        "depends_on": list(s6deps), "resource_class": "CPU", "targets": [],
    }
    item = autonomy._validate_batch([candidate], previous)[0]
    # Revalidate graph after inserting edges into *existing* tasks as well.
    graph = dict(previous)
    graph[PREFLIGHT_KEY] = list(s6deps)
    graph[S6_KEY] = s6deps + [PREFLIGHT_KEY]
    graph[FINAL_KEY] = finaldeps + [PREFLIGHT_KEY]
    visited, active = set(), set()
    def visit(node):
        if node in active:
            raise ValueError("DAG cycle detected")
        if node in visited:
            return
        active.add(node)
        for parent in graph[node]:
            if parent not in graph:
                raise ValueError("Missing DAG dependency")
            visit(parent)
        active.remove(node)
        visited.add(node)
    for node in graph:
        visit(node)
    return {
        "result": "PENDING_INSTALL", "project_id": pid,
        "candidate": item,
        "preflight_dependencies": list(s6deps),
        "s6_dependencies": s6deps + [PREFLIGHT_KEY],
        "final_dependencies": finaldeps + [PREFLIGHT_KEY],
    }


def execute(root: Path, pid: str, *, apply=False, check_tmux=True):
    root = Path(root).expanduser().resolve()
    _guard(root, pid, check_tmux=check_tmux)
    path = root / ".re_harness_mvp" / "state.sqlite3"
    if not path.is_file():
        raise ValueError("Existing SQLite state missing")
    db = (sqlite3.connect(path, timeout=10) if apply else
          sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True, timeout=10))
    db.row_factory = sqlite3.Row
    try:
        if apply:
            db.execute("BEGIN IMMEDIATE")
            _guard(root, pid, check_tmux=check_tmux)
        outcome = _rows(db, pid)
        if apply and outcome["result"] == "PENDING_INSTALL":
            candidate = outcome["candidate"]
            task_id = autonomy.ident()
            db.execute(
                "INSERT INTO auto_tasks(id,project_id,task_key,title,acceptance,kind,"
                "priority,dependencies,status,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (task_id,pid,PREFLIGHT_KEY,TITLE,ACCEPTANCE,"AUDIT",98,
                 json.dumps(outcome["preflight_dependencies"]),"PENDING",core.now()),
            )
            scheduler.attach(db, task_id, "AUDIT", "CPU", [])
            for key, deps in (
                (S6_KEY, outcome["s6_dependencies"]),
                (FINAL_KEY, outcome["final_dependencies"]),
            ):
                result = db.execute(
                    "UPDATE auto_tasks SET dependencies=?,updated_at=? "
                    "WHERE project_id=? AND task_key=? AND status='PENDING' AND owner IS NULL",
                    (json.dumps(deps),core.now(),pid,key),
                )
                if result.rowcount != 1:
                    raise ValueError("Concurrent task status update; rollback")
            autonomy.event(db,pid,PREFLIGHT_KEY,"S6_PREFLIGHT_GATE_INSTALLED",{
                "task":PREFLIGHT_KEY,"s6":S6_KEY,"final":FINAL_KEY,
                "old_s6_dependencies":outcome["preflight_dependencies"],
                "new_s6_dependencies":outcome["s6_dependencies"],
                "new_final_dependencies":outcome["final_dependencies"],
                "no_e2e_claim":True,
            })
            verified = _rows(db,pid)
            if verified["result"] != "ALREADY_INSTALLED":
                raise ValueError("Post-write DAG verification failed")
            outcome = dict(verified, result="INSTALLED")
        else:
            outcome.pop("candidate", None)
        if apply:
            db.commit()
        return outcome
    except Exception:
        if apply:
            db.rollback()
        raise
    finally:
        db.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--project",required=True)
    p.add_argument("--root",type=Path,default=Path.cwd())
    a=p.add_mutually_exclusive_group(required=True)
    a.add_argument("--check",action="store_true")
    a.add_argument("--apply",action="store_true")
    args=p.parse_args()
    try:
        outcome=execute(args.root,args.project,apply=args.apply)
    except (ValueError,OSError,sqlite3.Error) as exc:
        p.exit(2,"STOP: "+str(exc)+"\n")
    print(json.dumps(outcome,indent=2))


if __name__=="__main__":
    main()
