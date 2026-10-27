# RE Dragon — Go Game Server 5,000 CCU Technical Test Plan

**ID:** RS-UH-V2-PERF-5000-TP1  
**Status:** OWNER_APPROVED_TEST_DESIGN / NOT EXECUTED  
**Date:** 2026-10-27  
**Scope:** Owner-approved V2 Go TCP Server + PostgreSQL + integrated Android client; numerical SLO candidates remain provisional until hardware-baseline review  
**Protected V1 project:** `20d3b705a4314d80` (reported COMPLETE in Telegram; preserve its state/artifacts, verify supervisor idle before V2 activation)  
**Project references:** `docs/production/RS_UNIFIED_HEROES_V2_FULLSTACK.md`, `docs/production/GO_GAME_SERVER_AGENT_STANDARD_V1.md` and `docs/returnsaiyan_p2_protocol_model.md` in `khanhpn308/re_dragon`.

> Owner-approved test design; **NO TESTS EXECUTED**. No load tests, database queries, packet transmissions, staging deployments or migration operations have been run. A planned threshold is not measured capability. All tests must target an owner-authorized, isolated staging environment, never a third-party live game service.

## 1. Purpose, boundaries, definitions

Prove 5,000 *concurrent valid game sessions* (CCU) can remain connected and process an approved workload with bounded latency, bounded resources, correct PostgreSQL persistence, safe schema evolution and demonstrated recovery. CCU is distinct from connected TCP sockets, authentication events/s, application packets/s and SQL operations/s. Record each separately.

Production-ready requires evidence for TCP protocol S1, authentication S2, game state S3, gameplay S4, database S5, real Android end-to-end S6, and relevant client G1–G8. A load generator passing cannot alone prove S6 or playable Global heroes. A protocol or feature that is still unknown must be marked BLOCKED/NOT_RUN, not simulated and declared compatible.

**Evidence constraint from P2:** prior reverse-engineering recorded 7 initial server bytes received by the client, a C2S model `[2-byte big-endian length][1-byte sequence][1-byte opcode][payload]`, XOR transforms and modulo-256 sequence rollover. This applies to the *pinned binary analyzed in P2*, not necessarily to an integrated APK or the undocumented server greeting prefix. At G1/S1 preflight, verify exact client/native SHA-256 and source-derived golden vectors; do not invent banner, opcodes, response semantics or hidden server logic.

## 2. Workload model (initial hypotheses, not game measurements)

| Cohort | CCU | Sessions | Offered C2S/s per client | Aggregate C2S/s | Persistence principle |
|---|---:|---:|---:|---:|---|
| Idle online | 40% | 2,000 | 0.05 | 100 | No per-heartbeat SQL unless verified contract demands it |
| World/movement | 30% | 1,500 | 1.00 | 1,500 | Maintain volatile state in memory |
| Combat/skills | 20% | 1,000 | 4.00 | 4,000 | Compute in memory, persist critical results |
| Menu/inventory | 10% | 500 | 0.20 | 100 | Measured read/write DB contracts |
| **Total** | **100%** | **5,000** | — | **5,700** | **Not 5,700 SQL/s** |

The cohort rates, body sizes, server push fan-out, ACKs and valid game states must be updated using verified client evidence before a production benchmark. Record offered AND achieved messages/s. The generator cannot omit actions to conceal overload. Server-to-client broadcast bytes/s may dominate: measure separately.

**Independent database micro-workloads:** 100 → 250 → 500 → 1,000 *approved business operations/s* for 90/10 read-heavy, 70/30 balanced and 40/60 write-heavy mixes. At 500 ops/s in the 70/30 workload, target 350 reads/s + 150 writes/s. These figures are proposed capacity probes, NOT observed ReturnSaiyan DB demand. `pgbench` can benchmark DB hardware separately but is not proof of game business consistency.

Test fixtures must contain 5,000 synthetic local accounts with varied hero counts, inventory and progression, realistic cardinality and skew recorded in the manifest. No real third-party account data or session tokens. Database state snapshots and expected mutation ledger must be generated before each destructive suite.

## 3. Provisional SLO and hard correctness gates

