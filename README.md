## v0.6.6 — Telegram durable crash logs

The bot is launched via `scripts/telegram-supervised.sh`. Its output is
written with file mode 0600 to `.re_harness/telegram.log` so startup
exceptions remain accessible even after the tmux server disappears.
Check via `./dragon telegram logs` (token-shaped secrets redacted for
display), then use `./dragon telegram doctor` for read-only Bot API
and webhook diagnostics. Running `./dragon telegram start` launches
only the Telegram bridge; it does **not** start another Agent or
reset existing Harness checkpoints.

A tmux session being present only establishes that the process has
not yet exited: Bot API connectivity requires doctor or successful
Telegram command delivery. If no tmux server is running, do not assume
that Telegram credentials are invalid: inspect the persistent log.

## v0.6.5 — Telegram self-diagnostic

If the Telegram tmux session is RUNNING but /start or /status does not reply,
run `./dragon telegram doctor`. This read-only command checks getMe
(username and connectivity) and getWebhookInfo (webhook conflict) using the
Bot Token stored locally, without displaying the token or consuming updates.
Use `tmux capture-pane -pt re-dragon-telegram -S -80` to inspect hidden
runtime errors (redact tokens before sharing output). Telegram Desktop
can use a separate proxy from WSL2; working Desktop messaging does not
prove WSL2 has HTTPS access to `api.telegram.org`.

The command does not delete webhook state, clear messages, reset auth,
run a second getUpdates consumer or touch the main Agent checkpoint.

## v0.6.4 — live status & Telegram ChatOps (optional)

- `./dragon status` now reports AGENT_RUNNING, PID, elapsed seconds
  and supervisor heartbeat while the tracked CLI process is alive.
  Heartbeat verifies that the supervisor is alive, **not** that the agent
  is making progress.
- Telegram delivery uses the established open-source python-telegram-bot library,
  long polling, private chat allowlist, and local SQLite queue.
- One-time setup:
  ```bash
  python3 -m venv .venv-telegram
  .venv-telegram/bin/pip install -e '.[telegram]'
  ./dragon telegram setup
  ./dragon telegram start
  ```
- On later reboots, `./dragon start` brings up the Telegram bot automatically
  if the credential file and Python environment exist.
- Commands in the private DM: `/status`, `/tasks`, `/task <text>`.
  Sending a task queues it; the next headless turn triages it. Telegram
  does not run shell commands, grant permissions or bypass quota.
- Local credentials: `~/.config/re-dragon/telegram.json` (chmod 600).
  Never commit/send Telegram bot tokens or use a shared group for control.
- Before pulling this version while a headless turn is active, finish the
  turn and stop the watchdog, then update/restart to avoid concurrent code versions.
  A real Telegram delivery/polling test requires an actual bot token and user ID.

## One-command unattended ReturnSaiyan mode (v0.6.3)

After updating your checkout, use only:

```bash
./dragon start       # create/reuse Unified Heroes production goal, start tmux + headless agy
./dragon status      # inspect persisted state
./dragon logs        # short supervisor status log
./dragon stop        # preserve progress and stop worker
./dragon resume      # explicit human rearm ONLY after resolving a blocker
```

The **first** `./dragon start` safely creates the agreed ReturnSaiyan
Unified Heroes project if none exists (e.g. when only two ACCEPTED pilot
projects are present), then starts a **new dedicated Antigravity headless
conversation**, not the unrelated latest pilot in the CLI cache. The CLI
conversation ID is saved from its first successful JSON result. Subsequent
starts reuse both pinned IDs without manual copying. The original APK/SO
remain untouched; production task planning is delegated to Harness.

Only the exact tutorial placeholders `PROJECT_ID`/`CONVERSATION_ID` are
cleared automatically. Real auth, permission, ambiguous project or approval
failures require explicit operator resolution; `./dragon start` will not
silently change project or resume after such a stop.

Auto-restart still requires Windows/WSL to remain running; test one real CLI
turn and quota refresh before claiming unattended operation.

