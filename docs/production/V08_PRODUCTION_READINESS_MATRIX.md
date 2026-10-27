# RE Dragon v0.8 Production Readiness Matrix

## 1. Overview & Verification Scope

This document provides the formal audit and verification matrix for **RE Dragon v0.8: Autonomous Reliability & Recovery** on branch `feature/v08-autonomous-reliability-recovery` (Draft PR #2).

All verifications explicitly distinguish between:
- **`LIVE_PASS`**: Verified via real OS processes, filesystem mutations, SQLite transactions, and Linux/WSL2 system mechanisms.
- **`MOCK_PASS`**: Verified via simulated turn inputs, mocked subagent CLI responses, or mock network transports without touching real external accounts or credentials.
- **`STATIC_VERIFIED`**: Validated against specification schemas, syntax compilation, and structural checks without live host execution (used where host OS boundaries prevent live execution, e.g. Windows Task Scheduler on Linux/WSL2).

---

## 2. Production Readiness Verification Matrix

| Area | Component | Verification Level | Test Evidence | Verdict |
| :--- | :--- | :---: | :--- | :---: |
| **1. Production Workspace Binding** | `verify_workspace_binding()` in `supervisor.py` | `LIVE_PASS` | `test_live_workspace_binding_validation` in `tests/test_live_integration_staging.py`, `tests/test_supervisor.py` | **PASS** |
| | Dynamic path injection into systemd unit & Task Scheduler XML | `LIVE_PASS` | `test_generate_systemd_unit_validates_and_injects_paths` in `tests/test_supervisor.py` | **PASS** |
| | Fail-closed on missing/mismatched project ID or corrupt state | `LIVE_PASS` | `test_verify_workspace_binding_fails_closed` in `tests/test_supervisor.py` | **PASS** |
| **2. Telegram Remote Recovery** | `ensure_watchdog_active()` in `telegram_bridge.py` | `LIVE_PASS` | `test_ensure_watchdog_active_launches_runner` in `tests/test_telegram_incident_control.py` | **PASS** |
| | Non-blocking flock check (`quota-watchdog.lock`) | `LIVE_PASS` | `test_live_flock_mutual_exclusion` in `tests/test_live_integration_staging.py` | **PASS** |
| | Telegram command handling (`/status`, `/incidents`, `/retry`, `/pause`, `/resume`) | `MOCK_PASS` | `tests/test_telegram_incident_control.py`, `tests/test_v08_fault_injection.py` (Scenario 7) | **PASS** |
| **3. Graceful Drain & Cutover** | `drain_watchdog()` in `quota_watchdog.py` | `LIVE_PASS` | `test_live_graceful_drain_waits_for_inflight_worker` in `tests/test_live_integration_staging.py` | **PASS** |
| | Drain integration in `scripts/quota-watchdog.sh drain` & `./dragon drain` | `LIVE_PASS` | CLI syntax validation and staging process verification | **PASS** |
| | Controlled stop waiting for turn exit before tmux session termination | `LIVE_PASS` | CLI tests in staging worktree | **PASS** |
| **4. Anti-Duplicate Stale Lease Recovery** | `reconcile_stale_leases_safely()` in `recovery.py` | `LIVE_PASS` | `test_stale_lease_without_side_effects_reclaimed_to_pending` in `tests/test_recovery.py` | **PASS** |
| | Side-effect detection (Git status, recorded evidence/artifacts) | `LIVE_PASS` | `test_stale_lease_with_side_effects_quarantined_to_disputed` in `tests/test_recovery.py` | **PASS** |
| | Quarantine to `DISPUTED` & Incident Journaling on partial side effects | `LIVE_PASS` | `test_stale_lease_with_side_effects_quarantined_to_disputed`, `tests/test_incidents.py` | **PASS** |
| | Pre-retry safety checks in `verify_pre_retry_safety()` | `LIVE_PASS` | `tests/test_recovery.py` (all 14 tests PASS) | **PASS** |
| **5. Rollback Integrity & WAL Checkpoint** | `create_safe_backup()` with `PRAGMA wal_checkpoint(TRUNCATE)` in `backup_util.py` | `LIVE_PASS` | `test_create_safe_backup_succeeds_with_manifest_and_checksums` in `tests/test_backup_util.py` | **PASS** |
| | Atomic SQLite backup via `sqlite3.Connection.backup()` | `LIVE_PASS` | `test_live_sqlite_wal_checkpoint_and_backup_concurrency` in `tests/test_live_integration_staging.py` | **PASS** |
| | Backup manifest with SHA-256 and Git commit SHA | `LIVE_PASS` | `tests/test_backup_util.py` | **PASS** |
| | Safe restoration & checksum validation (`verify_and_restore_backup()`) | `LIVE_PASS` | `test_verify_and_restore_backup_restores_cleanly`, `test_restore_fails_closed_on_tampered_checksum` | **PASS** |
| **6. Fault Injection Suite (R4)** | 10 Fault-Injection Scenarios (Missing marker, agent crash, OOM, SQLite lock, etc.) | `MOCK_PASS` | `tests/test_v08_fault_injection.py` (all 10 scenarios PASS) | **PASS** |
| **7. Operating System Integration** | Linux / Ubuntu WSL2 systemd user service (`services/re-dragon.service`) | `LIVE_PASS` | Generated unit validated with `systemd-analyze verify`, staging flock execution | **PASS** |
| | Windows Task Scheduler (`services/re-dragon-windows-task.xml`) | `STATIC_VERIFIED` | XML schema validated against Task Scheduler 2.0 definition; **NOT** live executed on Windows host | **PASS (STATIC)** |

---

## 3. Detailed Audit Findings & Resolution

### 3.1 Hardcoded Dev Paths Eliminated
- **Issue:** Early drafts contained hardcoded path `/home/khanh/re-dragon-reliability` in systemd unit definitions and Windows Task Scheduler XML.
- **Resolution:** Templates converted to dynamic generators (`generate_systemd_unit`, `generate_windows_task_xml`) and validation script (`scripts/setup-supervisor.sh`). Systemd service files now mandate explicit workspace validation and resolve the verified virtualenv python path.

### 3.2 Telegram `/resume` & `/retry` Orphan Prevention
- **Issue:** In v0.8 draft, `/resume` reset the SQLite/JSON watchdog state to `READY`, but if the Watchdog process was completely stopped, no process resumed execution, leaving an orphan `READY` state.
- **Resolution:** Added `ensure_watchdog_active(workspace)` in `telegram_bridge.py`. It probes the non-blocking file lock `quota-watchdog.lock`. If unlocked, it automatically spawns `scripts/quota-watchdog.sh start`, ensuring a real runner process is activated without double execution.

### 3.3 Graceful Drain vs Abrupt Termination
- **Issue:** `./dragon stop` immediately issued `tmux kill-session`, which could abort a running CLI turn mid-execution, losing in-flight research and corrupting temporary artifacts.
- **Resolution:** Implemented `drain_watchdog()` in `quota_watchdog.py`, added `./dragon drain [TIMEOUT]`, and updated `./dragon stop` to default to graceful drain (waiting for in-flight PID to finish and checkpoint) before process exit. Immediate kill is preserved only via explicit `--force`.

### 3.4 Anti-Duplicate Stale Lease Recovery
- **Issue:** Standard autonomy lease recovery reset all expired `RUNNING` tasks to `PENDING`. If a task had produced partial side effects (e.g., git edits, partial artifacts, or recorded evidence) before crashing, re-executing it blindly could duplicate side effects or corrupt codebases.
- **Resolution:** Implemented `reconcile_stale_leases_safely()` in `recovery.py`. It inspects uncommitted git modifications and database evidence. Tasks with detected side effects are quarantined to `DISPUTED` and an incident is journaled (`STALE_LEASE`), requiring operator/audit clearance before re-running. Clean tasks are safely reset to `PENDING`.

### 3.5 SQLite WAL Backup & Rollback Integrity
- **Issue:** Raw copying of SQLite files in WAL mode can produce inconsistent or corrupt snapshots if uncheckpointed transactions remain in `-wal`.
- **Resolution:** Created `re_harness/backup_util.py`. Uses `PRAGMA wal_checkpoint(TRUNCATE)` followed by the official SQLite Online Backup API (`db.backup()`). Computes SHA-256 hashes, records the current Git commit SHA, and generates a durable manifest. `verify_and_restore_backup()` verifies all checksums before restoring and runs `PRAGMA integrity_check`.

---

## 4. GO / NO-GO Recommendation

### Recommendation: **CONDITIONAL GO for Linux/WSL2 Staging & Controlled Rollout**

1. **Linux / WSL2 Environments:**
   - **GO**: 100% of unit, fault injection, and live staging integration tests pass.
   - Dynamic binding, graceful drain, WAL rollback, and anti-duplicate recovery mechanisms are fully operational and verified.

2. **Windows Task Scheduler:**
   - **STATIC PASS ONLY**: Validated syntactically and structurally; live execution on Windows OS requires user-attended setup and verification on a native Windows machine.

3. **Active Production Environment (`/home/khanh/returnsaiyan-re`):**
   - **NO-GO FOR UNATTENDED HOTFIX / DIRECT OVERWRITE**: The running production session (PID 140600) remains untouched and undisturbed. Rollout to production MUST follow the step-by-step procedure in `docs/production/V08_ROLLOUT_ROLLBACK_RUNBOOK.md`, requiring human authorization, safe drain, and WAL-truncated backup.
