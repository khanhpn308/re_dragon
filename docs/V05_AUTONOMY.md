# RE Dragon v0.5 — Autonomous Agent Orchestration

## Goal

One user goal should create an Agent-owned continuous decision cycle rather than requiring the user to prompt each project stage.

Architecture: User → active Codex/Antigravity LLM → REA MCP and RE Dragon Harness MCP → local evidence, tools, Git and SQLite.

The harness is a durable orchestration control plane. It does not itself contain a hidden reasoning model or an always-on daemon.

## One-prompt usage

In Antigravity or Codex, open the re_dragon project and tell the Agent:

> Read AGENTS.md. Continue existing ReturnSaiyan evidence. Start or resume a v0.5 project with the overall goal of finishing the offline protocol reconstruction and source-grounded verification. Create a dependency backlog. Repeatedly call harness_auto_tick and carry out each task with REA MCP and local development tools. Submit outcomes and checked evidence, delegate independent review to a genuinely separate reviewer Agent, and continue automatically to the next eligible task. If you find incompatible schema/code evidence, create and review an audit task and replan. Do not ask me for subsequent P-stage prompts. Commit safe code and reports to re_dragon. Stop only for a genuine blocker, bounded session yield or final review.

## MCP controller contract

- harness_auto_start: create the goal with bounded acceptance.
- harness_auto_plan: seed or extend Agent-authored dependency DAG.
- harness_auto_tick: atomically decide PLAN, EXECUTE, REVIEW, WAIT, BLOCKED, FINAL_REVIEW or YIELD.
- harness_auto_renew: heartbeat long Agent tasks.
- harness_auto_submit: persist result/evidence/artifacts and queue review.
- harness_auto_review: separate actual reviewer inspects sources then approves/rejects.
- harness_auto_issue: contradiction becomes priority AUDIT and invalidates stale downstream approvals.
- harness_auto_resolve_issue: after independent audit approval, reopen source for rework.
- harness_auto_status: read the project, dependencies, blockers, attempts and last decisions on reconnect.
- harness_auto_final_review: bounded goal-level acceptance.
- harness_auto_stop and harness_auto_resume: pause/continue projects.

After each submit, review, issue or plan, the Agent must call harness_auto_tick again in the same live chat. This is the key difference from v0.4.

## Task lifecycle

PENDING → RUNNING → SUBMITTED → REVIEWING → VERIFIED, or REWORK if rejected. Execution retries are bounded; exhausted work becomes BLOCKED. Dependencies unlock only after VERIFIED.

The reviewer must have a different real Agent execution from the producer. A different caller-supplied actor ID is enforced technically, but does not independently attest identity. If the host cannot spawn a real reviewer, a pending review is an honest blocker, not permission to impersonate one.

## Evidence-driven replan

When code, schema or binary evidence contradicts a VERIFIED task:
1. Record issue with source references.
2. Create high-priority audit task and set source DISPUTED.
3. Mark VERIFIED downstream tasks REWORK.
4. Complete audit with independent review.
5. Resolve issue and reexecute source task before dependent tasks.

The old evidence history remains stored. Audit approval never silently restores prior VERIFIED state.

## Concurrency, budget and persistence

SQLite uses BEGIN IMMEDIATE for claiming one task and ownership tokens for completion. Agent task leases expire after 1200 seconds and can be re-claimed. They do not kill or resume native OS processes.

The controller has ceilings on task count, attempts and decisions per session, and produces YIELD to encourage resumable handoff. The user can start a new active Agent session later, which reads the stored project status rather than re-running prior phases.

## Acceptance limitations

- Task approval requires evidence/artifact references and a separate reviewing actor plus checked primary sources.
- Project acceptance requires all tasks reviewed and original local binary checksum unchanged if pinned.
- Host-reported evidence and reviewer identity are not cryptographically verified by this system.
- Native decompiler semantic correctness and live game compatibility require independent evidence beyond unit tests.
- There is NO background autonomous worker if the host Agent session closes; an additional supported scheduler/Agent SDK would be needed for that.

## Backward compatibility

The legacy v0.2–v0.4 tools remain available. For new work, the auto_* tools implement goal-level coordination. The existing ReturnSaiyan project should be resumed from verified stored artifacts, not discarded.
