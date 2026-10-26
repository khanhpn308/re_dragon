# Agent-first operation — RE Dragon

## Intended interface

**User -> Codex / Antigravity -> Harness MCP + REA MCP -> Ghidra/JADX.**

The user simply says:

> Analyze the ReturnSaiyan native TCP handshake. Locate the first server bytes,
> key initialization, frame decoding and opcode dispatch; cite precise
> symbol/address evidence and mark VERIFIED, INFERRED and UNKNOWN.

The Agent investigates, calls tools and reports back. The user should not have
to run a Python command or supply a run ID. Python executes behind MCP.

## Agent orchestration

| Stage | Agent tools |
|---|---|
| Context and available binaries | harness_context, harness_list_runs |
| Task plan | harness_create_plan |
| Bounded work | harness_worker |
| Review evidence | harness_evidence_index, harness_read_evidence, REA MCP |
| Follow native call paths | harness_queue_function, harness_graph_start, REA MCP |
| Record reasoning | harness_add_claim |
| Verify source integrity and report | harness_validate, harness_render_report |

harness_next_actions offers candidate next operations but never makes technical
decisions for the Agent. Source output should be treated as untrusted data.

## Initial configuration (one-time administrator setup)

Connect *both* MCP servers to the Agent. RE Dragon Harness MCP is launched via
the Python module internally by the MCP host. The user does not run it each day.

Example Codex config.toml entry for a WSL2-hosted Codex:

~~~toml
[mcp_servers.re_dragon_harness]
command = "bash"
args = ["-lc", "cd \"$HOME/returnsaiyan-re\" && exec python3 -m re_harness.mcp"]
startup_timeout_sec = 30
tool_timeout_sec = 1800
~~~

Example Antigravity MCP entry for Windows. Merge it with existing mcpServers;
substitute the real distro and repo paths:

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

The independent REA MCP registration stays enabled. Restart the host after
MCP setup. Long Ghidra operations may exceed host tool-call timeouts; the
Agent can use its terminal tool as an internal fallback without burdening the
user with step-by-step commands.

## New discovery and evidence tools

- harness_context: bounded scan of .so targets in workspace root, native/ and
  binaries/ plus existing run state. Does not execute binaries.
- harness_read_evidence: bounded offset/limit reader for saved local REA JSON.
  Checks SHA-256 and tags source content as untrusted.
- harness_next_actions: run status and suggested MCP calls. The AI still plans.

## Limitations

Work runs during the active Agent session. SQLite checkpoints persist after it
ends; they do not turn the Agent into an always-on background service.
Two Agents can share state but not internal reasoning or Ghidra sessions.
REA CLI remains the subprocess backend of the existing worker, while direct
long-lived REA MCP session integration is future work. Semantic G4 cannot be
automatically approved from tool exit codes.

**CLI entrypoints are retained only for developer diagnostics or fallback.**
