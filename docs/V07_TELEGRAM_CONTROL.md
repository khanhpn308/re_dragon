# RE Dragon v0.7 — Telegram Orchestrator Control Center

## Overview

RE Dragon v0.7 introduces the **Telegram Orchestrator Control Center**, extending the headless autonomous agent controller with interactive command and approval primitives directly from Telegram, powered by `python-telegram-bot` (v22+).

The architecture maintains strict boundaries:
- **No remote shell or arbitrary command execution**.
- **No model token transmission or bypass of evidence gates**.
- **Fail-closed security**: private-chat allowlist, transactional SQLite, idempotency, nonces, and report redaction.

---

## 1. Project Lifecycle

| Command | Description |
|---|---|
| `/projects` | List all projects in SQLite with task counts (`[X/Y verified]`) and `⭐ [ACTIVE]` marker. |
| `/newgoal <goal> [\| <acceptance>]` | Create a new project goal in SQLite and activate a dedicated, isolated session. |
| `/project <id>` or `/activate <id>` | Switch the active project, restoring or initializing its independent conversation session. |

### Session Isolation & ACCEPTED Project Protection
- Each project has an independent `conversation_id` recorded in `project_conversations`.
- Switching projects switches session bindings safely without cross-contaminating context or reusing previous sessions.
- Projects with status `ACCEPTED` are strictly immutable: they cannot be reactivated or restarted for execution. Their checkpoints and binary evidence remain preserved.

---

## 2. Task Management

| Command | Description |
|---|---|
| `/tasks [limit]` | List project tasks with statuses and highlight `⚠️ [BLOCKED]` items with blocker reasons. |
| `/task <description>` | Queue a user task proposal for the next agent turn (1–900 characters, bounded input). |
| `/progress` | Visual progress bar (`[████████░░] 80%`), task status breakdown, and blocker details. |
| `/taskdetail <task_key>` | Detailed task inspection: title, kind, acceptance criteria, producer, reviewer, attempts, evidence references, and review notes. |

- **Exactly-once processing**: Ingress messages are deduplicated by `telegram_update` ID in SQLite.
- **Harness decomposition**: During the agent's turn, queued user requests are injected as untrusted data into the prompt, triaged via `autonomy.plan`, and marked `FORWARDED` only upon turn success.

---

## 3. Human Approval Gate

| Command | Description |
|---|---|
| `/approvals` | List pending approval proposals with interactive Inline Keyboards. |
| `/propose <action> <desc>` | Submit a proposal requiring human authorization. |

### Inline Keyboard Actions
- `✅ Xác nhận (Approve)` -> Callback `appr:<id>:<nonce>:APPROVE`
- `❌ Từ chối (Reject)` -> Callback `appr:<id>:<nonce>:REJECT`
- `✏️ Yêu cầu sửa (Rework)` -> Callback `appr:<id>:<nonce>:REWORK`

### Verification & Security
- **Owner Authentication**: Only the configured Telegram user in a private chat can submit decisions.
- **Nonce Verification**: Every proposal has a cryptographically random nonce; mismatched callbacks are rejected.
- **Expiry Enforcement**: Stale proposals expire automatically; expired callbacks are rejected.
- **Idempotency & Replay Protection**: Decisions transition from `PENDING` exactly once. Replay attempts return already decided without mutating state.
- **Transactional Audit Log**: All approvals, rejections, actors, nonces, and timestamps are recorded in `approval_audit_log`.
- **Honest Limitations**: Human approval records operator authorization for high-level gates; it does not replace or fake independent subagent verification of native binary evidence.

---

## 4. Reports & Redaction

| Command | Description |
|---|---|
| `/report` | Summarize VERIFIED, BLOCKED, and in-progress tasks, and deliver a sanitized markdown report. |

### Strict Path & Binary Restrictions
- **Path Ownership**: Reports must resolve within the project's authorized `auto_reports` folder (`auto_reports/<pid>.md`). Path traversal attempts (`../`) are blocked.
- **Forbidden Binaries**: Export of `.apk`, `.so`, `.bin`, `.elf`, `.exe`, or other binaries is strictly prohibited.
- **Redaction Engine**: Automatically redacts:
  - Telegram bot tokens (`[REDACTED_BOT_TOKEN]`)
  - Google / Gemini API keys (`[REDACTED_API_KEY]`)
  - Bearer tokens (`[REDACTED_TOKEN]`)
  - Private cryptographic keys (`[REDACTED_PRIVATE_KEY]`)

---

## 5. Discrete Notifications & Anti-Spam

The background notification worker polls every 15 seconds, generating discrete status signatures:
- Events triggering notifications:
  - Quota pause / wait (`WAIT_QUOTA`)
  - Resource wait (`WAIT_RESOURCE`, memory headroom, CPU)
  - Blocker events (`BLOCKED`)
  - Review queue submissions (`SUBMITTED`)
  - Verified milestone completions (`VERIFIED`)
  - Human approval proposals (`proposals:N`)
  - Final project completion (`COMPLETE`, `ACCEPTED`)
- **Deduplication Cursor**: Signatures are recorded in `notification_cursor` in SQLite. Unchanged signatures are suppressed.
- **Heartbeat Suppression**: Heartbeat timestamps and process PIDs are excluded from signatures, preventing notification spam.

---

## 6. Supervisor Concurrency & Recovery

- **Single Telegram Polling Worker**: An advisory file lock (`.re_harness/telegram.lock` via `fcntl.flock(LOCK_EX | LOCK_NB)`) prevents concurrent bot polling workers against the same token and avoids Telegram 409 Conflict errors.
- **Single Watchdog Process**: Protected by `quota-watchdog.lock`.
- **Crash Recovery**: State is persisted transactionally with SQLite WAL mode and fsync-backed JSON. Dead PIDs and stale heartbeats are cleaned up automatically without user intervention.