These SLOs are **candidates requiring approval after baseline**; measure p50/p95/p99 per opcode/action and reporting window. Latency boundaries must distinguish local app processing, staging network RTT and real Android latency.

| Metric | Proposed pass condition (steady 5k CCU) |
|---|---|
| Simultaneously valid active sessions | ≥ 5,000 sustained, server and loadgen counts reconcile |
| Fast game action server processing latency | p95 ≤ 50 ms; p99 ≤ 150 ms |
| Durable DB-backed action latency | p95 ≤ 250 ms; p99 ≤ 600 ms, measured request→committed ACK |
| Valid request success | ≥ 99.9% in non-injected steady state |
| DB pool acquisition wait | p95 ≤ 10 ms during nominal profile |
| Go CPU sustained | ≤ 80% allocated CPU (DB CPU reported separately) |
| Memory, goroutines and pending queues | Warmup plateau, no unbounded upward slope |
| Lost critical transaction after durable ACK | **0** |
| Duplicate item/reward/progression grant from retry | **0** |
| Invalid hero/account permissions accepted | **0** |
| Constraint violations, state divergence or irreversible corruption | **0** |

Concurrently record tail latency per cohort, 1-second throughput bins, dropped sends, queue wait, protocol errors, split server/network latencies, CI confidence and histogram counts. Failed/injected recovery phases have separate RTO/RPO verdicts; do not dilute normal SLO with their downtime. On generator saturation, classify results INVALID/INCONCLUSIVE.

## 4. Go load generator specification (future implementation only)

Use Go standard `net.Conn` and state-machine-driven clients, no arbitrary TCP/HTTP flooder. Choose exact module layout after approved V2 project creation, e.g.:

```text
game-server/tools/loadgen/
  cmd/loadgen/main.go                # CLI, safe target allowlist
  internal/protocol/adapter.go       # verified binary framing/crypto golden vectors
  internal/session/engine.go         # handshake, auth, hero, world states
  internal/workload/scheduler.go     # cohort distributions, pacing, jitter, seeds
  internal/transport/client.go       # bounded read/write loops + timeouts
  internal/metrics/report.go         # offered/achieved rates and histograms
  internal/oracle/ledger.go          # independent business invariant comparison
  scenarios/5000ccu.yaml
  testdata/golden/                  # sanitized source-verified byte vectors
```

**Key design requirements:**
1. Isolate generator on one or more separate hosts from server/DB. Partition 5k accounts across workers to avoid generator bottleneck; measure generator CPU, RAM, sockets, FD and NIC saturation independently.
2. Per client maintain one legal protocol state machine; use bounded reader/writer goroutines, outbound buffers, deadlines and deterministic seeded workload. Avoid one OS thread per socket, one unbounded goroutine per packet, or indefinite retry loops.
3. Only send packets whose wire format/opcode/field order and permissible phase are proven. If S1/S2 protocol unknown, label run `transport-only synthetic`, not game-compatible. Default allowlist is loopback/explicit private staging endpoints; reject public or unauthorized targets.
4. Model connect, greeting, handshake, local auth, roster, hero selection, world and legal actions; report which transitions were skipped or unverified. Treat ambiguous ACK when server commits but network drops as UNKNOWN and retry using a stable idempotency key, not a new mutation.
5. Schedule by intended monotonic timestamps, record lateness/coordinated-omission, per-opcode planned/sent/completed/failed counts and true response or state-correlated latency. A raw byte receipt without meaningful correlation does not prove action latency.
6. Simulate TCP fragmentation, frame coalescing, partial writes, slow readers, idle disconnect and protocol error conditions only in approved negative tests. Seed, action mix and frame length distributions must be deterministic/reproducible.
7. Export JSON/CSV or histogram time series with configuration hash, Git/binary hashes, environment, epoch, observation window and error classifications. Do not log tokens, private payloads or use per-user Prometheus labels.

**Proposed (not executable yet) scenario YAML:**

