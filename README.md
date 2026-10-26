# re_dragon — Reverse Engineering Agent Harness

MVP v0.2.0 for evidence-first Android native reverse engineering. The system runs locally on WSL2 with Python, SQLite, **REA CLI** and Ghidra. Codex and Antigravity can operate the same durable tasks through its CLI or the optional **harness MCP server**.

**Source code lives in this repository. APK, ELF/SO binaries, network captures, login data and full evidence stay on your machine.**

## Features in MVP

- JSON workflow/task planning with explicit dependencies, SHA-256 pinned binary identity
- Real read-only REA/Ghidra operations: inspect, procedure search, function dossier, pseudocode
- SQLite persistent state and a local per-run lock for two agents accessing one checkout
- Sequential task execution with configurable retry, per-attempt evidence JSON/stderr, checkpoint/resume
- Add function/address investigations to an existing run
- Claim ledger: VERIFIED / INFERRED / UNKNOWN classifications, task references and rationale
- Deterministic gates G0–G3 for provenance/integrity, G4 always requires semantic review
- Markdown reports and local MCP tools for Codex / Antigravity

The MCP server is **agent-facing control for this harness**; native analysis is delegated to the actual local REA CLI. It is not yet a persistent direct REA-MCP session or an autonomous symbol-selection planner.

## Requirements

- Ubuntu WSL2 (or Linux), Python 3.10+ (standard library sufficient)
- REA CLI (rea-agents) configured with Ghidra 12.1.x native provider
- Local binary, for example libaos_jogo.so in this repository root
- Keep the binaries ignored by Git

Full prerequisite docs: https://github.com/morluto/rea/blob/main/docs/native-investigation.md

## First run

~~~bash
cd ~/returnsaiyan-re
git pull --ff-only origin main

python3 -m re_harness doctor
python3 -m re_harness plan --binary ./libaos_jogo.so
~~~

Copy the generated run_id and execute the first discovery task:

~~~bash
python3 -m re_harness execute --run-id RUN_ID --max-steps 1
python3 -m re_harness status --run-id RUN_ID
~~~

Or execute the full workflow in one command:

~~~bash
python3 -m re_harness run --binary ./libaos_jogo.so
~~~

If a Ghidra operation fails or you interrupt a long operation, continue without repeating completed tasks:

~~~bash
python3 -m re_harness resume --run-id RUN_ID --timeout 1800 --retries 1
~~~

The workflow is stored at workflows/network-handshake.json. It is read-only and searches for CProtocolManager, Conexao, CGameNetwork, threadRecepcao, gerarChaveSecreta and registrarTratadores.

## Deep dive by discovered function

Take the **exact function name or address** from REA evidence, then:

~~~bash
python3 -m re_harness add-function --run-id RUN_ID --procedure 'EXACT_SYMBOL_OR_ADDRESS'
python3 -m re_harness resume --run-id RUN_ID
~~~

Record hypotheses, linking VERIFIED claims to a completed task, symbol/address and explanation:

~~~bash
python3 -m re_harness claim --run-id RUN_ID \
  --assessment INFERRED \
  --task-key connection \
  --symbol 'aos::Conexao' \
  --text 'Candidate receive path related to handshake' \
  --rationale 'Name-based candidate; requires pseudocode review'

python3 -m re_harness validate --run-id RUN_ID
python3 -m re_harness report --run-id RUN_ID
~~~

The validation result is **ready_for_review**, not automatic proof of semantic correctness. Do not mark claims VERIFIED without examining the actual code and its limitations.

## Artifact directory

Nothing under .re_harness_mvp/ is pushed to GitHub.

~~~text
.re_harness_mvp/
  state.sqlite3
  locks/
  evidence/<run-id>/<step>_attempt_<n>.json
  evidence/<run-id>/<step>_attempt_<n>.stderr.txt
  reports/<run-id>.md
~~~

## Connect Codex and Antigravity

Start the harness MCP server **from the repository root in WSL2**:

~~~bash
python3 -m re_harness.mcp
~~~

For Codex, register a stdio MCP server with command bash and arguments:

~~~text
-lc
cd "$HOME/returnsaiyan-re" && exec python3 -m re_harness.mcp
~~~

For Antigravity **running on Windows**, add a stdio MCP entry in its own MCP configuration (do not replace other servers). Example for the Ubuntu-24.04 distro:

~~~json
{
  "mcpServers": {
    "re_dragon_harness": {
      "command": "wsl.exe",
      "args": [
        "-d", "Ubuntu-24.04", "--exec", "bash", "-lc",
        "cd \"$HOME/returnsaiyan-re\" && exec python3 -m re_harness.mcp"
      ]
    }
  }
}
~~~

Select the actual WSL distro name shown by wsl -l -v. Restart the agent after changing MCP config. Keep the independent REA MCP integration if you have already configured it: this harness server adds planning/state tools.

Available MCP tools: harness_create_plan, harness_execute_step, harness_list_runs, harness_get_run, harness_queue_function, harness_add_claim, harness_validate, harness_render_report. Harness_execute_step runs one local REA command synchronously; increase the MCP client's tool timeout for slow Ghidra operations, or invoke long commands using the terminal CLI.

## Scope and limitations

- Static ELF analysis only in the shipped workflow. No automated game login, active server probing, binary patching, runtime hooks, or proprietary server emulation.
- Execution gate = REA exit code zero. Full raw evidence is retained, but CLI exit success is **not** proof that function discovery is complete.
- Only provenance and filesystem integrity are checked automatically; G4 semantic verification always needs a reviewer.
- MCP uses a small local stdio JSON-RPC implementation suitable for basic tool calls. It is not a general production MCP framework.
- This release was written and committed without executing a test suite, per requested delivery priority; runtime interoperability with the local REA/Ghidra installation remains to be confirmed.

See docs/MVP.md for implementation boundaries. The original P0 remains at prototype/re_harness.py for reference.
