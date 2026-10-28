# Task p5-e2e-db-persistence-audit Report

**Project ID:** `6181397b27b247e9`  
**Task Key:** `p5-e2e-db-persistence-audit`  
**Target Database:** PostgreSQL 16 (`rs-postgres`, `returnsaiyan_dev`)  
**Target Account:** ID `14` (`guest1443138206`)  
**Target Character / Role:** ID `24` (`guest1443138206`, Hero `10001`, Level `1`)  
**Execution Timestamp:** 2026-10-28T02:16:16Z to 2026-10-28T02:17:26Z  

---

## 1. Executive Summary

Task `p5-e2e-db-persistence-audit` conducted an exhaustive PostgreSQL persistence and data consistency audit for the Android gameplay E2E session executed against the operator-local Go TCP game server.

Key findings:
1. **Fresh End-to-End Gameplay Record:** The physical Android client (`RMX3461`, serial `10b3139c`) authenticated as guest user `guest1443138206`, creating account ID `14` and auto-provisioning starter role ID `24` (`hero_code = '10001'`).
2. **Accounts & Credential Security:** The `accounts` record verified `status = 'ACTIVE'`, a cryptographically secure 16-byte random salt (32-character hex `73f56229f5ef9735fe11b4b147cbf29b`), and SHA-256 password hash (64-character hex). Redaction in application logs complied with `SEC-GAME-001`.
3. **Role & Source Classification:** Role ID `24` verified name `guest1443138206`, hero code `10001` (Son Goku starter), level `1`, exp `0`, gender `1`, status `0`, and origin source classification `CANONICAL_BASELINE` (Migration 000002).
4. **Roster Unlocks Architecture:** In accordance with schema migration `000001_init_schema.up.sql`, `roster_unlocks` specifically manages server-gated entitlements for Global donor additions. Canonical baseline heroes are inherently accessible. ACID grant and revoke operations (`GrantUnlock` and `RevokeUnlock`) were verified on account `14` with zero residual side effects.
5. **Player Progression Consistency:** Progression queries for role `24` authoritatively resolved to default baseline state (`stage_id = 1`, `stage_progress = 0`, `stars = 0`). Upsert idempotency and read queries via `PostgresProgressionRepository` were verified.
6. **Zero Data Corruption or Leaks:** Audited referential integrity across all public tables with 0 orphaned records, 0 uncommitted transactions, 0 active locks in `pg_locks`, and clean schema migration version 2 (`000002_unified_heroes_source_mapping`).

---

## 2. Primary Evidence Ledger

### 2.1 Audit & Manifest Artifacts
| Artifact File | Size (Bytes) | SHA-256 Checksum | Description |
|---|---|---|---|
| `evidence/s6_e2e/p5_db_audit_report.json` | 4,582 | `d3d07223742d01658a59a3b5057c7c47dbcf246fa87cefc520ff41e30a82de78` | Machine-readable 10-point PostgreSQL persistence audit report |
| `evidence/s6_e2e/db_persistence.json` | 1,061 | `5f15dfd674cea716e539c212a540deb08bcf1d77ab374985e343f75e72a43cbe` | E2E runner raw psql snapshot of accounts and roles |
| `evidence/s6_e2e/e2e_run_manifest.json` | 2,452 | `5a420b9e843e9fa82eb38676fa1cbe6256f082e66f3630fca56d43e597793d5f` | Complete run manifest correlating screenshots, logs, and DB state |

### 2.2 Gameplay E2E Screenshots (2412 x 1080 Native RGBA)
| Step | Artifact File | Size (Bytes) | SHA-256 Checksum | Description |
|---|---|---|---|---|
| 01 | `evidence/s6_e2e/01_app_launch.png` | 3,386,999 | `9c1475e28e9aa4cdfeb8d1088a588dfcdcf64b41c9cf51901a7ff7a1c2f94e46` | App launch and title screen on physical RMX3461 |
| 02 | `evidence/s6_e2e/02_server_selection.png` | 326,597 | `fbfa885fa7d91b8e9fb39fef447e3de39251a3ef8e2d5affc331886650d75cfb` | Guest authentication; server card displaying role info |
| 03 | `evidence/s6_e2e/03_world_entry.png` | 2,306,801 | `e18bd23218c69f2a727c05d43b782f510f2af0cdff9e33defe1b0b74f12be9db` | Handshake complete; character loaded into game world |
| 04 | `evidence/s6_e2e/04_gameplay_movement.png` | 2,264,230 | `cd452444dd8e1befde12e04622508b5a6518442f17024e6f53f1716fcc55e964` | In-world movement and action inputs executed on device |

### 2.3 System & Server Logs
| Artifact File | Size (Bytes) | SHA-256 Checksum | Description |
|---|---|---|---|
| `evidence/s6_e2e/orchestrator_server.log` | 9,051 | `643cb6837dacf8dbca2217b9a453304a2d616700b835834bae88e4a2f57eebd5` | Game server log recording account 14 auto-registration, conn-1 login, conn-2 handshake, and conn-2 world entry |
| `evidence/s6_e2e/orchestrator_logcat.log` | 418,163 | `17a88e613a57d100e29c347c529c7293af2479a25ef16db453f1d37f4c895762` | Device logcat recording Cocos2d-x UI events (`Show : fuwuqi`), handshake, and world rendering |
| `evidence/s6_e2e/orchestrator_updater.log` | 396 | `7265716e5284522e0b7225791481408e997b2c63f6ad1e1450ebbb1595519c20` | Mock updater logs for client patch query |

---

## 3. Detailed Database State & Audit Results

The audit was executed via `tools/e2e_runner/audit_p5_db_persistence.py`. All 10 verification points passed cleanly:

