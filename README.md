# re_dragon — Reverse Engineering Agent Harness

**Prototype P0**: a local, reproducible investigation runner for Android native binaries. The original APK and `.so` files stay on your WSL2 machine and are **not committed to GitHub**.

## Requirements

- WSL2 Ubuntu 24.04 / Python 3.10+ (standard library only)
- `rea` CLI from [morluto/rea](https://github.com/morluto/rea), with Ghidra native provider installed and configured
- A local, extracted ARM64 or ARM32 ELF file (for example `libaos_jogo.so`)

## Quick start

From the repo root in WSL2:

~~~bash
git pull --ff-only origin main
rea doctor --provider ghidra --json
python3 prototype/re_harness.py run --binary ./libaos_jogo.so
~~~

The default investigation performs three **real, read-only** REA CLI operations: binary `inspect`, procedure search for `CProtocolManager`, and procedure search for `Conexao`.

To investigate a specific symbol after you discover its **exact** name/address:

~~~bash
python3 prototype/re_harness.py run --binary ./libaos_jogo.so --query CProtocolManager --function 'EXACT_SYMBOL_OR_ADDRESS'
~~~

To inspect a preserved run or continue after a failure:

~~~bash
python3 prototype/re_harness.py status
python3 prototype/re_harness.py status --run-id RUN_ID
python3 prototype/re_harness.py resume --run-id RUN_ID
python3 prototype/re_harness.py report --run-id RUN_ID
~~~

State is saved under `.re_harness/` and ignored by Git:

- `state.sqlite3`: runs, steps, statuses, command provenance
- `evidence/<run-id>/`: complete REA JSON stdout and stderr for each operation, plus SHA-256 digests
- `reports/<run-id>.md`: machine-generated execution report with evidence paths

Successful REA execution is **not** proof that a proposed protocol interpretation is correct. A human/AI investigator must inspect `normalized_result`, `coverage`, and `limitations` before labeling any claim VERIFIED. The prototype contains no game-server emulator, runtime hooking, or automatic network login.

## Scope

Python + SQLite + REA CLI are deliberately used for the first working slice. Codex and Antigravity can call the same CLI from the WSL2 workspace. Direct persistent REA MCP orchestration, automatic planning, collaborative agent leasing and semantic claim validation are future phases; they are **not** implemented by P0.

GitHub: <https://github.com/khanhpn308/re_dragon>.
