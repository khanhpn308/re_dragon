# S6 Android Recovery Hotfix: BLOCKED Project State

## Root cause
The previous Environment Recovery module required `auto_projects.status=ACTIVE`.
But the Harness scheduler intentionally sets a project to `BLOCKED` when no
runnable work remains and S6 cannot run without an Android device. That
prevented recovery even when Linux ADB worked and Watchdog was explicitly
PAUSED. The Watchdog also invoked its terminal-project gate before attempting
environment recovery, so even automatic recovery could not run.

## Guarded resolution
* Permit recovery of an `ACTIVE` or `BLOCKED` project **only if S6 is the
  one and only BLOCKED task**, and S6's recorded blocker matches the known
  missing ADB/device reason.
* Keep all existing device, candidate APK, dependency, lease, attempt,
  partial-artifact and operator-pause guards.
* Under a single `BEGIN IMMEDIATE` SQLite transaction update
  `S6: BLOCKED -> PENDING` and, only if needed,
  `project: BLOCKED -> ACTIVE`, with immutable `ENVIRONMENT_RECOVERED`
  event recording old project/task state. A failure rolls back both changes.
* Move automatic environment recovery to before terminal project-status
  inspection at the beginning of a Watchdog turn. Never auto-resume an already
  PAUSED or NEEDS_USER Watchdog; user-initiated manual --apply remains required.
* Keep S6 unverified until independent Android↔Go↔Postgres E2E checks pass.
  Candidate APK validity only checks ZIP/manifest/DEX and SHA; does not prove
  V2 compatibility or signing. No APK installation or third-party endpoint.

## Recovery on current project
The user is currently at a stopped Watchdog checkpoint. After merge and
sync, run `--check` first. If READY_TO_REQUEUE, run `--apply` only while
PAUSED, after snapshotting SQLite. Confirm both S6 PENDING and project ACTIVE
with the Watchdog still PAUSED. Only then explicitly /resume.

## Tests
`python3 -m unittest discover -s tests -p 'test_environment_recovery.py' -v`
and
`python3 -m unittest discover -s tests -p 'test_marker_checkpoint_recovery.py' -v`.
