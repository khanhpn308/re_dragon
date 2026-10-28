# RS-UH-V2 REAL DUNGEON / COMBAT E2E — correction handoff

**Date:** 2026-10-28  
**Historical project:** `6181397b27b247e9` (`ACCEPTED` in Harness; acceptance disputed by later independent evidence inspection)  
**Execution rule:** Do not modify the accepted baseline, original screenshots/manifests, APK, SO, user accounts, or previous acceptance history. Record all new testing in new immutable, per-run evidence directories. Do not start while another Harness project/Agent holds the execution lease.

## 1. Confirmed facts, not assumptions

1. On the real RMX3461, the screen in `evidence/s6_e2e/03_world_entry.png` is the **Main Lobby**, after successful guest authentication and server entry. It is **not** proof of entering a playable combat stage.
2. The bottom-right **Phó bản** and **Chiến đấu** entries are distinct navigation targets. Explore and validate each path separately; do not assume they are equivalent, and do not mistake **Phiêu lưu** / flying-cloud Adventure mode for dungeon/stage combat.
3. Prior P4 `04c_combat_skill.png` and `04d_hero_roster.png` displayed a flying-cloud / **Connecting Server...** scene, not a verified combat effect or hero roster. Packet logs alone do not establish a completed battle.
4. Authentication, local TCP handshake and persistence of an initial account/role are supported by previous evidence. Manual character creation, selected dungeon, actual stage start, in-stage movement, victory/rewards, and stage progression have not been independently established.

## 2. Source-code diagnosis (read the actual repository code)

| Script | Location in uploaded revision | Failure mechanism |
|---|---|---|
| `tools/e2e_runner/orchestrator_gameplay_e2e.py` | ~138–155 | Blind swipe `(450,750)->(650,750)` and tap `(2000,850)` directly from post-login; no scene/transition validation. Screenshot labeled gameplay regardless of displayed scene. |
| `tools/e2e_runner/test_p4_actions.py` | ~91–96 | Unconditional BACK and tap `(1850,180)` may dismiss or navigate incorrectly; no detected popup precondition. |
| Same | ~110–131 | Three blind swipes interpreted as movement; no in-stage position, movement opcode, or stage-state assertion. RGB pixel difference alone is insufficient. |
| Same | ~134–155 | Three guessed combat-button taps; no proof of stage entry, enemy state, skill animation, damage, or result. |
| Same | ~157–171 | Tap `(1380,1000)` assumed to open roster; screenshot filename and description asserted success without scene validation. |
| Both | startup/teardown | Fixed sleeps, unchecked service readiness; mutable shared evidence paths; hard-coded DB credential; logcat clear and unconditional app force-stop. These can invalidate existing evidence and create collision with active runs. |
| P4 manifest vs uploaded source | source ~102–107, 126–131, 149–154, 165–170 | Uploaded P4 source contains per-image timestamps but the earlier uploaded `p4_run_manifest.json` does not. Establish exact source revision used in that run; do not silently retrofit old timestamps. |

**Important:** Python syntax validation passing, successful ADB taps, or a zero-exit script are not end-to-end gameplay acceptance.

## 3. Implementation requirements

### A. Preserve provenance and preflight

- Check worktree/commit, current Harness project/lease, ADB device `10b3139c`, Android resolution/orientation, reverse mappings `30001` and `30008`, local Go server, and PostgreSQL readiness. Respect Windows ADB bridge `ADB_SERVER_SOCKET` when configured.
- Pin source SHA/commit, APK SHA and script SHA. Backup database only through approved mechanisms and avoid modifying unrelated accounts.
- Create unique `evidence/real_dungeon_combat/<UTC_run_id>/`; do not overwrite `evidence/s6_e2e/` or accepted reports. Redact passwords, tokens, DSNs and PII from logs; use an injected database secret rather than embedding it in source; review/rotate credentials if the exposed values are live.
- Run only one game-testing agent; use bounded retries and acquire/retain the approved single-agent lease.

### B. Replace blind taps with observable scene-based navigation

Model an explicit state machine with at least these classes:

`TITLE -> SERVER_SELECTION -> MAIN_LOBBY -> PHO_BAN_MENU / CHIEN_DAU_MENU -> STAGE_SELECTION -> STAGE_LOADING -> IN_STAGE_BATTLE -> RESULT_VICTORY / RESULT_DEFEAT -> REWARD_SETTLEMENT -> STAGE_SELECTION/MAIN_LOBBY`.

Also classify `PHIEU_LUU`, `CONNECTING_SERVER`, `UNKNOWN`, and `ERROR` as distinct states. Do not treat them as combat success.

