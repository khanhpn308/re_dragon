# RE Dragon — Reverse Engineering Agent Harness

**Stable-engine source v0.3.0**. Python + SQLite orchestration for static ELF analysis using REA CLI and Ghidra on WSL2. Shared work via Codex and Antigravity. The engine has been authored but has NOT been runtime-tested on your workstation.

## Included

- Workflow JSON, persistent planning and pinned binary SHA-256.
- SQLite task leases, global native-engine slots, multi-worker coordination.
- Heartbeats, native child PID/start-time awareness, guarded stale recovery.
- Per-attempt stdout/stderr evidence, SHA-256, JSON error validation, bounded retry/backoff.
- Bounded symbol/address candidate indexing and call-graph expansion.
- Existing G0–G4 validation gates and claim records; graph edges remain only static candidates.
- Updated CLI and local MCP server, documentation, old Prototype P0 retained.

## Requirements

WSL2/Linux, Python 3.10+, REA CLI with the Ghidra native provider configured. Store the ELF and APK locally; .gitignore excludes them.

## Installation and workflow

~~~bash
cd ~/returnsaiyan-re
git pull --ff-only origin main
python3 -m re_harness doctor

# Full investigation, default native capacity=1
python3 -m re_harness run --binary ./libaos_jogo.so --timeout 1800 --retries 2 --capacity 1

# Or plan, obtain RUN_ID, then run limited steps
python3 -m re_harness plan --binary ./libaos_jogo.so
python3 -m re_harness worker --run-id RUN_ID --max-steps 1
python3 -m re_harness status --run-id RUN_ID
python3 -m re_harness resume --run-id RUN_ID --max-steps 10
~~~

Two workers may share the same SQLite state directory and coordinate through leases. Keep capacity consistent between workers; capacity=1 is the conservative default for large Ghidra binaries.

## Bounded static call graph

~~~bash
python3 -m re_harness graph-start --run-id RUN_ID \
  --root 'EXACT_SYMBOL_OR_ADDRESS' --depth 2 --max-nodes 30
python3 -m re_harness resume --run-id RUN_ID --max-steps 30
python3 -m re_harness graph --run-id RUN_ID
python3 -m re_harness evidence --run-id RUN_ID --limit 100
~~~

The graph only adds nodes from identifiable static call candidates returned in raw REA function dossiers. Absence of indexed edges is UNKNOWN rather than proof of no runtime calls.

## Recovery

~~~bash
python3 -m re_harness recover --run-id RUN_ID
python3 -m re_harness resume --run-id RUN_ID --retries 2
python3 -m re_harness validate --run-id RUN_ID
python3 -m re_harness report --run-id RUN_ID
~~~

Recovery refuses to steal an expired lease if the original native process is still alive. The runner terminates only its own child process group on timeout. Exhausted retries require operator attention.

## MCP

Use the existing local harness MCP server: python3 -m re_harness.mcp. It adds worker, graph, symbol index and recovery tools. It is separate from REA's full MCP server.

For Antigravity on Windows, add this server entry to its existing MCP JSON, adjusting the distro name from wsl -l -v:

~~~json
{
  "mcpServers": {
    "re_dragon_harness": {
      "command": "wsl.exe",
      "args": ["-d", "Ubuntu-24.04", "--exec", "bash", "-lc",
        "cd \"$HOME/returnsaiyan-re\" && exec python3 -m re_harness.mcp"]
    }
  }
}
~~~

Do not replace your existing MCP entries. Long Ghidra jobs may exceed client MCP timeouts; use terminal CLI if necessary.

## Data / acceptance

Generated runs, reports and Evidence remain in the Git-ignored .re_harness_mvp/ directory. G0–G3 cover integrity and provenance; G4 semantic interpretation always requires review. There is no automatic game login, server probing, binary patching or proof of protocol compatibility.

Architecture and limits: docs/STABLE.md. Agent protocol: AGENTS.md. Previous MVP architecture: docs/MVP.md.

**No automated/runtime tests were executed for this release, as requested.** The code is delivered, but reliability must not be represented as empirically verified.
