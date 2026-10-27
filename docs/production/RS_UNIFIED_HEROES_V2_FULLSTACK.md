---
document_id: RS-UH-PROD-V2
version: 2.0.0
status: OWNER_APPROVED_REQUIREMENTS_LOCKED
approval: OWNER_APPROVED_2026-10-27
created: 2026-10-27
v1_charter_commit: 52435214aab34c9083d2d3dc8ac18979c4c64348
---

# ReturnSaiyan Unified Heroes — Full-Stack Playable Edition (V2 APPROVED CHARTER)

**OWNER-APPROVED V2 SCOPE (2026-10-27), NOT AN EXECUTED PROJECT.** This charter becomes the immutable production contract for a NEW V2 Harness project only after that project pins the Git commit containing this exact document. V1 project `20d3b705a4314d80` is reported COMPLETE (10/10 VERIFIED) in the operator's Telegram screenshot at 17:13 local time. This is evidence of Harness lifecycle completion only, NOT independent proof that a playable APK, all hero assets, or Android functional tests exist. **The first V2 milestone is an evidence-level V1 handoff audit.** Do not rewrite V1 acceptance, reuse its VERIFIED flags automatically, or alter its SQLite checkpoint. Read `RS_UH_V1_TO_V2_HANDOFF.md` for transfer preflight.

## 1. North-star outcome

Produce a reproducible, reversible Android client derived from playable ReturnSaiyan that preserves all existing heroes (including the two newer heroes), inventories and incorporates compatible missing hero content from Dragon Ball Global 1.1.13, and **actually plays** against a separate privately operated Go game server with PostgreSQL. Separate these evidence dimensions: asset presence, hero registration, rendered and animated hero, legitimate server-authorized character selection, and actual game playability. Assets cannot prove online gameplay.

Authorized local compatibility work only. Do not impersonate the historical server, connect to a third-party live server without authorization, bypass authentication/entitlements/payment/DRM or publish proprietary assets without rights.

### Pinned source lineage

- V1 contract: docs/production/RS_UNIFIED_HEROES_V1.md at Git SHA 52435214aab34c9083d2d3dc8ac18979c4c64348.
- Client Harness project: 20d3b705a4314d80; operator-provided screenshot reports COMPLETE/ACCEPTED and 10/10 VERIFIED (2026-10-27 17:13 ICT); no local SQLite/artifact audit was performed by this document author.
- Two operator-reported co-located inputs: ReturnSaiyan-arm64.apk and DRAGONBALL_GLOBAL_1_1_13_LOCAL_GO_HTTPS_INIT_DIAGNOSTIC_SIGNED (1).xapk. Neither has been inspected in this authoring operation.
- Reuse previously VERIFIED client findings only after confirming original input SHA-256, unchanged semantics, original producer/reviewer and immutable artifact evidence. Never migrate VERIFIED statuses without rechecking.
- If V1 G6 is blocked by server-dependent gameplay, V1 must stay BLOCKED/PARTIAL rather than fabricated ACCEPTED. The V2 S6 test may complete the full-stack requirement independently.

## 2. Owner-approved technology baseline (runtime not yet verified)

| Layer | Choice | Decision status |
|---|---|---|
| Game client | Existing ReturnSaiyan Android ARM64 build, working-copy asset mapping | Keep V1 charter |
| Game transport | TCP binary protocol, exact verified client handshake and codec | Client evidence required |
| Server runtime | Go 1.27.3, single Go module, Modular Monolith | Approved target; verify installed toolchain and compatibility |
| TCP implementation | Go standard net, context, encoding/binary | Prefer standard library |
| Game domain | Sessions, identities, heroes, world, combat, inventory, progression | Derive from client observations |
| Persistence | PostgreSQL, explicit SQL and versioned migrations; pgx/v5 candidate | Approve exact dependency version |
| Logging | Standard log/slog, redaction, correlation IDs | Approved practice; validate implementation |
| Testing | Golden protocol vectors; Go unit/fuzz/race; real PostgreSQL; real Android E2E | Independent measured evidence |
| Deployment | Controlled local Go service and database | Never expose third-party endpoints |
| Agent process | Existing RE Dragon Harness, one quota supervisor, independent reviewer | No duplicate watchdog |

**Not included:** MQTT, LoRa, RF/TDMA scheduling, ESP32 firmware, ChirpStack, public game service emulation claims, Redis, Kafka or microservices without a reviewed need. Do not reuse IoT MQTT-specific contracts or issue acceptance tests. Owner-approved RE Dragon-scoped backend coding rules: `docs/production/GO_GAME_SERVER_AGENT_STANDARD_V1.md`, pinned at the same charter commit. The unrelated IoT source remains PROPOSED / NOT_APPROVED.

## 3. Server acceptance gates

### S1 — TCP Protocol Server

Validate real framing, handshake, opcode maps, byte order, XOR/session transformation where proven, sequence rollover, partial reads/writes, invalid packets, timeouts and disconnections. Build bounded loopback listener and exactly reproducible golden-vector tests. Distinguish VERIFIED, INFERRED and UNKNOWN. No fabricated fields or original server semantics.

