#!/usr/bin/env python3
"""Operator-run, audited recovery. No forced project acceptance or SQLite editing."""
import argparse
import json
from pathlib import Path
from re_harness import autonomy,core

def main():
    p=argparse.ArgumentParser(description="Review-gated blocked task recovery")
    p.add_argument("action",choices=("prepare","apply"))
    p.add_argument("--state-dir",default=".re_harness_mvp")
    p.add_argument("--project-id",required=True)
    p.add_argument("--task-key",required=True)
    p.add_argument("--reason")
    p.add_argument("--evidence",action="append",default=[])
    p.add_argument("--audit-key")
    p.add_argument("--confirm",action="store_true",help="Explicit operator confirmation")
    args=p.parse_args()
    if not args.confirm:
        p.error("--confirm is required (this changes durable controller state)")
    with core.database(Path(args.state_dir)) as db:
        autonomy.migrate(db)
        if args.action=="prepare":
            if not args.reason:p.error("prepare requires --reason")
            result=autonomy.prepare_blocked_rework_audit(
                db,args.project_id,args.task_key,args.reason,args.evidence)
        else:
            if not args.audit_key or not args.reason:
                p.error("apply requires --audit-key and --reason")
            result=autonomy.reopen_blocked_after_audit(
                db,args.project_id,args.task_key,args.audit_key,args.reason)
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
