# RE Dragon — Autonomous Agent-Driven Reverse Engineering

v0.6 adds adaptive CPU/RAM and single-heavy-Ghidra task scheduling to the v0.5 goal-level controller for Codex and Antigravity. The user provides ONE objective; the active AI Agent plans, executes, reviews and re-plans through MCP without requesting a new P-stage prompt each time.

## Start in the Agent chat

> Read AGENTS.md. Resume the ReturnSaiyan research. Use harness_auto_projects to find existing goals, then harness_auto_start if needed, write an evidence-based task DAG, and repeatedly use harness_auto_tick until a real blocker, session budget or final review. Use REA MCP and local tools to do the assigned work, harness_auto_submit to checkpoint, and a genuinely distinct reviewer Agent for harness_auto_review. Replan automatically on contradictions and commit safe code to re_dragon. Do not ask me for P5/P6 prompts or to run Python manually.

Both REA MCP and the RE Dragon Harness MCP must be connected once to the Agent host.

## Pilot gate before bulk execution

The source-controlled smoke protocol is in
[docs/LIVE_PILOT.md](docs/LIVE_PILOT.md). A deliberately defective local
fixture and the [re-dragon-reviewer subagent](.agents/agents/re-dragon-reviewer.md)
test whether a real reviewer spots a bug, rejects it, allows repair, and
unlocks a dependent task without extra human prompts. Harness event traces
can be evaluated with harness_pilot_evaluate, but actual Antigravity
subagent execution must be verified in /agents.

## v0.6 adaptive task admission and decomposition

The orchestrator (not the user) decides what to execute next:
resource_class estimates per task; at most one GHIDRA_HEAVY task globally;
CPU/memory admission; bounded project worker concurrency; dynamic concurrency
after review/timeout; bounded automatic target-list bisection when Ghidra
times out; and independently reviewed child tasks before final synthesis.

See [v0.6 scheduler and its limits](docs/V06_SCHEDULER.md).
There is still no always-on LLM and no OS-level enforcement outside
cooperating Harness sessions.

## v0.5 new features

- Goal decomposition as an Agent-authored dependency graph.
- Continuous MCP task scheduling within an active Agent session.
- Durable evidence/artifact/result checkpoints, claims and bounded retries.
- Explicit separate reviewer gating; no self-approved findings.
- Contradiction-triggered audit and invalidation of stale dependent approvals.
- Resume across sessions, session limits, final review and report state.

Limitations: the Python package implements durable MCP control, not an LLM or an always-on background Agent. It cannot run after Antigravity/Codex shuts down, and a real separate reviewer must be provided by the host. A5 REA receipt authenticity and semantic correctness remain independent review matters.

Full contract: docs/V05_AUTONOMY.md. Agent run instructions: AGENTS.md. Legacy v0.2–v0.4 APIs remain available for existing investigations. Store original game binaries and private evidence locally only.
