# RE Dragon v0.8 — Autonomous Reliability & Recovery Specification

**Document Version:** 1.0.0  
**Status:** Approved Architecture Draft  
**Target Architecture:** RE Dragon Autonomous Multi-Agent Orchestration  
**Applies to:** R1 (Recovery Engine), R2 (Process Supervision), R3 (Telegram Control), R4 (Fault Injection Acceptance)

---

## 1. Executive Summary & Goals

RE Dragon v0.8 provides unattended, fault-tolerant operation for reverse-engineering orchestration. A human operator monitoring via Telegram does not need to sit at the console to resolve transient network drops, missed output markers, SQLite locks, or temporary resource constraints. At the same time, the system adheres strictly to the **Fail-Closed Safety Contract**:
1. Zero automatic bypassing of authentication, tool permissions, or human approvals.
2. Zero unauthorized project creation or silent project switching.
3. Zero false verification or synthetic approval of tasks/projects.
4. Strict single-runner concurrency (preventing double execution and duplicate side-effects).
5. Comprehensive incident journaling with redaction and anti-spam rate limiting.

---

## 2. Failure Classification Taxonomy

Every execution outcome or runtime fault is classified into one of the canonical categories below.

| Category ID | Error Name | Detection Signatures | Severity | Recoverable? | Default Budget | Backoff Strategy | Safety Preconditions Before Retry |
|---|---|---|---|---|---|---|---|
| `MISSING_MARKER` | CLI Succeeded But Missing State Marker | Exit code 0, status SUCCESS, missing `RE_DRAGON_RUN_STATE` in response | WARNING | Yes | 3 turns | Exponential (60s, 120s, 240s) | Pinned project exists & ACTIVE; PID dead; task lease uncompromised |
| `AGENT_CRASH` | Unhandled Agent Process Exit | Exit code != 0 (e.g. 1, 139 segfault, unhandled exception), not quota/auth | ERROR | Yes | 3 turns | Exponential (30s, 60s, 120s) | Pinned project ACTIVE; PID verified dead; stale leases cleared safely |
| `TIMEOUT` | CLI or Task Timeout | Exit code 124, `watchdog process timeout`, or task lease duration exceeded | WARNING | Yes | 2 turns | Linear (60s, 120s) | Process group terminated (`SIGKILL`); checkpoint verified |
| `SQLITE_LOCK` | Database Contention / Lock | `database is locked`, `OperationalError: database is locked`, `busy` | WARNING | Yes | 5 attempts | Short Exponential (2s, 4s, 8s, 16s, 30s) + jitter | Database accessible; WAL checkpoint intact |
| `STALE_LEASE` | Stale or Expired Task Lease | Lease expired without submission, or lease conflict detected | WARNING | Yes | 2 attempts | Immediate audit / reset | Task reset to READY only if no partial uncommitted side effects |
| `QUOTA_EXHAUSTED` | Provider Rate/Quota Limit | `RESOURCE_EXHAUSTED`, `rate limit exceeded`, `quota exceeded`, `429` | INFO | Yes | Unlimited (Wait) | Wait until reported reset timestamp + 60s grace, or 900s default | Project ACTIVE; wait without consuming tokens |
| `RESOURCE_EXHAUSTION` | Out of Memory / Ghidra RAM | `java.lang.OutOfMemoryError`, exit code 137 (OOM killed), `low memory` | ERROR | Conditional | 2 attempts | 120s backoff, mark resource heavy | Confirm memory freed, task decomposable via scheduler split |
| `NETWORK_TRANSIENT` | Network / Transport Fault | `ECONNRESET`, `ETIMEDOUT`, `EAI_AGAIN`, `502 Bad Gateway`, `503` | WARNING | Yes | 4 attempts | Exponential (30s, 60s, 120s, 240s) | Socket closed; connectivity test |
| `AUTH_OR_PERMISSION` | Missing Credentials or Tool Permission Denied | `soft-denied`, `permission denied`, `requires approval`, `waiting for approval` | CRITICAL | **NO** (Fail-closed) | 0 (Immediate STOP) | None (Hold state) | Requires operator intervention via Telegram `/approvals` or terminal |
| `TELEGRAM_DELIVERY` | Telegram API Delivery Failure | Telegram network error, HTTP 429 flood, network timeout | WARNING | Yes | 5 attempts | Exponential (10s, 20s, 40s) | Independent from agent execution; does not stop watchdog |
| `CORRUPT_STATE` | Corrupt JSON or SQLite State | `json.JSONDecodeError` in state file, SQLite corruption | CRITICAL | **NO** (Fail-closed) | 0 (Immediate STOP) | None | Requires backup restoration or manual inspection |

