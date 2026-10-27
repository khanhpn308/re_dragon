"""Telegram ChatOps adapter powered by python-telegram-bot (optional dependency).

No webhook, no remote shell, no model token and no arbitrary project switching.
The controller remains RE Dragon. This bot only reports and queues user tasks.
"""
from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import sqlite3
import sys
from pathlib import Path

from . import quota_guard, quota_watchdog, runtime_state, telegram_inbox

CONFIG=Path.home()/".config"/"re-dragon"/"telegram.json"


def configure(input_fn=input,secret_fn=getpass.getpass):
    print("Create a Telegram bot with @BotFather (/newbot).")
    print("Find your numeric Telegram user ID using your Telegram account settings")
    print("or a trusted ID display bot; configure private-chat commands only.")
    token=secret_fn("Bot token (hidden): ").strip()
    uid=input_fn("Your Telegram numeric user ID: ").strip()
    if not token or ":" not in token or not uid.isdecimal() or int(uid)<1:
        raise ValueError("Invalid bot token or numeric user ID")
    CONFIG.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temp=CONFIG.with_suffix(".tmp")
    temp.write_text(json.dumps({"token":token,"user_id":int(uid)}),encoding="utf8")
    os.chmod(temp,0o600)
    os.replace(temp,CONFIG)
    print("Telegram configured locally; credentials never go into Git.")


def config():
    if not CONFIG.is_file():
        raise ValueError("First run: ./dragon telegram setup")
    if CONFIG.stat().st_mode & 0o077:
        raise ValueError("Telegram credentials must be chmod 600")
    data=json.loads(CONFIG.read_text(encoding="utf8"))
    if not isinstance(data,dict) or not data.get("token") or not isinstance(data.get("user_id"),int):
        raise ValueError("Invalid Telegram config")
    return data


def allowed(user_id,chat_id,chat_type,owner_id):
    return (chat_type=="private" and
            int(user_id or 0)==int(owner_id) and
            int(chat_id or 0)==int(owner_id))


def watched(workspace):
    root=Path(workspace).resolve()
    state=quota_watchdog.load(root/".re_harness"/"quota-watchdog.json")
    live=runtime_state.snapshot(root/".re_harness"/"agent-runtime.json")
    return state,live


def status_text(workspace):
    state,live=watched(workspace)
    status="AGENT_RUNNING" if live else state.get("status","UNKNOWN")
    lines=["RE Dragon — "+status,
           "Project: "+str(state.get("project_id") or "unbound"),
           "Turns completed: "+str(state.get("attempts",0)),
           "Quota hits: "+str(state.get("quota_hits",0))]
    if live:
        lines += ["PID: "+str(live["pid"]),
                  "Elapsed: "+str(live["elapsed_seconds"])+"s",
                  "Heartbeat age: "+str(live["heartbeat_age_seconds"])+"s"]
    else:
        lines += ["Reason: "+str(state.get("last_reason",""))[:220]]
    return "\n".join(lines)


def tasks_text(workspace,limit=15):
    state,_=watched(workspace)
    pid=state.get("project_id")
    if not pid:
        return "No pinned project yet"
    info=quota_guard.inspect(Path(workspace)/".re_harness_mvp",pid)
    uri="file:"+str((Path(workspace)/".re_harness_mvp"/"state.sqlite3").resolve())+"?mode=ro"
    with sqlite3.connect(uri,uri=True) as db:
        rows=db.execute(
            "SELECT task_key,status FROM auto_tasks WHERE project_id=? "
            "ORDER BY updated_at DESC LIMIT ?",(pid,limit)).fetchall()
    head="Project: "+str(pid)+" ("+info["project_status"]+")"
    if not rows:
        return head+"\nNo planned tasks"
    inbox=telegram_inbox.summary(workspace,pid)
    return "\n".join([head]+[str(t)+": "+str(s) for t,s in rows]+
                     ["Telegram queued: "+str(inbox.get("QUEUED",0))])


def submit_task(workspace,update_id,userid,chatid,body):
    state,_=watched(workspace)
    pid=state.get("project_id")
    if not pid:
        raise ValueError("No pinned project")
    info=quota_guard.inspect(Path(workspace)/".re_harness_mvp",pid)
    if info["project_status"] not in quota_guard.ACTIVE:
        raise ValueError("Project is not active; task not queued")
    return telegram_inbox.enqueue(workspace,pid,update_id,userid,chatid,body)


