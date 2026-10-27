# RE Dragon v0.7.1 — Telegram Production Readiness Hotfix

## Immediate incident response

When Telegram starts repeating messages:

```bash
cd ~/returnsaiyan-re
./dragon telegram stop
./dragon status
```

This stops only the Telegram polling bridge; it leaves the Watchdog,
agent session and Harness SQLite checkpoints untouched.

## At-most-once notification delivery

Notification claims are transactionally reserved **before** calling Telegram.
The shared, permission-restricted global SQLite ledger is stored at
`~/.local/state/re-dragon/notification-guard.sqlite3`, keyed by
hashed bot token, owner and stable event signature. `COMPLETE` is emitted
at most once per project and bot/owner identity, even across restarts and
worktrees. A global token-scoped flock prevents two polling bridges sharing
the token from running in multiple worktrees.

The tradeoff is deliberate: an ambiguous failed send stays `CLAIMED` and
is not automatically retried. Thus rare notifications can be missed rather
than duplicated. Status can always be queried with `/status` and `/progress`.

## Human confirmation for project lifecycle changes

`/newgoal <goal> | <acceptance>` creates ONLY a pending 10-minute
confirmation with buttons. Nothing changes until the explicitly approved
Telegram callback, verified against the private chat allowlist, owner ID,
nonce and transactionally persisted one-time action ID.

`/project <project_id>` also requires confirmation. Replay or stale
buttons cannot re-execute. If Watchdog owns its process lock or an Agent
process is active, lifecycle mutations are refused, leaving the current
conversation and checkpoint intact. The user can retry after the current
turn ends and Watchdog exits.

After successful approval and local project activation, the bot starts the
existing trusted `scripts/quota-watchdog.sh start` launcher, without
accepting arbitrary shell commands from Telegram. If launch fails,
Telegram reports this separately. Project creation is not rolled back,
and the checkpoint remains persisted for diagnosis.

`/approvals` lists pending lifecycle confirmations and ordinary proposal
records. Human proposal approvals remain auditable decisions, **not**
evidence-gate bypasses nor an independent reviewer verdict.

## Updating

Stop the Telegram bridge before pulling a new version; do not stop
the Watchdog or Agent in the middle of a bounded turn just to update.

```bash
cd ~/returnsaiyan-re
./dragon telegram stop
# once any active Agent turn has completed:
git pull --ff-only origin main
.venv-telegram/bin/pip install -e '.[telegram]'
./dragon telegram start
./dragon telegram status
./dragon telegram logs
```

Check `/status`, `/projects` and `/approvals` without changing production
state, then create a small, reversible pilot goal for end-to-end verification.

## Acceptance boundaries

Offline CI verifies idempotency, lock contention, expiry, owner/nonce
validation, project checkpoint integrity and the fixed launcher.
Real Telegram callback delivery, unattended startup in the user's WSL2,
network interruption and quota-bound recovery still require live smoke
checks. Do not mark Telegram production ready solely on unit tests.
