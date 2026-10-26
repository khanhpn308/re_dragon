# RE Dragon stable-engine v0.3.0 — design and boundaries

## Architecture

- core.py: v0.2 persistent runs, tasks, claims and Markdown report.
- stable.py: additive SQLite migration, task leases, native-engine slots, worker process lifecycle, evidence indexing and bounded call-graph queueing.
- cli.py: interactive commands and worker execution.
- mcp.py: local agent-facing JSON-RPC stdio tools for Codex and Antigravity.
- workflows/network-handshake.json: read-only starter workflow.

The engine executes the actual installed REA CLI with inspect, search, function and decompile. It does not retain a direct REA MCP/Ghidra database session across commands.

## Concurrency and recovery

A worker atomically selects a dependency-ready pending/failed task and a free global engine slot using BEGIN IMMEDIATE. Each worker gets a unique ownership token. SQLite stores a timed lease, PID and Linux /proc start-time; it heartbeats both task and slot during native execution. Default engine capacity is 1. All workers must share the same local state directory and consistent capacity setting.

REA runs as a subprocess in its own POSIX process group. Timeout sends TERM, followed by KILL if required. stdout/stderr are captured on disk for each attempt. Attempt count and exponential cooldown survive Agent restarts.

Stale recovery inspects expired leases and recorded child identity. If the process is alive, the lease is not stolen. If the child is absent, the worker marks the task failed and releases its expired engine slot. Retry is limited by the configured attempts. This is process-level recovery, NOT restoration of an interrupted in-memory Ghidra database.

## Evidence and graph

Only JSON within a bounded 32 MiB indexing window is parsed; raw output is preserved independently. Explicit error payloads, malformed JSON or unindexable oversized JSON are recorded as a failed operation. The index extracts bounded symbol and address candidates from normalized_result, and graph edges from static call/callee lists. Candidate calls may be unresolved, incomplete or decompiler-inferred.

graph-start starts from an exact symbol/address, queues a native function dossier and expands discovered static candidate callees within depth 0–5 and total nodes 1–100. This is deliberately not a runtime call trace. It never asserts that missing edges are impossible.

## Gates

G0 exact binary digest; G1 task completion; G2 persisted output digest; G3 VERIFIED claim provenance. G4 is always REVIEW_REQUIRED, since protocol semantics cannot be validated from a task's success code or symbol names alone.

## Security and limitations

No shell execution; REA commands are argv arrays. No automatic network login, game server interrogation, payload interception, token capture or source patching. State, raw evidence and binaries are locally stored and ignored by Git.

Linux/WSL2 assumed for POSIX process groups and /proc process identity. MCP adapter is synchronous; callers must allow adequate time for Ghidra, or use the CLI. SQLite locking is local to one state DB, not a cross-machine distributed lock. Exhausted failed jobs require operator intervention.

Current v0.3 is delivered without execution tests per project instruction. The label stable-engine describes implemented resilience mechanisms, not production-tested reliability.
