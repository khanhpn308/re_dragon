# RE Dragon — one unattended quota-bounded Agent turn

You are in the official Antigravity CLI headless mode started by a local
quota watchdog. This is one bounded turn of the EXISTING project.

1. Read AGENTS.md and docs/V06_SCHEDULER.md. Call harness_auto_projects and
   harness_auto_status to resume the ReturnSaiyan Unified Heroes Edition goal.
   The supervisor injects a pinned PROJECT ID. Work ONLY on that project;
   do not create a new goal or switch projects or conversations. If the goal
   is absent or blocked, emit NEEDS_USER.
2. Continue autonomous tasks with harness_auto_tick. Respect Ghidra exclusion,
   resource leases, evidence reviews, scope decomposition and task checkpoint
   rules. Complete more than one task only when their acceptance gates permit.
3. Never invoke live game servers, real accounts or external account services.
   Keep original APK and SO unchanged, do not push game binaries or credentials.
   Do not turn off sandbox, approvals, model limits or quota enforcement.
4. If quota runs out, allow the official CLI to return its actual error.
   Never retry repeatedly in-process, change accounts or override provider caps.
5. If interactive permission/authentication is needed, STOP and report
   NEEDS_USER. Do not forge a reviewer by relabeling the same model session.
6. Preserve intermediate findings and checkpoints. Prefer bounded tasks
   shorter than the host execution time and renew leases as necessary.
7. Before exiting, inspect goal status. If relevant goals are accepted, emit
   COMPLETE; if independently reviewed tasks remain ready, CONTINUE; if
   waiting for legitimate resource release, WAIT; for a recoverable session
   yield, YIELD; for a genuine unresolved blocker, BLOCKED; for approval or
   authorization only the user can provide, NEEDS_USER.

CRITICAL: Emit exactly one final machine-readable line without code fence:
RE_DRAGON_RUN_STATE {"state":"CONTINUE","note":"checkpoint saved; work remains"}

Allowed states: CONTINUE, YIELD, WAIT, COMPLETE, BLOCKED, NEEDS_USER.
If the whole project has not passed its acceptance gates, never say COMPLETE.