---

## 3. Recovery Engine Architecture (R1)

### 3.1 Pinned Project Identity & Resume Guarantee
- When `./dragon resume` or `./dragon start` is invoked without explicit project ID:
  1. If `quota-watchdog.json` contains a `project_id`, verify that this ID exists in SQLite `auto_projects`.
     - If it exists and status is in `ACTIVE` / `PLANNING`, resume this project.
     - If it exists and status is in `ACCEPTED` / `TERMINAL`, **fail closed** with an explicit error: `"Project is already ACCEPTED; will not restart or duplicate a closed project"`.
     - If it does not exist in SQLite, **fail closed**: `"Pinned watchdog project_id is absent in Harness SQLite; refusing fallback"`.
  2. If `quota-watchdog.json` does not contain a `project_id`:
     - Query SQLite for projects matching the goal.
     - **Crucial fix**: Distinguish ACTIVE/PLANNING projects from legacy ACCEPTED projects. If there is exactly one ACTIVE/PLANNING project, resume it even if an older legacy project is ACCEPTED. If multiple ACTIVE projects exist, fail closed and require `--project-id`.

### 3.2 Pre-Retry Safety Verification (Anti-Double Execution)
Before any recovery attempt is initiated:
```python
def verify_pre_retry_safety(workspace, project_id, previous_pid):
    # 1. Verify previous process is completely dead
    if previous_pid and is_pid_alive(previous_pid):
        terminate_process_group(previous_pid)
        time.sleep(1)
        if is_pid_alive(previous_pid):
            kill_process_group(previous_pid)
    
    # 2. Verify Harness SQLite integrity & project status
    info = quota_guard.inspect(harness_state_dir, project_id)
    if info["project_status"] not in quota_guard.ACTIVE:
        raise SafetyCheckError(f"Project status is {info['project_status']}, cannot auto-retry")
        
    # 3. Verify task lease state to prevent duplicate execution
    # If a task was CLAIMED by the dead process:
    # Check if task was completed/submitted; if unsubmitted and lease expired,
    # safely reset task claim to READY with updated attempts counter.
```

### 3.3 Incident Journaling & Anti-Spam Throttling
- Incidents are recorded in `.re_harness/incidents.sqlite3` with fields:
  `id`, `project_id`, `task_id`, `category`, `severity`, `status`, `error_message` (redacted), `details` (JSON), `recovery_attempts`, `max_recovery_attempts`, `next_retry_at`, `created_at`, `updated_at`, `resolved_at`, `resolution_notes`.
- **Deduplication / Anti-Spam**:
  If a new incident occurs for the same `project_id` and `category` within 300 seconds of an existing `OPEN` incident, it updates the existing incident (bumping `occurrence_count` and `updated_at`) rather than creating a duplicate notification.
- **Redaction**:
  All incident messages pass through `redact_sensitive_data()`, stripping Telegram bot tokens, API keys (`AIza...`, `sk-...`), bearer tokens, and private paths.

---

## 4. Independent Process Supervision (R2)

### 4.1 Process Concurrency & Lock Protocol
- The Watchdog process continues to use file locking via `fcntl.flock(LOCK_EX | LOCK_NB)` on `.re_harness/quota-watchdog.lock`.
- The Supervisor service wraps Watchdog execution and ensures:
  1. Only one supervisor or Watchdog runs at any given time.
  2. If the user starts Watchdog manually or in tmux (`./dragon start`), the supervisor detects the active lock and enters passive standby.
  3. Controlled cutover: `./dragon supervisor {enable|disable|status|start|stop}` allows seamless switching without killing in-flight agent tasks.

