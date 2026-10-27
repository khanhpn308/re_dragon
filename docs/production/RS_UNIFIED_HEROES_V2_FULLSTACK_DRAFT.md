---
document_id: RS-UH-PROD-V2
version: 2.0.0-DRAFT
status: PROPOSED_NOT_ACTIVATED
approval: PENDING_OWNER_APPROVAL
created: 2026-10-27
v1_charter_commit: 52435214aab34c9083d2d3dc8ac18979c4c64348
---

# ReturnSaiyan Unified Heroes — Full-Stack Playable Edition (V2 draft)

**This is a proposed charter, NOT a running project.** Do not stop, switch, replan, mark complete or otherwise alter the currently ACTIVE V1 Harness project 20d3b705a4314d80. The V1 acceptance is immutable and must not be silently rewritten. Read RS_UH_V1_TO_V2_HANDOFF.md for transfer procedures.

## 1. North-star outcome

Produce a reproducible, reversible Android client derived from playable ReturnSaiyan that preserves all existing heroes (including the two newer heroes), inventories and incorporates compatible missing hero content from Dragon Ball Global 1.1.13, and **actually plays** against a separate privately operated Go game server with PostgreSQL. Separate these evidence dimensions: asset presence, hero registration, rendered and animated hero, legitimate server-authorized character selection, and actual game playability. Assets cannot prove online gameplay.

Authorized local compatibility work only. Do not impersonate the historical server, connect to a third-party live server without authorization, bypass authentication/entitlements/payment/DRM or publish proprietary assets without rights.

### Pinned source lineage

- V1 contract: docs/production/RS_UNIFIED_HEROES_V1.md at Git SHA 52435214aab34c9083d2d3dc8ac18979c4c64348.
- Client Harness project: 20d3b705a4314d80; ACTIVE in last user screenshot, not live verified at drafting.
- Two operator-reported co-located inputs: ReturnSaiyan-arm64.apk and DRAGONBALL_GLOBAL_1_1_13_LOCAL_GO_HTTPS_INIT_DIAGNOSTIC_SIGNED (1).xapk. Neither has been inspected in this authoring operation.
- Reuse previously VERIFIED client findings only after confirming original input SHA-256, unchanged semantics, original producer/reviewer and immutable artifact evidence. Never migrate VERIFIED statuses without rechecking.
- If V1 G6 is blocked by server-dependent gameplay, V1 must stay BLOCKED/PARTIAL rather than fabricated ACCEPTED. The V2 S6 test may complete the full-stack requirement independently.

## 2. Proposed technology baseline

| Layer | Choice | Decision status |
|---|---|---|
| Game client | Existing ReturnSaiyan Android ARM64 build, working-copy asset mapping | Keep V1 charter |
| Game transport | TCP binary protocol, exact verified client handshake and codec | Client evidence required |
| Server runtime | Go 1.27.3, single Go module, Modular Monolith | Proposed; check installed toolchain |
| TCP implementation | Go standard net, context, encoding/binary | Prefer standard library |
| Game domain | Sessions, identities, heroes, world, combat, inventory, progression | Derive from client observations |
| Persistence | PostgreSQL, explicit SQL and versioned migrations; pgx/v5 candidate | Approve exact dependency version |
| Logging | Standard log/slog, redaction, correlation IDs | Proposed |
| Testing | Golden protocol vectors; Go unit/fuzz/race; real PostgreSQL; real Android E2E | Independent measured evidence |
| Deployment | Controlled local Go service and database | Never expose third-party endpoints |
| Agent process | Existing RE Dragon Harness, one quota supervisor, independent reviewer | No duplicate watchdog |

**Not included:** MQTT, LoRa, RF/TDMA scheduling, ESP32 firmware, ChirpStack, public game service emulation claims, Redis, Kafka or microservices without a reviewed need. Do not reuse IoT MQTT-specific contracts or issue acceptance tests. Proposed backend coding reference: docs/production/GO_GAME_SERVER_AGENT_STANDARD_V1_DRAFT.md.

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

## 5. Change control / deferred launch

1. Keep V1 active as-is and preserve existing SQLite checkpoints, local APK binaries, source hashes and reports. This draft does not authorize V2 to replace V1 in a running controller.
2. Only after safe V1 checkpoint and explicit owner approval: record V1 status and source/evidence digests, drain existing worker/leases, stop or freeze V1 scheduling, ensure no second watchdog.
3. Approve exact V2 charter commit and game-server standard separately, create a NEW Harness project and pin both SHA and project ID, reuse evidence references only with revalidation.
4. A missing real Android test, signing key, permission, client protocol field, or server-controlled game behavior requires NEEDS_USER/BLOCKED, never false PASS.

## 6. Source of Go adaptation

The operator provided GO_BACKEND_ENGINEERING_STANDARD_V2 (2).md and AGENTS (1).md from khanhpn308/LoRa-P2P-Hybrid-TDMA-MVP and go-version.txt containing 1.27.3. Source standard is PROPOSED/NOT_APPROVED and has Git blob SHA 7e08b93fdae6f86b61b06fc71837e80ec175aed4. The LoRa AGENTS governance is NOT imported into RE Dragon. Go 1.27.3 is officially released (2026-10-19, https://go.dev/doc/devel/release); host toolchain compatibility remains NOT_VERIFIED. The adapted policy is explicitly DRAFT pending approval.
