# V1 → V2 full-stack safe handoff

**Status: V2_CHARTER_APPROVED / V2_PROJECT_NOT_CREATED** (2026-10-27). V1 Harness reported COMPLETE in owner screenshot; local controller status and product artifacts NOT_VERIFIED.

- V1 project ID: 20d3b705a4314d80 (Telegram COMPLETE/ACCEPTED and 10/10 VERIFIED, 2026-10-27 ~17:13 Asia/Ho_Chi_Minh). No local product evidence audit yet.
- Frozen client charter: 52435214aab34c9083d2d3dc8ac18979c4c64348:docs/production/RS_UNIFIED_HEROES_V1.md.
- New candidate charter: docs/production/RS_UNIFIED_HEROES_V2_FULLSTACK.md.
- Candidate coding policy: docs/production/GO_GAME_SERVER_AGENT_STANDARD_V1.md.
- No V2 project has been created; no watchdog was switched and no Android/Go build was initiated by this documentation work. Requirements approved, execution requires authorized local activation.

## Precondition gates for transfer

1. Inspect current V1 /status, /progress, /tasks, /approvals and Harness SQLite task/evidence logs; record running PID, current turn, lease state, active subagent review and resource reservations.
2. Freeze every transferable artifact by hash, producing/reviewing task IDs, original APK/XAPK SHA-256 and why the evidence actually applies. Do not copy VERIFIED status directly.
3. V1 state is already reported ACCEPTED in Harness; do not mutate/reopen it. If G6/G8 lack primary proof, report V1 product evidence as NOT_VERIFIED in V2 H0 and open V2 remediation tasks. Never misrepresent prior SQLite ACCEPTED as independently proven functionality.
4. At a safe checkpoint obtain explicit owner approval, drain running workers and Ghidra lease, prevent new V1 turns and retain immutable SQLite checkpoints. Do NOT run two quota supervisors/heavy agent sessions concurrently.
5. V2 charter and Go game-server standard are owner-approved on 2026-10-27. After V1 supervisor is IDLE/COMPLETE with no live Agent/lease, operator may use Telegram /newgoal to create a NEW project pinning exact charter commit SHA. Never rewrite old project acceptance or reuse verified task status blindly. H0 audits the old evidence before any inheritance.
6. Bootstrap bounded dependency graph containing H0, S1–S6, G client remediation if needed, and T00–T13 from approved test design; check actual first Go task results, genuine protocol evidence and final 5k CCU gates. Preserve V1 rollback path.
7. If transition fails, safely leave projects stopped or restore V1 checkpoint with explicit operator decision. Never hide a partially transferred state.

No commands are executed on the operator's WSL machine by this preparation; a running Watchdog must not be interrupted by a documentation update.

## Mandatory preflight before Telegram V2 /newgoal

1. Use /status and /projects: verify V1 is not AGENT_RUNNING and identify existing V2 duplicate if any.
2. On local WSL workspace, only with no active agent editing files: check `git status --short`; avoid overwriting WIP; `git pull --ff-only origin main` for the pinned charter only when safe. Do not blindly reset/clean.
3. Fetch /report and per-task details for V1; preserve exact local artifact hashes and any Android test evidence. Classify unknown/missing evidence NOT_VERIFIED even though the Harness says COMPLETE.
4. Send a concise `/newgoal <goal> | <acceptance>` within Telegram 500/1000 character limits with the pinned commit SHA and both charter/standard paths; confirm in Telegram. /newgoal creates a new independent Harness SQLite project; do NOT use ./dragon start default fallback because it may seed V1.
5. Verify new project ID, `/status` and `/tasks`, and first H0 handoff audit task. NO full-stack GO until S6 real Android and 5k test design evidence verified.