### 4.2 Exit Code Delineation
The Watchdog exits with specific codes to inform the supervisor of the nature of the termination:
- **Code 0 (`COMPLETE`)**: Goal achieved, project ACCEPTED. Supervisor must NOT restart.
- **Code 10 (`BLOCKED`)**: Blocked on external dependency or review. Supervisor must NOT restart; notifies operator.
- **Code 11 (`NEEDS_USER`)**: Blocked on authentication, permissions, or quota exhaustion retry limit. Supervisor must NOT restart.
- **Code 12 (`PAUSED`)**: Paused by operator via Telegram `/pause`. Supervisor must NOT restart until `/resume`.
- **Code 1 (`CRASH`) / Signals**: Unexpected process termination. Supervisor applies bounded exponential restart backoff (up to 5 attempts with 15s, 30s, 60s, 120s, 240s delays) before creating a CRITICAL incident and staying down.

### 4.3 Heartbeat: Process Liveness vs Task Progress
`runtime_state.py` produces:
```json
{
  "state": "AGENT_RUNNING",
  "pid": 12345,
  "elapsed_seconds": 180,
  "supervisor_heartbeat_at": 1729999000.0,
  "heartbeat_age_seconds": 5,
  "heartbeat_is_progress_proof": false,
  "last_task_key": "T-004",
  "last_task_progress_at": 1729998950.0,
  "task_stall_seconds": 50
}
```
If `task_stall_seconds > 1800` while PID is alive (e.g. native Ghidra analysis hang), supervisor treats this as a stalled lease, logs a `TIMEOUT` incident, and triggers bounded recovery.

### 4.4 OS Integration
- **Ubuntu WSL2**: systemd user service unit (`~/.config/systemd/user/re-dragon.service`) with `Restart=on-failure`, `RestartPreventExitStatus=0 10 11 12`.
- **Windows Task Scheduler**: XML task definition running at user logon to start WSL2 background service with minimal overhead and no desktop interference.

---

## 5. Telegram Incident Control (R3)

### 5.1 Command Interface Extensions
- `/status`: Real-time watchdog state, active PID, process liveness, task progress, last turn outcome.
- `/progress`: ASCII progress bar, completed/pending/blocked tasks count, active milestones.
- `/incidents`: List open and recently resolved incidents with ID, category, severity, and timestamp.
- `/incident <ID>`: Detailed incident inspection: root cause, affected task, SQLite checkpoint, recovery history.
- `/retry <ID>`: Manually request recovery retry for a blocked incident after verifying safety conditions.
- `/pause`: Gracefully pause autonomous execution after the active turn completes; prevents new turns.
- `/resume`: Unpause autonomous execution and resume the pinned project.
- `/approvals`: List pending approvals (human decision proposals and project switch confirmations).

### 5.2 Callback Security & Nonce Verification
- All interactive callback queries contain a cryptographically secure 12-byte hex nonce:
  `cmd:id:nonce:decision`
- Nonces expire after 600 seconds and are single-use (stored in SQLite `control_requests` / `proposals`).
- Strict owner verification (`allowed(user_id, chat_id, chat_type, owner_id)`); unauthorized requests are dropped.
- **Zero Shell Execution**: No Telegram command or callback executes shell code.

---

## 6. Fault-Injection Acceptance Suite (R4)

The test suite in `tests/test_v08_fault_injection.py` systematically simulates all 10 target failure scenarios:
1. **Missing or Malformed Marker**: Verifies bounded recovery turn up to limit, followed by incident creation without project corruption.
2. **Agent Crash Mid-Task**: Verifies cleanup of dead PID, stale lease reset, bounded restart, and no duplicate side-effects.
3. **Network Disconnect & Timeout**: Verifies transport error classification, bounded exponential backoff, and recovery upon reconnect.
4. **SQLite Lock & Contention**: Verifies WAL concurrency handling, retry with jitter, and state preservation.
5. **Quota Exhaustion & Refresh**: Verifies calculation of reset delay + grace, state transition to `WAIT_QUOTA`, and resuming only after reset timestamp.
6. **Ghidra RAM Exhaustion (OOM)**: Verifies error classification, resource limit marking, and task split delegation.
7. **Telegram Network Disconnect**: Verifies bot reconnection loop, failure journaling under `TELEGRAM_DELIVERY`, and zero interruption to Agent execution.
8. **Coexistence of ACCEPTED and ACTIVE Projects**: Verifies that resume never selects the legacy ACCEPTED project.
9. **WSL2 / System Restart Simulation**: Verifies state survival across simulated reboot with stale PIDs and recovery to ACTIVE state.
10. **Permission Denial & Human Approvals**: Verifies fail-closed transition to `NEEDS_USER`, incident generation, and requirement for human resolution via `/approvals`.
