# ReturnSaiyan Client Rebuild — Functional Slice / Work Package Registry v1

Status: PROPOSED INVENTORY; not a confirmed catalog of original APK features.
Priority P0 = unblock real summon; P1 = playable PvE; P2 = economy/progression/PvP; P3 = extension.

## A. Rules for every leaf Work Package

| Contract field | Mandatory detail | Acceptance gate |
|---|---|---|
| Origin | Original APK family/version, exact SHA-256, installed app vs donor asset | Preserve binary identity |
| Feature | Game domain, unique WP ID, visible player action or one state transition | Single behavior; explicit exclusions |
| Entry | Pre-state, eligible actor, screen, CSB control, Lua callback / JNI entry | Client evidence |
| C2S | Trigger, opcode, field order/type, session, packet CRC/XOR/framing | Source plus physical packet |
| S2C | Reply opcode, data types, callback, error payload, state update | Client reader/callback proof |
| State | Names of states, transition events, retry, reconnect, relogin, cancellation | State-machine tests |
| Data | Account/hero/item keys, transactions, economy ledger, constraints | DB and consistency tests |
| Resources | UI scene, hero.xc actor ID, spine/card textures, localized strings | Validated assets |
| Domain rules | Cost, probability, cap, difficulty, formula, cooldown, eligibility | VERIFIED or OWNER_DECISION |
| Security | Authority split, anti-replay, idempotency, concurrency, exploit boundary | Negative tests |
| Failure | Insufficient currency, missing content, packet error, offline, duplicate request | Explicit state/error result |
| REA scope | Source target list, target SHA, 1–8 functions, XREF depth <=2 | Registered bounded calls |
| Evidence | Function address, XREF/call graph, short source reference, hash, confidence | VERIFIED/INFERRED/UNKNOWN |
| Outputs | Source patch, focused test, evidence document, real-device logs where necessary | Artifacts independently inspected |
| DAG | Specific dependency IDs, independent acceptance and readiness | Verified prerequisites only |

No leaf WP has a wall-clock deadline. If further source analysis is needed
after reaching call/output/function limits, the Agent checkpoints evidence,
splits scope, and resumes; it must not erase already completed work.
A physical Android PASS cannot be asserted from GitHub tests.

## B. Foundation: original APK, reverse engineering, source rebuild

| WP / priority | Single functional boundary | Exact information to extract | Output / positive test | Dependencies |
|---|---|---|---|---|
| F00 P0 | Identify original/current/donor APK | SHA-256 for APK, DEX, .so, resource archives; package, ABI, versions | Versioned binary manifest, read-only artifacts | none |
| F01 P0 | Locate Lua loader/script encoding | Lua bytecode or source headers, resource path, loader decryption, error symbol location | Script inventory with accessible/unavailable classification | F00 |
| F02 P0 | Map Android start-up | Activity→JNI→Cocos2d-x init and screen lifecycle | Verified launch call graph, rebuild feasibility | F00 |
| F03 P0 | Decode framing | C2S/S2C length, seq, XOR, encoding, packet/vector corpus | Golden wire vectors; symmetric codec tests | F00 |
| F04 P0 | Map UI scene to callback | CSB names, tap widgets, Lua event binding, native bridge | Screen/control/function registry | F01,F02 |
| F05 P1 | Map hero/asset IDs | hero.xc, actorId/photoId/cardSpineId, Spine/PKM/atlas, collisions | Automated integrity manifest | F00 |
| F06 P1 | Build reproducible client project skeleton | Java bootstrap, native ABI, Lua runtime, assets, build tools | Minimum build target and explicit blocked areas | F01,F02,F05 |
| F07 P1 | Persist source navigation index | Ghidra program SHA, function address, XREF, packet and Lua refs | Queryable evidence store and reviewer links | F00 |
| F08 P1 | Establish Android evidence runner | ADB device state, screenshot, logcat and DB timestamp correlation | Repeatable physical test + hash manifest | F03,F04 |
| F09 P1 | Build version compatibility matrix | old/ReturnSaiyan/Global client symbols and asset versions | Compatibility report, not simulated playability | F00,F05 |

## C. Account / game session

| WP / priority | Player action | Source or rule uncertainties | Output / verification | Dependencies |
|---|---|---|---|---|
| A01 P1 | Open client, update, select server | Updater manifest/auth callback/host routing | Real start-to-login without external live server | F02,F03 |
| A02 P1 | Guest/login, role select/create | Token, role identifiers, account scope, reconnect | Owned character session; negative auth tests | A01 |
| A03 P1 | Load lobby and initial state | Hero roster, bag, wallet, quest/profile initial payload | All UI state tied to real account | A02 |
| A04 P2 | Disconnect/reconnect/relogin | Token expiry, duplicate session, version mismatch | Persistent state reload and no duplicate grant | A03 |
| A05 P2 | Language/settings | player:lang RPC, persistence and UI callback | Locale survives reload without combat impact | A03 |

