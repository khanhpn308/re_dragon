"""Durable, strictly scoped Telegram task inbox (no shell execution)."""
from __future__ import annotations
import sqlite3
from pathlib import Path

MAX_PENDING=50
MAX_MESSAGE=900


def connection(workspace):
    path=Path(workspace).resolve()/".re_harness"/"telegram-inbox.sqlite3"
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    db=sqlite3.connect(path,timeout=15)
    db.row_factory=sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""CREATE TABLE IF NOT EXISTS requests(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      telegram_update INTEGER NOT NULL UNIQUE,
      sender_id INTEGER NOT NULL, chat_id INTEGER NOT NULL,
      project_id TEXT NOT NULL, body TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'QUEUED',
      created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
      forwarded_at TEXT
    )""")
    return db


def enqueue(workspace,project_id,update_id,sender_id,chat_id,body):
    if not isinstance(body,str) or not body.strip() or len(body.strip())>MAX_MESSAGE:
        raise ValueError("Task must contain 1-900 characters")
    if not project_id or len(project_id)>80:
        raise ValueError("Invalid pinned project")
    with connection(workspace) as db:
        old=db.execute("SELECT id FROM requests WHERE telegram_update=?",
                       (int(update_id),)).fetchone()
        if old:
            return int(old["id"]),False
        db.execute("BEGIN IMMEDIATE")
        outstanding=db.execute(
            "SELECT count(*) FROM requests WHERE project_id=? AND status='QUEUED'",
            (project_id,)).fetchone()[0]
        if outstanding>=MAX_PENDING:
            raise ValueError("Task inbox full; wait for next agent turn")
        cursor=db.execute(
          "INSERT INTO requests(telegram_update,sender_id,chat_id,project_id,body)"
          " VALUES(?,?,?,?,?)",
          (int(update_id),int(sender_id),int(chat_id),project_id,body.strip()))
        return cursor.lastrowid,True


def queued(workspace,project_id,limit=5):
    with connection(workspace) as db:
        rows=db.execute(
            "SELECT id,body FROM requests WHERE status='QUEUED' AND project_id=? "
            "ORDER BY id LIMIT ?",(project_id,int(limit))).fetchall()
        return [dict(r) for r in rows]


def forwarded(workspace,project_id,ids):
    if not ids:
        return
    with connection(workspace) as db:
        db.executemany(
            "UPDATE requests SET status='FORWARDED',forwarded_at=CURRENT_TIMESTAMP "
            "WHERE id=? AND project_id=? AND status='QUEUED'",
            [(int(i),project_id) for i in ids])


def summary(workspace,project_id):
    with connection(workspace) as db:
        rows=db.execute(
            "SELECT status,count(*) n FROM requests WHERE project_id=? GROUP BY status",
            (project_id,)).fetchall()
    return {r["status"]:r["n"] for r in rows}
