"""Durable, strictly scoped Telegram task inbox and human approvals (no shell execution)."""
from __future__ import annotations
import secrets
import sqlite3
import time
from pathlib import Path

MAX_PENDING = 50
MAX_MESSAGE = 900
DEFAULT_PROPOSAL_EXPIRY_SECONDS = 3600
VALID_DECISIONS = {"APPROVE", "REJECT", "REWORK"}


def connection(workspace):
    path = Path(workspace).resolve() / ".re_harness" / "telegram-inbox.sqlite3"
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(path, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.executescript("""
      CREATE TABLE IF NOT EXISTS requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_update INTEGER NOT NULL UNIQUE,
        sender_id INTEGER NOT NULL, chat_id INTEGER NOT NULL,
        project_id TEXT NOT NULL, body TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'QUEUED',
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        forwarded_at TEXT
      );

      CREATE TABLE IF NOT EXISTS proposals (
        id TEXT PRIMARY KEY,
        project_id TEXT NOT NULL,
        action TEXT NOT NULL,
        description TEXT NOT NULL,
        nonce TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'PENDING',
        created_at REAL NOT NULL,
        expires_at REAL NOT NULL,
        actor_id INTEGER,
        actor_username TEXT,
        decision TEXT,
        decision_note TEXT,
        decided_at REAL
      );

      CREATE TABLE IF NOT EXISTS approval_audit_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        proposal_id TEXT NOT NULL,
        project_id TEXT NOT NULL,
        action TEXT NOT NULL,
        actor_id INTEGER NOT NULL,
        decision TEXT NOT NULL,
        note TEXT,
        timestamp REAL NOT NULL,
        nonce TEXT NOT NULL
      );

      CREATE TABLE IF NOT EXISTS notification_cursor (
        name TEXT PRIMARY KEY,
        signature TEXT NOT NULL,
        updated_at REAL NOT NULL DEFAULT 0
      );
    """)
    return db


def enqueue(workspace, project_id, update_id, sender_id, chat_id, body):
    if not isinstance(body, str) or not body.strip() or len(body.strip()) > MAX_MESSAGE:
        raise ValueError("Task must contain 1-900 characters")
    if not project_id or len(project_id) > 80:
        raise ValueError("Invalid pinned project")
    with connection(workspace) as db:
        old = db.execute(
            "SELECT id FROM requests WHERE telegram_update=?",
            (int(update_id),)
        ).fetchone()
        if old:
            return int(old["id"]), False
        db.execute("BEGIN IMMEDIATE")
        outstanding = db.execute(
            "SELECT count(*) FROM requests WHERE project_id=? AND status='QUEUED'",
            (project_id,)
        ).fetchone()[0]
        if outstanding >= MAX_PENDING:
            raise ValueError("Task inbox full; wait for next agent turn")
        cursor = db.execute(
            "INSERT INTO requests(telegram_update,sender_id,chat_id,project_id,body)"
            " VALUES(?,?,?,?,?)",
            (int(update_id), int(sender_id), int(chat_id), project_id, body.strip())
        )
        return cursor.lastrowid, True


def queued(workspace, project_id, limit=5):
    with connection(workspace) as db:
        rows = db.execute(
            "SELECT id,body FROM requests WHERE status='QUEUED' AND project_id=? "
            "ORDER BY id LIMIT ?",
            (project_id, int(limit))
        ).fetchall()
        return [dict(r) for r in rows]


def forwarded(workspace, project_id, ids):
    if not ids:
        return
    with connection(workspace) as db:
        db.executemany(
            "UPDATE requests SET status='FORWARDED',forwarded_at=CURRENT_TIMESTAMP "
            "WHERE id=? AND project_id=? AND status='QUEUED'",
            [(int(i), project_id) for i in ids]
        )


def summary(workspace, project_id):
    with connection(workspace) as db:
        rows = db.execute(
            "SELECT status,count(*) n FROM requests WHERE project_id=? GROUP BY status",
            (project_id,)
        ).fetchall()
    return {r["status"]: r["n"] for r in rows}


# ---------------------------------------------------------------------------
# Human Approval Proposals & Transactional Decision State
# ---------------------------------------------------------------------------

def create_proposal(workspace, project_id, action, description,
                    timeout_seconds=DEFAULT_PROPOSAL_EXPIRY_SECONDS, nonce=None):
    if not isinstance(project_id, str) or not project_id.strip():
        raise ValueError("Invalid project_id")
    if not isinstance(action, str) or not action.strip():
        raise ValueError("Invalid approval action")
    if not isinstance(description, str) or not description.strip():
        raise ValueError("Proposal description must be non-empty")
    
    proposal_id = f"prop_{secrets.token_hex(6)}"
    prop_nonce = nonce or secrets.token_hex(6)
    now = time.time()
    expires_at = now + max(10, float(timeout_seconds))

    with connection(workspace) as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute(
            "INSERT INTO proposals (id, project_id, action, description, nonce, "
            "status, created_at, expires_at) VALUES (?, ?, ?, ?, ?, 'PENDING', ?, ?)",
            (proposal_id, project_id.strip(), action.strip(), description.strip(),
             prop_nonce, now, expires_at)
        )
        row = db.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
        return dict(row)


def expire_stale_proposals(workspace):
    now = time.time()
    with connection(workspace) as db:
        db.execute(
            "UPDATE proposals SET status='EXPIRED' WHERE status='PENDING' AND expires_at < ?",
            (now,)
        )


def list_proposals(workspace, project_id=None, status="PENDING"):
    expire_stale_proposals(workspace)
    query = "SELECT * FROM proposals WHERE 1=1"
    params = []
    if project_id:
        query += " AND project_id=?"
        params.append(project_id)
    if status:
        query += " AND status=?"
        params.append(status)
    query += " ORDER BY created_at DESC"
    with connection(workspace) as db:
        rows = db.execute(query, params).fetchall()
        return [dict(r) for r in rows]


def get_proposal(workspace, proposal_id):
    expire_stale_proposals(workspace)
    with connection(workspace) as db:
        row = db.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
        return dict(row) if row else None


def decide_proposal(workspace, proposal_id, decision, actor_id,
                    actor_username=None, nonce=None, note=None):
    decision_clean = str(decision or "").strip().upper()
    if decision_clean not in VALID_DECISIONS:
        raise ValueError(f"Decision must be one of {sorted(VALID_DECISIONS)}")
    if not int(actor_id or 0) > 0:
        raise ValueError("Valid numeric actor_id required")

    with connection(workspace) as db:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
        if not row:
            raise ValueError(f"Proposal {proposal_id} not found")
        
        # Check current status
        if row["status"] != "PENDING":
            return {
                "success": False,
                "reason": f"Proposal already decided ({row['status']})",
                "proposal": dict(row),
            }
        
        now = time.time()
        # Check expiry
        if now > row["expires_at"]:
            db.execute("UPDATE proposals SET status='EXPIRED' WHERE id=?", (proposal_id,))
            updated = db.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
            return {
                "success": False,
                "reason": "Proposal has expired",
                "proposal": dict(updated),
            }
        
        # Check nonce if provided
        if nonce is not None and str(nonce).strip() != row["nonce"]:
            return {
                "success": False,
                "reason": "Invalid proposal nonce",
                "proposal": dict(row),
            }
        
        # Commit decision
        db.execute(
            "UPDATE proposals SET status=?, decision=?, actor_id=?, actor_username=?, "
            "decision_note=?, decided_at=? WHERE id=? AND status='PENDING'",
            (decision_clean, decision_clean, int(actor_id),
             str(actor_username or ""), str(note or ""), now, proposal_id)
        )
        db.execute(
            "INSERT INTO approval_audit_log (proposal_id, project_id, action, "
            "actor_id, decision, note, timestamp, nonce) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (proposal_id, row["project_id"], row["action"], int(actor_id),
             decision_clean, str(note or ""), now, row["nonce"])
        )
        updated = db.execute("SELECT * FROM proposals WHERE id=?", (proposal_id,)).fetchone()
        return {
            "success": True,
            "reason": f"Proposal {decision_clean} recorded",
            "decision": decision_clean,
            "proposal": dict(updated),
        }


def audit_log(workspace, proposal_id=None, limit=50):
    query = "SELECT * FROM approval_audit_log WHERE 1=1"
    params = []
    if proposal_id:
        query += " AND proposal_id=?"
        params.append(proposal_id)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(int(limit))
    with connection(workspace) as db:
        rows = db.execute(query, params).fetchall()
        return [dict(r) for r in rows]
