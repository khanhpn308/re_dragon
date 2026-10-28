# P0 — RS HERO SUMMON → OWNERSHIP → FORMATION → DUNGEON

Status: OPERATOR-SUPPLIED GAMEPLAY CONTRACT / NOT IMPLEMENTATION EVIDENCE
Project: RS-UH-V2-REAL-DUNGEON-COMBAT-E2E
Baseline: preserve immutable accepted V2 APK, evidence, old Harness task states and PostgreSQL user data.
Priority: P0 blocking dependency for stage/dungeon battle E2E.
Device: physical Realme RMX3461 / 10b3139c, ADB reverse 30001/30008 to operator-local services.

## 1. Confirmed GUI truth supplied by operator

- New account can log in and reach MAIN_LOBBY. Server starter **role** does not imply ownership of a usable **hero**.
- MAIN_LOBBY bottom menu has `Triệu hồi` and `Đội hình`; bottom-right has distinct `Phó bản` and `Chiến đấu` entrances.
- At `Triệu hồi`: choose **Dragon God of Earth** (left, `3–5 stars`) and **`Ước 1 lần`** (leftmost green button). Do NOT default to Namek (right), 10x, or paid/premium action.
- Current failure: tapping summon makes the client freeze/unresponsive. Treat as a protocol/response/UI-state blocker; do not infer completion from animation or tap success.
- At `Đội hình`: active formation is the right-hand column labeled `ĐỘI HÌNH` with `+` slots; do NOT mistake the middle equipment `+` slots for battle formation. Tapping an empty formation slot must show the account's owned hero collection, from which the newly summoned hero can be selected.
- Stage mode may show `Chưa xếp anh hùng nào.` This means no assigned formation, independent of whether the player owns a hero.
- Earlier adventure/flying-cloud screenshots are **not** dungeon combat evidence. Main lobby is **not** an in-battle world.

## 2. Mandatory dependency DAG

`ACCOUNT_AUTH -> VERIFY_HERO_OWNERSHIP -> (IF NONE: SUMMON_X1 -> SERVER_ATOMIC_GRANT -> VERIFY_HERO_OWNERSHIP) -> FORMATION_SLOT_SELECT -> FORMATION_PERSIST -> FORMATION_RELOAD_VERIFY -> PHO_BAN/CHIEN_DAU -> STAGE_ENTRY -> REAL_BATTLE -> REWARD_AND_PROGRESS_PERSIST`.

Create a separate audit/task for SUMMON_FREEZE_DIAGNOSIS; it is a hard gate. Do NOT keep tapping, retrying indefinitely, or proceeding with a simulated hero.

## 3. Summon freeze root-cause investigation

1. Capture fresh timestamped screenshot and Android logcat **before** tapping; check UI responds prior to input.
2. Tap Earth Dragon's `Ước 1 lần` once only; wait within a bounded timeout. Capture logcat, Android ANR/crash indicators, server receive/send logs, client transport errors, TCP frames, and PostgreSQL changes. Only retry after identifying a specific remedial hypothesis.
3. Trace client summon-button handler -> actual C2S opcode, field layout, encryption framing, request sequence and cost -> Go server handler -> S2C response (including null-terminated strings, packet format, data types, counts) -> client parser/callback -> UI result screen. Determine whether freeze is ANR, native crash, waiting for absent/invalid S2C, or asset/UI fault. **Never guess an opcode**.
4. If backend lacks the relevant handler/response, implement a minimal client-compatible version based on observed binary/protocol behavior. Add malformed-frame, timeout and duplicate-request tests. No access to third-party servers.
5. Verify the client returns to a responsive state and displays a valid summon result; document observed hero ID/rarity, requested cost and authoritative outcome.

## 4. Authoritative hero ownership / server contract

- On a legitimate Earth x1 summon, server picks **one eligible hero** at random from the actual supported ReturnSaiyan/Global unified roster. Use configured original drop rules if available; if not, propose a clearly labeled local-test policy, not an invented claim about official rates. Use a secure RNG and record the selection outcome for audit.
- Respect actual game-currency semantics. If first summon requires resources not present on a fresh account, determine the intended tutorial/free summon path, or obtain explicit approval for an isolated **test-only** funding fixture; do not silently alter real balances or issue premium purchases.
- In **one database transaction** validate user, eligibility and cost; debit cost if appropriate; create the unique hero ownership record linked by account_id; persist instance attributes; and record a unique summon transaction/operation ID. Then send the exact client-accepted S2C response.
- Idempotency: retries/timeouts must NOT create duplicate grants or double-charge; save transaction/response record or enforce equivalent unique constraint. Roll back on failure. Never directly inject a hero in DB as a shortcut for passing the *summon* test.
- Distinguish account/role starter hero metadata from a hero instance in owned inventory and from a hero assigned to formation. Use current schema if viable; otherwise introduce versioned additive migrations with backwards compatibility and rollback plan. Never rewrite existing migration or user data.
- After relogin, same owned hero must reappear in the collection. The client list must be populated using DB-backed authoritative data rather than hardcoded mock entries.

