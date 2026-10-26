"""Stable runner: SQLite leases, bounded graph extraction and safe REA subprocesses.

Linux/WSL2 only. Agent orchestration shares SQLite; REA still runs as a CLI.
Runtime results are evidence candidates, never automatically VERIFIED claims.
"""
from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import time
import uuid
from pathlib import Path

from . import core

STATE = core.DEFAULT_STATE
MAX_JSON_BYTES = 32 * 1024 * 1024
HEARTBEAT_SECONDS = 3.0


def migrate(db):
    """Non-destructive migration of v0.2 state, idempotent on reopen."""
    columns = {row[1] for row in db.execute("PRAGMA table_info(tasks)")}
    for col, kind in {
        "lease_owner": "TEXT", "lease_until": "REAL",
        "pid": "INTEGER", "pid_start": "TEXT", "retry_after": "REAL DEFAULT 0"
    }.items():
        if col not in columns:
            db.execute(f"ALTER TABLE tasks ADD COLUMN {col} {kind}")
    db.executescript("""
      CREATE TABLE IF NOT EXISTS engine_slots (
          slot INTEGER PRIMARY KEY, owner TEXT, lease_until REAL,
          pid INTEGER, pid_start TEXT, run_id TEXT
      );
      CREATE TABLE IF NOT EXISTS observations (
          id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT NOT NULL,
          task_key TEXT NOT NULL, kind TEXT NOT NULL,
          symbol TEXT, address TEXT, details TEXT NOT NULL,
          UNIQUE(run_id, task_key, kind, symbol, address)
      );
      CREATE TABLE IF NOT EXISTS graph_edges (
          run_id TEXT NOT NULL, task_key TEXT NOT NULL,
          caller TEXT NOT NULL, callee TEXT NOT NULL,
          source_kind TEXT NOT NULL, PRIMARY KEY(run_id, task_key, caller, callee)
      );
      CREATE TABLE IF NOT EXISTS graph_roots (
          run_id TEXT NOT NULL, root TEXT NOT NULL, max_depth INTEGER NOT NULL,
          max_nodes INTEGER NOT NULL, PRIMARY KEY(run_id, root)
      );
      CREATE TABLE IF NOT EXISTS graph_nodes (
          run_id TEXT NOT NULL, root TEXT NOT NULL, selector TEXT NOT NULL,
          depth INTEGER NOT NULL, task_key TEXT NOT NULL,
          PRIMARY KEY(run_id, root, selector)
      );
    """)
    db.commit()


def proc_start(pid):
    if not pid or not os.path.exists(f"/proc/{pid}/stat"):
        return None
    try:
        data = Path(f"/proc/{pid}/stat").read_text()
        return data.rsplit(") ", 1)[1].split()[19]
    except (OSError, IndexError, ValueError):
        return None


def alive(pid, start):
    if not pid:
        return False
    observed = proc_start(pid)
    # Conservative on unreadable /proc: do not reclaim unknown ownership.
    if observed is None:
        return os.path.exists(f"/proc/{pid}")
    return start is None or observed == start


def json_result(path):
    """Recognize tool failures even when wrapper exits with code 0."""
    path = Path(path)
    if path.stat().st_size > MAX_JSON_BYTES:
        return None, "JSON exceeds 32 MiB indexing limit"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None, "REA stdout is not valid JSON"
    if not isinstance(data, dict):
        return None, "REA stdout is not a JSON object"
    if data.get("isError") is True or (isinstance(data.get("error"), dict)):
        return None, "REA reported an error"
    result = data.get("result")
    if isinstance(result, dict) and (
        result.get("isError") is True or isinstance(result.get("error"), dict)
    ):
        return None, "REA nested result reported an error"
    return data, None


def _normalized(doc):
    value = doc.get("normalized_result")
    if value is None and isinstance(doc.get("result"), dict):
        value = doc["result"].get("normalized_result")
    return value if isinstance(value, (dict, list)) else {}


