# Environment Recovery — Android S6 (WSL2/Telegram)

Scope: RE Dragon V2 `ac927848392a4a6e`. This is a **task admission**
mechanism, **not** an Android E2E pass or source of release approval.

## Automatic mode

At the start of each new Watchdog turn (no CLI child running), check only
`s6-android-go-e2e` if it is already `BLOCKED` for exactly the known
absence-of-local-ADB/test-device reason. An existing project stays pinned.
Conditions: project ACTIVE, S6 unowned and unleased, retry budget available,
all S6 dependencies VERIFIED, Linux ADB available, exactly one authorized
online device, device model `RMX3461`, and readable candidate
`dist/ReturnSaiyan-UnifiedHeroes-signed.apk` with a ZIP manifest/DEX.
Record APK SHA-256 **only as a candidate**, never proof of signing or
V2 protocol compatibility.

A single SQLite BEGIN IMMEDIATE transaction conditionally requeues S6
`BLOCKED -> PENDING` and appends `ENVIRONMENT_RECOVERED` to auto_events
with old blocker, test device, and APK SHA. No prior VERIFIED state changes.
Watchdog still schedules regular independent reviewer and Android E2E gates;
no installation or remote server access occurs.

When any prerequisite fails, do not unstick S6; other independent tasks run.
When Watchdog is STOPPED / NEEDS_USER, auto mode does not override it.

## Telegram

`/environment` = safe read-only preflight; reports missing ADB/device/APK.

`/recoverenv` = privileged private-chat action; only applies when operator
has PAUSED Watchdog and no agent process owns the runtime. Never bypasses
task lease or missing checkpoint. `/resume` remains a separate explicit
operator decision following safety assessment.

The Telegram monitor sends a discrete deduplicated event message when S6
is requeued; this event is independent of periodic progress updates.

## Manual offline commands

```bash
cd ~/returnsaiyan-re
python3 -m re_harness.environment_recovery --project ac927848392a4a6e --check
# only after explicitly PAUSING Watchdog and letting current turn finish:
python3 -m re_harness.environment_recovery --project ac927848392a4a6e --apply
```

No `adb install`, APK patch, TCP probing, Android gameplay, or server
connection takes place during environment recovery. The candidate
`dist/ReturnSaiyan-UnifiedHeroes-signed.apk` may be the V1 artifact and
**must not** be treated as a valid V2 build without S6 evidence.

CI: `python3 -m unittest discover -s tests -p 'test_environment_recovery.py' -v`.
