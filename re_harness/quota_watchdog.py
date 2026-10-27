"""Quota-respecting Antigravity headless watchdog for a single RE Dragon workspace.

Runs only with existing official CLI credentials/permissions, resumes the
checkpointed conversation, and never circumvents provider rate limits.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import json
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

ACTIVE_CHILD = None
MARKER = "RE_DRAGON_RUN_STATE "
STOP = {"COMPLETE", "BLOCKED", "NEEDS_USER", "ERROR"}
NEXT = {"CONTINUE": 30, "YIELD": 60, "WAIT": 180}
DEFAULT_QUOTA_POLL = 900
RESET_GRACE = 60


def utc(ts):
    return dt.datetime.fromtimestamp(ts, dt.timezone.utc).isoformat()


def reset_seconds(message):
    match = re.search(r"\bResets?\s+in\s+((?:\d+\s*[dhms]\s*){1,4})",
                      message or "", re.I)
    if not match:
        return None
    units = {"d": 86400, "h": 3600, "m": 60, "s": 1}
    values = re.findall(r"(\d+)\s*([dhms])", match.group(1), re.I)
    return min(sum(int(v)*units[u.lower()] for v,u in values), 8*86400) if values else None


def quota_error(text):
    s = (text or "").lower()
    return any(k in s for k in ("resource_exhausted", "individual quota reached",
                                "quota exceeded", "quota reached", "resets in ",
                                "rate limit exceeded", "usage limit reached", "weekly limit reached", "too many requests"))


def auth_error(text):
    s = (text or "").lower()
    return any(k in s for k in ("soft-denied", "tool denied", "action denied",
                                "tool permission", "needs approval", "not allowed",
                                "authentication required", "not authenticated",
                                "sign in", "login required", "permission denied",
                                "requires approval", "waiting for approval"))


def agent_state(response):
    for line in reversed((response or "").splitlines()):
        if line.strip().startswith(MARKER):
            try:
                data = json.loads(line.strip()[len(MARKER):])
                state = data.get("state")
                if state in {*NEXT, "COMPLETE", "BLOCKED", "NEEDS_USER"}:
                    return state, str(data.get("note", ""))[:400]
            except (ValueError, TypeError, AttributeError):
                pass
            return None, "Invalid structured watchdog state"
    return None, "Agent did not emit the required structured watchdog state"


def load(path):
    if path.exists():
        value = json.loads(path.read_text(encoding="utf8"))
        if not isinstance(value, dict):
            raise ValueError("Invalid watcher state")
        return value
    return {"status": "READY", "conversation_id": None, "attempts": 0,
            "quota_hits": 0, "next_at": 0, "last_reason": "new project"}


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    with temp.open("w", encoding="utf8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)
        file.flush()
        os.fsync(file.fileno())
    os.replace(temp, path)
    os.chmod(path, 0o600)


def log(path, event, state):
    # Do not log raw model outputs, raw tool traces or credentials.
    data = {"at": utc(time.time()), "event": event,
            "status": state.get("status"), "attempts": state.get("attempts"),
            "next_at": utc(state["next_at"]) if state.get("next_at") else None}
    with path.open("a", encoding="utf8") as file:
        file.write(json.dumps(data)+"\n")


def terminate_group(signum, frame):
    """Stop only the child process launched by our own watcher."""
    if ACTIVE_CHILD is not None and ACTIVE_CHILD.poll() is None:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(ACTIVE_CHILD.pid, signal.SIGTERM)
    raise SystemExit(128 + signum)


def invoke(workspace, prompt, conversation, binary="agy", mode="auto",
           timeout=1900):
    if mode not in ("auto", "accept-edits", "plan"):
        raise ValueError("Invalid mode")
    argv = [binary, "-p", prompt, "--output-format", "json",
            "--print-timeout", "30m", "--mode", mode]
    argv += ["--conversation", conversation] if conversation else ["--continue"]
    global ACTIVE_CHILD
    p = subprocess.Popen(argv, cwd=workspace, text=True, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, start_new_session=True)
    ACTIVE_CHILD = p
    try:
        stdout, stderr = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(p.pid, signal.SIGTERM)
        try:
            p.communicate(timeout=10)
        except subprocess.TimeoutExpired:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(p.pid, signal.SIGKILL)
            p.communicate()
        ACTIVE_CHILD = None
        return {"code": 124, "data": {}, "stderr": "watchdog process timeout"}
    ACTIVE_CHILD = None
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        data = {}
    return {"code": p.returncode, "data": data, "stderr": stderr[-2000:]}


def evaluate(result, previous, timestamp):
    state = dict(previous)
    state["attempts"] = int(state.get("attempts", 0))+1
    data = result.get("data") or {}
    data = data if isinstance(data, dict) else {}
    cid = data.get("conversation_id")
    if isinstance(cid, str) and re.fullmatch(r"[0-9a-zA-Z-]{8,128}", cid):
        state["conversation_id"] = cid
    err = str(data.get("error") or "")+"\n"+str(result.get("stderr") or "")
    status = str(data.get("status") or "").upper()
    # Headless may soft-deny a tool and still exit successfully.
    # Never count such a turn as progress, even with a valid final marker.
    if auth_error(err):
        state.update(status="NEEDS_USER", next_at=0,
                     last_reason="CLI authentication/permissions require user")
    elif result.get("code")==0 and status=="SUCCESS":
        tag, note = agent_state(data.get("response", ""))
        if tag in NEXT:
            state.update(status=tag, next_at=timestamp+NEXT[tag],
                         last_reason=note or "Autonomous turn yielded")
        elif tag:
            state.update(status=tag, next_at=0,
                         last_reason=note or "Goal gate reached")
        else:
            state.update(status="NEEDS_USER", next_at=0, last_reason=note)
    elif quota_error(err):
        delay = reset_seconds(err)
        state.update(status="WAIT_QUOTA",
                     next_at=timestamp+(max(60,delay+RESET_GRACE)
                         if delay is not None else DEFAULT_QUOTA_POLL),
                     quota_hits=int(state.get("quota_hits",0))+1,
                     last_reason="Provider quota exhausted; waiting for refresh")
    elif status in ("WAITING", "CANCELED", "INTERRUPTED") or result.get("code")==124:
        state.update(status="NEEDS_USER", next_at=0,
                     last_reason="Run requires interaction or reached process timeout")
    else:
        state.update(status="ERROR", next_at=0,
                     last_reason="CLI returned an unexpected error; inspect local log")
    return state


def once(workspace, state_path, prompt_path, binary="agy", mode="auto",
         clock=None, runner=invoke):
    ts = time.time() if clock is None else clock
    current = load(state_path)
    if current["status"] in STOP or float(current.get("next_at") or 0)>ts:
        return current
    prompt = prompt_path.read_text(encoding="utf8")
    if not prompt.strip():
        raise ValueError("Missing watchdog continuation instructions")
    try:
        outcome = runner(workspace, prompt, current.get("conversation_id"),
                         binary=binary, mode=mode)
    except (OSError, ValueError):
        outcome = {"code": 127, "data": {}, "stderr": "Failed to launch CLI"}
    updated = evaluate(outcome, current, ts)
    save(state_path, updated)
    log(state_path.parent/"quota-watchdog.log","TURN",updated)
    return updated


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("run", "once", "status", "reset"))
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--conversation", default="")
    parser.add_argument("--binary", default="agy")
    parser.add_argument("--mode", default="auto",
                        choices=("auto","accept-edits","plan"))
    args = parser.parse_args(argv)
    root = Path(args.workspace).expanduser().resolve()
    state_file = root/".re_harness"/"quota-watchdog.json"
    prompt_file = root/"docs"/"QUOTA_WATCHDOG_TURN.md"
    if not prompt_file.is_file():
        parser.error("Run inside the RE Dragon repository")
    state_file.parent.mkdir(parents=True, exist_ok=True)
    # Status is a read-only snapshot; it must work while daemon owns the lock.
    if args.action == "status":
        print(json.dumps(load(state_file), indent=2, ensure_ascii=False))
        return 0
    if args.action == "run":
        signal.signal(signal.SIGTERM, terminate_group)
        signal.signal(signal.SIGINT, terminate_group)
    with (state_file.parent/"quota-watchdog.lock").open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Quota watchdog is already active", file=sys.stderr)
            return 2
        state = load(state_file)
        if args.action=="reset":
            state.update(status="READY",next_at=0,
                         last_reason="User resumed after intervention")
            if args.conversation:
                state["conversation_id"]=args.conversation
            save(state_file,state)
            return 0
        if args.conversation and not state.get("conversation_id"):
            state["conversation_id"]=args.conversation
            save(state_file,state)
        if args.action=="once":
            state=once(root,state_file,prompt_file,args.binary,args.mode)
            print(json.dumps(state, indent=2, ensure_ascii=False))
            return 0 if state["status"] not in {"ERROR","NEEDS_USER"} else 1
        while True:
            state=load(state_file)
            if state["status"] in STOP:
                return 0 if state["status"]=="COMPLETE" else 1
            if state.get("next_at",0)>time.time():
                time.sleep(min(60,max(1,state["next_at"]-time.time())))
                continue
            once(root,state_file,prompt_file,args.binary,args.mode)


if __name__=="__main__":
    raise SystemExit(main())
