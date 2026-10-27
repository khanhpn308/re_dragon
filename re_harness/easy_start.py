"""One-time, ID-free production onboarding for the quota watchdog.

This module only seeds/chooses the explicitly approved ReturnSaiyan
content-integration goal. It never calls a model or starts an agent itself.
Subsequent start invocations reuse the durable project/session binding.
"""
from __future__ import annotations

import argparse
import fcntl
import json
from pathlib import Path

from . import autonomy, core, quota_guard, quota_watchdog

TITLE = "ReturnSaiyan — Unified Heroes Edition"
ACCEPTANCE = (
    "Preserve the currently playable ReturnSaiyan APK and all existing heroes "
    "(including its two newer heroes). Inventory both ReturnSaiyan and Dragon Ball "
    "Global 1.1.13 resources; map hero, actor, skeleton, animation, texture, "
    "skills and skins with binary-backed evidence. Integrate missing compatible "
    "assets in a reversible copy without modifying original APK/SO; verify "
    "client rendering and animation; distinguish server-controlled playable "
    "hero availability from client assets and never interact with a live game "
    "server. Perform independent review, offline and controlled Android tests, "
    "document unsupported features and release only an evidenced build."
)
GOAL = (
    TITLE + ": integrate the missing Dragon Ball Global hero resources into "
    "the working ReturnSaiyan client while preserving its gameplay and heroes."
)
VALID_STATES = {"PLANNING", "ACTIVE"}


class SetupError(ValueError):
    pass


def _select_project(db):
    matches = db.execute(
        "SELECT id,status FROM auto_projects WHERE goal LIKE ? "
        "ORDER BY created_at DESC",
        (TITLE+"%",),
    ).fetchall()
    if len(matches) > 1:
        raise SetupError(
            "Multiple ReturnSaiyan production goals already exist; "
            "choose/resolve the correct project before enabling unattended runs"
        )
    if matches:
        row=matches[0]
        if row["status"] not in VALID_STATES:
            raise SetupError("Production goal is "+row["status"]+
                             "; will not restart or duplicate a closed project")
        return row["id"], False

    # Never replace unrelated active or pilot projects; they remain intact.
    created=autonomy.start(db,GOAL,ACCEPTANCE)
    return created["project_id"], True


def bootstrap(workspace, state_dir=None):
    root=Path(workspace).expanduser().resolve()
    watch_dir=root/".re_harness"
    watch_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
    state_path=watch_dir/"quota-watchdog.json"
    db_dir=Path(state_dir).expanduser().resolve() if state_dir else root/".re_harness_mvp"
    lock_path=watch_dir/"quota-watchdog.lock"
    with lock_path.open("a+") as handle:
        try:
            fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SetupError("Watchdog currently running; inspect status first") from exc
        state=quota_watchdog.load(state_path)

        # Only clear literal tutorial placeholders, not arbitrary broken bindings.
        if state.get("project_id") == "PROJECT_ID" and state.get("conversation_id") == "CONVERSATION_ID":
            state=quota_watchdog.load(watch_dir/"_nonexistent_initial_state.json")
        elif state.get("project_id") in {"PROJECT_ID","CONVERSATION_ID"} or state.get("conversation_id") in {"PROJECT_ID","CONVERSATION_ID"}:
            raise SetupError("Partial example ID binding found; reset it manually")

        if state.get("status") in quota_watchdog.STOP:
            raise SetupError(
                "Watchdog stopped at "+state["status"]+
                ". Resolve the blocker explicitly with ./dragon resume; "
                "do not auto-override a real failure."
            )
        with core.database(db_dir) as db:
            autonomy.migrate(db)
            project_id,created=_select_project(db)
        if state.get("project_id") and state["project_id"]!=project_id:
            raise SetupError("Watchdog pinned to another project; cannot silently switch")
        state["project_id"]=project_id
        if not state.get("conversation_id"):
            # A brand-new CLI headless conversation is safer than --continue,
            # which may silently switch to an old unrelated pilot session.
            state["bootstrap_new_conversation"]=True
        else:
            state.pop("bootstrap_new_conversation",None)
        quota_watchdog.save(state_path,state)
        return {"project_id":project_id,"project_created":created,
                "conversation":("pinned" if state.get("conversation_id")
                                else "new dedicated headless session"),
                "status":state["status"]}


def main(argv=None):
    p=argparse.ArgumentParser(description="One-time ReturnSaiyan production bootstrap")
    p.add_argument("--workspace",default=".")
    p.add_argument("--state-dir",default="")
    args=p.parse_args(argv)
    try:
        info=bootstrap(args.workspace,args.state_dir or None)
    except (SetupError, OSError, ValueError) as exc:
        p.exit(2,"Setup refused: "+str(exc)+"\n")
    print(json.dumps(info,indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
