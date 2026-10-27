"""One-time or project-scoped production onboarding for the quota watchdog.

This module seeds or selects an approved goal DAG in SQLite and binds it
to the watchdog state. It never calls a model or starts an agent itself.
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


def _select_project(db, goal=None, project_id=None):
    if project_id:
        row = db.execute(
            "SELECT id, goal, status FROM auto_projects WHERE id=?",
            (project_id.strip(),)
        ).fetchone()
        if not row:
            raise SetupError(f"Target project_id '{project_id}' not found in SQLite")
        if row["status"] not in VALID_STATES:
            raise SetupError(f"Project '{project_id}' is {row['status']}; "
                             "will not restart or duplicate a closed project")
        return row["id"], False

    if goal:
        cleaned_goal = goal.strip()
        matches = db.execute(
            "SELECT id, status FROM auto_projects WHERE lower(trim(goal)) = lower(trim(?)) "
            "ORDER BY created_at DESC",
            (cleaned_goal,)
        ).fetchall()
        if matches:
            row = matches[0]
            if row["status"] not in VALID_STATES:
                raise SetupError(f"Project goal is {row['status']}; "
                                 "will not restart or duplicate a closed project")
            return row["id"], False
        created = autonomy.start(db, cleaned_goal, cleaned_goal + " (verified binary evidence)")
        return created["project_id"], True

    # Default discovery: check for explicit ReturnSaiyan production goals
    matches = db.execute(
        "SELECT id,status FROM auto_projects WHERE goal LIKE ? "
        "ORDER BY created_at DESC",
        (TITLE + "%",),
    ).fetchall()
    if len(matches) > 1:
        raise SetupError(
            "Multiple ReturnSaiyan production goals already exist; "
            "choose/resolve the correct project before enabling unattended runs"
        )
    if matches:
        row = matches[0]
        if row["status"] not in VALID_STATES:
            raise SetupError("Production goal is " + row["status"] +
                             "; will not restart or duplicate a closed project")
        return row["id"], False

    # Never replace unrelated active or pilot projects; they remain intact.
    created = autonomy.start(db, GOAL, ACCEPTANCE)
    return created["project_id"], True


def bootstrap(workspace, state_dir=None, goal=None, acceptance=None, project_id=None):
    root = Path(workspace).expanduser().resolve()
    watch_dir = root / ".re_harness"
    watch_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    state_path = watch_dir / "quota-watchdog.json"
    db_dir = Path(state_dir).expanduser().resolve() if state_dir else root / ".re_harness_mvp"
    lock_path = watch_dir / "quota-watchdog.lock"
    with lock_path.open("a+") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise SetupError("Watchdog currently running; inspect status first") from exc
        state = quota_watchdog.load(state_path)

        # Only clear literal tutorial placeholders, not arbitrary broken bindings.
        if state.get("project_id") == "PROJECT_ID" and state.get("conversation_id") == "CONVERSATION_ID":
            state = quota_watchdog.load(watch_dir / "_nonexistent_initial_state.json")
        elif state.get("project_id") in {"PROJECT_ID", "CONVERSATION_ID"} or state.get("conversation_id") in {"PROJECT_ID", "CONVERSATION_ID"}:
            raise SetupError("Partial example ID binding found; reset it manually")

        if state.get("status") in quota_watchdog.STOP:
            raise SetupError(
                "Watchdog stopped at " + state["status"] +
                ". Resolve the blocker explicitly with ./dragon resume; "
                "do not auto-override a real failure."
            )
        with core.database(db_dir) as db:
            autonomy.migrate(db)
            # A durable project_id binding always takes precedence over legacy
            # title discovery. This is critical for resuming a V1 project while
            # an older ReturnSaiyan goal is already ACCEPTED. Do not silently
            # switch to another project after a failed lookup.
            pinned = state.get("project_id") if not (goal or project_id) else None
            if pinned:
                row = db.execute(
                    "SELECT id FROM auto_projects WHERE id=?", (pinned,)
                ).fetchone()
                if row is None:
                    raise SetupError(
                        "Pinned watchdog project_id is absent in Harness SQLite; "
                        "refusing fallback project discovery"
                    )
            selected_pid, created = _select_project(
                db, goal=goal, project_id=project_id or pinned
            )

        if state.get("project_id") and state["project_id"] != selected_pid and not (project_id or goal):
            raise SetupError("Watchdog pinned to another project; cannot silently switch")

        project_conversations = state.get("project_conversations", {})
        if state.get("project_id") and state.get("conversation_id"):
            project_conversations[state["project_id"]] = state["conversation_id"]
        state["project_conversations"] = project_conversations

        if state.get("project_id") != selected_pid:
            state["project_id"] = selected_pid
            target_cid = project_conversations.get(selected_pid)
            state["conversation_id"] = target_cid
            if not target_cid:
                state["bootstrap_new_conversation"] = True
            else:
                state.pop("bootstrap_new_conversation", None)
        else:
            if not state.get("conversation_id"):
                state["bootstrap_new_conversation"] = True
            else:
                state.pop("bootstrap_new_conversation", None)

        quota_watchdog.save(state_path, state)
        return {
            "project_id": selected_pid,
            "project_created": created,
            "conversation": ("pinned" if state.get("conversation_id")
                             else "new dedicated headless session"),
            "status": state["status"]
        }


def main(argv=None):
    p = argparse.ArgumentParser(description="RE Dragon project onboarding and bootstrap")
    p.add_argument("--workspace", default=".")
    p.add_argument("--state-dir", default="")
    p.add_argument("--project-id", default="")
    p.add_argument("--goal", default="")
    p.add_argument("--acceptance", default="")
    args = p.parse_args(argv)
    try:
        info = bootstrap(
            args.workspace,
            state_dir=args.state_dir or None,
            goal=args.goal or None,
            acceptance=args.acceptance or None,
            project_id=args.project_id or None,
        )
    except (SetupError, OSError, ValueError) as exc:
        p.exit(2, "Setup refused: " + str(exc) + "\n")
    print(json.dumps(info, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
