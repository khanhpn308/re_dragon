# RS-UH-PROD-V2: Go Standard v1.1 Backaudit release gate

**Operator safety:** project `ac927848392a4a6e` must remain `PAUSED` and the
watchdog tmux session `re-dragon-quota-watchdog` must be stopped. Never
trigger `/retry` or `/resume` to install this gate.

* `python3 -m re_harness.release_gate --project ac927848392a4a6e --check`
  validates live Harness SQLite and proposed DAG changes **read-only**.
* After inspecting the output and confirming the existing backup, run
  `python3 -m re_harness.release_gate --project ac927848392a4a6e --apply`
  to atomically insert `v2-go-v1-1-backaudit` and add it as a dependency of
  `final-fullstack-release-audit`. No existing VERIFIED task, acceptance,
  artifact, or T01-T04 REVIEWING checkpoint is mutated. Output must say
  `INSTALLED` or `ALREADY_INSTALLED`.
* Run `--check` again and independently verify the new task is PENDING, the
  final release task includes it in dependencies, and Watchdog remains PAUSED.
* Telegram Request #2 stays QUEUED; when eventually forwarded, the Agent must
  **work the already-existing audit task**, not create a duplicate.

The gate is a **necessary but not sufficient** condition for final GO.
The AUDIT acceptance requires remediation of findings and independent review
BEFORE it can be VERIFIED. Existing S1-S5 statuses cannot be retroactively
declared v1.1 compliant. Final GO additionally requires the full frozen V2
charter and E2E evidence. If a finding requires separate remediation, it must
be a child/dependency verified before the audit is closed. If the Agent cannot
enforce these conditions, it must BLOCK/NEEDS_USER; not bypass the gate.

`--check` never writes. `--apply` fails closed on a missing/unpinned/unpaused
project, active Watchdog, claimed or altered Final Release, unverified S1-S5,
conflicting pre-existing task, or task capacity overflow. All changes run under
`BEGIN IMMEDIATE` and roll back together on failure. Project V1 is never
selected or changed. Offline tests:
`python3 -m unittest -v tests.test_release_backaudit_gate`.

This mechanism does **not** create/verify an APK or run a live 5,000 CCU test.
