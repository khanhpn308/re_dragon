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

from . import quota_guard

ACTIVE_CHILD = None
MARKER = "RE_DRAGON_RUN_STATE "
STOP = {"COMPLETE", "BLOCKED", "NEEDS_USER", "ERROR"}
NEXT = {"CONTINUE": 30, "YIELD": 60, "WAIT": 180}
DEFAULT_QUOTA_POLL = 900
RESET_GRACE = 60
MAX_TRANSIENT_RETRIES = 3


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


def temporary_error(text):
    """Only retry known transport/server faults, not permission/tool failures."""
    s = (text or "").lower()
    return any(k in s for k in (
        "econnreset", "etimedout", "eai_again", "temporary failure in name resolution",
        "network is unreachable", "connection reset by peer",
        "service unavailable", "502 bad gateway", "503 service unavailable",
    ))


def cached_conversation(workspace):
    """Resolve exact CLI workspace conversation; never start a new session silently."""
    path = Path.home()/".gemini"/"antigravity-cli"/"cache"/"last_conversations.json"
    try:
        mapping=json.loads(path.read_text(encoding="utf8"))
        cid=mapping.get(str(Path(workspace).resolve()))
        if isinstance(cid,str) and re.fullmatch(r"[0-9A-Za-z-]{8,128}",cid):
            return cid
    except (OSError,ValueError,AttributeError):
        pass
    return None


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
    return {"status": "READY", "project_id": None, "conversation_id": None,
            "attempts": 0, "quota_hits": 0, "transient_failures": 0,
            "next_at": 0, "last_reason": "new project"}


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_suffix(".tmp")
    with temp.open("w", encoding="utf8") as file:
        json.dump(data, file, indent=2, ensure_ascii=False)
        file.flush()
        os.fsync(file.fileno())
    os.chmod(temp, 0o600)
    os.replace(temp, path)


def log(path, event, state):
    # Do not log raw model outputs, raw tool traces or credentials.
    data = {"at": utc(time.time()), "event": event,
            "status": state.get("status"), "attempts": state.get("attempts"),
            "next_at": utc(state["next_at"]) if state.get("next_at") else None}
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_APPEND,0o600)
    with os.fdopen(fd,"a",encoding="utf8") as file:
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
    """Provider result -> durable state, never treating failed turns as success."""
    state = dict(previous)
    state["attempts"] = int(state.get("attempts",0))+1
    data = result.get("data") or {}
    data = data if isinstance(data, dict) else {}
    cid = data.get("conversation_id")
    err = str(data.get("error") or "")+"\n"+str(result.get("stderr") or "")
    status = str(data.get("status") or "").upper()
    if (state.get("conversation_id") and isinstance(cid,str) and cid and
            cid != state["conversation_id"]):
        state.update(status="NEEDS_USER",next_at=0,
                     last_reason="CLI returned different conversation ID; refusing context switch")
        return state
    # Never trust a reported new session on a failed invocation.
    if (not state.get("conversation_id") and result.get("code")==0 and
            status=="SUCCESS" and isinstance(cid,str) and re.fullmatch(
            r"[0-9A-Za-z-]{8,128}",cid)):
        state["conversation_id"]=cid
    if auth_error(err):
        state.update(status="NEEDS_USER",next_at=0,
                     last_reason="CLI authentication/permissions require user")
    elif quota_error(err):
        delay=reset_seconds(err)
        state.update(status="WAIT_QUOTA",
                     next_at=timestamp+(max(60,delay+RESET_GRACE)
                         if delay is not None else DEFAULT_QUOTA_POLL),
                     quota_hits=int(state.get("quota_hits",0))+1,
                     transient_failures=0,
                     last_reason="Provider quota exhausted; honoring reported refresh")
    elif result.get("code")==0 and status=="SUCCESS":
        state["transient_failures"]=0
        tag,note=agent_state(data.get("response",""))
        if tag in NEXT:
            state.update(status=tag,next_at=timestamp+NEXT[tag],
                         last_reason=note or "Agent turn checkpointed")
        elif tag:
            state.update(status=tag,next_at=0,last_reason=note or "Agent stopped")
        else:
            state.update(status="NEEDS_USER",next_at=0,last_reason=note)
    elif status in ("WAITING","CANCELED","INTERRUPTED") or result.get("code")==124:
        state.update(status="NEEDS_USER",next_at=0,
                     last_reason="Interaction/approval required or process timeout")
    elif temporary_error(err):
        n=int(state.get("transient_failures",0))+1
        if n>MAX_TRANSIENT_RETRIES:
            state.update(status="ERROR",next_at=0,transient_failures=n,
                         last_reason="Transient network retry budget exhausted")
        else:
            state.update(status="WAIT_RETRY",next_at=timestamp+min(900,60*2**(n-1)),
                         transient_failures=n,
                         last_reason="Transient transport error; bounded backoff")
    else:
        state.update(status="ERROR",next_at=0,
                     last_reason="Unexpected CLI error; operator inspection required")
    return state