```yaml
schema: rs-uh-loadgen/v1
target:
  address: "127.0.0.1:PORT_FROM_APPROVED_SERVER_CONFIG"
  allowed_cidrs: ["127.0.0.0/8"]
seed: 20261027
ccu: 5000
ramp: 15m
steady: 60m
mode: verified-protocol-only
cohorts:
  idle:   {count: 2000, rate_c2s_s: 0.05}
  world:  {count: 1500, rate_c2s_s: 1.0}
  combat: {count: 1000, rate_c2s_s: 4.0}
  menu:   {count: 500,  rate_c2s_s: 0.2}
limits:
  max_connections: 5000
  max_pending_writes_per_client: 16
  connect_timeout: 5s
  action_timeout: 3s
  stop_on_unapproved_target: true
  stop_on_evidence_mismatch: true
```

Before testing, verify `ulimit -n`, generator ephemeral ports, server accept limits, NIC bandwidth, memory, Go scheduler/GC and DB pool sizes. A 5k result on WSL2 with 8 GB RAM is not representative proof of production capacity. Exact staging hardware must be declared; no hardware capacity is assumed by this plan.

## 5. Test matrix and run order (planned, NOT executed)

| ID | Scenario | Proposed offer and duration | Primary acceptance check |
|---|---|---|---|
| T00 | Static protocol vectors, isolated endpoints, fixture audit | No load | Client/native SHA, golden vector hashes, valid opcodes/states, safe target allowlist |
| T01 | Functional smoke | 100 CCU for 10 min | Supported connect/auth/world/action/reconnect paths correct |
| T02 | Capacity ramp | 500→1,000→2,500→5,000 CCU; 5–10 min/plateau | Achieved offered load, no connection leak; observe saturation knee |
| T03 | Nominal mixed 5k | 5,000 CCU, 60 min; initial 5,700 C2S/s | Candidate SLOs in §3, correct state, generator unsaturated |
| T04 | Soak, steady 5k | 5,000 CCU for 4 h | No unbounded RSS, heap, goroutine, FD, WAL/queue backlog growth or data drift |
| T05 | Burst login and reconnect | Maintain 5k, staged churn; try 50,100,250 login attempts/s in separate windows | Session uniqueness, deadlines, reconnect result; no thundering-herd effects |
| T06 | Database read/write throughput | 100/250/500/1,000 business ops/s; mixes 90/10,70/30,40/60 | DB time, locks, pool wait, WAL/IO, consistency per business action |
| T07 | Contended mutations/replay | Hot rows, simultaneous reward and spend, duplicate request IDs | Exactly one committed business outcome per idempotency key; no negative balance or duplicate hero |
| T08 | Adverse TCP/network | Split/coalesced frame, slow reader, EOF/half-close, delay/loss on private test link | Bounded parse/queue/goroutines; safe state cleanup; no false ACK |
| T09 | Controlled crash/restart | Go crash, PostgreSQL process restart, DB disconnect, after-commit/before-ACK kill | Safe uncertain-outcome retry, no loss of committed ACKed state, measured RTO |
| T10 | Online migration under load | Maintain T03 load while executing expand, backfill, old/new switch | No data loss, compatible schema, no long blocking lock, p99 controlled |
| T11 | Backup/PITR disaster drill | Independent recovered staging copy | Proven WAL coverage, restore accuracy, measured RPO and RTO |
| T12 | Optional headroom | 7,500 CCU (1.5×) only after T03/T04 | Controlled backpressure, no corruption; not a replacement for 5k PASS |
| T13 | Real Android E2E | Actual integrated APK + approved Go/Postgres staging service | Login→hero→world→action→commit→reconnect verified with independent reviewer |

**Order:** T00→T01→T02→T03→T04; schedule T05–T11 after the required S1–S5 capabilities are present, and T13 for S6. T12 is optional. Reset to a known fixture/snapshot before destructive tests. Separate observations into warmup, steady, degraded, recovery and cool-down windows. A passed transport benchmark must never be labeled game-load or Android E2E PASS.

**Protocol negative cases within T00/T08:** 7-byte greeting evidence boundaries and unknown prefix; 1-byte fragmentation; many frames in one read; length zero/overflow/truncated payload; sequence wrap 255→0; duplicate/replayed sequence; wrong-state opcode; invalid session; extreme slow client; stale connection after reconnect; intentional server close. The exact wire rules must be bound to a valid client revision, not assumed universal.