def extract(db, run_id, task, doc):
    """Bounded observations. Edges are candidates, not proven runtime calls."""
    result = _normalized(doc)
    seen = set()
    candidates = []

    def walk(node, depth=0):
        if depth > 6 or len(candidates) >= 1200:
            return
        if isinstance(node, dict):
            name = next((node[k] for k in ("name", "symbol", "procedure", "label")
                         if isinstance(node.get(k), str)), None)
            addr = next((node[k] for k in ("address", "entry", "entry_address")
                         if isinstance(node.get(k), str)), None)
            if name or addr:
                ident = (name, addr)
                if ident not in seen:
                    seen.add(ident)
                    candidates.append((name, addr))
            for value in list(node.values())[:100]:
                walk(value, depth + 1)
        elif isinstance(node, list):
            for item in node[:150]:
                walk(item, depth + 1)

    walk(result)
    with db:
        for name, address in candidates[:300]:
            db.execute(
                "INSERT OR IGNORE INTO observations "
                "(run_id, task_key, kind, symbol, address, details) "
                "VALUES (?, ?, 'candidate', ?, ?, ?)",
                (run_id, task["key"], name, address, "{}"),
            )
    if task["operation"] != "function":
        return

    caller = task["selector"]
    targets = []

    def collect(node, depth=0):
        if depth > 5 or len(targets) >= 200:
            return
        if isinstance(node, dict):
            for key in ("calls", "callees", "resolved_calls"):
                value = node.get(key)
                if not isinstance(value, list):
                    continue
                for item in value[:150]:
                    if isinstance(item, str):
                        targets.append(item)
                    elif isinstance(item, dict):
                        target = item.get("target") or item.get("callee") or item.get("procedure")
                        if isinstance(target, dict):
                            target = target.get("address") or target.get("name")
                        if not isinstance(target, str):
                            target = item.get("target_address") or item.get("address") or item.get("name")
                        if isinstance(target, str) and target:
                            targets.append(target)
            for value in list(node.values())[:80]:
                if isinstance(value, (dict, list)):
                    collect(value, depth + 1)
        elif isinstance(node, list):
            for item in node[:100]:
                collect(item, depth + 1)

    collect(result)
    with db:
        for target in list(dict.fromkeys(targets))[:100]:
            if target != caller:
                db.execute(
                    "INSERT OR IGNORE INTO graph_edges VALUES (?, ?, ?, ?, ?)",
                    (run_id, task["key"], caller, target, "static_candidate"),
                )


def add_graph(db, run_id, selector, depth=2, max_nodes=30):
    migrate(db)
    core.get_run(db, run_id)
    if not isinstance(selector, str) or not selector or len(selector) > 2048:
        raise ValueError("Graph root must be an exact nonempty symbol/address")
    if not 0 <= depth <= 5 or not 1 <= max_nodes <= 100:
        raise ValueError("Bounds: depth 0–5, nodes 1–100")
    with db:
        db.execute(
            "INSERT OR IGNORE INTO graph_roots VALUES (?, ?, ?, ?)",
            (run_id, selector, depth, max_nodes),
        )
        existing = db.execute(
            "SELECT task_key FROM graph_nodes WHERE run_id=? AND root=? AND selector=?",
            (run_id, selector, selector),
        ).fetchone()
        if existing:
            return {"root": selector, "task_key": existing["task_key"], "already_queued": True}
        key = _queue_function(db, run_id, selector)
        db.execute(
            "INSERT INTO graph_nodes VALUES (?, ?, ?, 0, ?)",
            (run_id, selector, selector, key),
        )
        core.event(db, run_id, "graph_started", {"root": selector, "depth": depth,
                                                 "max_nodes": max_nodes})
        return {"root": selector, "task_key": key, "already_queued": False}


def _queue_function(db, run_id, selector):
    ordinal = db.execute(
        "SELECT COALESCE(MAX(ordinal), 0)+1 FROM tasks WHERE run_id=?", (run_id,)
    ).fetchone()[0]
    key = f"graph-{ordinal}"
    db.execute(
        "INSERT INTO tasks (id, run_id, ordinal, key, operation, selector, "
        "dependencies, status, updated_at) "
        "VALUES (?, ?, ?, ?, 'function', ?, '[]', 'pending', ?)",
        (uuid.uuid4().hex, run_id, ordinal, key, selector, core.now()),
    )
    db.execute("UPDATE runs SET status='planned', updated_at=? WHERE id=?",
               (core.now(), run_id))
    return key


