"""Incident Journal and Recovery Audit Trail for RE Dragon.

Provides durable, redacted, anti-spam incident tracking in SQLite.
Distinguishes agent technical errors from Telegram delivery failures,
tracks recovery attempts, and protects against notification flooding.
"""
from __future__ import annotations

import contextlib
import json
import re
import secrets
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

INCIDENT_DB = "incidents.sqlite3"
DEDUPLICATION_WINDOW_SECONDS = 300  # 5 minutes anti-spam window

CATEGORIES = {
    "MISSING_MARKER",
    "AGENT_CRASH",
    "TIMEOUT",
    "SQLITE_LOCK",
    "STALE_LEASE",
    "QUOTA_EXHAUSTED",
    "RESOURCE_EXHAUSTION",
    "NETWORK_TRANSIENT",
    "AUTH_OR_PERMISSION",
    "TELEGRAM_DELIVERY",
    "CORRUPT_STATE",
    "UNEXPECTED_ERROR",
}

SEVERITIES = {"INFO", "WARNING", "ERROR", "CRITICAL"}
STATUSES = {"OPEN", "INVESTIGATING", "RESOLVED", "FAILED_UNRECOVERABLE"}

RE_BOT_TOKEN = re.compile(r"\b\d{6,}:[A-Za-z0-9_-]{25,}\b")
RE_API_KEY = re.compile(r"\b(AIza[0-9A-Za-z_-]{35}|sk-[0-9A-Za-z]{20,})\b")
RE_BEARER = re.compile(r"\bBearer\s+[A-Za-z0-9._-]+\b", re.I)
RE_SECRET_PARAM = re.compile(r"([?&]|\b)(password|token|secret|key)=([^&\s]+)", re.I)


def redact_sensitive(text: str) -> str:
    """Strip tokens, API keys, and sensitive parameters from incident text."""
    if not text:
        return ""
    s = str(text)
    s = RE_BOT_TOKEN.sub("[REDACTED_BOT_TOKEN]", s)
    s = RE_API_KEY.sub("[REDACTED_API_KEY]", s)
    s = RE_BEARER.sub("Bearer [REDACTED_TOKEN]", s)
    s = RE_SECRET_PARAM.sub(r"\1\2=[REDACTED]", s)
    return s


def connection(workspace: Path | str) -> sqlite3.Connection:
    path = Path(workspace).resolve() / ".re_harness" / INCIDENT_DB
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(path, timeout=20)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=5000")
    db.executescript("""
      CREATE TABLE IF NOT EXISTS incidents (
        id TEXT PRIMARY KEY,
        project_id TEXT,
        task_id TEXT,
        category TEXT NOT NULL,
        severity TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'OPEN',
        error_message TEXT NOT NULL,
        details TEXT,
        recovery_attempts INTEGER NOT NULL DEFAULT 0,
        max_recovery_attempts INTEGER NOT NULL DEFAULT 3,
        next_retry_at REAL,
        occurrence_count INTEGER NOT NULL DEFAULT 1,
        created_at REAL NOT NULL,
        updated_at REAL NOT NULL,
        resolved_at REAL,
        resolution_notes TEXT
      );

      CREATE INDEX IF NOT EXISTS idx_incidents_status ON incidents(status);
      CREATE INDEX IF NOT EXISTS idx_incidents_project ON incidents(project_id);
      CREATE INDEX IF NOT EXISTS idx_incidents_category ON incidents(category);

      CREATE TABLE IF NOT EXISTS incident_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        incident_id TEXT NOT NULL,
        event_type TEXT NOT NULL,
        message TEXT NOT NULL,
        timestamp REAL NOT NULL,
        FOREIGN KEY (incident_id) REFERENCES incidents(id) ON DELETE CASCADE
      );

      CREATE INDEX IF NOT EXISTS idx_incident_events_id ON incident_events(incident_id);
    """)
    return db


def create_or_update_incident(
    workspace: Path | str,
    project_id: Optional[str],
    category: str,
    error_message: str,
    severity: str = "WARNING",
    task_id: Optional[str] = None,
    details: Optional[Dict[str, Any]] = None,
    max_retries: int = 3,
    now: Optional[float] = None,
) -> Tuple[Dict[str, Any], bool]:
    """Create a new incident or deduplicate against a recently active incident.

    Returns:
        (incident_dict, is_new: bool)
    """
    if category not in CATEGORIES:
        category = "UNEXPECTED_ERROR"
    if severity not in SEVERITIES:
        severity = "WARNING"
    current_ts = time.time() if now is None else now
    clean_msg = redact_sensitive(error_message)[:1500]
    clean_details = redact_sensitive(json.dumps(details or {}, ensure_ascii=False))

    with contextlib.closing(connection(workspace)) as db, db:
        # Check for open duplicate incident within deduplication window
        window_start = current_ts - DEDUPLICATION_WINDOW_SECONDS
        row = db.execute(
            """SELECT * FROM incidents 
               WHERE category=? AND (project_id=? OR (project_id IS NULL AND ? IS NULL))
               AND status IN ('OPEN', 'INVESTIGATING') AND updated_at >= ?
               ORDER BY updated_at DESC LIMIT 1""",
            (category, project_id, project_id, window_start),
        ).fetchone()

        if row:
            inc_id = row["id"]
            new_count = row["occurrence_count"] + 1
            db.execute(
                """UPDATE incidents 
                   SET occurrence_count=?, updated_at=?, error_message=?, details=?
                   WHERE id=?""",
                (new_count, current_ts, clean_msg, clean_details, inc_id),
            )
            db.execute(
                """INSERT INTO incident_events(incident_id, event_type, message, timestamp)
                   VALUES(?, 'OCCURRENCE_BUMP', ?, ?)""",
                (inc_id, f"Deduplicated occurrence #{new_count}: {clean_msg[:200]}", current_ts),
            )
            updated_row = db.execute("SELECT * FROM incidents WHERE id=?", (inc_id,)).fetchone()
            return dict(updated_row), False

        # Create new incident
        inc_id = f"INC-{int(current_ts):x}-{secrets.token_hex(3)}"
        db.execute(
            """INSERT INTO incidents(
                 id, project_id, task_id, category, severity, status,
                 error_message, details, recovery_attempts, max_recovery_attempts,
                 occurrence_count, created_at, updated_at
               ) VALUES (?, ?, ?, ?, ?, 'OPEN', ?, ?, 0, ?, 1, ?, ?)""",
            (
                inc_id,
                project_id,
                task_id,
                category,
                severity,
                clean_msg,
                clean_details,
                max_retries,
                current_ts,
                current_ts,
            ),
        )
        db.execute(
            """INSERT INTO incident_events(incident_id, event_type, message, timestamp)
               VALUES(?, 'CREATED', ?, ?)""",
            (inc_id, f"Incident opened: {clean_msg[:200]}", current_ts),
        )
        created_row = db.execute("SELECT * FROM incidents WHERE id=?", (inc_id,)).fetchone()
        return dict(created_row), True


