# AGENTS.md — re_dragon

Use this repository as the sole versioned source for all RE Dragon harness code. Do not commit APKs, SO/ELF binaries, proprietary assets, account credentials, raw packet dumps, generated Ghidra databases or local evidence.

## Project purpose

Restore/understand ReturnSaiyan Android client networking from inspectable native binaries. Prioritize evidence-bound claims rather than speculative packet formats.

## MVP tools

- Run in WSL2 from the repository root.
- CLI: python3 -m re_harness {plan,run,execute,resume,status,add-function,claim,validate,report,doctor}
- MCP: python3 -m re_harness.mcp ; exposes the local task registry to Codex/Antigravity.
- REA CLI is used by the harness engine; use existing REA MCP separately when a live REA provider session is more suitable.
- Workflow: workflows/network-handshake.json
- Local state: .re_harness_mvp/ (ignored by git)

## Agent protocol

1. Create a task plan for the exact local binary; do not fabricate its checksum.
2. Run only read-only static operations by default.
3. Inspect returned Evidence JSON, not just exit code, before writing claims.
4. Preserve function symbol/address, procedure-selection ambiguity, evidence task key and limitations.
5. Label every claim VERIFIED, INFERRED or UNKNOWN. VERIFIED requires source-linked evidence, symbol/address and rationale; G4 still needs human/agent semantic review.
6. On interruption, use resume; do not re-run completed steps merely for appearance.
7. Write findings to local evidence and Markdown report, then commit only safe textual source/config/curated summaries to re_dragon.
8. Never route unapproved network requests to a third-party game server or capture user tokens/passwords.

## Working agreement

The user prioritizes delivering working code over additional test scaffolding. Do not assert runtime tests have passed when they have not been run. Keep the scope anchored to Reverse Engineering and the existing WSL2 + REA/Ghidra environment.
