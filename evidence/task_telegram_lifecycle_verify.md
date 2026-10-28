# Evidence: Telegram Lifecycle Confirmation & Guard Mechanism Verification

- **Task Key**: `telegram-lifecycle-verify`
- **Project**: `5272cb1126334490`
- **Kind**: `TEST`
- **Resource Class**: `LIGHT`
- **Date**: 2026-10-27

## Scope & Implementation Inspected
1. `re_harness/telegram_control.py`:
   - Two-phase proposal & claim lifecycle (`propose()`, `claim()`, `pending()`, `audit_log()`).
   - Transactional nonce validation (`secrets.token_hex(6)`), 600-second TTL enforcement, owner authorization matching.
   - At-most-once decision state transition (`PENDING` -> `APPROVE` / `REJECT` / `EXPIRED`).
2. `re_harness/telegram_bridge.py`:
   - Interactive Telegram command handling for `/newgoal` and `/project`.
   - Callback button handling with nonce verification and lock acquisition.
   - Guarded execution preventing switch/goal creation when watchdog lock is held.
   - Safe launcher integration (`start_watchdog_for_new_goal`).

## Test Execution Evidence
Command:
```bash
python3 -m unittest tests/test_telegram_v071.py tests/test_telegram_v07.py
```

Result:
```
Ran 37 tests in 6.622s
OK (skipped=1)
```

Key Invariants Verified:
- `ControllerTests.test_newgoal_requires_confirmation_and_is_idempotent`: PASS
- `ControllerTests.test_reject_and_owner_nonce_security`: PASS
- `ControllerTests.test_expired_confirmation_rejected`: PASS
- `ControllerTests.test_watcher_lock_blocks_switch_and_prevents_orphan`: PASS
- `ControllerTests.test_controller_unlocked_switches_and_separates_sessions`: PASS
- `ControllerTests.test_fixed_launcher_no_shell_injection`: PASS
- `ControllerTests.test_global_bot_lock_separates_tokens`: PASS
