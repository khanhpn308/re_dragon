---
document_id: RS-GAME-SERVER-GO-STANDARD
version: 1.0.0-DRAFT
status: PROPOSED
approval: NOT_APPROVED
enforcement: CONSULTATIVE_UNTIL_APPROVED
source_standard_blob_sha: 7e08b93fdae6f86b61b06fc71837e80ec175aed4
toolchain_candidate: 1.27.3
---

# Go Game Server — Agent Engineering Standard v1 (DRAFT)

> Adapted from user-provided Go Backend Engineering Standard v2.0.0-DRAFT from the LoRa-P2P-Hybrid-TDMA-MVP repository. The source contains 134 migrated v1 rule IDs and 14 added Google-style rules; the source itself is PROPOSED / NOT_APPROVED. This derivative does not magically approve its MUST statements. It is not active in the running ReturnSaiyan V1 project.

## 0. Agent rule routing

On an OWNER-APPROVED V2 Game Server task: Read RE Dragon AGENTS.md -> pinned V2 charter -> Harness task/AC and allowed paths -> actual Go module/source -> only the relevant sections of this adapted standard -> current verified protocol/DB contracts. Distinguish rule source approval, proposed recommendations, and actual tests. Do not read the LoRa-specific AGENTS.md as authority; do not silently apply unrelated MQTT/RF rules.

| Target | Reuse source Rule ID families | Add game rules |
|---|---|---|
| TCP socket/codec/handshake | GB, GO, RT, SE, TS, QG, AI; relevant AR/OB | TCP-001..005 |
| Authentication/session | GB, GO, RT, SE, DB, TS, AI | AUTH-001..002 |
| Hero/world/combat | GB, AR, GO, RT, TS | DOMAIN-001..003 |
| PostgreSQL and migrations | DB, SE, GO, TS, QG | DB-GAME-001..002 |
| CI, entrypoint, operations | AR, GO, RT, OB, QG, AI | GOV-GAME-001, E2E-GAME-001 |

### Rule family disposition

**Reuse selectively (proposed):** GGS-001..014; GB-001..010; AR-002..004 and AR-006..008 after path/domain adaptation; GO-001..014; DB-001..010; RT-001..011; OB-001..004 and OB-006..012; SE-001..004 and SE-006..009; TS-001..003 and TS-007..011; QG-001..007; AI-001..012 after project/task scope updates.

**Excluded from Game Server:** MQ-001..012, SC-001..008, SE-005 LoRa crypto, TS-004..006 IoT MQTT/RF behavior, QG-008 RF/HIL, AR-005 firmware coupling, OB-005 HTTP-MQTT correlation, CT-001..009 as-written (MQTT/REST contracts). General input-validation or authorization principles are restated for game TCP below.

**Adapt, do not copy verbatim:** GB-007 dependency stack (Paho MQTT not applicable); AR-001..003 repository/module layout; GO-014 Go toolchain scope; DB-001 game domain schema; TS-004/TS-005 tests should use real game wire and PostgreSQL instead of MQTT broker; CT-003..005 game trust boundary. Original LoRa repo Issue #70 and firmware-only human gates are provenance, not automatically RE Dragon GitHub issue permissions.

## 1. Proposed generic Go rules

