"""Telegram ChatOps adapter powered by python-telegram-bot (optional dependency).

RE Dragon v0.7 — Telegram Orchestrator Control Center
No webhook, no remote shell, no model token, and strict private-chat allowlist.
Project lifecycle, task management, human approvals, redacted reports,
and deduplicated progress telemetry.
"""
from __future__ import annotations

import argparse
import contextlib
import subprocess
import asyncio
import fcntl
import getpass
import io
import json
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

from . import (
    autonomy,
    core,
    quota_guard,
    quota_watchdog,
    runtime_state,
    telegram_inbox,
    notification_delivery,
    telegram_control,
)

CONFIG = Path.home() / ".config" / "re-dragon" / "telegram.json"
FORBIDDEN_EXTENSIONS = {".apk", ".so", ".bin", ".elf", ".exe", ".dll", ".dex", ".o", ".a"}


def configure(input_fn=input, secret_fn=getpass.getpass):
    print("Create a Telegram bot with @BotFather (/newbot).")
    print("Find your numeric Telegram user ID using your Telegram account settings")
    print("or a trusted ID display bot; configure private-chat commands only.")
    token = secret_fn("Bot token (hidden): ").strip()
    uid = input_fn("Your Telegram numeric user ID: ").strip()
    if not token or ":" not in token or not uid.isdecimal() or int(uid) < 1:
        raise ValueError("Invalid bot token or numeric user ID")
    CONFIG.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = CONFIG.with_suffix(".tmp")
    temp.write_text(json.dumps({"token": token, "user_id": int(uid)}), encoding="utf8")
    os.chmod(temp, 0o600)
    os.replace(temp, CONFIG)
    print("Telegram configured locally; credentials never go into Git.")


def config():
    if not CONFIG.is_file():
        raise ValueError("First run: ./dragon telegram setup")
    if CONFIG.stat().st_mode & 0o077:
        raise ValueError("Telegram credentials must be chmod 600")
    data = json.loads(CONFIG.read_text(encoding="utf8"))
    if not isinstance(data, dict) or not data.get("token") or not isinstance(data.get("user_id"), int):
        raise ValueError("Invalid Telegram config")
    return data


def allowed(user_id, chat_id, chat_type, owner_id):
    return (chat_type == "private" and
            int(user_id or 0) == int(owner_id) and
            int(chat_id or 0) == int(owner_id))