```
=== RE Dragon P5 PostgreSQL Persistence & Data Consistency Audit ===
Target E2E Account: ID=14, Username=guest1443138206
[PASS] accounts_record_schema_and_integrity
[PASS] roles_starter_character_integrity
[PASS] roster_unlocks_table_consistency
[PASS] roster_unlocks_acid_grant_and_revoke
[PASS] player_progression_upsert_and_read
[PASS] player_inventories_consistency
[PASS] sessions_table_lifecycle
[PASS] foreign_key_referential_integrity
[PASS] zero_uncommitted_transactions_and_locks
[PASS] schema_migration_version

Audit complete: 10/10 checks passed. Status: PASS
Report saved to: /home/khanh/returnsaiyan-re/evidence/s6_e2e/p5_db_audit_report.json
```

### 3.1 Table: `accounts`
- **Record:** `{"id": 14, "username": "guest1443138206", "status": "ACTIVE", "created_at": "2026-10-28T02:16:27.226331+00:00", "updated_at": "2026-10-28T02:16:27.226331+00:00"}`
- **Security Check:** `salt` is a 32-character hexadecimal string generated via CSPRNG `crypto/rand` (16 bytes). `password_hash` is a 64-character SHA-256 hexadecimal hash string.
- **Timing Correlation:** Server log timestamp `2026-10-28T09:16:27.226+07:00` (`02:16:27 UTC`) perfectly matches `accounts.created_at`.

### 3.2 Table: `roles`
- **Record:** `{"id": 24, "account_id": 14, "name": "guest1443138206", "hero_code": "10001", "level": 1, "exp": 0, "gender": 1, "status": 0, "vip": 0, "guild": "", "origin_source": "CANONICAL_BASELINE", "external_hero_id": null}`
- **Integrity Check:** Foreign key `account_id REFERENCES accounts(id)` is valid. Unique constraint `uq_account_role_name (account_id, name)` is satisfied. Hero code `10001` correctly represents the canonical baseline starter hero Son Goku.

### 3.3 Table: `roster_unlocks`
- **Architectural Scope:** Migration `000001_init_schema.up.sql` establishes `roster_unlocks` to track server-gated hero entitlements (specifically the 14 donor additions from Global). Canonical baseline heroes (`10001`) are available by default without requiring an explicit entitlement record.
- **ACID Verification:** An audit test granted entitlement for donor hero `10081`, verified that `IsUnlocked` returned `true`, revoked the entitlement, and verified `IsUnlocked` returned `false`. Zero dangling records remained.

### 3.4 Table: `player_progression`
- **Contract Verification:** For newly created roles, `GetProgression` authoritatively yields default progression `stage_id = 1, stage_progress = 0, stars = 0`.
- **Upsert Idempotency:** An upsert test verified that saving campaign progress executes atomically via `ON CONFLICT (role_id) DO UPDATE` with full transaction safety.

### 3.5 Table: `player_inventories` & `sessions`
- **Inventories:** Starter loadout is managed in-memory with zero corrupt or out-of-bounds inventory slot rows.
- **Sessions:** In accordance with the 5,000 CCU high-throughput architecture, active sessions are indexed in-memory in `SessionManager` during TCP connections, while PostgreSQL provides durable credentials and role storage. Upon client disconnect and process teardown, no lingering orphaned sessions remain in PostgreSQL.

### 3.6 Referential Integrity & Concurrency
- **Foreign Key Audits:**
  - `orphaned_roles`: 0
  - `orphaned_roster_unlocks`: 0
  - `orphaned_player_progression`: 0
  - `orphaned_player_inventories`: 0
  - `orphaned_sessions`: 0
  - Total orphaned records: **0**
- **Active Transactions (`pg_stat_activity`):**
  - `idle in transaction`: 0
  - `active` hanging queries: 0
- **Locks (`pg_locks`):**
  - Ungranted or exclusive blocking locks: 0
- **Migrations:**
  - Version `2` applied (`000001_init_schema` and `000002_unified_heroes_source_mapping`).

---

## 4. Repository Unit Test Suite Verification

The core Go PostgreSQL repository test suite was executed against the active database container:
```bash
go test -v -run "TestAccountRepository|TestRosterRepository|TestProgressionRepository|TestSessionRepository" ./internal/repository/postgres
```
**Results:**
- `TestAccountRepository`: **PASS** (0.06s)
- `TestSessionRepository`: **PASS** (0.07s)
- `TestRosterRepository`: **PASS** (0.06s)
- `TestProgressionRepository`: **PASS** (0.05s)

---

## 5. Reviewer Verification Guide

To independently verify this task:
1. Verify task status and audit evidence via `harness_auto_status("6181397b27b247e9")`.
2. Inspect `evidence/s6_e2e/p5_db_audit_report.json` and verify that all 10 checks have status `"PASS"`.
3. Check table contents directly in PostgreSQL container:
   ```bash
   docker exec rs-postgres psql -U returnsaiyan -d returnsaiyan_dev -c "SELECT a.id, a.username, a.status, r.id as role_id, r.hero_code, r.origin_source FROM accounts a JOIN roles r ON a.id = r.account_id WHERE a.id = 14;"
   ```
4. Verify referential integrity and zero locks:
   ```bash
   docker exec rs-postgres psql -U returnsaiyan -d returnsaiyan_dev -c "SELECT pid, state, query FROM pg_stat_activity WHERE datname = 'returnsaiyan_dev' AND pid <> pg_backend_pid();"
   ```
5. Run the automated audit script:
   ```bash
   python3 tools/e2e_runner/audit_p5_db_persistence.py
   ```
