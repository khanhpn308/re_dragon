# RE Dragon — Autonomous Agent-Driven Reverse Engineering

v0.5 implements a goal-level controller for Codex and Antigravity. The user provides ONE objective; the active AI Agent plans, executes, reviews and re-plans through MCP without requesting a new P-stage prompt each time.

## Start in the Agent chat

> Read AGENTS.md. Resume the ReturnSaiyan research. Use harness_auto_start if needed, write an evidence-based task DAG, and repeatedly use harness_auto_tick until a real blocker, session budget or final review. Use REA MCP and local tools to do the assigned work, harness_auto_submit to checkpoint, and a genuinely distinct reviewer Agent for harness_auto_review. Replan automatically on contradictions and commit safe code to re_dragon. Do not ask me for P5/P6 prompts or to run Python manually.

Both REA MCP and the RE Dragon Harness MCP must be connected once to the Agent host.

## v0.5 new features

- Goal decomposition as an Agent-authored dependency graph.
- Continuous MCP task scheduling within an active Agent session.
- Durable evidence/artifact/result checkpoints, claims and bounded retries.
- Explicit separate reviewer gating; no self-approved findings.
- Contradiction-triggered audit and invalidation of stale dependent approvals.
- Resume across sessions, session limits, final review and report state.

Limitations: the Python package implements durable MCP control, not an LLM or an always-on background Agent. It cannot run after Antigravity/Codex shuts down, and a real separate reviewer must be provided by the host. A5 REA receipt authenticity and semantic correctness remain independent review matters.

Full contract: docs/V05_AUTONOMY.md. Agent run instructions: AGENTS.md. Legacy v0.2–v0.4 APIs remain available for existing investigations. Store original game binaries and private evidence locally only.
