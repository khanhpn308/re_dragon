"""One-time, expiring Telegram confirmations for project lifecycle mutations."""
from __future__ import annotations
import json
import secrets
import sqlite3
import time
from . import telegram_inbox

KINDS={"NEW_GOAL","SWITCH_PROJECT"}
DECISIONS={"APPROVE","REJECT"}

def ensure(db):
    db.execute("""CREATE TABLE IF NOT EXISTS control_requests(
      id TEXT PRIMARY KEY, update_id INTEGER NOT NULL UNIQUE,
      owner_id INTEGER NOT NULL, kind TEXT NOT NULL, payload TEXT NOT NULL,
      nonce TEXT NOT NULL, status TEXT NOT NULL,
      created_at REAL NOT NULL, expires_at REAL NOT NULL,
      decided_at REAL, result TEXT
    )""")

def propose(workspace,update_id,owner_id,kind,payload,ttl=600):
    if kind not in KINDS:
        raise ValueError("Invalid control kind")
    if not isinstance(payload,dict) or len(json.dumps(payload))>1600:
        raise ValueError("Control request too long")
    request_id=secrets.token_hex(5)
    nonce=secrets.token_hex(6)
    now=time.time()
    with telegram_inbox.connection(workspace) as db:
        ensure(db)
        db.execute("BEGIN IMMEDIATE")
        old=db.execute("SELECT * FROM control_requests WHERE update_id=?",
                       (int(update_id),)).fetchone()
        if old:
            return dict(old),False
        db.execute(
            "INSERT INTO control_requests(id,update_id,owner_id,kind,payload,"
            "nonce,status,created_at,expires_at) VALUES(?,?,?,?,?,?,'PENDING',?,?)",
            (request_id,int(update_id),int(owner_id),kind,
             json.dumps(payload,ensure_ascii=False),nonce,now,now+int(ttl)))
        return dict(db.execute(
            "SELECT * FROM control_requests WHERE id=?",(request_id,)).fetchone()),True

def list_pending(workspace,owner_id):
    with telegram_inbox.connection(workspace) as db:
        ensure(db)
        return [dict(x) for x in db.execute(
          "SELECT * FROM control_requests WHERE owner_id=? AND status='PENDING'"
          " AND expires_at>=? ORDER BY created_at DESC LIMIT 10",
          (int(owner_id),time.time())).fetchall()]

def claim(workspace,request_id,nonce,owner_id,decision):
    if decision not in DECISIONS:
        raise ValueError("Unknown control decision")
    with telegram_inbox.connection(workspace) as db:
        ensure(db)
        db.execute("BEGIN IMMEDIATE")
        row=db.execute(
            "SELECT * FROM control_requests WHERE id=?",(request_id,)).fetchone()
        if (not row or row["owner_id"]!=int(owner_id) or
                not secrets.compare_digest(str(row["nonce"]),str(nonce))):
            raise ValueError("Invalid confirmation identity or nonce")
        if row["status"]!="PENDING":
            raise ValueError("Already decided; callback replay refused")
        if row["expires_at"]<time.time():
            db.execute("UPDATE control_requests SET status='EXPIRED' WHERE id=?",
                       (request_id,))
            raise ValueError("Confirmation expired")
        db.execute(
          "UPDATE control_requests SET status=?, decided_at=? WHERE id=?",
          ("EXECUTING" if decision=="APPROVE" else "REJECTED",time.time(),request_id))
        return {**dict(row),"payload":json.loads(row["payload"]),"decision":decision}

def complete(workspace,request_id,status,result):
    if status not in {"DONE","FAILED","FAILED_START"}:
        raise ValueError("Invalid control result status")
    with telegram_inbox.connection(workspace) as db:
        ensure(db)
        db.execute("BEGIN IMMEDIATE")
        db.execute("UPDATE control_requests SET status=?,result=? "
                   "WHERE id=? AND status='EXECUTING'",
                   (status,str(result)[:600],request_id))
