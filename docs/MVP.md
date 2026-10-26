# MVP v0.2.0 — Architecture and boundaries

## Workflows

Input: local native ELF and a workflow JSON. Every workflow step has a unique key, operation and an optional list of earlier dependency keys. Supported REA CLI operations: inspect, search (procedure search), function (dossier) and decompile (pseudocode).

Planning hashes the binary and stores the exact absolute path, selected provider, workflow path and ordered tasks. A later binary checksum mismatch blocks execution/resume.

## State machine

Run statuses: planned, running, paused, failed, completed.

Task statuses: pending, running, failed, completed. The executor reads all noncompleted tasks in ordinal order, checks dependency completion and invokes the REA CLI with subprocess.run (no shell). Each attempt is recorded separately in SQLite and its JSON/stdout and stderr kept under a run-specific local evidence directory.

Completed tasks are never repeated during resume; interrupted/failed tasks can retry. A Linux flock held for the entire execution prevents two REA executors in the same checkout from concurrently running one run.

## Evidence and gates

- G0_BINARY_IDENTITY: source ELF digest has not changed.
- G1_TASK_EXECUTION: all tasks have completed status.
- G2_EVIDENCE_INTEGRITY: completed task's latest raw evidence exists and matches recorded SHA-256.
- G3_CLAIM_PROVENANCE: VERIFIED-labelled claims point to a completed task and include function symbol/address and rationale.
- G4_SEMANTIC_REVIEW: always REVIEW_REQUIRED. Code paths, observed frames, missing calls and runtime claims must be independently interpreted.

A run with G0–G3 PASS can be marked ready_for_review. This means nothing about its gameplay compatibility, completeness or actual server response.

## MCP boundary

The lightweight MCP adapter accepts stdio JSON-RPC calls: initialize, ping, tools/list and tools/call. It operates on the same SQLite state directory as the CLI. It is an adapter for agent task orchestration; it does not proxy the full REA MCP tool catalog.

For a multi-minute Ghidra cold start, use CLI execute/resume in the terminal, or increase the MCP client's tool timeout. The MCP execute tool performs **one** step per call to limit blocking and persists its result before returning.

## Storage / disclosure

The binary, raw REA output, SHA digests and working state never leave local WSL2 unless explicitly copied elsewhere. The repo ignores *.apk, *.so, packet captures, .re_harness/ and .re_harness_mvp/. No runtime tests were executed as part of this delivery.

## Next increment

Persistent REA MCP session transport; semantic evidence extractor supporting exact symbol/address resolution; bounded call-graph exploration; claim review checklist per task; stronger concurrent agent leasing and approval boundaries.
