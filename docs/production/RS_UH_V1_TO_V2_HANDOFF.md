# V1 → V2 full-stack safe handoff

**Status: PREPARED_NOT_EXECUTED** (2026-10-27)

- Running client project ID: 20d3b705a4314d80 (ACTIVE in user's last screenshot).
- Frozen client charter: 52435214aab34c9083d2d3dc8ac18979c4c64348:docs/production/RS_UNIFIED_HEROES_V1.md.
- New candidate charter: docs/production/RS_UNIFIED_HEROES_V2_FULLSTACK_DRAFT.md.
- Candidate coding policy: docs/production/GO_GAME_SERVER_AGENT_STANDARD_V1_DRAFT.md.
- No V2 project created, no watchdog switched and no Android/Go build initiated by these docs.

## Precondition gates for transfer

1. Inspect current V1 /status, /progress, /tasks, /approvals and Harness SQLite task/evidence logs; record running PID, current turn, lease state, active subagent review and resource reservations.
2. Freeze every transferable artifact by hash, producing/reviewing task IDs, original APK/XAPK SHA-256 and why the evidence actually applies. Do not copy VERIFIED status directly.
3. Keep V1 G6 or G8 BLOCKED when missing server runtime evidence. Never force V1 ACCEPTED simply to permit server build.
4. At a safe checkpoint obtain explicit owner approval, drain running workers and Ghidra lease, prevent new V1 turns and retain immutable SQLite checkpoints. Do NOT run two quota supervisors/heavy agent sessions concurrently.
5. Approve V2 charter and Go agent rulebook; then create NEW project and pin V2 commit SHA + project ID. Install the new rule routing only in the V2 scoped task context, not by changing the old project's acceptance.
6. Bootstrap bounded dependency graph for S1–S6 and relevant G tasks; check genuine first Go task results and real protocol evidence. Preserve V1 rollback path.
7. If transition fails, safely leave projects stopped or restore V1 checkpoint with explicit operator decision. Never hide a partially transferred state.

No commands are executed on the operator's WSL machine by this preparation; a running Watchdog must not be interrupted by a documentation update.