def expand_graph(db, run_id, task_key):
    """Queue only uniquely observed static callee candidates within limits."""
    roots = db.execute(
        "SELECT n.root, n.selector, n.depth, r.max_depth, r.max_nodes "
        "FROM graph_nodes n JOIN graph_roots r "
        "ON r.run_id=n.run_id AND r.root=n.root "
        "WHERE n.run_id=? AND n.task_key=?", (run_id, task_key),
    ).fetchall()
    queued = 0
    with db:
        for root in roots:
            if root["depth"] >= root["max_depth"]:
                continue
            targets = db.execute(
                "SELECT DISTINCT callee FROM graph_edges "
                "WHERE run_id=? AND task_key=? AND caller=? ORDER BY callee",
                (run_id, task_key, root["selector"]),
            ).fetchall()
            count = db.execute(
                "SELECT COUNT(*) FROM graph_nodes WHERE run_id=? AND root=?",
                (run_id, root["root"]),
            ).fetchone()[0]
            for target in targets:
                if count >= root["max_nodes"]:
                    break
                selector = target["callee"]
                prior = db.execute(
                    "SELECT 1 FROM graph_nodes WHERE run_id=? AND root=? AND selector=?",
                    (run_id, root["root"], selector),
                ).fetchone()
                if prior:
                    continue
                key = _queue_function(db, run_id, selector)
                db.execute(
                    "INSERT INTO graph_nodes VALUES (?, ?, ?, ?, ?)",
                    (run_id, root["root"], selector, root["depth"] + 1, key),
                )
                queued += 1
                count += 1
    return queued


def recover(db, run_id=None):
    """Recover only expired leases whose recorded child process is not alive.

    A still-live child is NEVER reclaimed: avoid competing Ghidra operations.
    """
    migrate(db)
    stamp = time.time()
    resolved, blocked = [], []
    db.execute("BEGIN IMMEDIATE")
    try:
        rows = db.execute(
            "SELECT * FROM tasks WHERE status='running' AND lease_until IS NOT NULL "
            "AND lease_until<? " + ("AND run_id=? " if run_id else ""),
            ((stamp, run_id) if run_id else (stamp,)),
        ).fetchall()
        for task in rows:
            if alive(task["pid"], task["pid_start"]):
                blocked.append(task["key"])
                continue
            db.execute(
                "UPDATE tasks SET status='failed', lease_owner=NULL, lease_until=NULL, "
                "pid=NULL, pid_start=NULL, error='Recovered expired orphan task; "
                "re-execution requires retry capacity', updated_at=? WHERE id=?",
                (core.now(), task["id"]),
            )
            core.event(db, task["run_id"], "expired_task_recovered", {"task": task["key"]})
            resolved.append(task["key"])
        slots = db.execute(
            "SELECT * FROM engine_slots WHERE owner IS NOT NULL AND lease_until<?",
            (stamp,),
        ).fetchall()
        for slot in slots:
            if not alive(slot["pid"], slot["pid_start"]):
                db.execute(
                    "UPDATE engine_slots SET owner=NULL, lease_until=NULL, pid=NULL, "
                    "pid_start=NULL, run_id=NULL WHERE slot=?",
                    (slot["slot"],),
                )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"recovered": resolved, "blocked_live_processes": blocked}


