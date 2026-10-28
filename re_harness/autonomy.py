"""v0.5 goal-level Agent orchestration control plane (SQLite; MCP-facing).

The LLM host (Codex/Antigravity) performs reasoning and calls REA MCP,
writes code/tests and invokes these APIs repeatedly. This module cannot
invoke the LLM by itself or continue when the host session has ended.

Run states persist across model sessions; reviews are assigned to an actor
different from the producer, but identity is host-reported (not attested).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from pathlib import Path

from . import core, scheduler

WORK = {"ANALYZE", "IMPLEMENT", "TEST", "AUDIT", "DOCUMENT"}
MAX_TASKS = 250
MAX_PLAN_BATCH = 50
LEASE_SECONDS = 1200
MAX_ATTEMPTS = 3
MAX_TURNS = 80


def ident():
    return uuid.uuid4().hex[:16]


def txt(value, name, limit=3000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{name} must be nonempty text (max {limit} chars)")
    return value.strip()


def json_arr(value, name, maxlen=25):
    if not isinstance(value, list) or len(value) > maxlen or any(
        not isinstance(x, str) or not x.strip() or len(x) > 512 for x in value
    ):
        raise ValueError(f"{name} must be a list of at most {maxlen} nonempty strings")
    return list(dict.fromkeys(value))


def migrate(db):
    db.executescript("""
      CREATE TABLE IF NOT EXISTS auto_projects (
        id TEXT PRIMARY KEY, goal TEXT NOT NULL, acceptance TEXT NOT NULL,
        binary_path TEXT, binary_sha256 TEXT, status TEXT NOT NULL,
        created_at TEXT NOT NULL, updated_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS auto_tasks (
        id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES auto_projects(id),
        task_key TEXT NOT NULL, title TEXT NOT NULL, acceptance TEXT NOT NULL,
        kind TEXT NOT NULL, priority INTEGER NOT NULL, dependencies TEXT NOT NULL,
        status TEXT NOT NULL, tries INTEGER NOT NULL DEFAULT 0,
        producer TEXT, owner TEXT, lease_token TEXT, lease_until REAL,
        result TEXT, evidence_json TEXT, artifacts_json TEXT,
        verification_json TEXT, reviewer TEXT, review_note TEXT,
        parent_issue TEXT, updated_at TEXT NOT NULL,
        UNIQUE(project_id,task_key)
      );
      CREATE TABLE IF NOT EXISTS auto_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        project_id TEXT NOT NULL, task_key TEXT, event TEXT NOT NULL,
        details TEXT NOT NULL, timestamp TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS auto_sessions (
        project_id TEXT NOT NULL, session_id TEXT NOT NULL,
        turns INTEGER NOT NULL DEFAULT 0, last_seen TEXT NOT NULL,
        PRIMARY KEY(project_id,session_id)
      );
    """)
    cols={r["name"] for r in db.execute("PRAGMA table_info(auto_tasks)")}
    for col in ("owner_session","producer_session","reviewer_session"):
        if col not in cols:
            db.execute("ALTER TABLE auto_tasks ADD COLUMN "+col+" TEXT")
    scheduler.migrate(db)
    db.commit()


def event(db, project, key, name, details=None):
    db.execute(
        "INSERT INTO auto_events(project_id,task_key,event,details,timestamp) "
        "VALUES(?,?,?,?,?)",
        (project,key,name,json.dumps(details or {},ensure_ascii=False),core.now())
    )


def project(db, pid):
    row=db.execute("SELECT * FROM auto_projects WHERE id=?",(pid,)).fetchone()
    if not row:
        raise ValueError("Unknown project_id")
    return row


def tasks(db,pid):
    return db.execute("SELECT * FROM auto_tasks WHERE project_id=? "
                      "ORDER BY priority DESC, updated_at ASC,task_key",(pid,)).fetchall()


def start(db,goal,acceptance,binary_path=None):
    migrate(db)
    goal=txt(goal,"goal",12000)
    acceptance=txt(acceptance,"acceptance",8000)
    binary, digest=None,None
    if binary_path is not None:
        binary=Path(txt(binary_path,"binary_path",4096)).expanduser().resolve()
        if not binary.is_file():
            raise ValueError("Local binary does not exist")
        digest=core.sha256(binary)
        binary=str(binary)
    pid=ident()
    with db:
        db.execute("INSERT INTO auto_projects VALUES(?,?,?,?,?,?,?,?)",
                   (pid,goal,acceptance,binary,digest,"PLANNING",
                    core.now(),core.now()))
        event(db,pid,None,"GOAL_ACCEPTED",{"has_binary":bool(binary)})
    return {"project_id":pid,"decision":"PLAN","next_tool":"harness_auto_plan",
            "goal":goal,"acceptance":acceptance,"binary_sha256":digest,
            "instructions":"Agent decomposes goal into bounded dependency tasks. "
                           "Do not ask the user to choose project phases."}


def _validate_batch(raw, previous):
    if not isinstance(raw,list) or not 1<=len(raw)<=MAX_PLAN_BATCH:
        raise ValueError("Plan must have 1-50 tasks")
    all_keys=set(previous)
    entries=[]
    for item in raw:
        if not isinstance(item,dict):
            raise ValueError("Each task must be an object")
        key=txt(item.get("key"),"task key",80)
        if not all(c.isalnum() or c in "-_" for c in key):
            raise ValueError("Task key may only contain letters/numbers/_/-")
        if key in all_keys:
            raise ValueError("Duplicate task key "+key)
        all_keys.add(key)
        kind=item.get("kind","ANALYZE")
        if kind not in WORK:
            raise ValueError("Invalid task kind")
        deps=json_arr(item.get("depends_on",[]),"depends_on")
        prio=item.get("priority",10)
        if type(prio) is not int or not 0<=prio<=100:
            raise ValueError("Priority must be an integer in 0..100")
        spec=scheduler.normalize(kind,item.get("resource_class"),item.get("targets",[]))
        entries.append({"resource_class":spec["profile"],"targets":spec["targets"],
                        "key":key,"title":txt(item.get("title"),"title",250),
             "acceptance":txt(item.get("acceptance"),"acceptance",3000),
             "kind":kind,"depends_on":deps,"priority":prio})
    for item in entries:
        if item["key"] in item["depends_on"]:
            raise ValueError("Self dependency")
        if any(key not in all_keys for key in item["depends_on"]):
            raise ValueError("Unknown dependency for "+item["key"])
    graph={**previous,**{x["key"]:x["depends_on"] for x in entries}}
    visited=set()
    visiting=set()
    def visit(name):
        if name in visiting:
            raise ValueError("Dependency cycle at "+name)
        if name in visited:
            return
        visiting.add(name)
        for dep in graph[name]:
            visit(dep)
        visiting.remove(name)
        visited.add(name)
    for node in graph:
        visit(node)
    return entries


def plan(db,pid,raw):
    migrate(db)
    pr=project(db,pid)
    if pr["status"] in {"STOPPED","READY_FOR_FINAL_REVIEW","ACCEPTED"}:
        raise ValueError("Project is stopped or awaiting final review")
    old={r["task_key"]:json.loads(r["dependencies"]) for r in tasks(db,pid)}
    items=_validate_batch(raw,old)
    if len(old)+len(items)>MAX_TASKS:
        raise ValueError("Task budget exceeded")
    db.execute("BEGIN IMMEDIATE")
    try:
        scheduler.ensure_policy(db,pid)
        for item in items:
            db.execute(
                "INSERT INTO auto_tasks(id,project_id,task_key,title,acceptance,"
                "kind,priority,dependencies,status,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
                (ident(),pid,item["key"],item["title"],item["acceptance"],
                 item["kind"],item["priority"],json.dumps(item["depends_on"]),
                 "PENDING",core.now()))
        for item in items:
            task=db.execute("SELECT id FROM auto_tasks WHERE project_id=? AND task_key=?",
                            (pid,item["key"])).fetchone()
            scheduler.attach(db,task["id"],item["kind"],item["resource_class"],item["targets"])
        db.execute("UPDATE auto_projects SET status='ACTIVE',updated_at=? WHERE id=?",

                   (core.now(),pid))
        event(db,pid,None,"PLAN_EXTENDED",{"keys":[x["key"] for x in items]})
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"project_id":pid,"added":[x["key"] for x in items],
            "decision":"CONTINUE","next_tool":"harness_auto_tick"}


def _expire(db,pid):
    """Agent claims are idempotent work leases, not OS process leases."""
    now=time.time()
    for row in db.execute(
        "SELECT * FROM auto_tasks WHERE project_id=? "
        "AND status IN ('RUNNING','REVIEWING','SPLITTING') AND lease_until<?",(pid,now)
    ).fetchall():
        state=("SPLIT_REQUIRED" if row["status"]=="SPLITTING"
               else "PENDING" if row["status"]=="RUNNING" else "SUBMITTED")
        if row["status"]=="RUNNING" and row["tries"]>=MAX_ATTEMPTS:
            state="BLOCKED"
        db.execute(
            "UPDATE auto_tasks SET status=?,owner=NULL,lease_token=NULL,"
            "lease_until=NULL,updated_at=? WHERE id=?",
            (state,core.now(),row["id"]))
        event(db,pid,row["task_key"],"LEASE_EXPIRED",{"state":state})


def _status_counts(all_tasks):
    return {key:sum(t["status"]==key for t in all_tasks) for key in
            ("PENDING","RUNNING","SUBMITTED","REVIEWING","SPLIT_REQUIRED","SPLITTING","WAIT_CHILDREN",
             "VERIFIED","REWORK","DISPUTED","BLOCKED")}


def _result(db,pid,decision,**payload):
    db.execute("UPDATE auto_projects SET status=?,updated_at=? WHERE id=?",
               ({"FINAL_REVIEW":"READY_FOR_FINAL_REVIEW",
                 "PLAN":"PLANNING","BLOCKED":"BLOCKED",
                 "YIELD":"ACTIVE"}.get(decision,"ACTIVE"),core.now(),pid))
    event(db,pid,payload.get("task_key"),"CONTROLLER_DECISION",{"decision":decision})
    return {"project_id":pid,"decision":decision,**payload}


def tick(db,pid,agent_id,session_id,role="executor",max_turns=MAX_TURNS):
    """Atomically schedule one admissible task, or request decomposition."""
    migrate(db)
    actor=txt(agent_id,"agent_id",128)
    session=txt(session_id,"session_id",128)
    if role not in {"executor","reviewer"}:
        raise ValueError("role must be executor or reviewer")
    if type(max_turns) is not int or not 1<=max_turns<=MAX_TURNS:
        raise ValueError("max_turns out of range")
    db.execute("BEGIN IMMEDIATE")
    try:
        pr=project(db,pid)
        if pr["status"] in {"STOPPED","ACCEPTED"}:
            outcome={"project_id":pid,"decision":pr["status"]}
        else:
            db.execute("INSERT OR IGNORE INTO auto_sessions VALUES(?,?,0,?)",
                       (pid,session,core.now()))
            n=db.execute(
                "SELECT turns FROM auto_sessions WHERE project_id=? AND session_id=?",
                (pid,session)).fetchone()[0]
            if n>=max_turns:
                outcome={"project_id":pid,"decision":"YIELD",
                         "reason":"Session decision budget reached; preserve project for resumption.",
                         "resume_tool":"harness_auto_tick"}
            else:
                db.execute("UPDATE auto_sessions SET turns=turns+1,last_seen=? "
                           "WHERE project_id=? AND session_id=?",(core.now(),pid,session))
                _expire(db,pid)
                unlocked=scheduler.unlock_parents(db,pid)
                for key in unlocked:
                    event(db,pid,key,"CHILDREN_VERIFIED_PARENT_UNLOCKED",{})
                current=tasks(db,pid)
                if not current:
                    outcome=_result(db,pid,"PLAN",
                           instruction="Agent composes a bounded dependency DAG with resource classes.")
                else:
                    verified={r["task_key"] for r in current if r["status"]=="VERIFIED"}
                    chosen=None
                    decision=None
                    denied=[]
                    for row in current:
                        if role=="reviewer":
                            eligible=(row["status"]=="SUBMITTED" and row["producer"]!=actor
                                and row["producer_session"] is not None
                                and row["producer_session"]!=session)
                        else:
                            eligible=(row["status"] in {"PENDING","REWORK","SPLIT_REQUIRED"} and
                                (row["tries"]<MAX_ATTEMPTS or row["status"]=="SPLIT_REQUIRED") and
                                all(x in verified for x in json.loads(row["dependencies"])))
                        if not eligible:
                            continue
                        if role=="executor" and row["status"]=="SPLIT_REQUIRED":
                            chosen=row
                            decision="DECOMPOSE"
                            break
                        allowed,why,spec=scheduler.capacity(db,pid,row)
                        if not allowed:
                            denied.append({"task_key":row["task_key"],"reason":why})
                            continue
                        chosen=row
                        decision="REVIEW" if role=="reviewer" else "EXECUTE"
                        break
                    if chosen:
                        token=ident()
                        state=("SPLITTING" if decision=="DECOMPOSE" else
                               "REVIEWING" if decision=="REVIEW" else "RUNNING")
                        db.execute(
                            "UPDATE auto_tasks SET status=?,owner=?,owner_session=?,lease_token=?,"
                            "lease_until=?,tries=tries+?,updated_at=? WHERE id=?",
                            (state,actor,session,token,time.time()+LEASE_SECONDS,
                             1 if decision=="EXECUTE" else 0,core.now(),chosen["id"]))
                        info=scheduler.spec_for(db,chosen)
                        event(db,pid,chosen["task_key"],"CLAIMED",
                              {"role":role,"actor":actor,"decision":decision,
                               "resource_class":info["profile"]})
                        outcome=_result(db,pid,decision,
                            task_key=chosen["task_key"],title=chosen["title"],
                            kind=chosen["kind"],acceptance=chosen["acceptance"],
                            depends_on=json.loads(chosen["dependencies"]),
                            claim_token=token,resource_class=info["profile"],
                            target_scopes=info["targets"],
                            instructions=("Supply evidence-grounded child scopes via harness_auto_split; "
                              "never merely increase timeout." if decision=="DECOMPOSE" else
                              "Check original evidence independently; do not impersonate reviewer."
                              if decision=="REVIEW" else
                              "Run only this bounded work item. On timeout call harness_auto_timeout; "
                              "on success submit and immediately tick again."))
                    elif all(row["status"]=="VERIFIED" for row in current):
                        outcome=_result(db,pid,"FINAL_REVIEW",completed=len(current),
                              note="Semantic and primary source verification still required.")
                    elif any(row["status"]=="BLOCKED" for row in current) and not any(
                          row["status"] in {"RUNNING","REVIEWING","SUBMITTED","SPLITTING"}
                          for row in current):
                        outcome=_result(db,pid,"BLOCKED",counts=_status_counts(current),
                            resource_wait=denied,
                            instruction="Agent triages blocked scopes without unbounded retry.")
                    else:
                        outcome=_result(db,pid,"WAIT",counts=_status_counts(current),
                            resource_wait=denied,
                            instruction=("Insufficient reserved resources; do not oversubscribe Ghidra."
                                         if denied else
                                         "Check pending independent reviews or active worker leases."))
        db.commit()
        return outcome
    except Exception:
        db.rollback()
        raise


def _task(db,pid,key):
    row=db.execute(
        "SELECT * FROM auto_tasks WHERE project_id=? AND task_key=?",(pid,key)
    ).fetchone()
    if not row:
        raise ValueError("Unknown task_key")
    return row


def _holder(row,actor,token,state):
    if row["status"]!=state or row["owner"]!=actor or row["lease_token"]!=token:
        raise ValueError("Task state or ownership token mismatch")
    if row["lease_until"] is None or row["lease_until"]<=time.time():
        raise ValueError("Claim expired; get a fresh decision from harness_auto_tick")


def renew(db,pid,key,actor,token):
    db.execute("BEGIN IMMEDIATE")
    try:
        task=_task(db,pid,key)
        if task["status"] not in {"RUNNING","REVIEWING","SPLITTING"}:
            raise ValueError("Task not leased")
        _holder(task,actor,token,task["status"])
        db.execute(
            "UPDATE auto_tasks SET lease_until=?,updated_at=? WHERE id=?",
            (time.time()+LEASE_SECONDS,core.now(),task["id"]))
        db.commit()
        return {"renewed":True,"lease_seconds":LEASE_SECONDS}
    except Exception:
        db.rollback()
        raise


def submit(db,pid,key,actor,token,summary,evidence,artifacts,checks):
    summary=txt(summary,"summary",12000)
    sources=json_arr(evidence,"evidence",40)
    files=json_arr(artifacts,"artifacts",40)
    validations=json_arr(checks,"checks",40)
    if not sources and not files:
        raise ValueError("Submission requires evidence references or artifact paths")
    db.execute("BEGIN IMMEDIATE")
    try:
        row=_task(db,pid,key)
        _holder(row,actor,token,"RUNNING")
        db.execute("UPDATE auto_tasks SET status='SUBMITTED',producer=?,producer_session=?,result=?,"
                   "evidence_json=?,artifacts_json=?,verification_json=?,"
                   "owner=NULL,owner_session=NULL,lease_token=NULL,lease_until=NULL,updated_at=? WHERE id=?",
                   (actor,row["owner_session"],summary,json.dumps(sources),json.dumps(files),
                    json.dumps(validations),core.now(),row["id"]))
        event(db,pid,key,"SUBMITTED",{"producer":actor,"evidence_count":len(sources),
                                    "artifact_count":len(files)})
        db.commit()
        return {"task_key":key,"status":"SUBMITTED","next":"Independent reviewer via harness_auto_tick(role=reviewer)"}
    except Exception:
        db.rollback()
        raise


def review(db,pid,key,actor,token,verdict,rationale,evidence_checked):
    rationale=txt(rationale,"rationale",8000)
    checked=json_arr(evidence_checked,"evidence_checked",40)
    if verdict not in {"APPROVE","REJECT"}:
        raise ValueError("Review verdict must be APPROVE or REJECT")
    if verdict=="APPROVE" and not checked:
        raise ValueError("Approval requires inspected primary evidence references")
    db.execute("BEGIN IMMEDIATE")
    try:
        row=_task(db,pid,key)
        _holder(row,actor,token,"REVIEWING")
        if actor==row["producer"]:
            raise ValueError("Producer cannot review own task")
        updated="VERIFIED" if verdict=="APPROVE" else (
            "BLOCKED" if row["tries"]>=MAX_ATTEMPTS else "REWORK")
        db.execute(
            "UPDATE auto_tasks SET status=?,reviewer=?,reviewer_session=?,review_note=?,"
            "owner=NULL,owner_session=NULL,lease_token=NULL,lease_until=NULL,updated_at=? WHERE id=?",
            (updated,actor,row["owner_session"],rationale,core.now(),row["id"]))
        scheduler.feedback(db,pid,key,"PASS" if verdict=="APPROVE" else "REJECT")
        event(db,pid,key,"REVIEW_"+verdict,{"actor":actor,
              "evidence_checked":checked,"state":updated})
        db.commit()
        return {"task_key":key,"status":updated,
                "decision":"CONTINUE" if updated=="VERIFIED" else "REPLAN"}
    except Exception:
        db.rollback()
        raise


def report_issue(db,pid,key,summary,evidence):
    """Evidence-driven replanning: add high-priority audit, invalidate dependents."""
    summary=txt(summary,"issue",5000)
    refs=json_arr(evidence,"evidence",40)
    if not refs:
        raise ValueError("Contradiction requires evidence references")
    db.execute("BEGIN IMMEDIATE")
    try:
        origin=_task(db,pid,key)
        digest=hashlib.sha256((key+"|"+summary).encode()).hexdigest()[:10]
        audit_key="audit-"+digest
        existing=db.execute(
            "SELECT task_key FROM auto_tasks WHERE project_id=? AND task_key=?",
            (pid,audit_key)).fetchone()
        if existing:
            db.commit()
            return {"created":False,"audit_task_key":audit_key}
        if len(tasks(db,pid))>=MAX_TASKS:
            raise ValueError("Task budget exceeded")
        # Keep evidence history; revoke prior VERIFIED status without deleting it.
        db.execute(
            "UPDATE auto_tasks SET status='DISPUTED',updated_at=? "
            "WHERE id=? AND status='VERIFIED'",(core.now(),origin["id"]))
        # Any downstream task needs re-evaluation after conflict resolution.
        allrows=tasks(db,pid)
        affected={key}
        changed=True
        while changed:
            changed=False
            for row in allrows:
                if row["task_key"] not in affected and any(
                    d in affected for d in json.loads(row["dependencies"])
                ):
                    affected.add(row["task_key"])
                    changed=True
        for dep in affected-{key}:
            row=_task(db,pid,dep)
            if row["status"]=="VERIFIED":
                db.execute(
                    "UPDATE auto_tasks SET status='REWORK',"
                    "tries=0,updated_at=? WHERE id=?",(core.now(),row["id"]))
        db.execute(
            "INSERT INTO auto_tasks(id,project_id,task_key,title,acceptance,kind,"
            "priority,dependencies,status,parent_issue,updated_at)"
            " VALUES(?,?,?,?,?,'AUDIT',100,'[]','PENDING',?,?)",
            (ident(),pid,audit_key,"Resolve contradiction in "+key,
             "Inspect original evidence; document conflict and repair path: "+
             summary,key,core.now()))
        event(db,pid,key,"CONTRADICTION",{"audit":audit_key,"evidence":refs,
                                       "affected":sorted(affected)})
        db.execute("UPDATE auto_projects SET status='ACTIVE',updated_at=? WHERE id=?",
                   (core.now(),pid))
        db.commit()
        return {"created":True,"audit_task_key":audit_key,"invalidated":sorted(affected),
                "decision":"REPLAN","next_tool":"harness_auto_tick"}
    except Exception:
        db.rollback()
        raise


def snapshot(db,pid):
    migrate(db)
    row=project(db,pid)
    arr=tasks(db,pid)
    return {"project":dict(row),"counts":_status_counts(arr),
        "tasks":[{"key":x["task_key"],"title":x["title"],
                  "kind":x["kind"],"status":x["status"],
                  "dependencies":json.loads(x["dependencies"]),
                  "tries":x["tries"],"producer":x["producer"],
                  "reviewer":x["reviewer"],"review_note":x["review_note"],
                  "producer_session":x["producer_session"],
                  "reviewer_session":x["reviewer_session"]}
                 for x in arr],
        "latest_events":[dict(x) for x in db.execute(
            "SELECT task_key,event,details,timestamp FROM auto_events "
            "WHERE project_id=? ORDER BY id DESC LIMIT 15",(pid,))],
        "resume_instruction":"Continue agent-driven harness_auto_tick loop; "
                             "never ask user to write phase-by-phase prompts."}


def final_review(db,pid,reviewer,decision,note):
    """Project-level acceptance needs human confirmation or separate reviewer."""
    reviewer=txt(reviewer,"reviewer",128)
    note=txt(note,"note",7000)
    if decision not in {"ACCEPT","REOPEN"}:
        raise ValueError("Expected ACCEPT or REOPEN")
    db.execute("BEGIN IMMEDIATE")
    try:
        row=project(db,pid)
        if row["status"] not in {"READY_FOR_FINAL_REVIEW","ACTIVE"}:
            raise ValueError("Project is not awaiting final acceptance")
        arr=tasks(db,pid)
        if not arr or any(t["status"]!="VERIFIED" for t in arr):
            raise ValueError("All tasks must have passed independent review")
        if row["binary_path"] and (
            not Path(row["binary_path"]).is_file() or
            core.sha256(row["binary_path"])!=row["binary_sha256"]
        ):
            raise ValueError("Pinned binary changed")
        outcome="ACCEPTED" if decision=="ACCEPT" else "ACTIVE"
        db.execute("UPDATE auto_projects SET status=?,updated_at=? WHERE id=?",
                   (outcome,core.now(),pid))
        event(db,pid,None,"PROJECT_"+decision,
              {"reviewer":reviewer,"note":note,
               "authenticity":"not attested by harness"})
        db.commit()
        return {"status":outcome,"decision":decision,"note":note,
                "warning":"Host actor identity and evidence content are not independently attested"}
    except Exception:
        db.rollback()
        raise


def pause(db,pid,reason):
    reason=txt(reason,"reason",3000)
    with db:
        project(db,pid)
        db.execute("UPDATE auto_projects SET status='STOPPED',updated_at=? WHERE id=?",
                   (core.now(),pid))
        event(db,pid,None,"STOPPED",{"reason":reason})
    return {"status":"STOPPED","reason":reason}


def resolve_issue(db,pid,source_key,audit_key,note):
    """Review-approved audit unlocks re-analysis, never silently restores VERIFIED."""
    note=txt(note,"resolution",5000)
    db.execute("BEGIN IMMEDIATE")
    try:
        source=_task(db,pid,source_key)
        audit=_task(db,pid,audit_key)
        if audit["parent_issue"]!=source_key or audit["status"]!="VERIFIED":
            raise ValueError("Audit task must independently pass review first")
        if source["status"]!="DISPUTED":
            raise ValueError("Original task is not disputed")
        db.execute(
            "UPDATE auto_tasks SET status='REWORK',tries=0,"
            "owner=NULL,owner_session=NULL,lease_token=NULL,lease_until=NULL,updated_at=? WHERE id=?",
            (core.now(),source["id"]))
        event(db,pid,source_key,"AUDIT_RESOLVED",
              {"audit_task":audit_key,"next":"rerun original","note":note})
        db.commit()
        return {"source_task":source_key,"status":"REWORK","decision":"CONTINUE",
                "note":"Re-execute original task and obtain fresh independent review"}
    except Exception:
        db.rollback()
        raise


def resume(db,pid,note):
    """Explicitly re-enable a paused project; never revoke final acceptance."""
    note=txt(note,"resume note",2000)
    db.execute("BEGIN IMMEDIATE")
    try:
        row=project(db,pid)
        if row["status"] not in {"STOPPED","BLOCKED"}:
            raise ValueError("Resume permitted only for STOPPED or BLOCKED projects")
        db.execute("UPDATE auto_projects SET status='ACTIVE',updated_at=? WHERE id=?",
                   (core.now(),pid))
        event(db,pid,None,"RESUMED",{"note":note})
        db.commit()
        return {"status":"ACTIVE","next_tool":"harness_auto_tick"}
    except Exception:
        db.rollback()
        raise


def list_projects(db,limit=30):
    """Agent can recover the active project without any user-supplied ID."""
    migrate(db)
    if type(limit) is not int or not 1<=limit<=50:
        raise ValueError("limit 1..50")
    data=[dict(r) for r in db.execute(
        "SELECT id,goal,acceptance,status,binary_path,updated_at "
        "FROM auto_projects ORDER BY "
        "CASE WHEN status IN ('ACTIVE','PLANNING','BLOCKED','READY_FOR_FINAL_REVIEW') "
        "THEN 0 ELSE 1 END, updated_at DESC LIMIT ?",(limit,))]
    return {"projects":data,"recommended_project_id":data[0]["id"] if data else None,
            "instruction":"Resume a matching ongoing goal; do not create a duplicate project"}


def task_detail(db,pid,key):
    """Read all per-task evidence/checks/attempts after context compaction."""
    row=dict(_task(db,pid,key))
    for col in ("dependencies","evidence_json","artifacts_json","verification_json"):
        if row.get(col):
            row[col]=json.loads(row[col])
    # Never disclose the ownership token to a different agent querying state:
    row.pop("lease_token",None)
    return {"task":row,"source_integrity":"Agent-submitted evidence references are not authenticated"}


def block_task(db,pid,key,actor,token,reason):
    """Explicit bounded stop for tool/permission blocker; not a fake success."""
    reason=txt(reason,"blocker",4000)
    db.execute("BEGIN IMMEDIATE")
    try:
        row=_task(db,pid,key)
        _holder(row,actor,token,"RUNNING")
        db.execute(
            "UPDATE auto_tasks SET status='BLOCKED',owner=NULL,lease_token=NULL,"
            "lease_until=NULL,review_note=?,updated_at=? WHERE id=?",
            (reason,core.now(),row["id"]))
        event(db,pid,key,"TASK_BLOCKED",{"actor":actor,"reason":reason})
        db.commit()
        return {"task_key":key,"status":"BLOCKED","reason":reason,
                "decision":"REPLAN_OR_REQUEST_PERMISSION"}
    except Exception:
        db.rollback()
        raise


def export_report(db,state,pid):
    """Durable local-only project report; never publishes binaries or evidence."""
    info=snapshot(db,pid)
    full=tasks(db,pid)
    root=Path(state).expanduser().resolve()
    folder=root/"auto_reports"
    folder.mkdir(parents=True,exist_ok=True)
    dest=folder/(pid+".md")
    lines=["# RE Dragon v0.5 Controller Report", "",
           "Project: "+pid, "Status: "+info["project"]["status"], "",
           "## Goal", "", info["project"]["goal"], "",
           "## Acceptance", "", info["project"]["acceptance"], "",
           "## Tasks", ""]
    for t in full:
        lines+=["### "+t["task_key"]+" — "+t["status"], "",
            "Title: "+t["title"], "Kind: "+t["kind"],
            "Acceptance: "+t["acceptance"],
            "Dependencies: "+", ".join(json.loads(t["dependencies"])),
            "Producer: "+str(t["producer"] or "none"),
            "Reviewer: "+str(t["reviewer"] or "none"),
            "Attempts: "+str(t["tries"]), "",
            "Reported result:", t["result"] or "none", "",
            "Evidence refs: "+str(t["evidence_json"] or "[]"),
            "Artifact refs: "+str(t["artifacts_json"] or "[]"),
            "Declared checks: "+str(t["verification_json"] or "[]"),
            "Review note: "+str(t["review_note"] or "none"), ""]
    lines+=["## Provenance limits", "",
      "References are supplied by the AI Agent and are not cryptographically authenticated.",
      "A different reviewer actor string does not prove two independent LLM instances.",
      "Completion requires real, source-grounded review and bounded project acceptance.", ""]
    temp=folder/(pid+".tmp")
    temp.write_text("\n".join(lines),encoding="utf-8")
    temp.replace(dest)
    return {"report":str(dest),"state":info["project"]["status"],
            "publication":"local-only"}


def _split_children(db,pid,parent,specs,reason):
    """Insert grounded, bounded scopes atomically. Parent is NOT auto-approved."""
    if not 2<=len(specs)<=8:
        raise ValueError("Split requires 2..8 smaller child tasks")
    if len(tasks(db,pid))+len(specs)>MAX_TASKS:
        raise ValueError("Project task budget exceeded")
    parent_spec=scheduler.spec_for(db,parent)
    if parent_spec["split_depth"]>=scheduler.MAX_SPLIT_DEPTH:
        raise ValueError("Maximum split depth reached; must BLOCK rather than loop")
    deps=json.loads(parent["dependencies"])
    previous={r["task_key"]:json.loads(r["dependencies"]) for r in tasks(db,pid)}
    proposed=[]
    all_targets=[]
    for child in specs:
        if not isinstance(child,dict):
            raise ValueError("Split child must be an object")
        scopes=scheduler.targets(child.get("targets",[]))
        if not scopes:
            raise ValueError("Split child needs bounded, evidence-grounded targets")
        all_targets+=scopes
        proposed.append({
            "key":txt(child.get("key"),"child_key",80),
            "title":txt(child.get("title"),"child_title",250),
            "acceptance":txt(child.get("acceptance"),"child_acceptance",3000),
            "priority":int(child.get("priority",parent["priority"])),
            "kind":child.get("kind",parent["kind"]),
            "resource_class":child.get("resource_class",parent_spec["profile"]),
            "targets":scopes,"depends_on":deps,
        })
    if len(set(all_targets))!=len(all_targets):
        raise ValueError("Child target scopes overlap")
    if parent_spec["targets"] and set(all_targets)!=set(parent_spec["targets"]):
        raise ValueError("Children must partition every parent target exactly")
    validated=_validate_batch(proposed,previous)
    for child in validated:
        ident_task=ident()
        db.execute(
            "INSERT INTO auto_tasks(id,project_id,task_key,title,acceptance,"
            "kind,priority,dependencies,status,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (ident_task,pid,child["key"],child["title"],child["acceptance"],
             child["kind"],child["priority"],json.dumps(child["depends_on"]),
             "PENDING",core.now()))
        scheduler.attach(db,ident_task,child["kind"],child["resource_class"],
                         child["targets"],parent_spec["split_depth"]+1,
                         parent["task_key"])
    db.execute(
        "UPDATE auto_tasks SET status='WAIT_CHILDREN',owner=NULL,owner_session=NULL,"
        "lease_token=NULL,lease_until=NULL,tries=0,updated_at=? WHERE id=?",
        (core.now(),parent["id"]))
    event(db,pid,parent["task_key"],"TASK_SPLIT",{
        "reason":reason,"depth":parent_spec["split_depth"]+1,
        "children":[x["key"] for x in validated]})
    return {"parent_task_key":parent["task_key"],"status":"WAIT_CHILDREN",
            "children":[x["key"] for x in validated],
            "decision":"CONTINUE","next_tool":"harness_auto_tick",
            "integration_rule":"Parent must be synthesized and independently reviewed after all children pass"}


def report_timeout(db,pid,key,actor,token,diagnostic):
    """Timeout never extends native analysis duration; halves scoped tasks."""
    diagnostic=txt(diagnostic,"diagnostic",3000)
    db.execute("BEGIN IMMEDIATE")
    try:
        parent=_task(db,pid,key)
        _holder(parent,actor,token,"RUNNING")
        spec=scheduler.spec_for(db,parent)
        adaptive=scheduler.feedback(db,pid,key,"TIMEOUT")
        if spec["split_depth"]>=scheduler.MAX_SPLIT_DEPTH:
            state="BLOCKED"
        elif len(spec["targets"])>=2:
            chunks=scheduler.groups(spec["targets"])
            children=[]
            for i,part in enumerate(chunks,1):
                children.append({"key":scheduler.task_group_key(key,spec["split_depth"]+1,i),
                    "title":parent["title"]+" — partition "+str(i),
                    "acceptance":parent["acceptance"]+
                      " Evidence and checks for ONLY these targets: "+", ".join(part),
                    "priority":parent["priority"],"kind":parent["kind"],
                    "resource_class":spec["profile"],"targets":part})
            result=_split_children(db,pid,parent,children,"TIMEOUT: "+diagnostic)
            result["adaptive"]=adaptive
            db.commit()
            return result
        elif len(spec["targets"])==0:
            state="SPLIT_REQUIRED"
        else:
            state="BLOCKED"
        db.execute(
            "UPDATE auto_tasks SET status=?,owner=NULL,owner_session=NULL,"
            "lease_token=NULL,lease_until=NULL,review_note=?,updated_at=? WHERE id=?",
            (state,"Timeout; narrow scope: "+diagnostic,core.now(),parent["id"]))
        event(db,pid,key,"TASK_TIMEOUT",{"next":state,"diagnostic":diagnostic})
        db.commit()
        return {"task_key":key,"status":state,"decision":
                "DECOMPOSE" if state=="SPLIT_REQUIRED" else "BLOCKED",
                "adaptive":adaptive,
                "instruction":"Agent must supply independently scoped children; "
                              "do NOT increase timeout or repeat full Ghidra import."}
    except Exception:
        db.rollback()
        raise


def split_task(db,pid,key,actor,token,children,rationale):
    """After timeout with no atomic targets, the Agent supplies evidence scopes."""
    rationale=txt(rationale,"rationale",3000)
    db.execute("BEGIN IMMEDIATE")
    try:
        parent=_task(db,pid,key)
        _holder(parent,actor,token,"SPLITTING")
        result=_split_children(db,pid,parent,children,rationale)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def resource_status(db,pid):
    migrate(db)
    project(db,pid)
    status=scheduler.policy_status(db,pid)
    return {**status,
            "ready_tasks":sum(r["status"] in {"PENDING","REWORK"} for r in tasks(db,pid)),
            "resource_mode":"advisory_reservation_no_os_enforcement"}


def resource_config(db,pid,max_concurrency):
    """Agent may tighten parallelism; never exceed physical CPU or four."""
    if type(max_concurrency) is not int:
        raise ValueError("max_concurrency must be integer")
    h=scheduler.read_host()
    if not 1<=max_concurrency<=min(scheduler.MAX_WORKERS,h.cpus):
        raise ValueError("max_concurrency exceeds host or safety limit")
    db.execute("BEGIN IMMEDIATE")
    try:
        project(db,pid)
        policy=scheduler.ensure_policy(db,pid,h)
        new=min(policy["concurrency"],max_concurrency)
        db.execute(
            "UPDATE auto_scheduler_policy SET max_concurrency=?,concurrency=?,"
            "updated_at=? WHERE project_id=?",
            (max_concurrency,new,core.now(),pid))
        event(db,pid,None,"RESOURCE_CONFIGURED",
              {"max_concurrency":max_concurrency})
        db.commit()
        return resource_status(db,pid)
    except Exception:
        db.rollback()
        raise


def recover_blocked_android_device(db, pid, task_key, *, device_serial, adb_proof, operator_note):
    """Explicit, evidence-gated environment recovery; not task acceptance.

    No VERIFIED/SUBMITTED/DISPUTED task is changed. Requires a previously
    device-blocked task and no other BLOCKED scopes. All writes are audited.
    """
    import re as _re
    from . import core as _core
    if not isinstance(adb_proof, dict) or adb_proof.get("device") != device_serial:
        raise ValueError("Live ADB proof does not match pinned device")
    if not adb_proof.get("required_reverse_ports") == [30001, 30008]:
        raise ValueError("Required ADB reverse tunnel proof missing")
    db.execute("BEGIN IMMEDIATE")
    try:
        pr = project(db, pid)
        if pr["status"] not in {"BLOCKED", "ACTIVE"}:
            raise ValueError("Project must be BLOCKED or ACTIVE, never accepted/stopped")
        task = _task(db, pid, task_key)
        if task["status"] not in {"BLOCKED", "REWORK", "PENDING"}:
            raise ValueError("P3 is not in an environment-recoverable task state")
        other = db.execute(
            "SELECT task_key FROM auto_tasks WHERE project_id=? AND status='BLOCKED' AND task_key<>?",
            (pid, task_key),
        ).fetchall()
        if other:
            raise ValueError("Other blocked tasks need independent review")
        old_note = (task["review_note"] or "")
        if task["status"] == "BLOCKED":
            if not (_re.search(r"RMX3461|10b3139c|ADB|Android test device|physical Android", old_note, _re.I)):
                raise ValueError("P3 blocker does not establish an ADB/device cause")
            db.execute(
                "UPDATE auto_tasks SET status='REWORK', tries=0, "
                "owner=NULL,owner_session=NULL,lease_token=NULL,lease_until=NULL, "
                "updated_at=? WHERE id=? AND status='BLOCKED'",
                (_core.now(), task["id"]),
            )
            event(db, pid, task_key, "ANDROID_DEVICE_BLOCKER_REQUEUED", {
                "device": device_serial, "adb_proof": adb_proof,
                "old_tries": task["tries"], "previous_blocker": old_note[:1500],
                "authorization": operator_note[:500],
                "result": "REWORK_NOT_VERIFIED",
            })
        else:
            event(db, pid, task_key, "ANDROID_DEVICE_RECOVERY_RECHECKED", {
                "device": device_serial, "adb_proof": adb_proof,
                "status_unchanged": task["status"],
            })
        if pr["status"] == "BLOCKED":
            db.execute("UPDATE auto_projects SET status='ACTIVE',updated_at=? WHERE id=?",
                       (_core.now(),pid))
            event(db,pid,None,"PROJECT_REOPENED_AFTER_DEVICE_RECOVERY",{
                "task_key":task_key,"acceptance_unchanged":True,
            })
        db.commit()
        return {"project": "ACTIVE", "task": "REWORK" if task["status"] == "BLOCKED" else task["status"]}
    except Exception:
        db.rollback()
        raise