def list_incidents(
    workspace: Path | str,
    project_id: Optional[str] = None,
    status: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 20,
) -> List[Dict[str, Any]]:
    """List recent incidents with optional project_id, status, and category filters."""
    query = "SELECT * FROM incidents WHERE 1=1"
    params: List[Any] = []
    if project_id:
        query += " AND project_id=?"
        params.append(project_id)
    if status:
        query += " AND status=?"
        params.append(status)
    if category:
        query += " AND category=?"
        params.append(category)
    query += " ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)

    with contextlib.closing(connection(workspace)) as db:
        rows = db.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def get_incident(workspace: Path | str, incident_id: str) -> Optional[Dict[str, Any]]:
    """Get incident details and recent events."""
    with contextlib.closing(connection(workspace)) as db:
        row = db.execute("SELECT * FROM incidents WHERE id=?", (incident_id,)).fetchone()
        if not row:
            return None
        res = dict(row)
        events = db.execute(
            "SELECT event_type, message, timestamp FROM incident_events WHERE incident_id=? ORDER BY timestamp ASC",
            (incident_id,),
        ).fetchall()
        res["events"] = [dict(e) for e in events]
        return res


def record_recovery_attempt(
    workspace: Path | str,
    incident_id: str,
    success: bool,
    note: str = "",
    next_retry_at: Optional[float] = None,
    now: Optional[float] = None,
) -> Dict[str, Any]:
    """Record recovery attempt result against an incident."""
    current_ts = time.time() if now is None else now
    clean_note = redact_sensitive(note)[:500]

    with contextlib.closing(connection(workspace)) as db, db:
        row = db.execute("SELECT * FROM incidents WHERE id=?", (incident_id,)).fetchone()
        if not row:
            raise ValueError(f"Incident {incident_id} not found")

        attempts = row["recovery_attempts"] + 1
        if success:
            db.execute(
                """UPDATE incidents 
                   SET status='RESOLVED', recovery_attempts=?, resolved_at=?,
                       resolution_notes=?, updated_at=?
                   WHERE id=?""",
                (attempts, current_ts, clean_note or "Auto-recovered successfully", current_ts, incident_id),
            )
            event_type = "RESOLVED"
            msg = f"Recovery attempt #{attempts} succeeded: {clean_note}"
        else:
            new_status = (
                "FAILED_UNRECOVERABLE"
                if attempts >= row["max_recovery_attempts"]
                else "INVESTIGATING"
            )
            db.execute(
                """UPDATE incidents 
                   SET status=?, recovery_attempts=?, next_retry_at=?, updated_at=?
                   WHERE id=?""",
                (new_status, attempts, next_retry_at, current_ts, incident_id),
            )
            event_type = "RETRY_FAILED" if attempts < row["max_recovery_attempts"] else "BUDGET_EXHAUSTED"
            msg = f"Recovery attempt #{attempts} failed ({event_type}): {clean_note}"

        db.execute(
            """INSERT INTO incident_events(incident_id, event_type, message, timestamp)
               VALUES(?, ?, ?, ?)""",
            (incident_id, event_type, msg, current_ts),
        )
        return dict(db.execute("SELECT * FROM incidents WHERE id=?", (incident_id,)).fetchone())


def resolve_incident(
    workspace: Path | str,
    incident_id: str,
    notes: str = "",
    now: Optional[float] = None,
) -> bool:
    """Manually resolve an incident."""
    current_ts = time.time() if now is None else now
    clean_notes = redact_sensitive(notes)[:500]
    with contextlib.closing(connection(workspace)) as db, db:
        res = db.execute(
            """UPDATE incidents 
               SET status='RESOLVED', resolved_at=?, resolution_notes=?, updated_at=?
               WHERE id=? AND status != 'RESOLVED'""",
            (current_ts, clean_notes or "Manually marked resolved", current_ts, incident_id),
        )
        if res.rowcount > 0:
            db.execute(
                """INSERT INTO incident_events(incident_id, event_type, message, timestamp)
                   VALUES(?, 'MANUAL_RESOLVED', ?, ?)""",
                (incident_id, f"Manually resolved: {clean_notes}", current_ts),
            )
            return True
        return False