def claim(db, run_id, worker, lease_seconds, capacity=1, max_attempts=3):
    migrate(db)
    if not 1 <= capacity <= 4 or not 1 <= max_attempts <= 10:
        raise ValueError("capacity 1–4; max attempts 1–10")
    stamp = time.time()
    db.execute("BEGIN IMMEDIATE")
    try:
        run = core.get_run(db, run_id)
        tasks = core.get_tasks(db, run_id)
        completed = {t["key"] for t in tasks if t["status"] == "completed"}
        task = next((
            t for t in tasks
            if t["status"] in ("pending", "failed")
            and t["attempts"] < max_attempts
            and (t["retry_after"] or 0) <= stamp
            and all(x in completed for x in json.loads(t["dependencies"]))
        ), None)
        if task is None:
            db.commit()
            return None
        selected_slot = None
        for number in range(capacity):
            slot = db.execute(
                "SELECT * FROM engine_slots WHERE slot=?", (number,)
            ).fetchone()
            if slot is None:
                db.execute(
                    "INSERT INTO engine_slots(slot, owner, lease_until, run_id) "
                    "VALUES (?, ?, ?, ?)",
                    (number, worker, stamp + lease_seconds, run_id),
                )
                selected_slot = number
                break
            if slot["owner"] is None:
                db.execute(
                    "UPDATE engine_slots SET owner=?, lease_until=?, run_id=? "
                    "WHERE slot=?", (worker, stamp + lease_seconds, run_id, number),
                )
                selected_slot = number
                break
            # Expired slots are intentionally not reused here; recover first.
        if selected_slot is None:
            db.commit()
            return None
        db.execute(
            "UPDATE tasks SET status='running', lease_owner=?, lease_until=?, "
            "attempts=attempts+1, error=NULL, updated_at=? WHERE id=?",
            (worker, stamp + lease_seconds, core.now(), task["id"]),
        )
        db.execute("UPDATE runs SET status='running', updated_at=? WHERE id=?",
                   (core.now(), run_id))
        core.event(db, run_id, "task_leased", {"task": task["key"], "owner": worker,
                                              "slot": selected_slot})
        db.commit()
        return {"task": dict(task), "attempt": task["attempts"] + 1,
                "slot": selected_slot, "run": dict(run)}
    except Exception:
        db.rollback()
        raise


def refresh(db, task_id, slot, worker, lease_seconds, pid=None, pid_token=None):
    expires = time.time() + lease_seconds
    with db:
        changed = db.execute(
            "UPDATE tasks SET lease_until=?, pid=?, pid_start=? "
            "WHERE id=? AND lease_owner=? AND status='running'",
            (expires, pid, pid_token, task_id, worker),
        ).rowcount
        changed_slot = db.execute(
            "UPDATE engine_slots SET lease_until=?, pid=?, pid_start=? "
            "WHERE slot=? AND owner=?",
            (expires, pid, pid_token, slot, worker),
        ).rowcount
    if changed != 1 or changed_slot != 1:
        raise RuntimeError("Lost task or engine lease during execution")


def terminate_group(process):
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=8)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
    except OSError:
        process.kill()
        process.wait()


def finish(db, state, item, code, error, out, err, max_attempts):
    task, run = item["task"], item["run"]
    artifact_id = uuid.uuid4().hex
    with db:
        db.execute(
            "INSERT INTO artifacts VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (artifact_id, task["id"], item["attempt"],
             str(out.relative_to(state)), str(err.relative_to(state)),
             core.sha256(out), out.stat().st_size,
             core.extract_evidence_id(out), code, core.now()),
        )
        retry_after = time.time() + min(60, 2 ** min(item["attempt"], 6))
        db.execute(
            "UPDATE tasks SET status=?, exit_code=?, error=?, updated_at=?, "
            "lease_owner=NULL, lease_until=NULL, pid=NULL, pid_start=NULL, "
            "retry_after=? WHERE id=? AND lease_owner=?",
            ("completed" if code == 0 else "failed", code, error, core.now(),
             0 if code == 0 else retry_after, task["id"], item["owner"]),
        )
        db.execute(
            "UPDATE engine_slots SET owner=NULL, lease_until=NULL, pid=NULL, "
            "pid_start=NULL, run_id=NULL WHERE slot=? AND owner=?",
            (item["slot"], item["owner"]),
        )
        core.event(db, run["id"], "task_finished", {
            "task": task["key"], "code": code, "attempt": item["attempt"],
            "retry_eligible": code != 0 and item["attempt"] < max_attempts,
        })
    if code == 0:
        doc, issue = json_result(out)
        if doc is not None:
            extract(db, run["id"], task, doc)
            expand_graph(db, run["id"], task["key"])


def reconcile(db, run_id, max_attempts):
    tasks = core.get_tasks(db, run_id)
    if tasks and all(t["status"] == "completed" for t in tasks):
        status = "completed"
    elif any(t["status"] == "running" for t in tasks):
        status = "running"
    elif any(t["status"] == "failed" and t["attempts"] >= max_attempts for t in tasks):
        status = "failed"
    else:
        status = "paused"
    with db:
        db.execute("UPDATE runs SET status=?, updated_at=? WHERE id=?",
                   (status, core.now(), run_id))
    return status