def once(workspace, state_path, prompt_path, binary="agy", mode="auto",
         clock=None, runner=invoke, harness_state_dir=None):
    """One bounded turn. Production passes harness_state_dir for project guard."""
    ts=time.time() if clock is None else clock
    current=load(state_path)
    if current["status"] in STOP:
        return current
    if harness_state_dir is not None:
        try:
            info=quota_guard.inspect(harness_state_dir,current.get("project_id"))
            current["project_id"]=info["project_id"]
            if quota_guard.actual_completion(info):
                current.update(status="COMPLETE",next_at=0,
                               last_reason="Verified ACCEPTED Harness project checkpoint")
                save(state_path,current)
                return current
            if info["project_status"] in quota_guard.TERMINAL:
                raise quota_guard.ProjectGateError("Harness project needs user/review intervention")
            if not current.get("conversation_id"):
                cid=cached_conversation(workspace)
                if not cid:
                    raise quota_guard.ProjectGateError(
                        "No pinned Antigravity conversation found; supply --conversation")
                current["conversation_id"]=cid
            # Persist project/session binding before any CLI invocation.
            save(state_path,current)
        except quota_guard.ProjectGateError as exc:
            current.update(status="NEEDS_USER",next_at=0,last_reason=str(exc))
            save(state_path,current)
            log(state_path.parent/"quota-watchdog.log","PROJECT_GUARD",current)
            return current
    if float(current.get("next_at") or 0)>ts:
        return current
    prompt=prompt_path.read_text(encoding="utf8")
    if not prompt.strip():
        raise ValueError("Missing watchdog continuation instructions")
    if harness_state_dir is not None:
        prompt += (
            "\n\nSUPERVISOR PROJECT BINDING (source: read-only Harness SQLite): "
            + current["project_id"]
            + "\nResume ONLY this project; do not create or switch projects. "
            "If this project is blocked/needs user review, emit NEEDS_USER.\n"
        )
    try:
        outcome=runner(workspace,prompt,current.get("conversation_id"),
                       binary=binary,mode=mode)
    except (OSError,ValueError):
        outcome={"code":127,"data":{},"stderr":"Failed to launch CLI"}
    # Schedule reset/backoff from the completed CLI result, not turn start.
    finished=time.time() if clock is None else clock
    updated=evaluate(outcome,current,finished)
    if harness_state_dir is not None and updated["status"] not in {
            "WAIT_QUOTA","ERROR","NEEDS_USER","WAIT_RETRY"}:
        try:
            after=quota_guard.inspect(harness_state_dir,updated["project_id"])
            if quota_guard.actual_completion(after):
                updated.update(status="COMPLETE",next_at=0,
                               last_reason="Harness project verified accepted")
            elif updated["status"]=="COMPLETE":
                updated.update(status="NEEDS_USER",next_at=0,
                               last_reason="Agent reported COMPLETE without verified Harness acceptance")
            elif after["project_status"] in quota_guard.TERMINAL:
                updated.update(status="NEEDS_USER",next_at=0,
                               last_reason="Harness project needs user/review intervention")
        except quota_guard.ProjectGateError:
            updated.update(status="NEEDS_USER",next_at=0,
                           last_reason="Harness project disappeared after headless turn")
    save(state_path,updated)
    log(state_path.parent/"quota-watchdog.log","TURN",updated)
    return updated


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("run", "once", "status", "reset"))
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--conversation", default="")
    parser.add_argument("--project-id", default="")
    parser.add_argument("--harness-state-dir", default="")
    parser.add_argument("--binary", default="agy")
    parser.add_argument("--mode", default="auto",
                        choices=("auto","accept-edits","plan"))
    args = parser.parse_args(argv)
    root = Path(args.workspace).expanduser().resolve()
    state_file = root/".re_harness"/"quota-watchdog.json"
    prompt_file = root/"docs"/"QUOTA_WATCHDOG_TURN.md"
    db_dir = Path(args.harness_state_dir).expanduser().resolve() if args.harness_state_dir else root/".re_harness_mvp"
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
            state.update(status="READY",next_at=0,transient_failures=0,
                         last_reason="User resumed after intervention")
            if args.project_id:
                state["project_id"]=args.project_id
            if args.conversation:
                state["conversation_id"]=args.conversation
            save(state_file,state)
            return 0
        if args.project_id:
            if state.get("project_id") and state["project_id"]!=args.project_id:
                parser.error("Project mismatch; explicit reset required to change target")
            state["project_id"]=args.project_id
        if args.conversation:
            if state.get("conversation_id") and state["conversation_id"]!=args.conversation:
                parser.error("Conversation mismatch; explicit reset required to change target")
            state["conversation_id"]=args.conversation
        save(state_file,state)
        if args.action=="once":
            state=once(root,state_file,prompt_file,args.binary,args.mode,
                       harness_state_dir=db_dir)
            print(json.dumps(state, indent=2, ensure_ascii=False))
            return 0 if state["status"] not in {"ERROR","NEEDS_USER"} else 1
        while True:
            state=load(state_file)
            if state["status"] in STOP:
                return 0 if state["status"]=="COMPLETE" else 1
            if state.get("next_at",0)>time.time():
                time.sleep(min(60,max(1,state["next_at"]-time.time())))
                continue
            once(root,state_file,prompt_file,args.binary,args.mode,
                 harness_state_dir=db_dir)


if __name__=="__main__":
    raise SystemExit(main())
