# Agent workflow — re_dragon

Use this repository for Reverse Engineering Harness code. Treat binary artifacts as local-only.

## Environment

- Repository is typically in WSL2 Ubuntu under `~/returnsaiyan-re`.
- REA CLI and Ghidra analyze extracted binaries; do not commit `*.apk`, `*.so`, raw captures, credentials or `.re_harness/`.
- Use `python3 prototype/re_harness.py run --binary ./libaos_jogo.so` for the P0 static investigation.
- Use `status`, `resume`, and `report` for checkpoint-based continuation. Never mark a technical conclusion verified solely from the CLI exit code.

## Evidence discipline

- Keep binary SHA-256, exact symbol/address, REA tool output and observed limitations.
- Separate VERIFIED facts, INFERRED hypotheses and UNKNOWN gaps in narrative reports.
- No connection to an unapproved third-party game server, token extraction or account automation by default.
- The user prefers a usable artifact first; avoid adding substantial test infrastructure in P0.

## What P0 actually provides

Deterministic REA CLI tasks, SQLite state, resumable execution and raw evidence/report export. It does not yet provide a persistent MCP client or an autonomous multi-agent planner.
