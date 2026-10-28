# Evidence: At-Most-Once Notification Guard Audit

- **Task Key**: `notification-guard-audit`
- **Project**: `5272cb1126334490`
- **Kind**: `AUDIT`
- **Resource Class**: `LIGHT`
- **Date**: 2026-10-27

## Audit Scope
1. Implementation: `re_harness/notification_delivery.py`
   - `claim(token, owner, event_key, *, base=None)`: Durable SQLite atomic insertion in `BEGIN IMMEDIATE` transaction. Uses `INSERT OR IGNORE`. Returns boolean whether row was inserted.
   - `delivered(token, owner, event_key, *, base=None)`: Transitions status from `CLAIMED` to `SENT` with `sent_at` timestamp.
   - `status(token, owner, event_key, *, base=None)`: Queries current status (`CLAIMED`, `SENT`, or `None`).
   - SQLite schema: `delivery(bot TEXT, owner INTEGER, event_key TEXT, status TEXT, claimed_at REAL, sent_at REAL, PRIMARY KEY(bot, owner, event_key))`. WAL journal mode and busy timeout configured.
2. Unit Test Suite: `tests/test_telegram_v071.py:NotificationTests`
   - `test_same_event_sent_once_across_restart_and_worktree`: PASS
   - `test_at_most_once_when_remote_delivery_uncertain`: PASS
   - `test_different_event_and_owner_can_notify`: PASS
   - `test_database_error_fails_closed`: PASS
   - `test_complete_key_ignores_changing_task_counts`: PASS

## Live SQLite Ledger Audit
Inspected primary ledger at `~/.local/state/re-dragon/notification-guard.sqlite3`:
- Table `delivery` verified.
- Row verified: `bot='59020c7b17ef679959c4', owner=6651746022, event_key='5998ee8249b64cf9:COMPLETE', status='SENT', sent_at='2026-10-27 06:13:29'`
- Row verified: `bot='59020c7b17ef679959c4', owner=6651746022, event_key='5272cb1126334490:submitted:1', status='SENT', sent_at='2026-10-27 06:22:30'`
- Confirmed that task submission event for this project was atomically claimed and transitioned to SENT by the active Telegram monitor.
