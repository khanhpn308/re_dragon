---
document_id: RS-GAME-SERVER-GO-APPLICABILITY
version: 1.1.0
status: OWNER_APPROVED_CONTENT_STAGED_FOR_PINNED_V2_ADOPTION
---

# RE Dragon — Go Rule Applicability Matrix v1.1

Use this file **before** reading the [complete registry](GO_GAME_SERVER_RULE_REGISTRY_V1_1.md). IDs are defined there; scope/exclusion decisions are binding only when this addendum is approved/pinned for the current task. `ADOPT` and `ADAPT` apply; `EXCLUDE` never applies. Read [standard](GO_GAME_SERVER_AGENT_STANDARD_V1_1.md) for 16 game rules + nine v1.1 clarifications.

## Task-to-rule selection (minimum required; add source-derived rules where needed)

| Harness gate / changed area | Baseline Go IDs | Mandatory game rules | Evidence required before claiming PASS |
|---|---|---|---|
| H0 / handoff, client binary analysis | GB-001..006, AI-001..012, QG-005, SE-002, SE-007, TS-011 | GOV-GAME-001, GOV-GAME-002, TCP-002, DOMAIN-001 | Exact client SHA, G1–G8 artifact ledger, true provenance; no old SQLite rewrites |
| S1 / `internal/protocol`, `internal/transport` | GGS-001..014, GO-001..014, RT-001..011, SE-004, TS-001..003, TS-007..011, QG-001..007 | TCP-001..005, PERF-GAME-002, SEC-GAME-002 | Real golden frame/sequence/XOR vectors; fragmentation/coalescing tests, fuzz, bounded I/O and review |
| S2 / `internal/session`, auth/update | GGS-001..014, GB-001..010, GO-001..014, RT-001..011, SE-001..004, SE-006..009, TS-001..003, TS-007..011 | AUTH-001..002, TCP-004..005, SEC-GAME-001..002 | Negative auth, local accounts, expiry, reconnect, duplicate session, safe update flow |
| S3 / `internal/heroes`, `internal/world` | GB-001..010, AR-001..004, AR-006..008, GO-001..014, DB-001..010, TS-001..003, TS-007..011 | DOMAIN-001..002, E2E-GAME-002..003 | Hero A∪B crosswalk, ownership rules, real role/world state proof, SERVER_GATED honesty |
| S4 / `internal/combat`, inventory | GB-001..010, GO-001..014, RT-001..011, TS-001..003, TS-007..011, DB-001..010 | DOMAIN-002..003, DB-GAME-002..003, PERF-GAME-002 | Deterministic combat; replay/invalid actions, transactional rewards and independent oracle |
| S5 / `internal/storage`, migrations | DB-001..010, GO-001..014, RT-001..011, SE-002..004, SE-006..009, TS-001..003, TS-007..011, QG-001..007 | DB-GAME-001..005, PERF-GAME-001..002, OPS-GAME-001 | Real Postgres idempotency, migration, lock/pool/IO metrics, WAL backup/PITR and recovery |
| S6 / integrated Android ↔ Go ↔ PostgreSQL | AI-001..012, TS-001..003, TS-007..011, QG-001..007, OB-001..004, OB-006..012 | E2E-GAME-001..003, PERF-GAME-001..002, OPS-GAME-001, GOV-GAME-002 | Real APK login→hero→world→combat→save/reconnect, 5,000 valid CCU and review |
| Startup/CI / `cmd/server`, `.github/workflows` | AR-001..004, AR-006..008, GO-001..014, QG-001..007, AI-001..012, OB-001..004 | GOV-GAME-001..002, SEC-GAME-001, OPS-GAME-001 | gofmt empty stdout, go vet, go test, race, exact Go toolchain and actual evidence |
| Telemetry/security / owned server boundaries | OB-001..004, OB-006..012, SE-001..004, SE-006..009, GO-006..011, RT-002..011 | SEC-GAME-001..002, OPS-GAME-001, TCP-005 | Redaction, measured latency, bounded cardinality and approved endpoint allowlist |

**Range syntax:** `GO-001..014` expands inclusive within its family; do not interpret `AUTH-001..002` as including new unknown IDs. The validation script verifies every referenced ID resolves to a live binding or game rule and no excluded ID leaks into a matrix range.

## Special rules and reporting

- **Every Go task:** also consult `GB-001..006`, `GGS-001..014`, `AI-001..012`, `QG-001..007` where applicable to touched code; AI must confirm actual existing paths, not create packages merely because listed.
- **No C2S/S2C invention:** `TCP-002` and `DOMAIN-002` prohibit converting unknown packet shape into a fake verified server contract.
- **No uncontrolled DB ACK:** `DB-GAME-003` and `DB-004/005/010` require real transaction tests.
- **Independent review:** producer and reviewer session separation, same SHA/evidence, `PASS` only on actual tested behavior.
- **Missing toolchain/module:** report `NOT_RUN_NO_MODULE`; CI policy check PASS alone is not build evidence.
- **Upstream exclusions:** all CT-001..009, MQ-001..012, SC-001..008, AR-005, OB-005, SE-005, TS-004..006, QG-008 are indexed but **not adopted**. Their game-relevant principles are explicitly restated in game rules/ADAPT rows. Never execute obsolete MQTT/RF semantics.
- **Pin discipline:** existing owner-approved charter SHA remains frozen; activate v1.1 only after the task/handoff records this exact addendum commit SHA with permission. Never rewrite V1 task acceptance or retroactively claim game-server capability.

## Evidence ledger template for Agent handoff

```text
TASK_ID:
PROJECT_ID:
CHARTER_SHA:
ADDENDUM_SHA:
BASE_SHA / HEAD_SHA:
APPLICABLE_RULE_IDS:
RULE_IDS_APPLIED:
RULE_CONFLICTS_AND_EXCEPTIONS:
CHANGED_PATHS / ALLOWED_PATHS:
PROTOCOL_EVIDENCE_SHA:
GOFMT: PASS/FAIL/NOT_RUN
BUILD: PASS/FAIL/NOT_RUN
GO_VET: PASS/FAIL/NOT_RUN
UNIT: PASS/FAIL/NOT_RUN
RACE: PASS/FAIL/NOT_RUN
PROTOCOL_CONTRACT: PASS/FAIL/NOT_RUN
POSTGRES_INTEGRATION: PASS/FAIL/NOT_RUN
MIGRATION_RECOVERY: PASS/FAIL/NOT_RUN
ANDROID_E2E: PASS/FAIL/NOT_RUN
CCU_5000: PASS/FAIL/NOT_RUN
REVIEWER_SESSION_AND_EVIDENCE:
FINAL_STATUS: VERIFIED/BLOCKED/NEEDS_USER/REWORK
```

**Note:** status labels in this template are report vocabulary, not evidence of any test already run.
