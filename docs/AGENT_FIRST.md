# Agent-first RE Dragon — v0.4 playbook

The **Codex/Antigravity Agent**, not the RE Dragon Python package, performs
investigative reasoning and calls REA MCP tools.

## User request example

> Examine ReturnSaiyan ARM64 network initialization from socket receive through
> decryption and protocol dispatcher. Decide a bounded plan, call REA MCP and
> trace code. Attach Evidence IDs and address/function identity to each claim.
> Stop if the provider cannot establish a fact, and report the gap as UNKNOWN.
> Keep state so the next Agent session can continue.

## What the Agent does

1. Discover: harness_context, harness_investigation_status.
2. Create goal: harness_begin_investigation with selected local ELF.
3. Author milestones with acceptance criteria: harness_set_investigation_plan.
4. Select and call REA MCP tools from its own connected MCP catalog. For example,
   open_binary → search_procedures → analyze_function → inspect_analysis_view,
   but use the **actual advertised input schema** from the active REA version.
5. Record truthful REA receipts via harness_record_rea_observation with the
   real Evidence ID and caveats. If no Evidence ID was returned, omit it.
6. Mark milestones done only when linked observations exist; leave blocked
   analysis steps visible.
7. Record VERIFIED/INFERRED/UNKNOWN findings with explicit observation links.
8. Review mechanical gates and write an Agent report. The Agent explains
   limitations, unavailable facets and the next scientific question.
9. Optionally close. If the session ends, query investigation_status in the
   next session and continue from remaining milestones.

REA MCP owns the native analysis session. Harness MCP owns the durable
research ledger. The two servers are separate; there is no in-process REA
client nor bridge that runs another decompiler.

## One-time MCP setup

Connect both REA and the RE Dragon harness server to each Agent.

For Codex running in WSL2, merge this TOML entry into Codex configuration:

~~~toml
[mcp_servers.re_dragon_harness]
command = "bash"
args = ["-lc", "cd \"$HOME/returnsaiyan-re\" && exec python3 -m re_harness.mcp"]
startup_timeout_sec = 30
tool_timeout_sec = 1800
~~~

For Antigravity on Windows, merge this JSON entry into its MCP configuration,
keeping other servers intact and using the correct distro and checkout path:

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

The host starts the service automatically. These are **one-time setup snippets**,
not commands to run with every investigation. REA's own connection is configured
independently via its official setup.

## Two sessions, one workflow

Session A: create plan, trace login/handshake functions via REA MCP, store
receipts and conclusions. Session B: read investigation_status, inspect
original REA data or reconfirm any stale Evidence IDs before carrying on.
SQLite checkpoints persist, but **REA retained session Evidence IDs may not
survive reconnecting the REA server**. Store an exported evidence bundle if
long-term verification is needed; exported bundle provenance must be verified
separately.

## Reliability and ethical boundary

The investigation is not an always-on background Agent. RE Dragon cannot
continue reasoning after the host AI Agent stops. The verification ledger has
two explicit non-PASS gates: A5 external receipt authenticity UNVERIFIED and
A6 semantics REVIEW_REQUIRED. Ghidra pseudocode remains a static approximation,
not direct proof of protocol interoperability or game-server state.