## 5. Formation contract

- From `MAIN_LOBBY` open `Đội hình`, tap an empty `+` **under the right-hand `ĐỘI HÌNH` heading**, and verify that the owned-hero picker opens. If picker is empty despite DB ownership, trace its C2S/S2C and list filtering; implement missing handlers.
- Select an eligible owned hero, persist assignment of `(account, formation slot, hero_instance_id)` server-side. Enforce ownership, uniqueness and valid slots. Do not alter equipment slots, reserve slots or another account.
- Verify visible icon in selected slot, correct selected hero details, and durability after leaving/reopening `Đội hình` and after relogin.
- Only then reopen actual `Phó bản` and `Chiến đấu` mode separately. `Chưa xếp anh hùng nào.` must not recur for a valid lineup.

## 6. Hero stats — domain contract; formula intentionally deferred

- **Tư** = aptitude/quality (stored per hero; preserve game's actual allowed domain/rules).
- **Lực** = combat power (derived or recomputed from stats). Aptitude, level, promotion and other stats affect it, but **do not invent weights or formula in this task**. Record unknown formula as separate design issue; preserve original semantics where provable.
- **Level** starts at its game-defined initial value, max **200**. **Nâng cấp** increases Level; it is not promotion.
- **Thăng cấp** changes a separate promotion/advancement tier `+0, +1, ... +40`. This is not Level. Store independently with explicit constraints and validation.
- Define clear read/write/API representation for `hero_instance_id`, `hero_code`, `aptitude`, `level`, `promotion_tier`, and combat-power value/status. Do not falsely report a recalculated `Lực` until a sourced formula exists.
- Any displayed sample values in the operator screenshots, especially `Lv.200`, `Tư 123`, `Lực 895050` and very large currency counters, are **reference UI**, not defaults for new accounts and not proof of actual test balance.

## 7. State-aware and bounded E2E acceptance

A. LOGIN and MAIN_LOBBY: screenshot + device log proof. B. SUMMON_SCREEN and Earth x1: correct screen before tap. C. SUMMON_RESULT: one valid hero returned; client responsive; matching server opcode/response. D. OWNERSHIP: matching hero instance in account DB and UI, including after relogin; transaction idempotency proven. E. FORMATION: select right-hand formation `+`, list owned heroes, assign, persist/reload; no empty-formation dialog. F. DUNGEON: physical `Phó bản` and `Chiến đấu` navigation (keep separate); actual stage entry, visible active battle, enemy reaction, result and reward persistence. Screenshots must show the claimed screen, not merely carry descriptive filenames.

- Use state recognition based on screenshot/UI+client/server observations; known tap coordinates only after screen-state gating and follow-up validation. Maintain a maximum of three **hypothesis-driven** retries per failing gate with a time budget; stop with exact blocker and Telegram `NEEDS_USER` only if truly operator-dependent.
- Each captured screenshot and server/logcat/DB item gets UTC timestamp, SHA-256, device identity, test-account ID and correlated transaction ID. Store in NEW immutable run-specific directory; never overwrite accepted `evidence/s6_e2e/` files.
- Unit, protocol, integration, idempotency, migration, and Android physical tests required. Independent reviewer evaluates actual screenshots as well as logs; no synthetic evidence, unsupported auto-PASS or bypass of review gates.
- Hard failure if client freezes on summon, no owned hero appears, formation is empty after save, or client only reaches Adventure/flying-cloud scene while calling it combat.

## 8. Execution / noninterference

Do not launch concurrent Agents, seize the Android device from an ongoing test, or restart active Harness workers indiscriminately. Add this as blocking P0 dependency for the active dungeon project using the normal controller task queue. Read and preserve earlier `RS_REAL_DUNGEON_COMBAT_E2E_HANDOFF.md`. After a new authoritative approved report, do not retroactively edit historical ACCEPTED results; attach an acceptance discrepancy record with source-grounded remediation results.