def work(db, state, run_id, steps=1, timeout=1800, retries=2, capacity=1):
    """Execute up to 'steps' leased tasks, resuming prior artifacts if present."""
    state = Path(state).expanduser().resolve()
    migrate(db)
    if not 1 <= steps <= 200 or not 1 <= timeout <= 10800 or not 0 <= retries <= 9:
        raise ValueError("steps 1–200; timeout 1–10800; retries 0–9")
    run = core.get_run(db, run_id)
    source = Path(run["binary_path"])
    if not source.is_file() or core.sha256(source) != run["binary_sha256"]:
        raise ValueError("Pinned native binary missing or SHA-256 changed")
    worker = f"worker-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    done, errors = 0, []
    for _ in range(steps):
        recover(db, run_id)
        item = claim(db, run_id, worker, max(timeout + 90, 120), capacity,
                     max_attempts=retries + 1)
        if item is None:
            break
        item["owner"] = worker
        task = item["task"]
        folder = state / "evidence" / run_id
        folder.mkdir(parents=True, exist_ok=True)
        basename = f"{task['ordinal']:02d}_attempt_{item['attempt']}"
        out, err = folder / (basename + ".json"), folder / (basename + ".stderr.txt")
        cmd = core.build_command(item["run"], task)
        code, reason = 127, None
        process = None
        try:
            with out.open("wb") as standard_out, err.open("wb") as standard_error:
                process = subprocess.Popen(
                    cmd, stdout=standard_out, stderr=standard_error,
                    start_new_session=True, close_fds=True,
                )
                token = proc_start(process.pid)
                started = time.monotonic()
                while True:
                    refresh(db, task["id"], item["slot"], worker,
                            max(timeout + 90, 120), process.pid, token)
                    try:
                        code = process.wait(timeout=HEARTBEAT_SECONDS)
                        break
                    except subprocess.TimeoutExpired:
                        if time.monotonic() - started >= timeout:
                            reason, code = "Timed out; child process group terminated", 124
                            terminate_group(process)
                            break
        except (OSError, RuntimeError) as exc:
            reason = f"REA process or lease failure: {exc}"
            code = 127
            if process is not None:
                terminate_group(process)
        if code == 0:
            _, issue = json_result(out)
            if issue:
                code, reason = 65, issue
        finish(db, state, item, code, reason, out, err, retries + 1)
        done += 1
        if code != 0:
            errors.append({"task": task["key"], "code": code, "reason": reason})
            # Do not continuously retry a failing binary/provider in one request.
            break
    return {"run_id": run_id, "worker": worker, "executed": done,
            "status": reconcile(db, run_id, retries + 1), "errors": errors,
            "report": str(core.render_report(db, state, run_id))}


def graph(db, run_id, root=None, limit=200):
    migrate(db)
    if not 1 <= limit <= 1000:
        raise ValueError("limit 1–1000")
    if root is not None:
        nodes = db.execute(
            "SELECT selector, depth, task_key FROM graph_nodes "
            "WHERE run_id=? AND root=? ORDER BY depth, selector LIMIT ?",
            (run_id, root, limit),
        ).fetchall()
    else:
        nodes = db.execute(
            "SELECT root, selector, depth, task_key FROM graph_nodes "
            "WHERE run_id=? ORDER BY root, depth, selector LIMIT ?",
            (run_id, limit),
        ).fetchall()
    edges = db.execute(
        "SELECT caller, callee, task_key, source_kind FROM graph_edges "
        "WHERE run_id=? ORDER BY caller, callee LIMIT ?",
        (run_id, limit),
    ).fetchall()
    return {"nodes": [dict(n) for n in nodes], "edges": [dict(e) for e in edges],
            "coverage": "bounded_static_candidates_not_runtime_truth"}


def observations(db, run_id, task_key=None, limit=200):
    migrate(db)
    if not 1 <= limit <= 1000:
        raise ValueError("limit 1–1000")
    if task_key:
        rows = db.execute(
            "SELECT task_key, kind, symbol, address FROM observations "
            "WHERE run_id=? AND task_key=? LIMIT ?",
            (run_id, task_key, limit),
        )
    else:
        rows = db.execute(
            "SELECT task_key, kind, symbol, address FROM observations "
            "WHERE run_id=? LIMIT ?", (run_id, limit),
        )
    return {"items": [dict(row) for row in rows],
            "note": "Extracted candidates; review linked REA output before verification"}
