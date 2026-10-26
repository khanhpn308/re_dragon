# RE Dragon — Reverse Engineering Agent Harness

**The product interface is an AI Agent (Codex or Antigravity), not a Python CLI.**

The user describes a reverse-engineering objective in natural language. The Agent
plans, calls MCP tools, reads native evidence, selects additional functions,
records findings and reports back. Python + SQLite are internal infrastructure.

## Example request to an Agent

> Analyze ReturnSaiyan ARM64 networking from TCP handshake to opcode dispatch.
> Find exact symbols and addresses, verify key/frame handling from pseudocode,
> preserve evidence and checkpoint the task. Distinguish VERIFIED, INFERRED
> and UNKNOWN, and report the remaining gaps.

No manual Python commands or run IDs required.

## System roles

- **Codex / Antigravity:** active orchestration and technical reasoning.
- **REA MCP + Ghidra/JADX:** native and Android decompilation tools.
- **RE Dragon Harness MCP:** tasks, checkpoints, evidence, leases, retries, gates.
- **Python + SQLite:** implementation details behind MCP, not an end-user UI.

The Agent-facing MCP has been expanded with harness_context,
harness_read_evidence and harness_next_actions, alongside existing planning,
worker, graph and validation tools. A persistent REA MCP native-analysis session
has not yet been integrated into the worker; it invokes REA CLI internally.

## Setup and operating protocol

Read [Agent-first setup](docs/AGENT_FIRST.md) and [Agent instructions](AGENTS.md).
Initial MCP registration happens once. Afterwards work begins through chat.

## Capabilities and boundaries

Durable SQLite checkpoints, native task leasing for multiple Agents, process
recovery, bounded static graph candidates, evidence digests and claims.
Generated binary/evidence files stay Git-ignored and local.

A success code or static call graph cannot prove runtime protocol behavior.
G0–G3 check artifact/provenance integrity; G4 requires code-level review.
The current implementation is suitable as an Agent-controlled backend but
is not an always-on autonomous service.

For CLI diagnostics (not normal user workflow), see [Stable engine developer
notes](docs/STABLE.md). CI has validated mocked REA scenarios; real Ghidra
integration still needs verification in the selected WSL2 environment.

Repository: https://github.com/khanhpn308/re_dragon
