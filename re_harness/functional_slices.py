"""Evidence-budgeted functional slices. No per-task wall-clock deadline.

REA remains an external MCP: this module gates registered calls and acceptance,
but cannot intercept unwrapped direct REA calls from the agent host.
"""
import json
import re
import uuid
from . import core

LIMITS = {"max_rea_calls": 30, "max_functions": 8, "max_xref_depth": 2,
          "max_output_chars": 16000}
KINDS = {"xref", "decompile", "function", "strings", "script", "packet"}

def migrate(db):
    db.executescript("""
      CREATE TABLE IF NOT EXISTS auto_functional_slices(
        task_id TEXT PRIMARY KEY REFERENCES auto_tasks(id),
        contract_json TEXT NOT NULL, created_at TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS auto_slice_calls(
        id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES auto_tasks(id),
        actor TEXT NOT NULL, target TEXT NOT NULL, tool_kind TEXT NOT NULL,
        xref_depth INTEGER NOT NULL, state TEXT NOT NULL,
        function_id TEXT, evidence_ref TEXT, output_chars INTEGER,
        result_sha256 TEXT, confidence TEXT, created_at TEXT NOT NULL);
      CREATE INDEX IF NOT EXISTS auto_slice_calls_task_idx
        ON auto_slice_calls(task_id);
    """)

def _items(x, key, limit=24):
    if not isinstance(x, list) or not 1 <= len(x) <= limit:
        raise ValueError(key + " must be a nonempty bounded list")
    if len(set(x)) != len(x) or any(
        not isinstance(v, str) or not v.strip() or len(v) > 256 for v in x
    ):
        raise ValueError(key + " contains duplicate, empty or oversized items")
    return x

def validate_contract(c):
    required = {"feature_id", "objective", "binary_sha256", "entrypoints",
                "targets", "questions", "artifacts", "acceptance", "budget"}
    if not isinstance(c, dict) or set(c) != required:
        raise ValueError("incomplete functional slice contract")
    if not isinstance(c["feature_id"], str) or not re.fullmatch(
            r"[A-Za-z0-9_-]{3,80}", c["feature_id"]):
        raise ValueError("invalid feature_id")
    if not isinstance(c["objective"], str) or not 15 <= len(c["objective"]) <= 1200:
        raise ValueError("objective must be 15..1200 chars")
    if not isinstance(c["binary_sha256"], str) or not re.fullmatch(
            r"[0-9a-fA-F]{64}", c["binary_sha256"]):
        raise ValueError("binary_sha256 required")
    for k in ("entrypoints", "questions", "artifacts", "acceptance"):
        _items(c[k], k)
    _items(c["targets"], "targets", 8)
    b = c["budget"]
    if not isinstance(b, dict) or set(b) != set(LIMITS):
        raise ValueError("budget keys invalid")
    for k, hard in LIMITS.items():
        if type(b[k]) is not int or not (0 if k == "max_xref_depth" else 1) <= b[k] <= hard:
            raise ValueError(k + " outside enforced bounds")
    if len(c["targets"]) > b["max_functions"]:
        raise ValueError("scope has more targets than function budget")
    return c

def _task(db, pid, key):
    t = db.execute("SELECT * FROM auto_tasks WHERE project_id=? AND task_key=?",
                   (pid, key)).fetchone()
    if t is None:
        raise ValueError("unknown task")
    return t

def _contract(db, t):
    row = db.execute("SELECT contract_json FROM auto_functional_slices WHERE task_id=?",
                     (t["id"],)).fetchone()
    return json.loads(row["contract_json"]) if row else None

def define(db, pid, key, contract):
    c = validate_contract(contract)
    db.execute("BEGIN IMMEDIATE")
    try:
        t = _task(db, pid, key)
        if t["kind"] != "ANALYZE" or t["status"] not in ("PENDING", "REWORK"):
            raise ValueError("slice requires pending/rework ANALYZE task")
        if _contract(db, t) is not None:
            raise ValueError("frozen slice may not be overwritten")
        proj = db.execute("SELECT binary_sha256 FROM auto_projects WHERE id=?",
                          (pid,)).fetchone()
        if proj["binary_sha256"] and proj["binary_sha256"].lower() != c["binary_sha256"].lower():
            raise ValueError("binary digest mismatches project identity")
        db.execute("INSERT INTO auto_functional_slices VALUES(?,?,?)",
                   (t["id"],json.dumps(c,ensure_ascii=False),core.now()))
        db.commit()
        return {"status":"SCOPE_FROZEN","task_key":key,"budget":c["budget"],
                "wall_clock_deadline":None}
    except Exception:
        db.rollback()
        raise

def status(db, pid, key):
    t = _task(db,pid,key)
    c = _contract(db,t)
    if c is None:
        return {"task_key":key,"registered":False}
    rows = db.execute("SELECT state,target,tool_kind,function_id,evidence_ref,confidence "
                      "FROM auto_slice_calls WHERE task_id=? ORDER BY rowid",(t["id"],)).fetchall()
    return {"registered":True,"task_key":key,"contract":c,"calls_used":len(rows),
            "calls_remaining":c["budget"]["max_rea_calls"]-len(rows),
            "pending_receipts":sum(x["state"]=="RESERVED" for x in rows),
            "functions":sorted({x["function_id"] for x in rows if x["function_id"]}),
            "receipts":[dict(x) for x in rows],"wall_clock_deadline":None}

def _holder(t, actor, token):
    from . import autonomy
    autonomy._holder(t,actor,token,"RUNNING")