# RE Dragon — Autonomous Agent-Driven Reverse Engineering

v0.6 adds adaptive CPU/RAM and single-heavy-Ghidra task scheduling to the v0.5 goal-level controller for Codex and Antigravity. The user provides ONE objective; the active AI Agent plans, executes, reviews and re-plans through MCP without requesting a new P-stage prompt each time.

## Automatic restart after Antigravity five-hour quota refresh

The local WSL2 Quota Watchdog can run the same project across fresh
headless CLI turns without manual prompts. It respects official quota errors,
waits for the provider's reset countdown and then resumes the pinned
conversation plus RE Dragon Harness SQLite checkpoints.

After one-time Antigravity authentication and scoped permissions setup
(default auto sandbox mode; never use --dangerously-skip-permissions):
  bash scripts/quota-watchdog.sh start [CONVERSATION_ID] [PROJECT_ID]

To inspect or stop:
  bash scripts/quota-watchdog.sh status
  bash scripts/quota-watchdog.sh logs
  bash scripts/quota-watchdog.sh stop

Documentation: [docs/QUOTA_WATCHDOG.md](docs/QUOTA_WATCHDOG.md).
This does NOT defeat quota limits, bypass approvals or run with Windows asleep.
The watcher pins one project and one conversation, stops on ambiguous projects,
uses bounded transport retries and checks SQLite before accepting COMPLETE.

## Start in the Agent chat

> Read AGENTS.md. Resume the ReturnSaiyan research. Use harness_auto_projects to find existing goals, then harness_auto_start if needed, write an evidence-based task DAG, and repeatedly use harness_auto_tick until a real blocker, session budget or final review. Use REA MCP and local tools to do the assigned work, harness_auto_submit to checkpoint, and a genuinely distinct reviewer Agent for harness_auto_review. Replan automatically on contradictions and commit safe code to re_dragon. Do not ask me for P5/P6 prompts or to run Python manually.

Both REA MCP and the RE Dragon Harness MCP must be connected once to the Agent host.

## Pilot gate before bulk execution

The source-controlled smoke protocol is in
[docs/LIVE_PILOT.md](docs/LIVE_PILOT.md). A deliberately defective local
fixture and the [re-dragon-reviewer subagent](.agents/agents/re-dragon-reviewer.md)
test whether a real reviewer spots a bug, rejects it, allows repair, and
unlocks a dependent task without extra human prompts. Harness event traces
can be evaluated with harness_pilot_evaluate, but actual Antigravity
subagent execution must be verified in /agents.

## v0.6 adaptive task admission and decomposition

The orchestrator (not the user) decides what to execute next:
resource_class estimates per task; at most one GHIDRA_HEAVY task globally;
CPU/memory admission; bounded project worker concurrency; dynamic concurrency
after review/timeout; bounded automatic target-list bisection when Ghidra
times out; and independently reviewed child tasks before final synthesis.

See [v0.6 scheduler and its limits](docs/V06_SCHEDULER.md).
There is still no always-on LLM and no OS-level enforcement outside
cooperating Harness sessions.

## v0.5 new features

- Goal decomposition as an Agent-authored dependency graph.
- Continuous MCP task scheduling within an active Agent session.
- Durable evidence/artifact/result checkpoints, claims and bounded retries.
- Explicit separate reviewer gating; no self-approved findings.
- Contradiction-triggered audit and invalidation of stale dependent approvals.
- Resume across sessions, session limits, final review and report state.

Limitations: the Python package implements durable MCP control, not an LLM or an always-on background Agent. It cannot run after Antigravity/Codex shuts down, and a real separate reviewer must be provided by the host. A5 REA receipt authenticity and semantic correctness remain independent review matters.

Full contract: docs/V05_AUTONOMY.md. Agent run instructions: AGENTS.md. Legacy v0.2–v0.4 APIs remain available for existing investigations. Store original game binaries and private evidence locally only.