## 6. Database read/write test specification

Before running T06 or T07, create a contract inventory per operation with: triggering verified opcode or server action, SQL shape, number of reads/writes, key indexes, transaction boundary, idempotency key, max affected rows, consistency class, ACK point and possible lock/serialization conflicts.

**Minimum critical operations once server exists:** local account login/session, read hero roster, select role, load inventory, award item, spend resource, complete battle, save progression, disconnect/reconnect. Correctness invariants:

- Unique owned item/hero records and valid references (`player_id`, canonical hero ID, inventory ownership).
- No double award, no duplicate spend, and no negative balances if domain forbids them.
- A response marked `COMMITTED` must be sent only after durable transaction success; volatile queues may hold disposable telemetry, *not* acknowledged critical purchases/awards.
- If commit succeeded but response was lost, replay of the **same idempotency key** returns the existing result. Exactly-once network delivery is not assumed.
- Two concurrent requests modifying the same actor may not overwrite each other silently. Evaluate row-level lock vs optimistic version field with conflicting write tests.
- No per-frame SQL if gameplay state can be kept in RAM with appropriately specified durable checkpoint/results. However no RAM-only success acknowledgment for critical durable mutations.

**Indices and query plans:** collect `EXPLAIN (ANALYZE, BUFFERS)` in isolated staging for representative real queries, documenting actual rows, execution, blocks, index usage and lock waits. Check parameterized SQL; do not create a blanket index on every field. Compare results with realistic fixture table and index sizes; record bloat/dead tuples/autovacuum behavior for the four-hour soak.

**Pool:** Candidate PostgreSQL Go client is `pgxpool` (version requires approval). Instrument `AcquiredConns`, `IdleConns`, `MaxConns`, `AcquireDuration`, `CanceledAcquireCount`, and where version supports it `EmptyAcquireCount` / `EmptyAcquireWaitTime`. Interpret cumulative counters as deltas. A candidate pool-size tuning sweep might try **16/32/64 connections per Go instance**, measured against DB concurrency limits; none is a mandated 5k-CCU value. Never allocate one PostgreSQL connection per player. Read replicas are an optional future optimization only with explicit read-after-write consistency semantics.

**Instrumentation:** PostgreSQL `pg_stat_statements`, `pg_stat_activity`, `pg_stat_io` when version supports it, locks/deadlocks, CPU, RAM, WAL rate, checkpoint I/O, fsync and storage latency, disk space, autovacuum and replication lag (if present). Go: semantic operation histograms, connection pool wait, error type, queue depth/age, worker utilization. Do not label metrics by player ID; redact secrets, real packet payloads and personal data.

## 7. Migration scenario under 5,000 CCU

**Test fixture:** schema Vn and Go server Vn, both already functional. Proposed Vn+1 adds a versioned source-hero mapping/attribute relevant to Unified Heroes, where ReturnSaiyan IDs cannot be replaced by colliding donor Global IDs. Maintain deterministic check sums and count reconciliation for all migrated records.

1. **Expand** compatible schema (nullable column or new table/constraints that do not break Vn). Apply bounded statement and lock timeouts; inspect DDL blocking and client error counts. To create an index on a large hot table, evaluate `CREATE INDEX CONCURRENTLY` **outside a transaction block** and handle invalid interrupted-index state. Do not combine the entire migration into one long transaction.
2. **Coexist** old Vn and new Vn+1 server binaries against expanded schema; document which fields each reads/writes. Use a reviewed dual-read/dual-write compatibility design only if necessary, with one clear source of truth.
3. **Backfill** by primary-key/keyset batches, each independently committed with a replayable checkpoint; throttle to preserve SLO, monitor WAL, locks, autovacuum and replication lag. Compare per-batch counts, IDs and data constraints. No silent hero ownership replacement or ID reuse.
4. **Switch** small controlled cohort/canary to Vn+1; perform auth/roster, gameplay mutation, restart/reconnect, compare old/new behavior; roll forward while recording results.
5. **Contract** remove deprecated schema only in a distinct later reviewed window after Vn is drained and data validated. Do not equate rolling back code with reversing already-applied schema/data.

