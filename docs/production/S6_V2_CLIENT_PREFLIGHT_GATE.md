# RS-UH-PROD-V2 — S6 V2 Client Preflight (blocking dependency)

Project: `ac927848392a4a6e`.

## Observed problem

`/task S6-PREFLIGHT-BLOCKING` queued Telegram request #3 but did **not**
alter the Harness DAG. S6 already sits in PENDING and can be claimed before
the queued request is forwarded. A textual message is not a scheduling barrier.

## DAG enforcement

`python3 -m re_harness.s6_preflight_gate --project <id> --check` is read-only.
`--apply` under a pinned PAUSED checkpoint inserts one independent AUDIT
task (`s6-client-v2-preflight`) and appends its task key to **both** existing
`s6-android-go-e2e` and `final-fullstack-release-audit` dependencies. Both
original statuses remain PENDING; old dependencies remain intact. The gate
starts PENDING, requiring independent review and evidence for VERIFIED.

Conditions: project ACTIVE, S6 and Final PENDING/unleased, no in-flight or
SUBMITTED tasks, S6 dependency charter unchanged, no prior S6 evidence or
side effects, watchdog PAUSED, no live Agent PID and no tmux Watchdog session.
Input graph and post-update DAG are cycle-checked. Single SQLite
BEGIN IMMEDIATE / commit and immutable event; any failure rolls back.

## Acceptance criteria

The preflight verifies a **real V2** Android client build and distinct SHA;
package identity, certificate, ABI, updater, bootstrap and game endpoint
configuration; local Go server, DB connectivity, TCP protocol compatibility,
device/ADB and independent reviewer evidence. The extant
`dist/ReturnSaiyan-UnifiedHeroes-signed.apk` with V1 SHA
`ff09e65a9f89c4773d6de904ce00443860feb3331a905fcd9508ea287685d583`
is not inherently proof of V2 compatibility.

If V2 client code/binary is missing, the Agent must create and independently
review bounded implementation/remediation tasks and **retain the blocking
preflight** until those tasks meet its acceptance. No existing Android app
installation/uninstallation, no V1 modification, no third-party endpoints,
no false claims that simple ADB readiness equals E2E success.

## Procedure

1. Maintain PAUSED operator checkpoint; backup SQLite using SQLite backup API.
2. Update Git after merging PR, run unit tests and preflight `--check`.
3. Run `--apply`; immediately rerun `--check` and `/tasks`.
4. Confirm S6 and Final dependencies explicitly include
   `s6-client-v2-preflight`. Statuses: preflight PENDING, S6 PENDING,
   Final PENDING, project ACTIVE, Watchdog PAUSED.
5. Then and only then operator may `/resume`.
6. Queued Telegram request #3 is informational when gate is already installed;
   no duplicate task should be inserted. Audit and remediation must be based
   on primary evidence and independent reviewer decision.
