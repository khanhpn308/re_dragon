# RE Dragon — Antigravity Quota Watchdog (WSL2)

## What it does

The watchdog is a local process that runs Antigravity CLI in officially
supported headless mode. On a legitimate RESOURCE_EXHAUSTED / individual quota
error, it keeps project checkpoints, sleeps until the provider's own reported
"Resets in ..." countdown plus 60 seconds, then resumes the same conversation.
When no reset countdown is available, it checks conservatively every
15 minutes. It never bypasses provider limits or switches accounts.

This avoids manually waiting for the usual five-hour window while the Windows
PC and its WSL2 environment stay on. Weekly quota or subscription limits may
take longer.

## Prerequisites and first use

- Google Antigravity CLI supports headless: agy -p PROMPT --output-format json.
- Authenticate once interactively with agy. Configure permissions only for
  intended project tools and allowed local workspace files. DO NOT use
  dangerously-skip-permissions for unattended jobs.
- Watchdog defaults to CLI auto mode, which uses the official terminal sandbox
  and evaluates safe commands on supported hosts. Unsupported environments
  fall back to default permissions; denied tools must stop the watcher.
- A headless tool permission can be soft-denied while CLI exit code is zero.
  The watchdog treats such stderr diagnostics as NEEDS_USER, not SUCCESS.
- Install tmux in Ubuntu WSL2 if absent: sudo apt install tmux.
- Ensure python3, tmux, agy and both MCP servers are working.
- Pull the repository updates into the same WSL2 workspace.
- Close your existing interactive Agent session before starting the watchdog.
  Running it simultaneously could lead to duplicate native tool operations.
- Optional: copy the conversation ID from the existing agy session to resume
  exactly that thread. Without it, agy --continue selects the latest
  conversation for the same absolute workspace path.

Start once from the repository:
  bash scripts/quota-watchdog.sh start CONVERSATION_ID PROJECT_ID

Or without a conversation ID:
  bash scripts/quota-watchdog.sh start

Observe:
  bash scripts/quota-watchdog.sh status
  bash scripts/quota-watchdog.sh logs

Stop deliberately:
  bash scripts/quota-watchdog.sh stop

The supervisor uses .re_harness_mvp/state.sqlite3 by default (override
RE_DRAGON_HARNESS_STATE_DIR). It binds exactly one active project or needs an
explicit PROJECT_ID. It binds a conversation supplied by the operator or
from the official Antigravity CLI workspace conversation cache. Unknown or
ambiguous bindings stop NEEDS_USER; existing progress is never overwritten.

A model COMPLETE marker is NOT sufficient: the watcher verifies actual
ACCEPTED status and VERIFIED tasks in the local Harness SQLite checkpoint.
STOPPED, BLOCKED and awaiting-final-review goals stop for user intervention.

Quota waits respect the provider countdown plus 60 seconds; missing
countdowns mean one permitted recheck per 15 minutes, not an assumed five
hour reset. Separate transient network retry budget: at most 3 attempts
with bounded backoff. Permission/authentication and ambiguous tool timeouts
stop immediately, without switching model/account or skipping approval.
Only short status metadata is logged.

After resolving a permissions or authentication blocker:
  bash scripts/quota-watchdog.sh reset
  bash scripts/quota-watchdog.sh start

Use 'once' for a bounded first trial:
  bash scripts/quota-watchdog.sh once

## State machine and safety

- READY / CONTINUE / YIELD: run another bounded headless turn.
- WAIT_RETRY: bounded transport retries, not quota retries.
- WAIT: back off temporarily before retrying.
- WAIT_QUOTA: no requests until the provider-reported reset countdown or
  a conservative recheck if unknown. The CLI may sometimes cache previous
  quota failures when resuming old conversations.
- COMPLETE: all actual goal acceptance gates accepted; stop.
- BLOCKED / NEEDS_USER / ERROR: stop, no auto-approval or destructive retry.

On every successful headless turn, the Agent must produce the standalone
RE_DRAGON_RUN_STATE JSON marker described in docs/QUOTA_WATCHDOG_TURN.md.
Absent or malformed marker fails closed.

The watcher does NOT impersonate a reviewer. Subagent independence and MCP
tool access remain required. Quota refresh alone does not grant permissions.

State and logs live only in the Git-ignored .re_harness directory:
  quota-watchdog.json (atomic checkpoint)
  quota-watchdog.log (short status-only log)
  quota-watchdog.lock (prevents duplicate watchdog instances)

An exact conversation ID is reused after the first successful turn. The
new CLI process restores conversation history and RE Dragon SQLite state;
this is not resuming a suspended process in memory.

## Power and runtime caveats

To run without attendance, Windows must remain awake (disable sleep and
hibernate). Locking the screen is fine. A Windows restart, 'wsl --shutdown',
expired Google authentication, required permission prompt, OS failure or loss
of network can still interrupt progress.

The watchdog uses a separate tmux session. The user can close the launching
terminal while WSL keeps running, but should verify this on their own PC.

Each headless turn has a 30-minute agy print timeout. Long native work must
remain within its RE Dragon task lease and be checkpointed. The watchdog will
not continue blindly after a process timeout that may leave child tasks
running; that requires checking actual host process state.

## Provider documentation

- https://www.antigravity.google/docs/cli/headless/
- https://www.antigravity.google/docs/cli/commands/resume/
- https://www.antigravity.google/docs/cli/commands/usage/
- https://www.antigravity.google/docs/plans/

## Acceptance test

Run tests/test_quota_watchdog.py in CI using mocked agy replies. Then run
a single harmless local headless turn on your authenticated WSL2. Simulate
exhausted quota and verify next_at is in the future; after an actual provider
refresh, confirm project_id and remaining tasks are loaded from Harness.
Only this live smoke test can establish that your connected Antigravity
account, model, MCP permissions, reviewer and WSL2 environment resume
without intervention.
