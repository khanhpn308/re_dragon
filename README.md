# RE Dragon — Agent-first Reverse Engineering Harness

**v0.4.0 · The Agent orchestrates; Python is invisible infrastructure.**

The system is designed for Codex and Antigravity working with the REA MCP
server, Ghidra and JADX. Users delegate reverse-engineering objectives
through chat. The Agent chooses analysis tools, produces an evidence-linked
investigation plan, persists findings, and delivers the report.

## How to use it

After one-time setup of both MCP connections, open Codex or Antigravity and ask:

> Investigate ReturnSaiyan ARM64 networking, from initial TCP handshake to
> session-key derivation, packet framing and opcode dispatch. Use REA/Ghidra
> directly, inspect actual pseudocode and native references, preserve exact
> symbols/Evidence IDs, distinguish VERIFIED/INFERRED/UNKNOWN, and checkpoint
> so the investigation can resume.

**No Python CLI commands, run IDs, or manual function selection are required.**

## Primary architecture (v0.4)

User → Codex / Antigravity (planner + investigator + reviewer)
→ REA MCP (native Ghidra/JADX function analysis)
+ RE Dragon Harness MCP (plan, observation receipts, claims, checkpoints, report)
→ Local SQLite and workspace.

### Agent-oriented MCP operations

- harness_context, harness_investigation_status: discover targets and existing work
- harness_begin_investigation: record a natural-language objective
- harness_set_investigation_plan: save an ordered plan authored by the Agent
- harness_record_rea_observation: attach the actual REA MCP tool name,
  Evidence ID when available, and qualified summary/limitations
- harness_update_milestone: record progress with evidence prerequisite
- harness_record_finding: record a claim with traceable observation IDs
- harness_investigation_review: validate workflow and provenance gates
- harness_investigation_report: export an evidence-linked Markdown report
- harness_close_investigation: close with explicit limitations

### Evidence boundary

These observation receipts are supplied by the Agent; the harness currently
does not cryptographically authenticate them against REA's session. Accordingly,
the external authenticity gate is always UNVERIFIED and technical conclusions
require semantic review. Do not mistake the presence of an Evidence ID for proof
that the associated analysis was correct. The original REA MCP session should
be used to inspect the full record and coverage.

## Backward compatibility

The v0.3 Stable Engine and CLI-based task worker remain in the codebase for
existing investigations. They are not the preferred front end. v0.4's
investigation workflow calls REA MCP **directly from the Agent**, rather than
launching a fresh REA CLI subprocess per native operation.

## Documentation

- [Agent-first setup and operational playbook](docs/AGENT_FIRST.md)
- [v0.4 architecture, contracts and limits](docs/V04.md)
- [Stable engine v0.3 (legacy)](docs/STABLE.md)
- [Contributor/agent instructions](AGENTS.md)

## Setup requirements

WSL2 Ubuntu, local binary artifacts, REA configured for both Codex and
Antigravity and RE Dragon Harness MCP connected to both clients. The MCP
host starts the Python-based harness server automatically. Configuration
examples are in the Agent-first setup guide; after that, all routine work
happens through the AI Agent, not a shell.

CI tests cover Python/SQLite state changes and MCP dispatch with mock REA
receipts. A real device/WSL2 Ghidra end-to-end analysis is a separate
acceptance requirement, not implied by CI.
