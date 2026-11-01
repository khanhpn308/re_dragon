"""Read-only Telegram audit for pinned project acceptance and reviewer metadata.

This report does not validate actual evidence contents or attest reviewer identity.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import quota_guard


def audit_text(workspace):
    root = Path(workspace).resolve()
    try:
        watcher = json.loads(
            (root / ".re_harness" / "quota-watchdog.json").read_text(encoding="utf-8"))
        pid = watcher.get("project_id")
        if not isinstance(pid, str) or not pid:
            return "RE Dragon — /audit\nProject: UNKNOWN (Watchdog chưa pin project)"
        info = quota_guard.inspect(root / ".re_harness_mvp", pid)
    except (OSError, ValueError, AttributeError) as exc:
        return "RE Dragon — /audit\nProject: UNKNOWN — không đọc được checkpoint hiện tại; không thay đổi dữ liệu."

    try:
        import sqlite3
        from urllib.parse import quote
        db_path = (root / ".re_harness_mvp" / "state.sqlite3").resolve()
        uri = "file:" + quote(str(db_path), safe="/") + "?mode=ro"
        with sqlite3.connect(uri, uri=True, timeout=5) as db:
            rows = db.execute(
                "SELECT task_key, status, producer, producer_session, "
                "reviewer, reviewer_session, evidence_json, artifacts_json "
                "FROM auto_tasks WHERE project_id=? ORDER BY task_key",
                (pid,),
            ).fetchall()
            events = db.execute(
                "SELECT event FROM auto_events WHERE project_id=? "
                "AND event IN ('PROJECT_ACCEPT', 'PROJECT_REOPEN') "
                "ORDER BY id DESC LIMIT 1",
                (pid,),
            ).fetchall()
    except (OSError, sqlite3.Error):
        return "RE Dragon — /audit\nCheckpoint task/review chưa đọc được."

    counts = info["task_status_counts"]
    complete = quota_guard.actual_completion(info)
    verified = counts.get("VERIFIED", 0)
    total = sum(counts.values())
    review_metadata = 0
    refs = 0
    for row in rows:
        key, status, producer, producer_session, reviewer, reviewer_session, ev, arts = row
        if status == "VERIFIED":
            if (producer and reviewer and producer != reviewer
                    and producer_session and reviewer_session
                    and producer_session != reviewer_session):
                review_metadata += 1
            try:
                if any(json.loads(raw or "[]") for raw in (ev, arts)):
                    refs += 1
            except (TypeError, ValueError):
                pass

    final_event = events[0][0] if events else "NONE"
    lines = [
        "RE Dragon — /audit (read-only)",
        "Project: " + pid,
        "Harness project: " + info["project_status"],
        "Watchdog: " + str(watcher.get("status", "UNKNOWN")),
        f"Tasks VERIFIED: {verified}/{total}",
        f"Reviewer metadata distinct actor/session: {review_metadata}/{verified}",
        f"Task evidence references stored: {refs}/{verified}",
        "Last final review event: " + final_event,
        "Final ACCEPTED: " + ("YES" if complete else "NO"),
    ]
    if complete:
        lines.append("Checkpoint accepted; evidence content must still be externally inspected.")
    elif total > 0 and verified == total:
        lines.append("Final review pending: ALL TASKS VERIFIED does not mean ACCEPTED.")
        lines.append("Check /report, /taskdetail <key>, and independently inspect original evidence.")
    else:
        lines.append("Not ready for final review: outstanding tasks remain.")
        for key, status, *_ in rows:
            if status != "VERIFIED":
                lines.append(f"  {key[:75]}: {status[:30]}")
                if len(lines) >= 20:
                    break
    lines.append("Reviewer identity and referenced evidence are NOT independently attested by this report.")
    return "\n".join(lines)[:3800]