def notification_signature(workspace):
    """Return only significant, non-secret status changes."""
    state,live=watched(workspace)
    pid=state.get("project_id")
    if not pid:
        return None,None
    status=state.get("status")
    counts={}
    try:
        info=quota_guard.inspect(Path(workspace)/".re_harness_mvp",pid)
        counts=info["task_status_counts"]
    except (quota_guard.ProjectGateError,sqlite3.Error):
        pass
    completed=int(counts.get("VERIFIED",0))
    if status in {"WAIT_QUOTA","NEEDS_USER","ERROR","BLOCKED","COMPLETE"}:
        return f"{pid}:{status}:{completed}",status_text(workspace)
    if completed>0:
        return f"{pid}:verified:{completed}",(
            f"RE Dragon: {completed} verified tasks\nProject: {pid}\n"
            "Use /tasks for details."
        )
    return None,None


def serve(workspace):
    try:
        from telegram.ext import ApplicationBuilder,CommandHandler
    except ImportError as exc:
        raise RuntimeError("Install: python3 -m pip install -e '.[telegram]'") from exc
    # construct the app inside a single synchronous entrypoint.
    return _serve_impl(workspace,ApplicationBuilder,CommandHandler)


def _serve_impl(workspace,ApplicationBuilder,CommandHandler):
    creds=config(); owner=int(creds["user_id"]); root=Path(workspace).resolve()
    app=ApplicationBuilder().token(creds["token"]).build()
    holder={"task":None}
    async def auth(update):
        u=update.effective_user; c=update.effective_chat
        if not allowed(getattr(u,"id",0),getattr(c,"id",0),getattr(c,"type",""),owner):
            if update.effective_message:
                await update.effective_message.reply_text("Unauthorized")
            return False
        return True
    async def command(update,context):
        if not await auth(update):return
        name=update.message.text.split()[0].split("@")[0].lower()
        if name in ("/start","/help"):
            msg="/status, /tasks, /task <description>\nTasks are queued for the next Agent turn. No shell or arbitrary execution."
        elif name=="/status":
            msg=status_text(root)
        elif name=="/tasks":
            try:msg=tasks_text(root)
            except (ValueError,sqlite3.Error,quota_guard.ProjectGateError):msg="Checkpoint unavailable"
        elif name=="/task":
            body=" ".join(context.args).strip()
            if not body:
                msg="Usage: /task <description>"
            else:
                try:
                    rid,created=submit_task(root,update.update_id,update.effective_user.id,update.effective_chat.id,body)
                    msg=("Queued" if created else "Already queued")+f" #{rid}. Forwarded on next turn, not yet VERIFIED."
                except (ValueError,sqlite3.Error,quota_guard.ProjectGateError) as exc:
                    msg="Not queued: "+str(exc)[:200]
        else:msg="Unsupported command"
        await update.message.reply_text(msg[:3900])
    for name in ("start","help","status","tasks","task"):
        app.add_handler(CommandHandler(name,command))
    async def monitor():
        last=None
        while True:
            try:
                sig,msg=notification_signature(root)
                if sig and sig!=last:
                    with telegram_inbox.connection(root) as db:
                        db.execute("CREATE TABLE IF NOT EXISTS notification_cursor("
                                   "name TEXT PRIMARY KEY, signature TEXT NOT NULL)")
                        rec=db.execute("SELECT signature FROM notification_cursor "
                                       "WHERE name='watchdog'").fetchone()
                        if not rec or rec[0]!=sig:
                            await app.bot.send_message(chat_id=owner,text=msg[:3900])
                            db.execute("INSERT INTO notification_cursor(name,signature) "
                                       "VALUES('watchdog',?) ON CONFLICT(name) "
                                       "DO UPDATE SET signature=excluded.signature",(sig,))
                    last=sig
            except Exception as exc:
                print("Telegram monitor:",type(exc).__name__,file=sys.stderr)
            await asyncio.sleep(30)
    async def post_init(application):
        holder["task"]=asyncio.create_task(monitor())
    async def post_stop(application):
        task=holder["task"]
        if task:
            task.cancel()
            try:await task
            except asyncio.CancelledError:pass
    app.post_init=post_init
    app.post_stop=post_stop
    app.run_polling(drop_pending_updates=False,allowed_updates=["message"])
    return 0


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("action",choices=("setup","run"))
    p.add_argument("--workspace",default=".")
    args=p.parse_args(argv)
    if args.action=="setup":
        try: configure()
        except ValueError as e:p.exit(2,str(e)+"\n")
        return 0
    try:return serve(args.workspace)
    except (ValueError,RuntimeError) as e:
        p.exit(2,str(e)+"\n")


if __name__=="__main__":
    raise SystemExit(main())
