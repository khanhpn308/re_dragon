"""Fail-closed Android environment recovery for an existing S6 BLOCKED task.

Only one explicitly matched ADB-environment blocker may be requeued. No APK
installation, device mutation, server access, or changes to review history.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import zipfile

from . import autonomy, core, runtime_state

TARGET = "s6-android-go-e2e"
MODEL = "RMX3461"
APK = "dist/ReturnSaiyan-UnifiedHeroes-signed.apk"
ADB_BLOCKER = "no local adb binary or android test device/emulator available"


class NotReady(ValueError):
    pass


def _run(argv, timeout=8):
    return subprocess.run(argv, text=True, capture_output=True, timeout=timeout,
                          shell=False, check=False)


def _adb_probe(expected_model=MODEL, run=_run):
    adb = shutil.which("adb")
    if not adb:
        raise NotReady("Linux adb not installed")
    result = run([adb, "devices", "-l"])
    if result.returncode != 0:
        raise NotReady("ADB devices command failed")
    devices = []
    for line in result.stdout.splitlines():
        parts = line.strip().split()
        if len(parts) >= 2 and re.fullmatch(r"[A-Za-z0-9._:-]{4,100}", parts[0]):
            if parts[1] == "device":
                devices.append(parts[0])
            elif parts[1] in ("unauthorized", "offline"):
                raise NotReady(f"ADB device requires authorization or is offline: {parts[1]}")
    if len(devices) != 1:
        raise NotReady(f"Require exactly one authorized ADB device; found {len(devices)}")
    serial = devices[0]
    alive = run([adb, "-s", serial, "get-state"])
    if alive.returncode != 0 or alive.stdout.strip() != "device":
        raise NotReady("ADB device is not stable")
    model = run([adb, "-s", serial, "shell", "getprop", "ro.product.model"])
    if model.returncode != 0 or model.stdout.strip() != expected_model:
        raise NotReady("ADB device model does not match approved test model")
    return {"serial": serial, "model": expected_model}


def _apk_probe(root: Path, relative=APK):
    root = root.resolve()
    p = (root / relative).resolve()
    if not p.is_relative_to(root) or not p.is_file() or p.suffix.lower() != ".apk":
        raise NotReady("Local candidate APK missing/outside repository")
    with zipfile.ZipFile(p) as z:
        names = set(z.namelist())
        if "AndroidManifest.xml" not in names or not any(
                n.startswith("classes") and n.endswith(".dex") for n in names):
            raise NotReady("Candidate APK missing AndroidManifest or DEX")
        info = z.getinfo("AndroidManifest.xml")
        if info.file_size == 0:
            raise NotReady("Candidate APK has empty AndroidManifest")
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return {"path": relative, "sha256": h.hexdigest(),
            "note": "format/hash only; signature and V2 compatibility NOT certified"}


def _state_guard(root, pid, auto, *, read_only=False):
    path = root / ".re_harness" / "quota-watchdog.json"
    if not path.is_file():
        raise NotReady("Watchdog state unavailable")
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("project_id") != pid:
        raise NotReady("Pinned project mismatch")
    if read_only:
        return state
    if runtime_state.snapshot(root / ".re_harness" / "agent-runtime.json"):
        raise NotReady("Agent currently running; never requeue during in-flight work")
    if auto:
        if state.get("status") in {"PAUSED", "NEEDS_USER", "ERROR", "COMPLETE", "BLOCKED"}:
            raise NotReady("Watchdog stopped: automatic recovery not permitted")
    else:
        if state.get("status") != "PAUSED":
            raise NotReady("Manual recovery requires PAUSED operator checkpoint")
        lockfile = root / ".re_harness" / "quota-watchdog.lock"
        if lockfile.exists():
            import fcntl
            with lockfile.open("a+") as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as e:
                    raise NotReady("Watchdog still owns running lock") from e
                finally:
                    # lock released at with-exit; the transaction repeats guard
                    pass
    return state


def _database(root, *, read_only):
    path = root / ".re_harness_mvp" / "state.sqlite3"
    if not path.is_file():
        raise NotReady("Harness checkpoint SQLite missing")
    if read_only:
        conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro",
                               uri=True, timeout=5)
    else:
        conn = sqlite3.connect(path, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def _eligibility(db, pid):
    pr = db.execute("SELECT status FROM auto_projects WHERE id=?", (pid,)).fetchone()
    if pr is None or pr["status"] != "ACTIVE":
        raise NotReady("Project must be ACTIVE")
    task = db.execute("SELECT * FROM auto_tasks WHERE project_id=? AND task_key=?",
                      (pid, TARGET)).fetchone()
    if task is None:
        return None
    if task["status"] != "BLOCKED":
        return None
    note = str(task["review_note"] or "").lower().strip()
    if not note.startswith(ADB_BLOCKER):
        raise NotReady("S6 blocked for a different reason; do not auto-requeue")
    if task["owner"] or task["lease_token"] or task["lease_until"]:
        raise NotReady("S6 has an active or disputed ownership lease")
    if task["tries"] >= autonomy.MAX_ATTEMPTS:
        raise NotReady("S6 task attempt budget exhausted")
    deps = json.loads(task["dependencies"])
    if not isinstance(deps, list):
        raise NotReady("Malformed S6 dependencies")
    for dep in deps:
        row = db.execute("SELECT status FROM auto_tasks WHERE project_id=? AND task_key=?",
                         (pid, dep)).fetchone()
        if row is None or row["status"] != "VERIFIED":
            raise NotReady(f"Dependency not VERIFIED: {dep}")
    return task


def recover(root, pid, *, apply=False, automatic=False,
            adb_probe=_adb_probe, apk_probe=_apk_probe):
    """Stateful only if apply=True. No Android app is installed/executed."""
    root = Path(root).expanduser().resolve()
    _state_guard(root, pid, automatic, read_only=not apply)
    db = _database(root, read_only=True)
    try:
        task = _eligibility(db, pid)
    finally:
        db.close()
    if task is None:
        return {"result": "NO_MATCHING_BLOCKED_TASK", "project_id": pid, "task": TARGET}
    try:
        device = adb_probe()
        apk = apk_probe(root)
    except (NotReady, OSError, subprocess.SubprocessError, zipfile.BadZipFile) as e:
        return {"result": "NOT_READY", "project_id": pid, "task": TARGET,
                "reason": str(e)[:200]}

    if not apply:
        return {"result": "READY_TO_REQUEUE", "project_id": pid, "task": TARGET,
                "device_model": device["model"], "apk_sha256": apk["sha256"],
                "apk_validation": apk["note"]}

    db = _database(root, read_only=False)
    try:
        db.execute("BEGIN IMMEDIATE")
        _state_guard(root, pid, automatic)
        current = _eligibility(db, pid)
        if current is None:
            db.rollback()
            return {"result": "ALREADY_REQUEUED", "project_id": pid, "task": TARGET}
        db.execute(
            "UPDATE auto_tasks SET status='PENDING',review_note=?,updated_at=? "
            "WHERE id=? AND status='BLOCKED'",
            ("ADB environment recovered; test APK is only a candidate. "
             "Reverify signature, endpoint and V2 compatibility before install. "
             "Original blocker preserved in auto_events.", core.now(),current["id"])
        )
        autonomy.event(db,pid,TARGET,"ENVIRONMENT_RECOVERED",{
            "original_reason":str(current["review_note"] or "")[:200],
            "device_serial":device["serial"], "device_model":device["model"],
            "candidate_apk":apk["path"], "candidate_sha256":apk["sha256"],
            "advisory":"Candidate only; full S6 Android-Go E2E remains required"
        })
        db.commit()
        return {"result": "REQUEUED", "project_id": pid, "task": TARGET,
                "device_model": device["model"], "apk_sha256": apk["sha256"],
                "apk_validation": apk["note"]}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--project", required=True)
    group=parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--check", action="store_true")
    group.add_argument("--apply", action="store_true")
    args=parser.parse_args()
    try:
        result=recover(args.root,args.project,apply=args.apply)
    except (NotReady,OSError,sqlite3.Error,ValueError) as exc:
        parser.exit(2, "STOP: " + str(exc) + "\n")
    print(json.dumps(result,indent=2))
    if result["result"]=="NOT_READY":
        parser.exit(2,"Not ready: leave S6 BLOCKED; do not retry blindly.\n")


if __name__=="__main__":
    main()