**Suggested migration scoring:** zero critical acknowledged-write loss/duplication, zero new unauthorized hero grants, zero incompatible old-version schema reads, zero unbounded pool wait/backlog, offered rate sustained. Provisional per-action migration p99 should remain ≤2× measured pre-migration p99 unless owner approves a different bounded degradation window. Migration duration, wait time and lock hold duration are separately logged. Freeze exact lock thresholds only after staging preflight.

**Fault injection:** interrupt backfill and resume with no double apply; cancel concurrent index build and inspect invalid index; restart Go service mid dual-version rollout; test colliding A/B hero IDs; force a DB disconnect during migration; verify restored snapshot after accidental failure in *test DB only*.

## 8. Crash, reconnect, failover and PITR plan

Failure models are not interchangeable. Test: (A) Go process kill; (B) PostgreSQL process crash with durable storage surviving; (C) network partition/connection reset; (D) host/storage loss; (E) configured async/sync standby promotion; (F) failed schema deploy. Use disposable staging topology and synthetic accounts exclusively.

| Fault | Injection observation point | Acceptance and evidence |
|---|---|---|
| Go kill | Before DB commit, just after DB commit but before ACK | No ACK for uncommitted action; after-commit retry uses same idempotency key and must not duplicate grant |
| PostgreSQL process crash | During transactions with WAL storage intact | Durably acknowledged writes survive supported crash-recovery; no partial multi-row mutation |
| TCP partition / timeout | During hero selection, combat and DB-backed reward | Bounded write queue and reconnection jitter, session/hero state reconstructed correctly |
| Primary failover | With configured async or sync standby | Actual RTO and actual RPO; acknowledge limitations of async replication |
| PITR restore | From base backup and archived WAL to chosen timestamp | Restored independent DB matches target-time ledger, schema version and invariant checks |
| Schema migration failure | During expanded-schema coexistence | Safe abort or code rollback with compatible schema, no corruption and no invisible retry loop |

**Provisional recovery objectives:** game process RTO ≤120 s; HA database failover RTO ≤300 s *if configured*. For app process / PostgreSQL process crash **with durable storage preserved**, target zero loss of already committed and acknowledged critical writes. Do **not** claim RPO=0 under lost storage or async standby failover without a separately verified replication design; operator must approve an explicit RPO objective for that failure class. PITR is PASS only after full restore and independently checked state reconciliation, not merely because a backup file exists.

Recovery with 5k reconnecting clients must avoid a synchronized retry storm: use bounded exponential backoff with jitter, max pending sessions, admission control and observed reconnect percentiles; no infinite blocking or unbounded database pool acquisition.

## 9. Instrumentation and evidence schema

**Mandatory every run:** immutable V2 charter SHA and V1 evidence references; client/native binary SHA-256; Go server SHA/version/config hash; generator SHA/seed/config; approved target allowlist; actual staging CPU/RAM/NIC/storage/network, Go version, PostgreSQL version/schema migration; number of synthetic users and database rows; timestamp window and synchronized clocks. Store credentials separately, never in artifacts or source control.

**Generator measures:** offered/achieved TCP accepts, valid authenticated CCU, session churn, handshake/auth completion, per-opcode planned/sent/acknowledged/error rates, fragmented/coalesced frames, server-to-client bytes, p50/p95/p99 per operation and per time window, backlog scheduler lateness, generator FD/CPU/heap/network saturation.

**Go measures:** network read/write latency, active sessions, in-memory state mutation duration, game tick/update duration, bounded queue depth and oldest age, goroutines, GC pause time, CPU/RSS, errors split by protocol vs business vs DB, retry/reconnect success.

**PostgreSQL measures:** semantic read/write ops, query p50/p95/p99, pool acquire p95/p99, checked-out pool connections, DB CPU/memory, IOPS and fsync, WAL/checkpoints, locks/deadlocks, migration blocking, replication lag, disk space and autovacuum. Capture query plan snapshots for hot statements using safe staging methods.