def acquire_worker_lock(workspace, bot_fingerprint=None):
    """Ensure exactly one Telegram polling worker runs per workspace."""
    root = Path(workspace).resolve()
    lock_path = (Path.home()/".local"/"state"/"re-dragon"/(f"telegram-worker-{bot_fingerprint}.lock") if bot_fingerprint else root / ".re_harness" / "telegram.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    handle = lock_path.open("a+")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (BlockingIOError, OSError) as exc:
        handle.close()
        raise RuntimeError("Another Telegram bot worker is already running (locked)") from exc
    return handle


def watched(workspace):
    root = Path(workspace).resolve()
    state = quota_watchdog.load(root / ".re_harness" / "quota-watchdog.json")
    live = runtime_state.snapshot(root / ".re_harness" / "agent-runtime.json")
    return state, live


def status_text(workspace):
    state, live = watched(workspace)
    status = "AGENT_RUNNING" if live else state.get("status", "UNKNOWN")
    lines = [
        "RE Dragon — " + status,
        "Project: " + str(state.get("project_id") or "unbound"),
        "Turns completed: " + str(state.get("attempts", 0)),
        "Quota hits: " + str(state.get("quota_hits", 0)),
    ]
    if live:
        lines += [
            "PID: " + str(live["pid"]),
            "Elapsed: " + str(live["elapsed_seconds"]) + "s",
            "Heartbeat age: " + str(live["heartbeat_age_seconds"]) + "s",
        ]
    else:
        lines += ["Reason: " + str(state.get("last_reason", ""))[:220]]
    return "\n".join(lines)


@contextlib.contextmanager
def exclusive_controller_lock(workspace):
    """Project mutation is forbidden while Watchdog holds its process lock."""
    lock = Path(workspace).resolve()/".re_harness"/"quota-watchdog.lock"
    lock.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with lock.open("a+") as handle:
        try:
            fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except (BlockingIOError,OSError) as exc:
            raise ValueError(
                "Watchdog is active. Wait for the current turn/project to finish "
                "before changing the pinned project."
            ) from exc
        try:
            if runtime_state.snapshot(Path(workspace)/".re_harness"/"agent-runtime.json"):
                raise ValueError("Agent CLI still running; project switch refused.")
            yield
        finally:
            fcntl.flock(handle,fcntl.LOCK_UN)


def start_watchdog_for_new_goal(workspace):
    """Launch fixed local supervisor script, never user-supplied commands."""
    root=Path(workspace).resolve()
    script=root/"scripts"/"quota-watchdog.sh"
    if not script.is_file():
        raise ValueError("Watchdog launcher missing")
    try:
        proc=subprocess.run(
            ["bash",str(script),"start"],cwd=root,
            capture_output=True,text=True,timeout=20,check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:
        raise ValueError("Could not start watchdog: "+type(exc).__name__) from exc
    if proc.returncode!=0:
        raise ValueError("Watchdog start failed; use /status or check local logs")
    return proc.stdout.strip()[:180]


def switch_project(workspace, target_pid, db_dir=None):
    """Refuse project switching while an Agent/Watchdog process is active."""
    with exclusive_controller_lock(workspace):
        return _switch_project_locked(workspace,target_pid,db_dir=db_dir)


def _switch_project_locked(workspace,target_pid,db_dir=None):
    root = Path(workspace).resolve()
    db_path = Path(db_dir).resolve() if db_dir else root / ".re_harness_mvp"
    with core.database(db_path) as db:
        row = db.execute(
            "SELECT id, goal, status FROM auto_projects WHERE id=?",
            (target_pid.strip(),)
        ).fetchone()
        if not row:
            raise ValueError(f"Project '{target_pid}' not found in SQLite")
        if row["status"] == "ACCEPTED":
            raise ValueError(
                f"Project '{target_pid}' is ACCEPTED. Completed projects cannot be "
                "activated for execution; evidence and checkpoints are preserved."
            )

    state_path = root / ".re_harness" / "quota-watchdog.json"
    state = quota_watchdog.load(state_path)

    project_conversations = state.get("project_conversations", {})
    if state.get("project_id") and state.get("conversation_id"):
        project_conversations[state["project_id"]] = state["conversation_id"]
    state["project_conversations"] = project_conversations

    state["project_id"] = target_pid
    target_cid = project_conversations.get(target_pid)
    state["conversation_id"] = target_cid
    if not target_cid:
        state["bootstrap_new_conversation"] = True
    else:
        state.pop("bootstrap_new_conversation", None)

    state["status"] = "READY"
    state["next_at"] = 0
    state["attempts"] = 0
    state["quota_hits"] = 0
    state["transient_failures"] = 0
    state["last_reason"] = f"Activated project {target_pid}"
    quota_watchdog.save(state_path, state)

    return {
        "project_id": target_pid,
        "goal": row["goal"],
        "status": row["status"],
        "conversation_id": target_cid,
        "new_session": not bool(target_cid),
    }


def create_goal(workspace, goal_text, acceptance_text=None, db_dir=None):
    """Create a new project goal in SQLite and activate its dedicated session."""
    root = Path(workspace).resolve()
    cleaned_goal = str(goal_text or "").strip()
    if len(cleaned_goal) < 5 or len(cleaned_goal) > 500:
        raise ValueError("Goal description must be between 5 and 500 characters")

    cleaned_acc = str(acceptance_text or "").strip() or f"{cleaned_goal} (verified binary evidence)"
    if len(cleaned_acc) > 1000:
        raise ValueError("Acceptance criteria must not exceed 1000 characters")

    db_path = Path(db_dir).resolve() if db_dir else root / ".re_harness_mvp"
    with exclusive_controller_lock(root):
        return _create_goal_locked(root,cleaned_goal,cleaned_acc,db_path)


def _create_goal_locked(root,cleaned_goal,cleaned_acc,db_path):
    with core.database(db_path) as db:
        autonomy.migrate(db)
        dup = db.execute(
            "SELECT id, status FROM auto_projects WHERE lower(trim(goal)) = lower(trim(?))",
            (cleaned_goal,)
        ).fetchone()
        if dup:
            raise ValueError(f"Duplicate goal: project '{dup['id']}' already exists with status {dup['status']}")
        created = autonomy.start(db, cleaned_goal, cleaned_acc)
        new_pid = created["project_id"]

    _switch_project_locked(root, new_pid, db_dir=db_path)
    return {
        "project_id": new_pid,
        "goal": cleaned_goal,
        "acceptance": cleaned_acc,
        "status": "PLANNING",
        "new_session": True,
    }


def projects_text(workspace, db_dir=None):
    root = Path(workspace).resolve()
    db_path = Path(db_dir).resolve() if db_dir else root / ".re_harness_mvp"
    state, _ = watched(workspace)
    active_pid = state.get("project_id")
    with core.database(db_path) as db:
        projects = db.execute(
            "SELECT id, goal, status, updated_at FROM auto_projects ORDER BY updated_at DESC LIMIT 20"
        ).fetchall()
        if not projects:
            return "No projects registered in Harness SQLite."
        lines = ["📁 RE Dragon Projects:"]
        for p in projects:
            pid = p["id"]
            status = p["status"]
            goal = p["goal"][:50] + ("..." if len(p["goal"]) > 50 else "")
            counts = db.execute(
                "SELECT status, count(*) AS n FROM auto_tasks WHERE project_id=? GROUP BY status",
                (pid,)
            ).fetchall()
            stats = {c["status"]: c["n"] for c in counts}
            v_cnt = stats.get("VERIFIED", 0)
            tot = sum(stats.values())
            active_marker = "⭐ [ACTIVE] " if pid == active_pid else "   "
            lines.append(f"{active_marker}{pid} ({status}) [{v_cnt}/{tot} verified]\n    {goal}")
        lines.append("\nUse /project <id> to activate, or /newgoal <goal> to start a new project.")
        return "\n".join(lines)


def progress_text(workspace, db_dir=None):
    root = Path(workspace).resolve()
    state, live = watched(workspace)
    pid = state.get("project_id")
    if not pid:
        return "No pinned project yet. Use /projects or /newgoal."
    db_path = Path(db_dir).resolve() if db_dir else root / ".re_harness_mvp"
    with core.database(db_path) as db:
        proj = db.execute("SELECT id, goal, status FROM auto_projects WHERE id=?", (pid,)).fetchone()
        if not proj:
            return f"Active project '{pid}' not found in SQLite."
        tasks = db.execute(
            "SELECT task_key, status, review_note, result FROM auto_tasks WHERE project_id=?",
            (pid,)
        ).fetchall()

    counts = {}
    blocked_tasks = []
    for t in tasks:
        st = t["status"]
        counts[st] = counts.get(st, 0) + 1
        if st == "BLOCKED":
            reason = str(t["review_note"] or t["result"] or "blocked")[:100]
            blocked_tasks.append(f"{t['task_key']}: {reason}")

    total = len(tasks)
    verified = counts.get("VERIFIED", 0)
    pct = int((verified / total) * 100) if total > 0 else 0
    filled = pct // 10
    bar = "█" * filled + "░" * (10 - filled)

    lines = [
        f"⚡ Progress — Project: {pid}",
        f"Status: {proj['status']}",
        f"Goal: {proj['goal'][:100]}",
        f"Progress: [{bar}] {pct}% ({verified}/{total} verified)",
        "",
        "Task Breakdown:",
    ]
    for k in sorted(counts.keys()):
        lines.append(f"  • {k}: {counts[k]}")

    if blocked_tasks:
        lines.append("\n⚠️ Blockers:")
        for b in blocked_tasks[:5]:
            lines.append(f"  • {b}")

    inbox = telegram_inbox.summary(workspace, pid)
    queued_cnt = inbox.get("QUEUED", 0)
    if queued_cnt > 0:
        lines.append(f"\n📬 Telegram queued requests: {queued_cnt}")

    if not live and state.get("last_reason"):
        lines.append(f"\nSupervisor state: {state.get('status')} ({state.get('last_reason')[:120]})")
    return "\n".join(lines)


def task_detail_text(workspace, task_key, db_dir=None):
    root = Path(workspace).resolve()
    state, _ = watched(workspace)
    pid = state.get("project_id")
    if not pid:
        return "No pinned project yet."
    db_path = Path(db_dir).resolve() if db_dir else root / ".re_harness_mvp"
    with core.database(db_path) as db:
        try:
            res = autonomy.task_detail(db, pid, task_key.strip())
            detail = res["task"]
        except Exception as exc:
            return f"Task '{task_key}' not found or error: {str(exc)}"

    lines = [
        f"📋 Task Detail: {detail['task_key']} ({detail['status']})",
        f"Title: {detail['title']}",
        f"Kind: {detail['kind']} | Priority: {detail['priority']}",
        f"Acceptance: {detail['acceptance']}",
        f"Dependencies: {', '.join(detail.get('dependencies', [])) if detail.get('dependencies') else 'None'}",
        f"Producer: {detail['producer'] or 'None'} | Reviewer: {detail['reviewer'] or 'None'}",
        f"Attempts: {detail['tries']}",
        "",
        f"Evidence Refs: {detail.get('evidence_json') if detail.get('evidence_json') else 'None'}",
        f"Artifacts: {detail.get('artifacts_json') if detail.get('artifacts_json') else 'None'}",
        f"Verification Checks: {detail.get('verification_json') if detail.get('verification_json') else 'None'}",
    ]
    if detail.get("review_note"):
        lines.append(f"\nReview Note: {detail['review_note']}")
    if detail.get("result"):
        lines.append(f"\nResult: {detail['result'][:300]}")
    return "\n".join(lines)


def tasks_text(workspace, limit=15):
    state, _ = watched(workspace)
    pid = state.get("project_id")
    if not pid:
        return "No pinned project yet"
    info = quota_guard.inspect(Path(workspace) / ".re_harness_mvp", pid)
    uri = "file:" + str((Path(workspace) / ".re_harness_mvp" / "state.sqlite3").resolve()) + "?mode=ro"
    with sqlite3.connect(uri, uri=True) as db:
        rows = db.execute(
            "SELECT task_key,status,review_note FROM auto_tasks WHERE project_id=? "
            "ORDER BY updated_at DESC LIMIT ?", (pid, limit)).fetchall()
    head = "Project: " + str(pid) + " (" + info["project_status"] + ")"
    if not rows:
        return head + "\nNo planned tasks"
    inbox = telegram_inbox.summary(workspace, pid)
    task_lines = []
    for t, s, note in rows:
        if s == "BLOCKED":
            reason = f" (blocker: {note[:60]})" if note else ""
            task_lines.append(f"⚠️ {t}: {s}{reason}")
        else:
            task_lines.append(f"{t}: {s}")
    return "\n".join([head] + task_lines +
                     ["Telegram queued: " + str(inbox.get("QUEUED", 0))])


def submit_task(workspace, update_id, userid, chatid, body):
    state, _ = watched(workspace)
    pid = state.get("project_id")
    if not pid:
        raise ValueError("No pinned project")
    info = quota_guard.inspect(Path(workspace) / ".re_harness_mvp", pid)
    if info["project_status"] not in quota_guard.ACTIVE:
        raise ValueError("Project is not active; task not queued")
    return telegram_inbox.enqueue(workspace, pid, update_id, userid, chatid, body)


def redact_sensitive_text(text: str) -> str:
    """Filter out bot tokens, API keys, bearer tokens and private keys."""
    if not text:
        return ""
    text = re.sub(r"[0-9]{6,}:[A-Za-z0-9_-]{25,}", "[REDACTED_BOT_TOKEN]", text)
    text = re.sub(r"AIza[0-9A-Za-z_-]{35}", "[REDACTED_API_KEY]", text)
    text = re.sub(r"(Bearer\s+)[A-Za-z0-9_\-\.]{15,}", r"\1[REDACTED_TOKEN]", text)
    text = re.sub(r"-----BEGIN [A-Z ]+ PRIVATE KEY-----[\s\S]*?-----END [A-Z ]+ PRIVATE KEY-----",
                  "[REDACTED_PRIVATE_KEY]", text)
    return text


def export_project_report(workspace, pid=None, db_dir=None):
    """Export and redact durable project report, strictly forbidding binaries."""
    root = Path(workspace).resolve()
    db_path = Path(db_dir).resolve() if db_dir else root / ".re_harness_mvp"
    if not pid:
        state, _ = watched(workspace)
        pid = state.get("project_id")
        if not pid:
            raise ValueError("No active or specified project to report")

    with core.database(db_path) as db:
        row = db.execute("SELECT id, goal, status FROM auto_projects WHERE id=?", (pid,)).fetchone()
        if not row:
            raise ValueError(f"Project '{pid}' not found")
        task_rows = db.execute("SELECT task_key, status FROM auto_tasks WHERE project_id=?", (pid,)).fetchall()
        counts = {}
        for r in task_rows:
            counts[r["status"]] = counts.get(r["status"], 0) + 1
        export_res = autonomy.export_report(db, db_path, pid)
        report_file = Path(export_res["report"]).resolve()

    # Strictly forbid binary extensions first
    if report_file.suffix.lower() in FORBIDDEN_EXTENSIONS or any(part.lower().endswith(s) for s in FORBIDDEN_EXTENSIONS for part in report_file.parts):
        raise ValueError("Binary and artifact export forbidden; reports only")

    # Path safety & Ownership check
    allowed_dir = (db_path / "auto_reports").resolve()
    if not (str(report_file).startswith(str(allowed_dir) + os.sep) or report_file == allowed_dir / f"{pid}.md"):
        raise ValueError("Report path ownership violation: file outside auto_reports directory")

    if report_file.suffix.lower() not in (".md", ".txt"):
        raise ValueError("Invalid report format; markdown reports only")

    raw_text = report_file.read_text(encoding="utf-8")
    redacted = redact_sensitive_text(raw_text)

    verified_cnt = counts.get("VERIFIED", 0)
    blocked_cnt = counts.get("BLOCKED", 0)
    total_cnt = len(task_rows)
    other_cnt = total_cnt - verified_cnt - blocked_cnt

    summary_lines = [
        f"📊 RE Dragon Report — {pid}",
        f"Goal: {row['goal'][:100]}",
        f"Project Status: {row['status']}",
        f"Tasks Total: {total_cnt}",
        f"  • VERIFIED: {verified_cnt}",
        f"  • BLOCKED: {blocked_cnt}",
        f"  • OTHER / IN-PROGRESS: {other_cnt}",
    ]
    return {
        "project_id": pid,
        "status": row["status"],
        "counts": counts,
        "summary": "\n".join(summary_lines),
        "filename": f"report_{pid}.md",
        "redacted_content": redacted,
        "path": report_file,
    }


def notification_signature(workspace):
    """Return only significant, discrete status changes without heartbeat jitter."""
    root = Path(workspace).resolve()
    state, live = watched(workspace)
    pid = state.get("project_id")
    if not pid:
        return None, None
    status = state.get("status")

    counts = {}
    pending_props = 0
    try:
        info = quota_guard.inspect(root / ".re_harness_mvp", pid)
        counts = info.get("task_status_counts", {})
    except (quota_guard.ProjectGateError, sqlite3.Error):
        pass

    try:
        props = telegram_inbox.list_proposals(root, pid, status="PENDING")
        pending_props = len(props)
    except (sqlite3.Error, OSError):
        pass

    completed = int(counts.get("VERIFIED", 0))
    blocked = int(counts.get("BLOCKED", 0))
    submitted = int(counts.get("SUBMITTED", 0))

    if status == "COMPLETE":
        return f"{pid}:COMPLETE", status_text(workspace)
    if status in {"WAIT_QUOTA", "NEEDS_USER", "ERROR", "BLOCKED"}:
        return f"{pid}:{status}:v{completed}:b{blocked}", status_text(workspace)

    if (not live and status == "WAIT" and
            any(term in str(state.get("last_reason", "")).lower()
                for term in ("memory headroom", "resource reservation", "insufficient memory"))):
        return f"{pid}:WAIT_RESOURCE", status_text(workspace)

    if pending_props > 0:
        return f"{pid}:proposals:{pending_props}", (
            f"⚠️ RE Dragon: {pending_props} pending approval proposal(s) for project {pid}\n"
            "Use /approvals to inspect and decide."
        )

    if blocked > 0:
        return f"{pid}:blocked:{blocked}", (
            f"⚠️ RE Dragon: {blocked} task(s) currently BLOCKED in project {pid}\n"
            "Use /tasks or /progress to inspect blockers."
        )

    if submitted > 0:
        return f"{pid}:submitted:{submitted}", (
            f"🔍 RE Dragon: {submitted} task(s) awaiting review in project {pid}\n"
            "Use /tasks to check submission queue."
        )

    if completed > 0:
        return f"{pid}:verified:{completed}", (
            f"✅ RE Dragon: {completed} verified tasks for project {pid}\n"
            "Use /progress or /tasks for details."
        )

    return None, None


async def telegram_probe(bot_factory, token):
    """Read-only Bot API connectivity and webhook check; redact credentials."""
    bot = bot_factory(token)
    async with bot:
        me = await asyncio.wait_for(bot.get_me(), timeout=20)
        hook = await asyncio.wait_for(bot.get_webhook_info(), timeout=20)
    return {
        "api_reachable": True,
        "bot_username": getattr(me, "username", None),
        "webhook_configured": bool(getattr(hook, "url", "")),
        "pending_updates": getattr(hook, "pending_update_count", None),
    }


def doctor():
    """Safe on an active bot: no getUpdates, no webhook deletion, no token echo."""
    try:
        from telegram import Bot
        from telegram.error import InvalidToken, NetworkError, TimedOut
        creds = config()
    except (ImportError, ValueError, OSError) as exc:
        print("Telegram doctor: local setup unavailable:", type(exc).__name__)
        return 2
    print("Telegram doctor: testing getMe/getWebhookInfo via WSL2 (no changes)...",
          flush=True)
    try:
        report = asyncio.run(telegram_probe(Bot, creds["token"]))
    except InvalidToken:
        print("ERROR: invalid/revoked Bot Token. Update with ./dragon telegram setup.")
        return 2
    except (NetworkError, TimedOut, OSError, asyncio.TimeoutError) as exc:
        print("ERROR: cannot reach Telegram Bot API from WSL2:", type(exc).__name__)
        print("Check DNS, network policy, HTTPS access to api.telegram.org, "
              "or whether Telegram Desktop uses a separate proxy.")
        return 2
    except Exception as exc:
        print("ERROR: Telegram Bot API check failed:", type(exc).__name__)
        return 2
    print("Bot API: OK; username: @" + str(report["bot_username"]))
    print("Telegram polling webhook conflict:",
          "YES" if report["webhook_configured"] else "NO")
    print("Pending updates:", report["pending_updates"])
    if report["webhook_configured"]:
        print("BLOCKED: webhook is configured; polling needs a cleared webhook.")
        print("No webhook was changed by this diagnostic.")
        return 3
    print("API connectivity OK. If messages still have no replies, inspect the "
          "tmux bot log for polling/handler errors.")
    return 0


def serve(workspace):
    try:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        from telegram.ext import ApplicationBuilder, CallbackQueryHandler, CommandHandler
    except ImportError as exc:
        raise RuntimeError("Install: python3 -m pip install -e '.[telegram]'") from exc
    return _serve_impl(workspace, ApplicationBuilder, CommandHandler, CallbackQueryHandler,
                       InlineKeyboardButton, InlineKeyboardMarkup)


def _serve_impl(workspace, ApplicationBuilder, CommandHandler, CallbackQueryHandler,
                InlineKeyboardButton, InlineKeyboardMarkup):
    creds = config()
    owner = int(creds["user_id"])
    root = Path(workspace).resolve()

    lock_handle = acquire_worker_lock(root, notification_delivery.bot_fingerprint(creds["token"]))
    app = ApplicationBuilder().token(creds["token"]).build()
    holder = {"task": None}

    async def auth(update):
        u = update.effective_user
        c = update.effective_chat
        if not allowed(getattr(u, "id", 0), getattr(c, "id", 0), getattr(c, "type", ""), owner):
            if update.effective_message:
                await update.effective_message.reply_text("Unauthorized")
            elif update.callback_query:
                await update.callback_query.answer("Unauthorized", show_alert=True)
            return False
        return True

    def control_keyboard(row):
        return InlineKeyboardMarkup([[
            InlineKeyboardButton("Confirm", callback_data=f"ctrl:{row['id']}:{row['nonce']}:APPROVE"),
            InlineKeyboardButton("Cancel", callback_data=f"ctrl:{row['id']}:{row['nonce']}:REJECT")
        ]])

    async def command(update, context):
        if not await auth(update):
            return
        cmd_text = update.message.text or ""
        name = cmd_text.split()[0].split("@")[0].lower()

        if name in ("/start", "/help"):
            msg = (
                "🐉 RE Dragon v0.7 — Telegram Control Center\n\n"
                "Project Lifecycle:\n"
                "  /projects — List all projects and status\n"
                "  /newgoal <goal> [| <acceptance>] — Propose new goal for confirmation\n"
                "  /project <id> — Request confirmation before switch\n\n"
                "Task Management:\n"
                "  /tasks [limit] — List tasks and highlight blockers\n"
                "  /task <desc> — Queue user task for next agent turn\n"
                "  /progress — Show progress bar and blocker breakdown\n"
                "  /taskdetail <key> — Inspect evidence and review notes\n\n"
                "Human Approval:\n"
                "  /approvals — List pending human and controller decisions\n"
                "  /propose <action> <desc> — Submit a proposal\n\n"
                "Reports & Status:\n"
                "  /report — Export summary and redacted report\n"
                "  /status — Live watchdog and agent telemetry\n"
            )
            await update.message.reply_text(msg[:3900])
            return

        if name == "/status":
            await update.message.reply_text(status_text(root)[:3900])
            return

        if name == "/projects":
            await update.message.reply_text(projects_text(root)[:3900])
            return

        if name in ("/project", "/activate", "/newgoal"):
            body = " ".join(context.args or []).strip()
            if not body:
                usage=("/newgoal <goal> [| <acceptance>]" if name=="/newgoal"
                       else "/project <project_id>")
                await update.message.reply_text("Usage: "+usage)
                return
            if name=="/newgoal":
                parts=[p.strip() for p in body.split("|",1)]
                goal=parts[0]
                acceptance=parts[1] if len(parts)>1 else None
                if not 5<=len(goal)<=500 or (acceptance and len(acceptance)>1000):
                    await update.message.reply_text("Goal must be 5-500 characters; acceptance <=1000")
                    return
                kind,payload="NEW_GOAL",{"goal":goal,"acceptance":acceptance}
                desc=f"New goal: {goal[:250]}\\nAcceptance: {(acceptance or 'Harness-defined')[:200]}"
            else:
                target=body.split()[0]
                if len(target)>80:
                    await update.message.reply_text("Invalid project ID")
                    return
                kind,payload="SWITCH_PROJECT",{"project_id":target}
                desc=f"Switch active project to {target}"
            try:
                row,_=telegram_control.propose(
                    root,update.update_id,update.effective_user.id,kind,payload)
                await update.message.reply_text(
                    f"Please confirm within 10 minutes:\\n{desc}\\n"
                    "No project has been created or switched yet.",
                    reply_markup=control_keyboard(row))
            except (ValueError,sqlite3.Error) as exc:
                await update.message.reply_text("Cannot prepare confirmation: "+str(exc)[:180])
            return

        if name == "/tasks":
            try:
                msg = tasks_text(root)
            except (ValueError, sqlite3.Error, quota_guard.ProjectGateError):
                msg = "Checkpoint unavailable"
            await update.message.reply_text(msg[:3900])
            return

        if name == "/task":
            body = " ".join(context.args or []).strip()
            if not body:
                await update.message.reply_text("Usage: /task <description>")
            else:
                try:
                    rid, created = submit_task(root, update.update_id, update.effective_user.id,
                                               update.effective_chat.id, body)
                    msg = ("Queued" if created else "Already queued") + f" #{rid}. Forwarded on next turn, not yet VERIFIED."
                except (ValueError, sqlite3.Error, quota_guard.ProjectGateError) as exc:
                    msg = "Not queued: " + str(exc)[:200]
                await update.message.reply_text(msg[:3900])
            return

        if name == "/progress":
            await update.message.reply_text(progress_text(root)[:3900])
            return

        if name == "/taskdetail":
            args = context.args or []
            if not args:
                await update.message.reply_text("Usage: /taskdetail <task_key>")
                return
            await update.message.reply_text(task_detail_text(root, args[0].strip())[:3900])
            return

        if name == "/propose":
            args = context.args or []
            if len(args) < 2:
                await update.message.reply_text("Usage: /propose <ACTION> <description>")
                return
            action = args[0].strip().upper()
            desc = " ".join(args[1:]).strip()
            state, _ = watched(root)
            pid = state.get("project_id")
            if not pid:
                await update.message.reply_text("No active project.")
                return
            try:
                prop = telegram_inbox.create_proposal(root, pid, action, desc)
                await update.message.reply_text(f"Proposal created: #{prop['id']} for {pid} ({action}).")
            except Exception as exc:
                await update.message.reply_text(f"Error: {str(exc)[:200]}")
            return

        if name == "/approvals":
            state, _ = watched(root)
            pid = state.get("project_id")
            proposals = telegram_inbox.list_proposals(root, pid, status="PENDING")
            control_pending=telegram_control.list_pending(root,update.effective_user.id)
            if not proposals and not control_pending:
                await update.message.reply_text(f"No pending approvals for project {pid or 'all'}.")
                return
            for ctl in control_pending[:5]:
                desc=json.loads(ctl["payload"])
                await update.message.reply_text(
                    f"Pending controller confirmation ({ctl['kind']}):\n{str(desc)[:320]}",
                    reply_markup=control_keyboard(ctl))
            for prop in proposals[:5]:
                rem_sec = max(0, int(prop["expires_at"] - time.time()))
                rem_min = rem_sec // 60
                prop_text = (
                    f"⚖️ Approval Proposal: #{prop['id']}\n"
                    f"Project: {prop['project_id']}\n"
                    f"Action: {prop['action']}\n"
                    f"Description: {prop['description']}\n"
                    f"Expires in: {rem_min}m"
                )
                keyboard = InlineKeyboardMarkup([
                    [
                        InlineKeyboardButton("✅ Xác nhận (Approve)", callback_data=f"appr:{prop['id']}:{prop['nonce']}:APPROVE"),
                        InlineKeyboardButton("❌ Từ chối (Reject)", callback_data=f"appr:{prop['id']}:{prop['nonce']}:REJECT"),
                    ],
                    [
                        InlineKeyboardButton("✏️ Yêu cầu sửa (Rework)", callback_data=f"appr:{prop['id']}:{prop['nonce']}:REWORK"),
                    ]
                ])
                await update.message.reply_text(prop_text[:3900], reply_markup=keyboard)
            return

        if name == "/report":
            state, _ = watched(root)
            pid = state.get("project_id")
            try:
                rep = export_project_report(root, pid)
                await update.message.reply_text(rep["summary"][:3900])
                if hasattr(update.message, "reply_document"):
                    bio = io.BytesIO(rep["redacted_content"].encode("utf-8"))
                    bio.name = rep["filename"]
                    await update.message.reply_document(
                        document=bio,
                        filename=rep["filename"],
                        caption=f"RE Dragon Redacted Report ({pid})"
                    )
            except Exception as exc:
                await update.message.reply_text(f"❌ Report export failed: {str(exc)[:200]}")
            return

        await update.message.reply_text("Unsupported command. Use /help.")

    async def callback_query(update, context):
        if not await auth(update):
            return
        query = update.callback_query
        data = query.data or ""
        if data.startswith("ctrl:"):
            parts=data.split(":")
            if len(parts)!=4:
                await query.answer("Malformed confirmation",show_alert=True)
                return
            _,req_id,nonce,decision=parts
            try:
                ctl=telegram_control.claim(root,req_id,nonce,
                    update.effective_user.id,decision)
            except (ValueError,sqlite3.Error) as exc:
                await query.answer(str(exc)[:150],show_alert=True)
                return
            await query.answer("Decision received")
            if decision=="REJECT":
                await query.edit_message_text("Control request cancelled; no project changed.")
                return
            try:
                if ctl["kind"]=="NEW_GOAL":
                    d=ctl["payload"]
                    result=await asyncio.to_thread(
                        create_goal,root,d["goal"],d.get("acceptance"))
                elif ctl["kind"]=="SWITCH_PROJECT":
                    result=await asyncio.to_thread(
                        switch_project,root,ctl["payload"]["project_id"])
                else:
                    raise ValueError("Unrecognized controller action")
            except Exception as exc:
                telegram_control.complete(root,req_id,"FAILED",str(exc))
                await query.edit_message_text(
                    "Project change refused; Watchdog not rearmed. "+str(exc)[:220])
                return
            try:
                launch=await asyncio.to_thread(start_watchdog_for_new_goal,root)
            except Exception as exc:
                telegram_control.complete(root,req_id,"FAILED_START",str(exc))
                await query.edit_message_text(
                    f"Project {result['project_id']} activated, but Watchdog "
                    f"could not start: {str(exc)[:180]}. Use /status to inspect.")
                return
            telegram_control.complete(root,req_id,"DONE",result["project_id"])
            await query.edit_message_text(
                f"Project {result['project_id']} activated.\\n"
                f"Watchdog launcher: {launch}\\n"
                "Use /status and /progress to follow execution.")
            return
        if data.startswith("appr:"):
            parts = data.split(":")
            if len(parts) == 4:
                _, prop_id, nonce, decision = parts
                u = update.effective_user
                actor_name = getattr(u, "username", "") or str(getattr(u, "id", 0))
                res = telegram_inbox.decide_proposal(root, prop_id, decision, u.id, actor_name, nonce=nonce)
                if res["success"]:
                    await query.answer(f"Proposal {decision} recorded")
                    await query.edit_message_text(
                        f"⚖️ Proposal #{prop_id} [{decision}]\n"
                        f"Actor: @{actor_name} (ID: {u.id})\n"
                        f"Decision: {decision}\n"
                        f"Status: Committed in transactional audit log."
                    )
                else:
                    await query.answer(res["reason"], show_alert=True)
                    if "already decided" in res["reason"].lower() or "expired" in res["reason"].lower():
                        await query.edit_message_text(
                            f"Proposal #{prop_id} cannot be modified ({res['reason']})."
                        )

    command_names = [
        "start", "help", "status", "projects", "project", "activate",
        "newgoal", "tasks", "task", "progress", "taskdetail",
        "approvals", "propose", "report"
    ]
    for c_name in command_names:
        app.add_handler(CommandHandler(c_name, command))
    app.add_handler(CallbackQueryHandler(callback_query))

    async def bot_error(update, context):
        print("Telegram handler/polling error:", type(context.error).__name__, file=sys.stderr, flush=True)

    app.add_error_handler(bot_error)

    async def monitor():
        last = None
        while True:
            try:
                sig, msg = notification_signature(root)
                if sig and sig != last:
                    if notification_delivery.claim(creds["token"], owner, sig):
                        try:
                            await app.bot.send_message(chat_id=owner, text=msg[:3900])
                        except Exception as exc:
                            print("Telegram delivery uncertain; not retrying:",
                                  type(exc).__name__,file=sys.stderr,flush=True)
                        else:
                            notification_delivery.delivered(creds["token"],owner,sig)
                    last = sig
            except Exception as exc:
                print("Telegram monitor:",type(exc).__name__,file=sys.stderr,flush=True)
            await asyncio.sleep(15)

    async def post_init(application):
        print("Telegram adapter initialized for @" +
              str(getattr(application.bot, "username", "unknown")) +
              "; polling will start next", flush=True)
        holder["task"] = asyncio.create_task(monitor())

    async def post_stop(application):
        task = holder["task"]
        if task:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        if lock_handle:
            try:
                fcntl.flock(lock_handle, fcntl.LOCK_UN)
                lock_handle.close()
            except OSError:
                pass

    app.post_init = post_init
    app.post_stop = post_stop
    app.run_polling(drop_pending_updates=False, allowed_updates=["message", "callback_query"])
    return 0


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("action", choices=("setup", "run", "doctor"))
    p.add_argument("--workspace", default=".")
    args = p.parse_args(argv)
    if args.action == "setup":
        try:
            configure()
        except ValueError as e:
            p.exit(2, str(e) + "\n")
        return 0
    if args.action == "doctor":
        return doctor()
    try:
        return serve(args.workspace)
    except (ValueError, RuntimeError) as e:
        p.exit(2, str(e) + "\n")


if __name__ == "__main__":
    raise SystemExit(main())