- Detect the current state from the **actual captured Android screen** together with matching client/server events; use screen-anchored UI recognition, normalized geometry based on the native screenshot and orientation, and documented confidence thresholds. Hardcoded pixel coordinates are not sufficient by themselves.
- Navigate both **Phó bản** and **Chiến đấu** separately. Capture a verified screen immediately before and after every navigation action; assert expected destination rather than waiting a fixed interval.
- On unknown scene, popup, loading timeout, or connection error: save evidence, classify the blocker, attempt only safe bounded recovery, and never advance the state machine on faith.
- If original menu logic or network payload is missing from the local server, trace the actual APK handler and protocol, implement only the clean-room local handler required, add deterministic unit/integration tests, then re-run physical Android testing. No invented protocol definitions, mock Android evidence, or unapproved APK mutation.

### C. Real dungeon combat acceptance (not Adventure)

Evidence must show the full flow on the physical RMX3461:

1. Logged-in Main Lobby with both entry buttons identified.
2. Open the **Phó bản** branch and document its actual menu and stage list. Separately inspect **Chiến đấu** and document whether it leads to the same or different stage flow.
3. Select a specific unlocked stage, recording stage ID/name and initial progress in PostgreSQL if schema supports it.
4. Enter a genuine in-stage battle, with visual map/combat UI and an independently correlated server-side stage/session transition.
5. Perform genuine in-stage movement and attack/skill on an enemy. Correlate touch input, client telemetry/logcat, relevant network messages, server-authoritative enemy HP/damage/cooldown state, and visible client effect. **Do not assume previous Opcode 0x25 represents dungeon combat.**
6. Observe definitive victory or defeat and, for victory, reward settlement and return to stage selection. Verify XP/item/progression persistence with a before/after PostgreSQL transaction-consistent comparison.
7. Independently navigate to the real hero roster screen and confirm displayed heroes/attributes. Do not use a filename as proof of state.
8. Repeat a representative stage flow after reconnect/restart to prove state persistence and avoid transient false positives.

### D. Evidence and gate rules

- Each transition: UTC timestamp, input/action, pre/post screenshots, SHA-256, actual image dimensions and byte length, expected/observed UI state, client/server correlation IDs, relevant DB records, test result.
- Structured JSON manifest must identify source commit, APK hash, runner hash, Android serial, screen classification decision, and explicit PASS/FAIL/UNKNOWN per gate. Securely redact raw credentials and personal data.
- If stage combat cannot be reached, set **BLOCKED_WITH_EVIDENCE** and name the exact UI/protocol/server blocker; do **not** report `PASS` based on synthetic movement or generic `0x25` logs.
- Independent reviewer must open and inspect actual images, verify SHA-256 of bytes on disk, inspect raw logs, and prove the claim that each image is a genuine scene of the named state. A reviewer name or actor string alone is not independence proof.

## 4. Execution order and autonomy constraints

- If `RS-REMOTE-OPS-HARDENING` is active, do not interrupt it. Schedule this as the next pre-approved goal only after that project's ACCEPTED gate, using supported Harness queue/confirmation semantics.
- Preserve historical Harness acceptance but append a **DISPUTED_ACCEPTANCE** finding for the prior combat/roster claims. Never edit historical screenshots, review reports or SQLite status directly.
- Resolve in order: P0 evidence freeze and preflight; P1 mode classification; P2 Phó bản UI path; P3 Chiến đấu UI path; P4 stage entry/server contract; P5 in-stage movement and combat; P6 reward/progression persistence; P7 roster independently; P8 repeat and independent review.
- Alert operator via Telegram only on true physical/user auth blockers or bounded recovery exhaustion. Do not declare `GO` for release until actual dungeon combat has independent verified evidence.

## 5. Required final deliverables

- New corrected runner/state machine (do not silently replace archived old source).
- Navigation trace for both main-lobby buttons.
- Source/byte hash manifest and unedited screenshots, logs and database comparisons.
- Explicit known-vs-unknown packet map for real dungeon mode.
- Independent review and discrepancy register linked to historical project ID.
- Reproducible one-command offline unit/integration checks plus an operator-local Android E2E command.

**Exit criteria:** `REAL_DUNGEON_COMBAT_E2E = VERIFIED` only when an authenticated physical-device run reaches a stage, demonstrates combat against an actual enemy, settles a result/reward, and persists the corresponding progression with raw evidence and independent review. Otherwise `PARTIAL_WITH_FINDINGS` or `BLOCKED_WITH_EVIDENCE`.
