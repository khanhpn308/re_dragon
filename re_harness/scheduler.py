"""v0.6 resource-aware admission, feedback and bounded task decomposition.

A reservation controller, NOT a process supervisor: the connected Agent must
honor tool permissions and use a declared GHIDRA_HEAVY task while invoking REA.
Capacity is measured conservatively on the current WSL/Linux host; no process
is started, killed or decompiled by this module.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass

from . import core

PROFILES = {
    "GHIDRA_HEAVY": (2, 3072),
    "CPU": (1, 512),
    "LIGHT": (1, 128),
}
KIND_PROFILE = {
    "ANALYZE": "GHIDRA_HEAVY",  # unknown legacy analysis fails closed
    "IMPLEMENT": "CPU",
    "TEST": "CPU",
    "AUDIT": "CPU",
    "DOCUMENT": "LIGHT",
}
MAX_SPLIT_DEPTH = 4
MAX_TARGETS = 64
MAX_WORKERS = 4
MIN_AVAILABLE_HEADROOM_MB = 384


@dataclass(frozen=True)
class Host:
    cpus: int
    available_mb: int
    load_1m: float = 0.0


def read_host():
    """Best-effort WSL/Linux host observation, not task-specific RSS."""
    cpus = max(1, len(os.sched_getaffinity(0))) if hasattr(os, "sched_getaffinity") else max(1, os.cpu_count() or 1)
    available = 0
    try:
        with open("/proc/meminfo", encoding="ascii") as inp:
            for line in inp:
                if line.startswith("MemAvailable:"):
                    available = int(line.split()[1]) // 1024
                    break
    except (OSError, ValueError, IndexError):
        pass
    try:
        load = float(os.getloadavg()[0])
    except (OSError, AttributeError):
        load = 0.0
    return Host(cpus, available, load)


def migrate(db):
    db.executescript("""
      CREATE TABLE IF NOT EXISTS auto_resource_specs (
        task_id TEXT PRIMARY KEY REFERENCES auto_tasks(id),
        profile TEXT NOT NULL,
        cpu_units INTEGER NOT NULL,
        memory_mb INTEGER NOT NULL,
        targets_json TEXT NOT NULL DEFAULT '[]',
        split_depth INTEGER NOT NULL DEFAULT 0,
        parent_key TEXT
      );
      CREATE TABLE IF NOT EXISTS auto_scheduler_policy (
        project_id TEXT PRIMARY KEY REFERENCES auto_projects(id),
        concurrency INTEGER NOT NULL DEFAULT 2,
        max_concurrency INTEGER NOT NULL DEFAULT 4,
        success_streak INTEGER NOT NULL DEFAULT 0,
        failures INTEGER NOT NULL DEFAULT 0,
        updated_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS auto_scheduler_samples (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id TEXT NOT NULL, task_key TEXT NOT NULL,
        kind TEXT NOT NULL, duration_seconds REAL,
        recorded_at TEXT NOT NULL
      );
    """)


def targets(value):
    if not isinstance(value, list) or len(value) > MAX_TARGETS:
        raise ValueError("targets must be a list with max 64 atomic scopes")
    result = []
    for target in value:
        if not isinstance(target, str) or not target.strip() or len(target) > 180:
            raise ValueError("targets entries must be nonempty bounded strings")
        if target not in result:
            result.append(target)
    return result


def normalize(kind, profile=None, scopes=None, depth=0):
    value = profile or KIND_PROFILE.get(kind, "GHIDRA_HEAVY")
    if value not in PROFILES:
        raise ValueError("resource_class must be GHIDRA_HEAVY, CPU or LIGHT")
    if type(depth) is not int or not 0 <= depth <= MAX_SPLIT_DEPTH:
        raise ValueError("split_depth is invalid")
    return {"profile": value, "cpu_units": PROFILES[value][0],
            "memory_mb": PROFILES[value][1],
            "targets": targets(scopes if scopes is not None else []),
            "split_depth": depth}


def attach(db, row_id, kind, profile=None, scopes=None, depth=0, parent_key=None):
    spec = normalize(kind, profile, scopes, depth)
    db.execute(
        "INSERT INTO auto_resource_specs(task_id,profile,cpu_units,memory_mb,"
        "targets_json,split_depth,parent_key) VALUES (?,?,?,?,?,?,?)",
        (row_id, spec["profile"], spec["cpu_units"], spec["memory_mb"],
         json.dumps(spec["targets"]), spec["split_depth"], parent_key))
    return spec


def spec_for(db, row):
    result = db.execute("SELECT * FROM auto_resource_specs WHERE task_id=?",
                        (row["id"],)).fetchone()
    if result is None:
        # pre-v0.6 tasks get conservative defaults without mutating legacy rows
        info = normalize(row["kind"])
        return {**info, "parent_key": None}
    return {"profile": result["profile"], "cpu_units": result["cpu_units"],
            "memory_mb": result["memory_mb"],
            "targets": json.loads(result["targets_json"]),
            "split_depth": result["split_depth"], "parent_key": result["parent_key"]}


def ensure_policy(db, project_id, host=None):
    h = host or read_host()
    upper = max(1, min(MAX_WORKERS, h.cpus))
    db.execute(
        "INSERT OR IGNORE INTO auto_scheduler_policy "
        "(project_id,concurrency,max_concurrency,updated_at) VALUES (?,?,?,?)",
        (project_id, min(2, upper), upper, core.now()))
    return db.execute("SELECT * FROM auto_scheduler_policy WHERE project_id=?",
                      (project_id,)).fetchone()


def running(db, now=None):
    stamp = time.time() if now is None else now
    return db.execute(
        "SELECT t.project_id,t.task_key,t.kind,t.status,t.id,"
        "s.profile,s.cpu_units,s.memory_mb "
        "FROM auto_tasks t LEFT JOIN auto_resource_specs s ON s.task_id=t.id "
        "WHERE t.status IN ('RUNNING','REVIEWING') AND t.lease_until>=?",
        (stamp,)).fetchall()


def capacity(db, pid, row, host=None):
    """Admission must be called INSIDE tick's SQLite BEGIN IMMEDIATE txn."""
    h = host or read_host()
    policy = ensure_policy(db, pid, h)
    current = running(db)
    active_project = [x for x in current if x["project_id"] == pid]
    info = spec_for(db, row)
    active_ghidra = sum(
        (x["profile"] or KIND_PROFILE.get(x["kind"], "GHIDRA_HEAVY")) == "GHIDRA_HEAVY"
        for x in current)
    cpu_used = sum(x["cpu_units"] or PROFILES[KIND_PROFILE.get(x["kind"], "GHIDRA_HEAVY")][0]
                   for x in current)
    memory_reserved = sum(x["memory_mb"] or PROFILES[KIND_PROFILE.get(x["kind"], "GHIDRA_HEAVY")][1]
                          for x in current)
    if len(active_project) >= policy["concurrency"]:
        return False, "project_concurrency_budget", info
    if len(current) >= MAX_WORKERS:
        return False, "global_worker_budget", info
    if info["profile"] == "GHIDRA_HEAVY" and active_ghidra >= 1:
        return False, "ghidra_exclusive_slot", info
    if cpu_used + min(info["cpu_units"],h.cpus) > h.cpus:
        return False, "cpu_slots_exhausted", info
    if h.available_mb <= 0:
        # Unknown memory -> fail closed for expensive analysis; small work can
        # proceed while host health is investigated.
        if info["profile"] != "LIGHT":
            return False, "memory_telemetry_unavailable", info
    elif memory_reserved + info["memory_mb"] + MIN_AVAILABLE_HEADROOM_MB > h.available_mb:
        return False, "memory_headroom_insufficient", info
    # On sustained host overload, pause *heavy* admissions, not all work.
    if info["profile"] == "GHIDRA_HEAVY" and h.load_1m > h.cpus * 1.75:
        return False, "host_load_too_high", info
    return True, "ok", info


def feedback(db, pid, task_key, kind, elapsed_seconds=None):
    """Controller feedback only; explicit and bounded additive decrease."""
    if kind not in {"PASS", "REJECT", "TIMEOUT"}:
        raise ValueError("Unsupported feedback category")
    policy = ensure_policy(db, pid)
    slots = policy["concurrency"]
    streak = policy["success_streak"]
    failures = policy["failures"]
    if elapsed_seconds is None:
        try:
            from datetime import datetime, timezone
            row=db.execute(
                "SELECT timestamp FROM auto_events WHERE project_id=? "
                "AND task_key=? AND event='CLAIMED' ORDER BY id DESC LIMIT 1",
                (pid,task_key)).fetchone()
            if row:
                elapsed_seconds=max(0.0,time.time()-datetime.fromisoformat(
                    row["timestamp"]).timestamp())
        except (ValueError,TypeError,OverflowError):
            elapsed_seconds=None
    if kind == "PASS":
        streak += 1
        if streak >= 3:
            slots = min(policy["max_concurrency"], slots + 1)
            streak = 0
    else:
        streak = 0
        failures += 1
        slots = max(1, slots // 2) if kind == "TIMEOUT" else max(1, slots - 1)
    db.execute(
        "UPDATE auto_scheduler_policy SET concurrency=?,success_streak=?,"
        "failures=?,updated_at=? WHERE project_id=?",
        (slots, streak, failures, core.now(), pid))
    db.execute(
        "INSERT INTO auto_scheduler_samples(project_id,task_key,kind,"
        "duration_seconds,recorded_at) VALUES(?,?,?,?,?)",
        (pid,task_key,kind,elapsed_seconds,core.now()))
    return {"concurrency": slots, "max_concurrency": policy["max_concurrency"],
            "success_streak": streak, "failures": failures}


def policy_status(db, pid, host=None):
    h = host or read_host()
    policy = ensure_policy(db,pid,h)
    active = running(db)
    return {"project_id":pid, "policy":dict(policy),
            "host": {"logical_cpus":h.cpus,"available_memory_mb":h.available_mb,
                     "load_1m":round(h.load_1m,2)},
            "active": [{"project_id":a["project_id"],"task_key":a["task_key"],
                        "profile":a["profile"] or KIND_PROFILE.get(a["kind"],"GHIDRA_HEAVY"),
                        "status":a["status"]} for a in active],
            "ghidra_exclusivity_limit":1,
            "warning":"These are advisory task admission reservations, not OS process limits."}


def unlock_parents(db, pid):
    """Integration parent remains unverified and MUST be executed/reviewed."""
    waiting = db.execute(
        "SELECT * FROM auto_tasks WHERE project_id=? AND status='WAIT_CHILDREN'",
        (pid,)).fetchall()
    unlocked = []
    for parent in waiting:
        children = db.execute(
            "SELECT t.status FROM auto_tasks t JOIN auto_resource_specs s "
            "ON s.task_id=t.id WHERE t.project_id=? AND s.parent_key=?",
            (pid,parent["task_key"])).fetchall()
        if children and all(x["status"]=="VERIFIED" for x in children):
            db.execute(
                "UPDATE auto_tasks SET status='PENDING',kind='DOCUMENT',tries=0,"
                "priority=MAX(priority,90),updated_at=? WHERE id=?",
                (core.now(),parent["id"]))
            db.execute("UPDATE auto_resource_specs SET profile='LIGHT',"
                       "cpu_units=1,memory_mb=128,targets_json='[]' WHERE task_id=?",
                       (parent["id"],))
            unlocked.append(parent["task_key"])
    return unlocked


def groups(scope):
    if len(scope) < 2:
        raise ValueError("Need two or more atomic scopes to partition")
    mid=(len(scope)+1)//2
    return [scope[:mid],scope[mid:]]


def task_group_key(parent, depth, index):
    # <=80 char, deterministic within parent; collision checked by caller
    return parent[:69]+"-s"+str(depth)+"-"+str(index)