## D. Gacha, hero acquisition, ownership, growth (current P0)

| WP / priority | Player action | Exact unknowns to prove | Output / acceptance | Dependencies |
|---|---|---|---|---|
| H01 P0 | Lobby→Triệu hồi→Dragon God of Earth | drawCard:open:1 and Lua mType assignment, state response | Screen initializes without mType nil | F01,F03,F04,A03 |
| H02 P0 | Press Ước 1 lần | Exact button Lua callback and actual wish-x1 C2S | Confirmed opcode, fields, no invented command | H01 |
| H03 P0 | Draw hero from valid pool | Eligible pool, cost, rarity weights, pity/duplicate rules | Server-authoritative RNG + rule fixtures | H02,F05 |
| H04 P0 | Receive result animation/card | S2C fields, result/error callback, hero ID mapping | Physical screen shows correct gained hero | H02,H03 |
| H05 P0 | Persist ownership + payment | Account/hero FK, currency debit, request key, retry/concurrency | Atomic debit and exactly-once grant | H03 |
| H06 P0 | Đội hình right + opens owned picker | Owned list payload, empty state, card mapping | Newly owned hero visible in picker | H04,H05 |
| H07 P0 | Assign hero to active battle slot | Slot count, uniqueness, constraints, save/reload command | Active slot persists after relogin | H06,A04 |
| H08 P1 | Open hero attributes | hero.xc base stats, client/server overlays, stat types | Correct values and safe client render | H05,F05 |
| H09 P2 | Upgrade hero level | EXP materials, per-level costs, approved cap | Atomic cost+level with boundaries | H08,I02 |
| H10 P2 | Promotion/aptitude | Promotion rules, materials, rank effects, cap | Data persists, no illegal increments | H08,I02 |
| H11 P2 | Wish x10 / additional banners | Separate command and currency, distinct pool and animation | No accidental premium spend or partial grant | H02,H05 |
| H12 P2 | Skill unlock/passive | Skill IDs, unlock stages, cooldown and effect stats | Client display matches server battle engine | H08,C04 |
| H13 P2 | Combat power display | Exact formula, modifiers, rounding, cap | Client/server computed values agree | H08,H09,H10 |
| H14 P3 | Hero sort/filter/sell/convert if present | UI mode, rarity, safe disposal and recovery | Explicit ownership mutation and guard | H05,H08 |

## E. Inventory, currency and item economy

| WP / priority | Player action | Fields / failure cases | Output / acceptance | Dependencies |
|---|---|---|---|---|
| I01 P1 | Open bag and category tabs | Item IDs/rarity/stack/slots and sync opcodes | Bag reflects account inventory | A03,F05 |
| I02 P1 | Gain/spend gold/gems/currency | Currency types, price source, balance invariant | Transaction ledger + no negative currency | I01 |
| I03 P1 | Claim reward from combat/event | Template ID, qty, duplicate/replay, overflow | Exactly-once reward grant | I01,I02 |
| I04 P2 | Use items and bundles | Consumable use packet, target, cooldown/expiry | One use -> one effect, valid rollback | I01,I02 |
| I05 P2 | Equip/unequip to hero | Equipment slots, type restrictions, stat recompute | Equipment persists and cannot be duplicated | I01,H08 |
| I06 P2 | Upgrade/refine equipment | Material cost, success rate, cap/failure path | Reproducible upgrade transaction | I02,I05 |
| I07 P2 | Shop purchase | SKU, price, stock, limit, receipt, refund | No double charge or phantom item | I01,I02 |
| I08 P3 | Mail / attachments | Expiration, unread, claim-once, sender/source | Retry-safe claim and account reload | I03,A04 |
| I09 P3 | Daily login/event rewards | Server day boundary, event state, claim eligibility | Stable reset/reward ledger | I03,Q01 |

## F. Shared combat engine and PvE

| WP / priority | Player action | State / protocol evidence | Output / acceptance | Dependencies |
|---|---|---|---|---|
| C01 P1 | Load battle scene | Scene states, team snapshot, instance metadata | Real combat scene, not Adventure map | F04,H07 |
| C02 P1 | Start combat tick/turn | Real-time vs turn rules, event ordering, cadence | Deterministic trace of state changes | C01,F03 |
| C03 P1 | Basic attack and defense | ATK/DEF, crit field cri, dodge, random seed, rounding | Source-backed damage/HP test vectors | C02,H08 |
| C04 P1 | Cast active skill | Binary 0x25 payload, targets, costs, cooldown | Combat handler works, RPC cannot cause damage | C02,C03 |
| C05 P1 | Buff/debuff/status | Tick order, stacking, dispel, duration | Event and status replay tests | C04 |
| C06 P1 | Enemy spawn and AI | Waves, target selection, enemy data and pacing | Correct enemy lifecycle | C02 |
| C07 P1 | Finish fight/victory/defeat | Win conditions, retries, disconnect, reward | Correct result with exactly-once loot | C03,C06,I03 |
| E01 P1 | Select Phó bản stage | Menu control, stage ID, unlock, navigation | Device selects intended stage without blind taps | C01,A03 |
| E02 P1 | Enter PvE instance | Instance ID, stage/party snapshot, transition | Authentic PvE stage with captured state | E01,H07 |
| E03 P1 | Fight first dungeon | Scene, enemy spawns, inputs, result/reward | Real device victory/loss + DB evidence | E02,C03,C04,C06,C07 |
| E04 P2 | Boss phases | Spawn/phase/skill/loot, boundary transitions | Deterministic boss phase state | E03 |
| E05 P2 | Unlock next stage | Prereqs, stars, difficulty, progression DB | Next stage persists through relogin | E03,Q01 |
| E06 P2 | Auto-battle / repeat if present | Toggle, retry, reward ledger, interruption | No blind loops or duplicate rewards | E03,C07 |
| Q01 P2 | Mission/quest completion | Objectives, event triggers, counters/claim | Reproducible quest progress | C07,I03 |
| E07 P3 | Cooperative PvE if present | Parties, ready, sync and disconnect | Two-client evidence or NOT_PRESENT | E02,A04 |