| Rule families | Adapted enforceable intent IF owner approves | Verification |
|---|---|---|
| GGS, GO | gofmt, MixedCaps, meaningful package names, typed errors, errors.Is/As where applicable, context first for cancellable operations, narrow interfaces, no speculative factories, actual Go docs | static, review, unit |
| GB | Correctness > Safety > Reliability > Maintainability > Performance; KISS/YAGNI; no silent fallback; optimize measured bottlenecks only | design+review |
| AR | Single Go module, cohesive feature packages, entrypoint only wires dependencies/lifecycle, no business logic in transport/storage, domain owns invariants | static+build |
| DB | PostgreSQL single primary store for MVP; parameterized SQL, bounded pool/queries, transactions, constraints, idempotency, versioned migrations, real DB tests | DB integration |
| RT | Bounded connections/queues/goroutines, cancellation, shutdown deadlines, no nested retries, race detector and leak tests | race+integration |
| OB | log/slog, meaningful event and state-transition logs, stable correlation IDs, metrics on actual features, redact secrets and raw sensitive packet data | inspection+runtime |
| SE | Server-side auth/authz, local-only insecure dev profile when approved, TLS when externally exposed, input limits, no tokens in logs, security review for auth/crypto | negative tests+review |
| TS | Behavior/invariants/failure-path tests, boundary vectors, fuzz binary parsing, concurrency/shutdown/restart, regression tests for bugfixes | unit/fuzz/race/E2E |
| QG | Pin exact Go toolchain, assert gofmt stdout EMPTY, go vet/test/race, record exact commands/revision, never mark NOT_RUN as PASS | CI+logs |
| AI | Inspect before edit, explicit Issue or Harness AC and allowed paths, smallest executable vertical slice, search before create, no invented APIs, independent reviewer, Draft PR not auto-merge | host+review |

Go 1.27.3 is the proposed exact toolchain (operator go-version.txt); confirm target host go env GOVERSION and actual go.mod first. Source suggests pgx/v5 as a dependency candidate. Do not add an ORM, Redis, microservices, MQTT, external frameworks or new dependency without a justified scoped approval and license/security/version check.

## 2. Game-server-specific proposed rules

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

## 3. Proposed package topology, not an already existing server

Single go.mod, modular monolith. Candidate scoped paths (create only when task permits): game-server/cmd/server/main.go (composition root), internal/protocol (codec/frames), internal/transport (bounded TCP), internal/session, internal/heroes, internal/world, internal/combat, internal/storage, migrations, tests. Do not create empty placeholder layers or a second Go module merely to match diagrams.

Current re_dragon Git tree was inspected: no active Go backend directory was found at drafting. No Go server code, build or integration PASS is claimed by this document.

## 4. AI worker state machine

- PRECHECK: pinned V2 SHA/project ID, allowed paths, clean branch/worktree, inspected current code, protocol evidence; exact Go/toolchain.
- DECIDE: 5-10 line minimal design with input/output, invariant, fail paths, contract proof, files, tests. Missing server wire schema or auth model -> STOP_AND_REPORT and request decision, do not fill gaps.
- IMPLEMENT: smallest correct working vertical slice, bounded I/O, explicit errors, no unapproved source/binary modifications or live endpoints.
- VERIFY: gofmt (check empty output, not only exit status), go vet ./..., go test ./..., go test -race ./... if supported; real DB and TCP/client E2E separate. Actual tool output needed for every PASS.
- INDEPENDENT_REVIEW: fresh reviewer examines immutable test logs and source/contract mapping, no shared mutable working tree and no self-acceptance.
- HANDOFF: feature branch and scoped commit/Draft PR only when approved; no auto-merge, no old accepted state reuse, no fabricated test results.

Minimal report: PROJECT_ID, PINNED_CHARTER_SHA, TASK_ID, SOURCE_RULE_APPROVAL, RULE_IDS_CONSULTED, RULE_IDS_APPLIED, PROTOCOL_EVIDENCE, BASE_SHA, HEAD_SHA, CHANGED_PATHS, ALLOWED_PATHS, TEST_COMMANDS, TEST_RESULTS, DB_INTEGRATION, ANDROID_E2E, NOT_RUN, REVIEWER_EVIDENCE, KNOWN_LIMITATIONS, BLOCKERS, FINAL_STATUS.

## 5. Provenance

User-supplied GO_BACKEND_ENGINEERING_STANDARD_V2 (2).md is byte-identical to original file from khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP (blob SHA 7e08b93fdae6f86b61b06fc71837e80ec175aed4 at source main 6b49ba090589496553de444b747b5b1d090a7650). AGENTS (1).md is specific to LoRa/IoT operator workflows and is NOT installed into this repository. Go-version.txt contains 1.27.3, officially released on 2026-10-19; Go installation in WSL not yet verified. This derivative remains NOT_APPROVED until human review and separate authorization.