### S2 — Authentication and Session

Support only approved local/test accounts. Trace client login, session creation, expiry, reconnect, duplicate login and character selection. Check authorization server-side. Do not forge commercial account identities or force-unlock server-controlled heroes. Verify negative auth tests and actual controlled client traces.

### S3 — Game State and Heroes

Define versioned hero roster and client-server state contract based on G2/G3 canonical A union B hero mapping; no unexplained ID collisions. Implement controlled world initialization, selected character state and role transitions required by observed client protocol. Account for donor characters whose assets exist but gameplay is SERVER_GATED.

### S4 — Gameplay

Implement small end-to-end slices of observed, server-authoritative combat, skills, world actions and inventory/progression. Use deterministic state rules where supported and test invalid/replayed/concurrent commands. Unknown formulas/drop rates/skill semantics remain UNKNOWN and require evidence, never guessed to claim fidelity.

### S5 — PostgreSQL Persistence

Design versioned migrations for approved local accounts, heroes, roster, inventory, progress and game state. Parameterized SQL, unique constraints, transactions, idempotent mutations, backup and restore; test on real PostgreSQL including concurrent operations, restart, rollback and reconnect. Mock-only SQL tests cannot PASS this gate.

### S6 — Integrated Android ↔ Go E2E

On an authorized Android device/emulator and privately controlled server, demonstrate connect -> verified handshake -> local login -> hero roster/selection -> world -> representative skill/battle/inventory interaction -> persisted restart/reconnect. Preserve all ReturnSaiyan heroes including the two new ones, display donor hero capability honestly, and run A baseline regression. Evidence requires APK SHA, server SHA, Go version, Android OS/ABI, per-step expected/actual logs and independent reviewer. A simulated client or TCP unit tests alone do NOT PASS S6.

### 5,000 CCU performance and persistence verification (APPROVED TEST DESIGN)

Performance evidence for S5 and S6 is specified in [RS_GO_SERVER_5000_CCU_TEST_PLAN.md](RS_GO_SERVER_5000_CCU_TEST_PLAN.md), document ID `RS-UH-V2-PERF-5000-TP1`. This is an **owner-approved test design and 5,000 CCU mandatory target, NOT an executed benchmark**. The numerical latency/resource SLO thresholds in the plan are provisional acceptance candidates; they become binding only when the owner signs off a measured, hardware-specific baseline. The proposed test profiles T00–T13 cover source-bound TCP binary traffic, 5,000 sustained authenticated game sessions, PostgreSQL read/write correctness, idempotency under concurrency, migration under load, crash/reconnect/recovery and real Android end-to-end validation.

Before any load run, the Orchestrator must have owner-approved staging target, validated protocol/client fixture hashes, representative hardware and approved load limits. No 5k claim is valid if the generator saturates, if offered traffic differs from achieved workload, or if the Android client/gameplay compatibility remains unverified. Candidate latency thresholds must be explicitly approved or revised using baseline evidence before turning them into binding production acceptance rules. V1 is reported COMPLETE by the operator; nonetheless, load tests may run only after V2 is activated on an authorized isolated staging environment with resource/performance preflight, and never on third-party game servers.

## 4. Product-level dependencies and acceptance

High-level dependency mapping:
- Source identity G1 precedes G2 hero inventories; G2 plus G3 governs hero IDs and game data.
- Verified P2/P3/P4 client codec/handshake evidence enables S1; S1 enables S2; S2 and G2/G3 enable S3; S3 enables S4.
- S5 schema design may begin after verified domain contracts; S5 integration required by S6.
- G4 client integration and G5 APK build, together with S1-S5, gate real Android S6.
- G7 regression and independent G8 review, plus independent server S1-S6 review, are both required for full-stack GO.

This is a high-level roadmap, NOT an excuse to make 14 giant tasks. At safe activation, Orchestrator persists bounded DAG in Harness SQLite, self-decomposes into verifiable vertical slices, honors one GHIDRA_HEAVY slot, finite retry/memory/quota budgets and genuine independent reviewer sessions. Do not ask for per-task human prompts.

**V2 ACCEPTED only if:** G1-G8 critical client obligations and S1-S6 critical server obligations have direct valid evidence, real end-to-end Android gameplay works with controlled Go/Postgres, documented unsupported donor hero behavior does not contradict approved scope, security/rollback are reviewed, and independent final adjudication is GO. No carry-over from unrelated ACCEPTED smoke tests.

If the operator requires EVERY donor hero to be playable, this remains a critical condition until proven by a real runnable client and local server; all missing dependencies must be BLOCKED or explicitly approved scope revisions, not hidden.

## 5. V1 evidence audit — first V2 acceptance gate (H0)