## G. PvP (do not assume a particular PvP mode exists)

| WP / priority | Player action | Authority and anti-abuse unknowns | Output / acceptance | Dependencies |
|---|---|---|---|---|
| P01 P2 | Discover actual arena/PvP modes | Original UI labels, unlocks, rules and reward types | Source-backed feature inventory | F04,A03 |
| P02 P2 | Queue/challenge/match | Player eligibility, queue cancel, matching/rating | Two valid accounts matched, no spoofing | P01,A04 |
| P03 P2 | Lock teams and start | Team snapshots, ready state, authority | Both clients see same match/team | P02,H07 |
| P04 P2 | PvP action/combat | Command validation, damage/cooldown, state ordering | Authoritative matched-session trace | P03,C03,C04,C05 |
| P05 P2 | Rank/reward result | Win/loss, rating formula, duplicate match replay | Consistent leaderboard and idempotent settlement | P04,I03 |
| P06 P2 | Reconnect/quit/AFK | Disconnection/game-rule grace and forfeits | One consistent authoritative winner | P04,A04 |
| P07 P3 | Anti-cheat and audit trail | Forged actions, replay, invalid inventory, lag | Reject invalid input and preserve evidence | P04,P05 |

## H. Social, live operations and maintenance

| WP / priority | Player or operator action | Technical unknowns | Deliverable | Dependencies |
|---|---|---|---|---|
| S01 P3 | Friends/chat | Channel, target/visibility, abuse and privacy | Two-device send/receive evidence | A04 |
| S02 P3 | Guild / party | Join/invite/leave, concurrent membership | Consistent membership DB and UI | S01 |
| S03 P3 | Time-limited events | Calendar, eligibility, reset and asset table | Reproducible event state without live dependencies | I09 |
| S04 P2 | Asset/update delivery | Manifest, integrity, rollback, APK version | Safe version compatibility drill | F05,F06 |
| S05 P1 | Correlate incidents | Client packet/logcat/DB timestamps, sanitized IDs | Evidence manifest end-to-end | F08 |
| S06 P3 | Backup/migrate/recover | PITR and schema version, transactional consistency | Isolated restoration drill | H05,I03 |
| S07 P3 | Localization and fonts | Strings, assets, screen overflow | UI regression results | F04 |
| S08 P3 | Load and latency | Session count, packet burst, DB contention | Actual measured profiles, not hypothetical CCU | C02,I02 |

## I. How work is divided and approved

Each leaf task must carry its own contract and dependencies. Source finding,
Go implementation, real-device E2E and independent review are different gates.
If one task needs more than its allotted source targets, create a child task
with a frozen disjoint target set, rather than broadening the active task.

Required statuses:
NOT_DISCOVERED -> SOURCE_MAPPED -> CONTRACT_VERIFIED -> CODE_READY ->
OFFLINE_TESTED -> ANDROID_TESTED -> INDEPENDENTLY_VERIFIED.

Alternative outcomes:
BLOCKED_MISSING_SOURCE, BLOCKED_PERMISSION, UNKNOWN_PROTOCOL,
NOT_PRESENT_IN_APK, OWNER_DESIGN_DECISION, DEFERRED.

Current critical path:
F00,F01,F03,F04 -> A03 -> H01,H02,H03,H04,H05,H06,H07 ->
C01,E01,E02,E03.

## J. Information ownership

Agent discovers independently: symbols, Lua names, scene IDs, existing
inventory/hero systems, actual packets, DB schema, existing PvP modes.
Do not ask the owner to reverse engineer those.

Owner decides: original-vs-modified gameplay rules, feature priority,
which APK is the design baseline, content/asset rights, currency and draw
policy when the original game cannot prove one, PvP fairness choices,
preferred release architecture (patched APK vs independently rebuilt APK).

Never promote owner intent into proof that the original APK behaves that way.
