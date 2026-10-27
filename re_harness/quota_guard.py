"""Read-only, fail-closed binding between a quota watcher and its RE Dragon goal.

The watchdog must not believe an LLM's 'COMPLETE' marker unless the durable
project acceptance state has actually reached ACCEPTED. Read-only SQL avoids
running migrations or changing user progress from an unattended supervisor.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from urllib.parse import quote

TERMINAL = {"ACCEPTED", "STOPPED", "BLOCKED", "READY_FOR_FINAL_REVIEW"}
ACTIVE = {"PLANNING", "ACTIVE"}


class ProjectGateError(ValueError):
    pass


def inspect(db_dir, project_id=None):
    database = (Path(db_dir).expanduser().resolve() / "state.sqlite3")
    if not database.is_file():
        raise ProjectGateError("Harness SQLite checkpoint missing; start project interactively")
    uri = "file:" + quote(str(database), safe="/") + "?mode=ro"
    try:
        with sqlite3.connect(uri, uri=True, timeout=5) as db:
            db.row_factory=sqlite3.Row
            rows = db.execute(
                "SELECT id,goal,acceptance,status FROM auto_projects ORDER BY updated_at DESC"
            ).fetchall()
            if project_id:
                found = [x for x in rows if x["id"] == project_id]
                if not found:
                    raise ProjectGateError("Pinned project_id not found in Harness SQLite")
                chosen = found[0]
            else:
                # Do not guess which of multiple unfinished investigations to run.
                eligible = [x for x in rows if x["status"] in ACTIVE]
                if len(eligible) != 1:
                    raise ProjectGateError(
                        "Exactly one active goal required for automatic project selection; "
                        "use --project-id to select explicitly"
                    )
                chosen = eligible[0]
            counts = db.execute(
                "SELECT status,COUNT(*) AS n FROM auto_tasks "
                "WHERE project_id=? GROUP BY status",(chosen["id"],)
            ).fetchall()
    except (sqlite3.Error, OSError) as exc:
        raise ProjectGateError("Cannot inspect Harness project checkpoint") from exc
    summary = {x["status"]:x["n"] for x in counts}
    if chosen["status"] not in ACTIVE | TERMINAL:
        raise ProjectGateError("Unrecognized Harness project status")
    return {"project_id":chosen["id"],"project_status":chosen["status"],
            "goal":chosen["goal"],"acceptance":chosen["acceptance"],
            "task_status_counts":summary}


def actual_completion(info):
    """Acceptance must be persisted and not contradict task review states."""
    counts=info["task_status_counts"]
    return info["project_status"] == "ACCEPTED" and (
        sum(counts.values()) > 0 and set(counts) == {"VERIFIED"}
    )
