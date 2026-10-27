---
document_id: RS-GAME-SERVER-GO-STANDARD
version: 1.1.0
status: OWNER_APPROVED_CONTENT_STAGED_FOR_PINNED_V2_ADOPTION
owner_approval: 2026-10-27
effective_for: V2 tasks that explicitly pin this addendum SHA, not the historical V2 charter SHA by itself
inherits: GO_GAME_SERVER_AGENT_STANDARD_V1.md
rule_registry: GO_GAME_SERVER_RULE_REGISTRY_V1_1.md
applicability_matrix: GO_GAME_SERVER_RULE_MATRIX_V1_1.md
target_toolchain: 1.27.3
---

# RE Dragon — Go Game Server Engineering Standard v1.1

## 0. Authority, versioning and safe activation

This document **completes the V1 Go standard** for the owner-approved ReturnSaiyan Unified Heroes Full-Stack V2. It does **not** change the locked S1–S6/G1–G8/T00–T13 acceptance or grant deployment permissions. The existing approved V2 contract is source-pinned at `adf815515d0b38645c136ad1d211cbae76c975aa` (and must continue using the exact SHA that the user's Harness project actually pins); this v1.1 rulebook is a **versioned, opt-in addendum**. The Agent must record both SHA values and confirm owner/task scope before using this addendum on an active project. On conflict, stop and obtain a controlled amendment; do not silently replace pinned rules.

**Priority:** Safety and authorized scope > frozen V2 product charter + observed client binary/source proofs > accepted versioned contract and reviewed security decisions > this v1.1 standard > inherited, formerly-DRAFT LoRa guidance > nonbinding style advice. The Go [Guide](https://google.github.io/styleguide/go/guide) is normative for style; Google Decisions subordinate; Best Practices advisory. New Google or upstream text revisions are not automatically approved. Explicit STOP if protocol opcode/framing, legacy XOR/session behavior, auth response, asset schema or durability ACK is unknown.

**Do not mutate or reopen V1:** project `20d3b705a4314d80`, its SQLite acceptance, APK/XAPK and artifact hashes. No third-party game-server calls, no secret capture, no speculative unlocking of SERVER_GATED heroes.

## 1. Required Agent lookup (selective, not 86 KB per task)

1. Read root `AGENTS.md`, exact pinned charter and addendum SHA, task ID/AC/allowed paths, current repo worktree, actual Go files/module and source-proved client protocol evidence.
2. Read [Rule Applicability Matrix](GO_GAME_SERVER_RULE_MATRIX_V1_1.md) for this task's S-gate/paths; retrieve **only applicable** Rule IDs in [148-ID Registry](GO_GAME_SERVER_RULE_REGISTRY_V1_1.md), plus the 16 game rules in §2. Excluded upstream IDs have no normative force. Explicit `ADAPT` local wording prevails over upstream draft.
3. Produce a small design: expected input/output, source hashes, invariants, error/timeout paths, persistence ACK policy, intended file set, test oracle and authorized staging endpoint.
4. Implement the smallest executable, source-grounded vertical slice. No placeholder package forests, fake handshake, invented hero skill attributes, or simultaneous unsupervised Ghidra-heavy imports.
5. Gather actual `gofmt`, `go vet`, `go test`, `-race`, protocol golden vectors, real PostgreSQL/Android evidence according to applicability. Independent reviewer must assess same immutable artifact hashes. A proposed CI check or skipped job is **NOT_RUN**.
6. Emit task audit: `PROJECT_ID`, `TASK_ID`, `CHARTER_SHA`, `ADDENDUM_SHA`, `SOURCE_APK_SHA`, `RULE_IDS_APPLICABLE`, `RULE_IDS_APPLIED`, `EXCEPTIONS`, `ALLOWED_PATHS`, `CHANGED_PATHS`, `TEST_COMMANDS`, `TEST_RESULTS`, `NOT_RUN`, `BLOCKERS`, `PRODUCER`, `REVIEWER`, `FINAL_STATUS`.

## 2. Core game-server rules (V1 carried forward)

| ID | Requirement | Evidence |
|---|---|---|
| TCP-001 | Validate frame lengths BEFORE allocation; handle TCP fragmentation/coalescing, EOF, deadline, partial read/write and bounded memory | Golden vectors, fuzz, socket integration |
| TCP-002 | No invented packet/opcode/endianness/codec; link every contract to verified client hash and function/disassembly or authorized packet observation | Protocol traceability |
| TCP-003 | Reproduce observed legacy XOR/session transformation byte-for-byte where necessary; never mistake XOR for secure authentication | Known-answer vectors + security review |
| TCP-004 | Enforce verified packet state ordering and sequence rollover; reject unknown or malformed protocol without false success | Negative state tests |
| TCP-005 | Default to loopback/private controlled endpoints; never test against unauthorized live game infrastructure | Network config audit |
| AUTH-001 | Authentication for approved local/test identities; ownership/selection authorization server-side, no real account impersonation or entitlement bypass | Negative auth tests |
| AUTH-002 | Explicit session lifecycle and timeout/reconnect/duplicate login behavior | Connection integration |
| DOMAIN-001 | Hero identity and assets link to V1 G2/G3 canonical A-union-B matrix; cosmetic resource presence does not confer playability | Manifest consistency |
| DOMAIN-002 | Authoritative server game state, combat and inventory; only implement observed or approved semantics | E2E state transition |
| DOMAIN-003 | Deterministic implemented combat rules, invalid action and replay protection, no invented drop rates/hidden formulas | Unit/fuzz/contract |
| DB-GAME-001 | SQL schema only for defined local account/hero/inventory/progression requirements; migration & constraint tests on real Postgres | DB integration |
| DB-GAME-002 | Transaction/idempotency/reconnect test; no duplicated rewards or stale overwrites | Concurrency DB test |
| SEC-GAME-001 | No raw credentials, handshake secrets, session tokens or proprietary payload bytes in GitHub/Telegram logs | Redaction test |
| E2E-GAME-001 | Android APK↔Go↔Postgres must be observed on controlled device with artifacts and separate reviewer | S6 E2E proof |
| E2E-GAME-002 | Per-hero ASSET_PRESENT, CLIENT_VISIBLE, ANIMATION_VERIFIED, OFFLINE_FUNCTIONAL, PLAYABLE_VERIFIED, SERVER_GATED, BLOCKED/UNKNOWN distinction | Hero matrix |
| GOV-GAME-001 | Never change active V1 watchdog, project criteria, AGENTS.md routing or parent SQLite state by preparing V2 docs | Handoff audit |

The game rules are *additional to* the selectively activated upstream Go IDs, not replacements for source/protocol evidence.

## 3. V1.1 clarifications for performance, operational safety and DB correctness

These are cross-cutting **additional acceptance interpretations**, not new ways to waive S5/S6:

| Additional rule | Requirement | Mandatory proof when applicable |
|---|---|---|
| PERF-GAME-001 | Measure **authenticated valid CCU** separately from open sockets and C2S/S2C packet/s; generator offered/achieved load must be reconciled | Approved T00–T04 run manifest + per-cohort metrics |
| PERF-GAME-002 | Backpressure and limits for sessions, reader/writer buffers, goroutines and pending actions; avoid unbounded fan-out and retry amplification | Queue/FD/RSS/CPU, race and soak evidence |
| DB-GAME-003 | Acknowledged inventory, currency and progression mutation must be durably committed; ambiguous lost-ACK retry must use stable idempotency keys | Concurrent retry/oracle + transaction restart tests |
| DB-GAME-004 | Execute versioned expand/backfill/switch/contract migration under controlled staged load, separately validate rollback/read compatibility | Real PostgreSQL migration evidence + lock/WAL analysis |
| DB-GAME-005 | Independently verify point-in-time restore, backup/WAL continuity and RTO/RPO by failure model; async replication does not imply zero RPO | Actual restore and invariant report |
| OPS-GAME-001 | Record per-operation p50/p95/p99, DB pool wait, Go GC/heap/FD, incident recovery and loadgen saturation; avoid high-cardinality identifiers in metrics | Bounded-cardinality metrics & run timeline |
| SEC-GAME-002 | Keep private endpoint allowlist, user-test credentials, certificate verification and redaction; do not use XOR as transport/auth security | Threat model/negative tests/static audit |
| E2E-GAME-003 | A simulated client at 5k does not replace real integrated APK↔Go↔Postgres gameplay; donor hero playability remains independently gated | Android recorded E2E, screenshots/logs and reviewer |
| GOV-GAME-002 | No V1 acceptance rewrite or silent v1.1 adoption by existing pinned project; archive evidence and require scoped approval for addendum activation | H0 handoff ledger and pinned SHAs |

## 4. Module and dependency architecture

Default is **one Go module**, scoped under `game-server/` once implementation is authorized. Candidate packages (create only as needed) `cmd/server`, `internal/protocol`, `internal/transport`, `internal/session`, `internal/heroes`, `internal/world`, `internal/combat`, `internal/storage` plus migration/test fixtures. Main owns startup/stop wiring; domain owns invariants, adapter owns external I/O. No MQTT, LoRa protocol, firmware, ChirpStack, default Redis, ORM, microservice expansion or custom crypto system unless separately approved. Validate pgx/v5 version and license before adding it. A 5,000 CCU target does not require 5,000 DB connections.

Use Go `context.Context` for bounded operations, `errors.Is/As` where callers need classifications, `log/slog` with redaction, measured pool sizing and controlled session lifecycles. Never ACK a durable game mutation before DB COMMIT. Preserve legacy codec compatibility *where proven*, without declaring XOR cryptographically secure.

## 5. Quality gates (real evidence only)

**Rule registry consistency:** CI checks 148 unique upstream IDs, exactly 86 ADOPT + 26 ADAPT + 36 EXCLUDE decisions, 16 game V1 IDs, nine v1.1 clarifications, known applicable Rule IDs and source lineage. A change in that inventory requires reviewed and versioned policy update.

**Go build/test gate:** If `game-server/go.mod` and real code exist, Go CI runs with `GOTOOLCHAIN=local`, **exact go1.27.3**, `gofmt` stdout empty, `go mod verify`, `go vet ./...`, `go test ./...`, `go test -race ./...` (on supported platform), plus `git diff --check`. When code exists without a Go module, CI fails. **When Go module/code do not exist, Go execution status is NOT_RUN_NO_MODULE**, regardless of a green docs CI. No placeholder Go server is created to make CI appear green.

**Feature gates:** Golden opcode/framing/handshake vectors, negative auth and protocol state cases, real PostgreSQL transaction/migration/restoration, actual Android gameplay and 5,000 CCU load must be separately measured when corresponding S-gates are ready. Mock-only or simulator-only results cannot be labeled full S6, DB recovery or 5,000-CCU PASS. Numerical performance latency SLO candidates remain provisional until hardware-baseline signoff.

## 6. Controlled rollout

- Phase A: documentation/registry/matrix + CI documentation integrity, in an isolated PR. Human review and CI PASS before merge; **no Agent auto-merge**.
- Phase B: on owner-approved V2 task, record new addendum commit SHA alongside *unchanged* charter SHA in the Harness task/decision ledger. Activate for Go tasks only after precedence/scope check.
- Phase C: implement Go module in its own bounded vertical slice, collect Go CI and functional test results, then independent review.
- Phase D: staged TCP/DB/Android load, migration and recovery under T00–T13, never on unauthorized external infrastructure.

**Release status as of this document:** RULEBOOK_COMPLETE_DESIGN_ONLY; GO_RUNTIME_NOT_VERIFIED; DB_TEST_NOT_RUN; ANDROID_V2_NOT_VERIFIED; 5K_CCU_NOT_RUN. A passing rulebook check is not game-server readiness.

## 7. Provenance

Upstream 148 unique IDs (14 Google GGS + 134 carried v1): [LoRa source blob 7e08b93fdae6f86b61b06fc71837e80ec175aed4](https://github.com/khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP/blob/6b49ba090589496553de444b747b5b1d090a7650/docs/development/backend-go/GO_BACKEND_ENGINEERING_STANDARD_V2.md) — source status **PROPOSED / NOT_APPROVED**. Per-ID original language, full local adaptations, exclusions and line references are preserved in the [Registry](GO_GAME_SERVER_RULE_REGISTRY_V1_1.md). V1 game-specific rule baseline in `GO_GAME_SERVER_AGENT_STANDARD_V1.md` stays immutable, and this document extends rather than rewrites it.
