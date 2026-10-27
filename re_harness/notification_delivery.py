"""At-most-once Telegram notification delivery across workers and restarts.

Claims are durable and atomically committed BEFORE the remote API is called.
In the ambiguous network-failure case, prefer a missed notification over spam.
Global per-bot storage also prevents duplicate notifications across worktrees.
"""
from __future__ import annotations
import contextlib
import hashlib
import os
import sqlite3
import time
from pathlib import Path

def database_path(base=None):
    return Path(base) if base is not None else Path.home()/".local"/"state"/"re-dragon"/"notification-guard.sqlite3"

def bot_fingerprint(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:20]

def connection(base=None):
    path=database_path(base)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    db=sqlite3.connect(path,timeout=15)
    db.execute("PRAGMA busy_timeout=15000")
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("""CREATE TABLE IF NOT EXISTS delivery(
      bot TEXT NOT NULL, owner INTEGER NOT NULL, event_key TEXT NOT NULL,
      status TEXT NOT NULL, claimed_at REAL NOT NULL, sent_at REAL,
      PRIMARY KEY(bot, owner, event_key)
    )""")
    return db

def claim(token, owner, event_key, *, base=None):
    """Atomic durable claim; on storage failure caller must NOT send."""
    if not isinstance(event_key,str) or not 0<len(event_key)<=240:
        raise ValueError("Invalid notification event key")
    fingerprint=bot_fingerprint(token)
    with contextlib.closing(connection(base)) as db, db:
        db.execute("BEGIN IMMEDIATE")
        cursor=db.execute(
          "INSERT OR IGNORE INTO delivery(bot,owner,event_key,status,claimed_at) "
          "VALUES(?, ?, ?, 'CLAIMED', ?)",
          (fingerprint,int(owner),event_key,time.time()))
        return cursor.rowcount==1

def delivered(token, owner, event_key, *, base=None):
    with contextlib.closing(connection(base)) as db, db:
        db.execute(
          "UPDATE delivery SET status='SENT', sent_at=? "
          "WHERE bot=? AND owner=? AND event_key=? AND status='CLAIMED'",
          (time.time(),bot_fingerprint(token),int(owner),event_key))

def status(token,owner,event_key,*,base=None):
    with contextlib.closing(connection(base)) as db, db:
        row=db.execute(
          "SELECT status FROM delivery WHERE bot=? AND owner=? AND event_key=?",
          (bot_fingerprint(token),int(owner),event_key)).fetchone()
        return row[0] if row else None