**H0 — handoff audit is mandatory before marking ANY client gate inherited from V1 as PASS.** Verify V1 project's actual Harness SQLite state and source fingerprints, retrieve every G1–G8 evidence reference, reconcile input digests, production outputs, Android device test logs, reviewer provenance and final product dossier. Record three independent fields: `HARNESS_STATUS`, `ARTIFACT_VERIFIED`, `PRODUCT_ACCEPTANCE`. A report containing "10/10 VERIFIED" or "ACCEPTED" without real artifact paths/hashes and runtime proofs is insufficient.

- If the original APK/XAPK are missing, request the exact local source from the operator; never claim the project had scanned binaries by inference.
- If the integrated APK, hero-union CSV, installation log or independent reviewer evidence is missing, create V2 remediation tasks with explicit dependencies; do NOT declare G4–G8 inherited PASS.
- Reuse valid source findings only after binding to matching SHA-256 and semantic version; what was INFERRED/UNKNOWN stays such until new evidence.
- H0 requires a detailed evidence ledger, not just a Python unit-test PASS. On substantial gaps, initial V2 project task DAG must include real client preparation alongside S1–S6, not silently skip G gates.

## 6. Hard performance, database and release contract

- **5,000 authenticated, protocol-valid CCU sustained** is a mandatory test goal, not an achieved benchmark or a claim one laptop can host them. The 5,000 CCU plan `docs/production/RS_GO_SERVER_5000_CCU_TEST_PLAN.md` is part of S5/S6. Load generator produces offered/achieved rates and user-session error accounting. One or more real Android clients additionally prove S6; 5,000 simulated sockets alone do not.
- PostgreSQL is the sole authoritative durable store for MVP. Maintain exact-once *business effect* under retry, bounded pool and DB timeouts, idempotency/unique constraints, transactions for inventory/currency/rewards, performance metrics and no SQL per game-loop tick by default. Never acknowledge durable success prior to commit. Durability model for each event type documented and reviewed.
- **Zero known confirmed-transaction loss**, no duplicated reward grants, no hero/ID corruption, no uncontrolled stale overwrite in tested scenarios. Run real DB correctness and recovery tests, not just mocks.
- Versioned expand/backfill/switch/contract migrations, backup + restore/PITR and release rollback must be tested. Zero downtime is a design aim subject to measured staged proof, not guaranteed by an architectural diagram.
- Track p50/p95/p99 at TCP/app/DB boundaries, pool wait, blocked transactions, WAL/IO pressure, network errors, reconnect success, generator CPU, and resource ceilings. Candidate numeric SLOs remain **PROVISIONAL** until owner confirms them against baseline and representative host hardware.
- No Redis, message broker, replica/shard, server cluster, ORM or microservice justified merely by 5,000 CCU. Test and profile before introducing additional consistency complexity.
- **Product release GO is stricter than SQLite ACCEPTED:** H0 evidence audit passed, relevant G1–G8 client outputs independently evidenced, S1–S6 service/E2E evidenced, T00–T13 relevant/approved cases run, 5,000 CCU mandatory profile measured and evaluated on representative staging, security and recovery reports reviewed, and independent final reviewer decides GO. Missing critical evidence must be BLOCKED/NO-GO. Human can change product scope only via a new versioned charter.

## 7. Change control and activation

1. Treat V1 as operator-reported COMPLETE, but verify its supervisor state and absence of in-flight tasks/leases locally. Preserve V1 immutable SQLite checkpoints, local APK binaries, source hashes and reports; do not re-open or rewrite V1.
2. Owner has approved V2 requirements on 2026-10-27. Confirm no running Watchdog/Agent/lease for V1, perform snapshot/handoff and ensure only one controller before onboarding V2. Any local mutation/command needs host permissions; documentation approval alone does not run scripts.
3. Create a NEW Harness project only using the user's authorized Telegram /newgoal confirmation, pin the exact V2 charter commit SHA and both documents there, and load them with `git show SHA:path`. The Go standard is OWNER_APPROVED only as adapted in RE Dragon and subject to protocol/permissions evidence. No historical LoRa issue/MQTT/firmware authority transfers. Reuse source evidence references only after H0.
4. A missing real Android test, signing key, permission, client protocol field, or server-controlled game behavior requires NEEDS_USER/BLOCKED, never false PASS.

## 8. Source of Go adaptation

The operator provided GO_BACKEND_ENGINEERING_STANDARD_V2 (2).md and AGENTS (1).md from khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP and go-version.txt containing 1.27.3. Source standard is PROPOSED/NOT_APPROVED and has Git blob SHA 7e08b93fdae6f86b61b06fc71837e80ec175aed4. The LoRa AGENTS governance is NOT imported into RE Dragon. Go 1.27.3 is officially released (2026-10-19, https://go.dev/doc/devel/release); host toolchain compatibility remains NOT_VERIFIED. The adapted RE Dragon-scoped policy is owner-approved as a coding rulebook by the V2 scope approval; the upstream LoRa Draft remains unapproved, and individual runtime protocol/DB/crypto/security decisions still require source evidence and applicable technical review.