**Correctness oracle:** expected and observed account/hero/inventory/progression state, mutation idempotency keys, acknowledged-before-crash flags, post-recovery reconciliation, unique/foreign-key/ownership invariant results and time-series integrity check. Avoid exporting copyrighted data payloads or raw authentication tokens.

Output layout *when an approved V2 run exists*:

```text
artifacts/perf/5000ccu/<run-id>/
  manifest.json
  scenario.yaml
  protocol-vector-references.json
  offered-achieved-and-latencies.csv
  server-metrics.csv
  pgxpool-postgres-metrics.csv
  correctness-oracle.json
  migration-timeline.md
  failure-and-recovery-timeline.md
  independent-review.md
  final-gate-verdict.json
```

## 10. Decision logic, blockers and independent review

**STOP immediately:** unauthorized target; incorrect source/contract digest; invalid credential/permission scope; critical data inconsistency or double reward; unbounded queue/FD/RSS; generator saturation masking offered load; disk/WAL exhaustion risk; migration that corrupts or reassigns hero identities; absent explicit permission for destructive fault injection. Stop creates a finding and does not change V1 task state.

Each test has `NOT_RUN`, `PASS`, `FAIL`, `BLOCKED` or `INVALID_MEASUREMENT`; never mark an unexecuted or synthetic workload as real-game PASS. Separate producer test author/runner and independent reviewer, with review of golden protocol evidence, code, exact commands, immutable outputs, source hashes, numerical SLO comparison and reproducibility.

| Server gate | Needed evidence |
|---|---|
| S1 — Protocol | T00/T01/T02/T08; binary-derived vectors and parser tests |
| S2 — Authentication | T05/T09, duplicate and reconnect session proof |
| S3 — State/Heroes | Verified A∪B canonical ID mapping, role/world state and T07 |
| S4 — Gameplay | T03/T04 plus real observed skill/combat result evidence |
| S5 — Persistence | T06/T07/T09/T10/T11 plus restore and invariants |
| S6 — E2E | T13 real Android APK↔Go↔PostgreSQL, reviewer, regression |

**Release decision:** 5,000 CCU production capacity is `GO` only when the stated CCU and achieved traffic are both reached, all mandatory SLOs and correctness gates pass, migration and recovery tests pass at approved objectives, the generator is not the limiter, and independent reviewers approve. A simulated Go client cannot replace real Android functional proof. A 7,500-CCU headroom stress test is optional; a `FAIL` in a severe overload test may still be acceptable if overload degrades safely *and the mandatory 5k test passes*.

## 11. Handoff to Agent Orchestrator (for future V2 only)

After owner approval, safe V1 checkpoint/handoff and NEW V2 project creation, give ONE top-level goal: implement source-validated Go protocol load generator, test oracle and isolated staging; autonomously plan gated T00–T13 and report evidence-driven PASS/FAIL with independent review. Agent must not infer original server fields, adjust SLOs post hoc to get green results, or run against any unauthorized service. No second watchdog competes for Ghidra/CPU/DB resources.

**The preparation of this plan has not created, resumed, paused or modified any Harness V1/V2 project, executed Go code, contacted a game server, or changed a database.**

## 12. Reference documentation

- Proposed RE Dragon V2 charter: https://github.com/khanhpn308/re_dragon/blob/main/docs/production/RS_UNIFIED_HEROES_V2_FULLSTACK.md
- Proposed RE Dragon Go standard: https://github.com/khanhpn308/re_dragon/blob/main/docs/production/GO_GAME_SERVER_AGENT_STANDARD_V1.md
- Client-only P2 reverse engineering: https://github.com/khanhpn308/re_dragon/blob/main/docs/returnsaiyan_p2_protocol_model.md
- PostgreSQL query stats: https://www.postgresql.org/docs/18/pgstatstatements.html
- PostgreSQL online index: https://www.postgresql.org/docs/current/sql-createindex.html
- PostgreSQL PITR: https://www.postgresql.org/docs/current/continuous-archiving.html
- PostgreSQL standby/failover: https://www.postgresql.org/docs/current/warm-standby.html
- `pgxpool`: https://pkg.go.dev/github.com/jackc/pgx/v5/pgxpool
- `net.Conn` API: https://pkg.go.dev/net
