# RE Dragon v0.6 — Adaptive Resource-Aware Orchestration

## What changed

The connected AI Agent still makes research decisions. The Harness now
atomically **admits** bounded tasks only when their estimated resource needs
fit CPU, memory and one globally reserved Ghidra-heavy slot.

This is NOT a background daemon, OS-level process limiter, container runtime
or native decompiler. It coordinates cooperating Agent sessions via a shared
SQLite database in WSL. All Agent/REA MCP calls must honor its reservation.

## Planning: let the Agent choose work, never the user

Use the usual single high-level goal and continuous harness_auto_tick loop.
For every task, specify optional resource_class and atomic targets:

- GHIDRA_HEAVY: Ghidra import/auto-analysis, native binary whole-module work
  (2 CPU slot estimate, 3072 MB reservation; only ONE globally)
- CPU: implementation, CPU-intensive offline test, schema reconciliation
  (1 CPU unit, 512 MB estimate)
- LIGHT: documentation or small local metadata work (1 CPU, 128 MB)

ANALYZE without an explicit class defaults to GHIDRA_HEAVY to fail closed.
Do not silently classify a native Ghidra import as LIGHT/CPU to bypass the
exclusive slot. All task classes are estimates, not measured process RSS.

Example bounded task in harness_auto_plan:
  {"key":"protocol-opcodes-01-10","title":"Trace opcode 0x01 and 0x10",
   "kind":"ANALYZE","acceptance":"Exact handler boundaries and source receipts",
   "resource_class":"GHIDRA_HEAVY",
   "targets":["0x01","0x10"],
   "priority":80,"depends_on":["binary-identity"]}

The Agent should decompose large work UPFRONT, before timeout, and use more
precise, independently verifiable acceptance criteria for each scope.
The Harness validates task DAG cycles and the target list, rejecting overlaps
during split and enforcing a project task-count cap.

## Scheduler

Inside the same SQLite BEGIN IMMEDIATE transaction as task claim:

1. Refresh expired leases; unlock a split parent ONLY after all child tasks
   reached VERIFIED through independent reviewer decisions.
2. Enumerate ready tasks in priority order.
3. Check project adaptive concurrency cap, global max 4 task reservations,
   one global GHIDRA_HEAVY reservation, CPU slot capacity, /proc/meminfo
   MemAvailable headroom, and high 1-minute load before heavy admission.
4. Skip tasks denied by resource pressure and consider other eligible lighter
   tasks; return WAIT/resource_wait with reasons when none fit.
5. Record resource class, atomic target scopes, claim owner/session and TTL
   in the task decision. Work executes using the Agent's existing tool set.

harness_auto_resources reports host resource observations, active controller
task reservations and current policy. harness_auto_resource_config allows
the Agent to tighten max_concurrency between 1 and min(4, logical CPU count).
No user needs to choose batch sizes.

## Feedback and timeouts

- Every independent review APPROVE increments a success streak; three
  successive approvals can increase project concurrency by ONE (never above
  bounded maximum).
- A REJECT reduces concurrency by ONE; a TIMEOUT halves it (floor 1).
- Samples include outcome and approximate time since last CLAIMED event.
  Success means reviewed work-item success, NOT verified binary equivalence.
- On a real tool timeout, call harness_auto_timeout with the exact task
  ownership token and diagnostic. DO NOT increase Ghidra timeout.
- With 2+ explicit atomic targets, the Harness automatically bisects the
  target set and creates two child tasks. Original parent enters WAIT_CHILDREN.
- If scope was not declared, original enters SPLIT_REQUIRED; next
  harness_auto_tick returns DECOMPOSE for the Agent, which uses
  harness_auto_split with 2..8 evidence-grounded, nonoverlapping children.
- An indivisible single-target task or max-depth=4 timeout becomes BLOCKED
  rather than retrying a giant analyzer indefinitely.
- After each child has independent review APPROVE, the parent becomes a
  LIGHT synthesis task. Parent is NEVER automatically VERIFIED; it must also
  run and pass review, preserving provenance.
- Split tasks are capped at 250 per project; no unbounded recursion.

## Host measurements and caveats

CPU count uses process affinity when available; available memory comes from
Linux /proc/meminfo (WSL reports may differ from physical host resources);
load average is a rough host-level pressure signal. Measurements do not include
accurate per-Ghidra Java RSS, GPU or native tool concurrency created outside
the Harness, and the scheduler does not enforce OS cgroups/process limits.
If memory telemetry is unavailable, high-resource admissions fail closed.

Leases expire after 1200 seconds; a lease is NOT a process handle and expiration
does not kill an ongoing native tool. The Agent must ensure old operations
have terminated before claiming another heavy task. Do not run multiple
independent Harness state databases for the same workstation and expect
global Ghidra reservation to coordinate them.

Independent reviewers continue to require separate REAL Antigravity subagent
sessions, verifiable in /agents; caller-supplied labels are not identity
attestation. All native analysis remains offline and source-bounded.

## Pilot before large workloads

1. Retain v0.5 live subagent pilot GO transcript and test evidence.
2. Run the v0.6 deterministic scheduling suite (tests/test_scheduler.py),
   including two projects contending for Ghidra, memory-pressure bypass of a
   heavy task by a light task, timeout-driven split, blocked atomic scope and
   parent review gate.
3. Use one actual small ReturnSaiyan scope via Antigravity CLI to observe
   a timed native call, real resources, capacity and recovery. Do not
   launch a mass import as part of this smoke test.
4. Only then let the Agent autonomously execute the existing project backlog,
   with no manual phase-by-phase prompting.

## New tools

- harness_auto_resources(project_id)
- harness_auto_resource_config(project_id,max_concurrency)
- harness_auto_timeout(project_id,task_key,agent_id,claim_token,diagnostic)
- harness_auto_split(project_id,task_key,agent_id,claim_token,children,rationale)

All v0.5 MCP tools remain backward-compatible. Checkpoints, prior
investigation evidence and CLI are preserved.