def reserve(db, pid, key, actor, token, tool_kind, target, xref_depth):
    if tool_kind not in KINDS or type(xref_depth) is not int:
        raise ValueError("invalid REA operation/depth")
    db.execute("BEGIN IMMEDIATE")
    try:
        t=_task(db,pid,key); _holder(t,actor,token)
        c=_contract(db,t)
        if c is None:
            raise ValueError("register frozen slice first")
        if target not in c["targets"]:
            raise ValueError("target outside frozen slice")
        if not 0<=xref_depth<=c["budget"]["max_xref_depth"]:
            raise ValueError("XREF depth exceeds budget")
        rows=db.execute("SELECT state FROM auto_slice_calls WHERE task_id=?",
                        (t["id"],)).fetchall()
        if any(x["state"]=="RESERVED" for x in rows):
            raise ValueError("finish previous REA receipt first")
        if len(rows)>=c["budget"]["max_rea_calls"]:
            raise ValueError("REA_CALL_BUDGET_EXHAUSTED: submit or checkpoint/split")
        ticket=uuid.uuid4().hex
        db.execute("INSERT INTO auto_slice_calls(id,task_id,actor,target,tool_kind,"
                   "xref_depth,state,created_at) VALUES(?,?,?,?,?,?,?,?)",
                   (ticket,t["id"],actor,target,tool_kind,xref_depth,"RESERVED",core.now()))
        db.commit()
        return {"approved":True,"ticket":ticket,"target":target,
                "max_output_chars":c["budget"]["max_output_chars"],"wall_clock_deadline":None}
    except Exception:
        db.rollback(); raise

def receipt(db, pid, key, actor, token, ticket, function_id,
            evidence_ref, output_chars, result_sha256, confidence):
    if confidence not in ("VERIFIED","INFERRED","UNKNOWN"):
        raise ValueError("invalid evidence confidence")
    if not isinstance(evidence_ref,str) or not 3<=len(evidence_ref)<=256:
        raise ValueError("evidence_ref required (not raw dump)")
    if not isinstance(function_id,str) or not 1<=len(function_id)<=180:
        raise ValueError("function_id required")
    if not isinstance(result_sha256,str) or not re.fullmatch(r"[0-9a-fA-F]{64}",result_sha256):
        raise ValueError("result_sha256 required")
    if type(output_chars) is not int or output_chars<0:
        raise ValueError("output_chars invalid")
    db.execute("BEGIN IMMEDIATE")
    try:
        t=_task(db,pid,key); _holder(t,actor,token)
        c=_contract(db,t)
        if c is None:
            raise ValueError("not a registered functional slice")
        if output_chars>c["budget"]["max_output_chars"]:
            raise ValueError("output exceeds bounded context: store file and excerpt only")
        row=db.execute("SELECT * FROM auto_slice_calls WHERE id=? AND task_id=?",
                       (ticket,t["id"])).fetchone()
        if row is None or row["state"]!="RESERVED" or row["actor"]!=actor:
            raise ValueError("missing/foreign/completed REA ticket")
        existing={x[0] for x in db.execute(
            "SELECT DISTINCT function_id FROM auto_slice_calls "
            "WHERE task_id=? AND state='RECORDED'",(t["id"],)).fetchall()}
        if len(existing|{function_id})>c["budget"]["max_functions"]:
            raise ValueError("function count exceeds budget")
        db.execute("UPDATE auto_slice_calls SET state='RECORDED',function_id=?,"
                   "evidence_ref=?,output_chars=?,result_sha256=?,confidence=? WHERE id=?",
                   (function_id,evidence_ref,output_chars,result_sha256.lower(),confidence,ticket))
        db.commit()
        return {"recorded":True,"ticket":ticket}
    except Exception:
        db.rollback(); raise

def enforce_submission(db, task, evidence, artifacts):
    c=_contract(db,task)
    if c is None:
        return
    rows=db.execute("SELECT state,evidence_ref,confidence FROM auto_slice_calls "
                    "WHERE task_id=?",(task["id"],)).fetchall()
    if not rows or any(r["state"]!="RECORDED" for r in rows):
        raise ValueError("functional slice requires complete REA receipts")
    verified={r["evidence_ref"] for r in rows if r["confidence"]=="VERIFIED"}
    if not verified.intersection(evidence):
        raise ValueError("slice requires included VERIFIED primary evidence")
    missing=set(c["artifacts"])-set(artifacts)
    if missing:
        raise ValueError("missing declared slice artifacts: "+", ".join(sorted(missing)))

def checkpoint_split(db,pid,key,actor,token,note,evidence):
    """Voluntary checkpoint, not a timer-triggered termination."""
    if not isinstance(note,str) or not 15<=len(note)<=1500:
        raise ValueError("checkpoint note too short/long")
    _items(evidence,"evidence")
    db.execute("BEGIN IMMEDIATE")
    try:
        t=_task(db,pid,key); _holder(t,actor,token)
        if _contract(db,t) is None:
            raise ValueError("slice not registered")
        pending=db.execute("SELECT count(*) FROM auto_slice_calls WHERE task_id=? "
                           "AND state='RESERVED'",(t["id"],)).fetchone()[0]
        if pending:
            raise ValueError("cannot split until all call receipts recorded")
        db.execute("UPDATE auto_tasks SET status='SPLIT_REQUIRED',owner=NULL,"
                   "owner_session=NULL,lease_token=NULL,lease_until=NULL,"
                   "updated_at=? WHERE id=?",(core.now(),t["id"]))
        db.execute("INSERT INTO auto_events(project_id,task_key,event,details,timestamp)"
                   " VALUES(?,?,?,?,?)",(pid,key,"SLICE_CHECKPOINT_SPLIT",
                   json.dumps({"note":note,"evidence":evidence},ensure_ascii=False),core.now()))
        db.commit()
        return {"task_key":key,"status":"SPLIT_REQUIRED","next_tool":"harness_auto_tick"}
    except Exception:
        db.rollback(); raise
