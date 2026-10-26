"""Independent runtime-pilot trace evaluator: fail-closed on host authenticity."""
from __future__ import annotations
import json
from . import autonomy


def evaluate(db,project_id):
    autonomy.migrate(db)
    pr=autonomy.project(db,project_id)
    if not pr["goal"].upper().startswith("PILOT:"):
        raise ValueError("pilot evaluation requires an isolated PILOT: project")
    rows={row["task_key"]:row for row in autonomy.tasks(db,project_id)}
    events=[dict(x) for x in db.execute(
        "SELECT id,task_key,event,details,timestamp "
        "FROM auto_events WHERE project_id=? ORDER BY id",(project_id,)
    ).fetchall()]
    fixture=rows.get("inspect-and-repair-fixture")
    continuation=rows.get("continuation")
    outcomes={}
    outcomes["bounded_pilot_task_graph"]=fixture is not None and continuation is not None and (
        "inspect-and-repair-fixture" in
        json.loads(continuation["dependencies"]) if continuation else False
    )
    outcomes["review_rejected_initial_defect"]=bool(
        fixture and any(e["task_key"]=="inspect-and-repair-fixture" and
                        e["event"]=="REVIEW_REJECT" for e in events)
    )
    outcomes["review_approved_repair"]=bool(
        fixture and fixture["status"]=="VERIFIED" and any(
            e["task_key"]=="inspect-and-repair-fixture" and
            e["event"]=="REVIEW_APPROVE" for e in events)
    )
    rejects=[x["id"] for x in events if x["task_key"]=="inspect-and-repair-fixture"
             and x["event"]=="REVIEW_REJECT"]
    approves=[x["id"] for x in events if x["task_key"]=="inspect-and-repair-fixture"
              and x["event"]=="REVIEW_APPROVE"]
    outcomes["reject_before_approve"]=bool(rejects and approves and
                                         min(rejects)<max(approves))
    outcomes["distinct_review_sessions_recorded"]=bool(
        fixture and fixture["producer_session"] and fixture["reviewer_session"] and
        fixture["producer_session"]!=fixture["reviewer_session"] and
        fixture["producer"]!=fixture["reviewer"]
    )
    outcomes["dependent_task_continued_without_manual_phase"]=bool(
        continuation and continuation["status"]=="VERIFIED"
        and any(e["task_key"]=="continuation" and e["event"]=="CLAIMED" for e in events)
    )
    outcomes["continuous_controller_events"]=sum(
        e["event"]=="CONTROLLER_DECISION" for e in events
    )>=5
    # The actual host's subagent conversations and actions are not accessible in
    # SQLite and cannot be authenticated by these caller-supplied labels.
    passed=all(outcomes.values())
    return {
        "project_id":project_id,
        "controller_checks":outcomes,
        "controller_gate":"PASS" if passed else "FAIL",
        "real_antigravity_subagent_gate":"UNVERIFIED",
        "host_checks_required":[
            "Observe a separate reviewer subagent conversation ID in /agents",
            "Inspect actual tool calls and independent counterexample in reviewer transcript",
            "Confirm no extra user prompt was required to start continuation",
            "Confirm no production source or live game-server activity in pilot"
        ],
        "overall":"PENDING_HOST_VERIFICATION" if passed else "NO_GO",
        "reason":"Different actor/session strings can still be fabricated by one LLM. "
                 "Host-level reviewer independence cannot be inferred from SQLite.",
    }
