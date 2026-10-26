"""CLI for the RE Dragon MVP. Python standard library only."""
from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
from pathlib import Path

from . import core, stable


def build_parser():
    p = argparse.ArgumentParser(
        prog="re-dragon",
        description="REA reverse-engineering agent harness (stable v0.3)",
    )
    p.add_argument("--state-dir", type=Path, default=core.DEFAULT_STATE)
    sub = p.add_subparsers(dest="action", required=True)

    def planning(subparser):
        subparser.add_argument("--binary", type=Path, required=True)
        subparser.add_argument("--workflow", type=Path, default=core.DEFAULT_WORKFLOW)
        subparser.add_argument("--provider", default="ghidra")
        subparser.add_argument("--rea-bin", default="rea")

    def execution(subparser):
        subparser.add_argument("--timeout", type=int, default=1800)
        subparser.add_argument("--retries", type=int, default=1)
        subparser.add_argument("--max-steps", type=int)
        subparser.add_argument("--capacity", type=int, default=1,
                               help="Maximum concurrent REA engine slots (1-4)")

    planning(sub.add_parser("plan", help="Persist task plan without executing"))
    run = sub.add_parser("run", help="Plan and execute workflow")
    planning(run)
    execution(run)

    for name in ("execute", "resume"):
        command = sub.add_parser(name, help="Execute or resume unfinished steps")
        command.add_argument("--run-id", required=True)
        execution(command)

    status = sub.add_parser("status", help="List runs or detailed status")
    status.add_argument("--run-id")

    queue = sub.add_parser("add-function", help="Queue function dossier + pseudocode")
    queue.add_argument("--run-id", required=True)
    queue.add_argument("--procedure", required=True)

    claim = sub.add_parser("claim", help="Record a technical claim with provenance")
    claim.add_argument("--run-id", required=True)
    claim.add_argument("--text", required=True)
    claim.add_argument("--assessment", choices=sorted(core.ASSESSMENTS),
                       default="INFERRED")
    claim.add_argument("--task-key")
    claim.add_argument("--symbol")
    claim.add_argument("--address")
    claim.add_argument("--rationale")

    validate = sub.add_parser("validate", help="Evaluate evidence integrity gates")
    validate.add_argument("--run-id", required=True)
    report = sub.add_parser("report", help="Generate Markdown investigation report")
    report.add_argument("--run-id", required=True)
    worker = sub.add_parser("worker", help="Leased executor for shared agent workflows")
    worker.add_argument("--run-id", required=True)
    execution(worker)

    graph_start = sub.add_parser("graph-start", help="Queue bounded call-graph discovery")
    graph_start.add_argument("--run-id", required=True)
    graph_start.add_argument("--root", required=True)
    graph_start.add_argument("--depth", type=int, default=2)
    graph_start.add_argument("--max-nodes", type=int, default=30)

    graph = sub.add_parser("graph", help="Read indexed static call-graph candidates")
    graph.add_argument("--run-id", required=True)
    graph.add_argument("--root")
    graph.add_argument("--limit", type=int, default=200)

    evidence = sub.add_parser("evidence", help="List extracted evidence symbol candidates")
    evidence.add_argument("--run-id", required=True)
    evidence.add_argument("--task-key")
    evidence.add_argument("--limit", type=int, default=200)

    recover = sub.add_parser("recover", help="Recover stale leases without killing live work")
    recover.add_argument("--run-id")

    sub.add_parser("doctor", help="Display local prerequisites (not a live test)")
    return p


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    state = args.state_dir.expanduser().resolve()
    if args.action == "doctor":
        value = {
            "python": sys.version.split()[0],
            "rea_executable": shutil.which("rea"),
            "ghidra_install_dir": __import__("os").environ.get("GHIDRA_INSTALL_DIR"),
            "state_dir": str(state),
            "note": "Prerequisite inspection only; Ghidra/REA are not exercised",
        }
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0
    try:
        with core.database(state) as db:
            stable.migrate(db)
            if args.action in {"plan", "run"}:
                run_id = core.create_plan(
                    db, args.binary, args.workflow, args.provider, args.rea_bin
                )
                result = ({"run_id": run_id, "status": "planned"}
                          if args.action == "plan" else
                          stable.work(db, state, run_id,
                                      steps=args.max_steps or 200,
                                      retries=args.retries,
                                      timeout=args.timeout,
                                      capacity=args.capacity))
            elif args.action in {"execute", "resume", "worker"}:
                result = stable.work(
                    db, state, args.run_id, steps=args.max_steps or 200,
                    retries=args.retries, timeout=args.timeout, capacity=args.capacity
                )
            elif args.action == "status":
                result = core.status(db, args.run_id)
            elif args.action == "add-function":
                result = {"queued": core.append_function(
                    db, args.run_id, args.procedure
                )}
            elif args.action == "claim":
                result = {"claim_id": core.add_claim(
                    db, args.run_id, args.text, args.assessment, args.task_key,
                    args.symbol, args.address, args.rationale,
                )}
            elif args.action == "validate":
                result = core.validate(db, state, args.run_id)
            elif args.action == "report":
                result = {"report": str(core.render_report(db, state, args.run_id))}
            elif args.action == "graph-start":
                result = stable.add_graph(db, args.run_id, args.root,
                                          args.depth, args.max_nodes)
            elif args.action == "graph":
                result = stable.graph(db, args.run_id, args.root, args.limit)
            elif args.action == "evidence":
                result = stable.observations(db, args.run_id, args.task_key, args.limit)
            elif args.action == "recover":
                result = stable.recover(db, args.run_id)
            else:
                parser.error("Unsupported action")
                return 2
        print(json.dumps(result, ensure_ascii=False, indent=2))
        if isinstance(result, dict) and result.get("status") == "failed":
            return 1
        if args.action == "validate" and not result["ready_for_review"]:
            return 1
        return 0
    except (ValueError, OSError, sqlite3.Error) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
