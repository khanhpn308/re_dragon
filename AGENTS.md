# RE Dragon — Agent-first operating contract

Canonical repository: https://github.com/khanhpn308/re_dragon

## Product goal (highest priority)

The user delegates a research goal to **Codex or Antigravity in natural language**.
The AI Agent is the planner, investigator, tool caller, reviewer, and reporter.
Python, SQLite and the harness are invisible implementation details: **never ask
the user to run Python CLI commands, copy run IDs, operate checkpoints or select
function names as part of the normal workflow.**

## Agent's normal workflow

1. Call harness_context to discover local binaries and existing runs. Reuse a
   relevant run when practical and avoid duplicate analysis.
2. Use harness_create_plan for the chosen binary and investigation workflow.
3. Call harness_worker or harness_execute_step with bounded steps. Those MCP
   operations use REA CLI/SQLite internally; they are not user-facing.
4. Inspect harness_evidence_index and harness_read_evidence, plus the REA MCP
   function/xref tools when available. Do not trust symbol names as conclusions.
5. Choose next functions based on actual code; call harness_queue_function or
   harness_graph_start with exact addresses/symbols.
6. Store claims using harness_add_claim: VERIFIED, INFERRED, UNKNOWN with
   symbol/address, task key and rationale.
7. Use harness_validate and harness_render_report, then give the user a concise
   technical report with verified evidence, uncertainties and next action.
8. Use harness_next_actions only as optional workflow hints, not as a substitute
   for agent planning. Resume interrupted work. Do not steal a live process lease.

## Separation of responsibility

- User: high-level task and final review.
- Codex/Antigravity: decisions, planning, interpretation and dialogue.
- Harness MCP: tasks, persistence, evidence navigation, leases and gates.
- REA MCP/Ghidra/JADX: native inspection.
- Python/SQLite: internal tool implementation. CLI is fallback/diagnostics.

## Safety and evidence

Static local analysis first. No server probing, APK patching, interception of
credentials or external account actions absent authorization. Only safe code,
schemas and curated findings belong on GitHub. APKs/SOs, packets and raw
evidence stay local. REA success never proves protocol semantics; G4 remains
semantic review. Share one state directory; default REA engine capacity is 1.
Do not claim tests were run unless they were.

**All future project documentation should be Agent-first, not Python-CLI-first.**

See docs/AGENT_FIRST.md and docs/STABLE.md.
