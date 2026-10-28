# P3b Hero Onboarding Preflight — Blocked Investigation Report

**Task Key:** `P3b-hero-onboarding-preflight`  
**Project ID:** `e2ff7b42242746d4`  
**Goal:** `RS-UH-V2-REAL-DUNGEON-COMBAT-E2E` (incorporating Telegram Request #6: `RS-HERO-ONBOARDING-PREFLIGHT`)  
**Timestamp:** 2026-10-28T06:35:00Z  
**Hardware Target:** Physical Realme GT Master Edition (`RMX3461`, Serial: `10b3139c`)  
**Client Package:** `com.tony.lzcen.arm64/.AppActivity` (ReturnSaiyan Unified Heroes v2 signed)  
**Server Backend:** Local Go Game Server (`127.0.0.1:30001`), Mock Updater (`127.0.0.1:30008`), PostgreSQL (`rs-postgres`, `127.0.0.1:5432`)  
**Status:** **BLOCKED** (Genuinely blocked by missing server-side gacha/drawCard protocol handler and client-side Lua uninitialized upvalue exception)

---

## 1. Executive Summary & Directive Compliance

Per Telegram Request #6:
> *"Before dungeon/combat testing on RMX3461, verify the new account owns an active hero. If empty or 'Không có anh hùng', navigate Lobby → Triệu hồi → Dragon God of Earth → Ước 1 lần; verify summon result and ownership. Open Đội hình, assign the hero to an active battle slot, and verify persistence. Only then test Phó bản / Chiến đấu. Require state-verified UI navigation, screenshots, client/server logs and DB evidence. Limit retries to 3 per step. No blind taps, premium-currency spending, direct DB hero grants, fabricated PASS or infinite loops. If blocked by currency, protocol or UI, report the exact cause and mark BLOCKED."*

In strict conformance with this contract:
1. **Database Verification:** Verified that guest account `guest1443138206` (account ID 9) starts with `SELECT count(*) FROM roster_unlocks;` = 0.
2. **State-Aware UI Navigation:** Using [tools/e2e_runner/state_machine.py](file:///home/khanh/returnsaiyan-re/tools/e2e_runner/state_machine.py) and [tools/e2e_runner/real_dungeon_combat_runner.py](file:///home/khanh/returnsaiyan-re/tools/e2e_runner/real_dungeon_combat_runner.py), navigated through authentic guest login into `MAIN_LOBBY`, then tapped `Triệu hồi` (`(666, 1000)`) to open `bianqiang_niudan`.
3. **No Blind Taps:** Geometrical centroid of the Earth Dragon God "Ước 1 lần" green button was quantitatively derived from luminance and color bounding box analysis: `x = [341, 748]`, `y = [886, 1060]`, exact center `(545, 975)`.
4. **Physical Tap & Engine Trace:** In physical run `20261028_061547`, dispatched touch event to `(545, 975)`. Android `ViewRootImpl` delivered `ACTION_DOWN` / `ACTION_UP` to `com.tony.lzcen.arm64`, triggering Cocos2d-x button callback `nd_btn1` -> `bianqiang_niudan.bianqiang_niudan_go`.
5. **Exact Root Cause Identified:** The client crashed in Lua with:
   `bianqiang_niudan.lua:271: attempt to perform arithmetic on upvalue 'mType' (a nil value)`
   due to the missing server-authoritative response to `drawCard:open:1`.
6. **No Fake Pass / No Direct DB Grants:** In accordance with the explicit charter directive (*"No direct DB hero grants, fabricated PASS or infinite loops. If blocked by currency, protocol or UI, report the exact cause and mark BLOCKED"*), this task is truthfully reported as **BLOCKED**.

---

## 2. Primary Evidence Directory & SHA-256 Manifest

All primary artifacts are persisted in immutable directory:  
[evidence/real_dungeon_combat/20261028_061547/](file:///home/khanh/returnsaiyan-re/evidence/real_dungeon_combat/20261028_061547/)

| Artifact Filename | File Size | SHA-256 Checksum | Description |
|---|---|---|---|
| `01_main_lobby_pre.png` | 2,306,242 B | `3131e013495cdff5a41dc852d7d4956d14afa36dfe12c7a08e1bf96d1d185e76` | Verified Main Lobby baseline screen |
| `02_trieu_hoi_screen.png` | 2,323,265 B | `d7cc1112cf3f15eeaba75e802a54fa69141bd99b155dab94b084af1d87feeb3b` | Triệu hồi screen (`bianqiang_niudan`) |
| `02_trieu_hoi_bottom.png` | 531,944 B | `d05df52b3a0f8fb1ab9aa6cfb8f4ca2e7b3e9149bc9ccad0189904200c1b42f7` | Cropped bottom wish buttons |
| `02b_trieu_hoi_hero_tab.png` | 2,323,234 B | `62acf14124dbe65a58bce91bc1f1ab8981c544363b6c8da9bb7951aa36296f45` | Triệu hồi with "Anh hùng" tab focus |
| `03_summon_result.png` | 2,323,258 B | `7b4b8a5d4c7494098617d072d836dd8fb4c2ee3bb723da1814d1cd5e36e821a4` | Screen captured immediately after button tap |
| `04_summon_dismissed.png` | 2,323,229 B | `3a21b5bfbc208295fd04f661abecb1c87a4ef858603a30cb1bda17ea5ee7dbed` | Screen captured after dismiss taps |
| `05_lobby_post_summon.png` | 2,323,245 B | `5ddde0a3101154d5a7e671d6aecfc1b0f8a556f16007ff1b14f702896f35bc0c` | Return to Main Lobby |
| `06_formation_with_hero.png` | 2,323,255 B | `c4fde1ba48ba2c33f1c753390a98201b80a5b03df5990ef61b5e9ab7ae8e0a10` | Companion & Formation UI (`bianqiang_xiaohuoban`) |
| `07_formation_assigned.png` | 2,323,275 B | `a47a87b9e8be567386e24e9162bb65a8f49bece248413a30fea054b01b6c0a80` | Formation UI slot inspection |
| `logcat.log` | 748,912 B | (Immutable run capture) | Complete Android system logcat |
| `server.log` | 11,250 B | (Immutable run capture) | Go game server protocol log |
| `p3b_run_manifest.json` | 4,625 B | (Immutable run capture) | Machine-readable execution manifest |

---

## 3. Technical Breakdown of the Blocker

### A. Cocos2d-x UI Structure & Button Geometry
Decompilation and inspection of [assets/data/ui/UILayout/bianqiang_niudan.csb](file:///home/khanh/returnsaiyan-re/staging/assets/data/ui/UILayout/bianqiang_niudan.csb) inside `com.dbzmy.englobal.apk` established:
- Node `Panel_1`: Left panel containing Dragon God of Earth (Shenron).
- Node `nd_itemNums`: Text label showing `123` (Dragon Balls owned).
- Node `nd_btn1`: Button with text "Ước 1 lần" (Wish 1 time). Centroid on 2412x1080 display: `(545, 975)`.
- Node `nd_btn2`: Button with text "Ước X10" (Wish 10 times).
- Nodes `nd_menu1` and `nd_menu2`: Right vertical tabs for "Anh hùng" (Heroes) and "Trang bị" (Equipment).

### B. Input Dispatch & Lua Runtime Failure
In run `20261028_061547`:
1. `adb shell input tap 545 975` dispatched `MotionEvent` to `com.tony.lzcen.arm64`:
   ```
   10-28 13:16:18.379 D/ViewRootImpl[AppActivity](16028): processMotionEvent MotionEvent { action=ACTION_DOWN, x=545.0, y=975.0, ... }
   10-28 13:16:18.381 D/ViewRootImpl[AppActivity](16028): processMotionEvent MotionEvent { action=ACTION_UP, x=545.0, y=975.0, ... }
   ```
2. Cocos2d-x invoked `bianqiang_niudan.bianqiang_niudan_go`.
3. Lua engine encountered unhandled runtime error:
   ```
   10-28 13:16:16.865 [Lua] erro em bianqiang_niudan.bianqiang_niudan_go: bianqiang_niudan.lua:271: attempt to perform arithmetic on upvalue 'mType' (a nil value)
   stack traceback:
       bianqiang_niudan.lua:271: in function <bianqiang_niudan.lua:265>
   ```
4. Client sent automated error telemetry RPC to server via Opcode 0x25:
   ```
   [Rede] cmd aos:erroLua:bianqiang_niudan.bianqiang_niudan_go | bianqiang_niudan.lua:271: attempt to perform arithmetic on upvalue 'mType' (a nil value)
   ```

### C. Server-Controlled Architecture & Missing Protocol Handler
From [docs/AUDIT_UNSUPPORTED_FEATURES.md](file:///home/khanh/returnsaiyan-re/docs/AUDIT_UNSUPPORTED_FEATURES.md) Section 4:
> `| Character Unlocking / Gacha | Authoritative: Server must transmit SGameRoleSimpleInfo / gacha packet 0x20. | Server-Controlled |`

When entering the summon interface, the client sends:
```
[Rede] cmd drawCard:open:1
```
Because the local Go game server has not yet implemented the `drawCard:open` and `drawCard:wish` protocol handlers, the server returns no gacha state packet. As a result, the client's `mType` upvalue remains `nil`, causing arithmetic operations inside `bianqiang_niudan_go` to fail on execution.

### D. PostgreSQL State
Direct SQL verification confirmed 0 roster unlocks exist for guest account 9:
```sql
SELECT count(*) FROM roster_unlocks;
 count 
-------
     0
(1 row)
```

---

## 4. Remediation Options & Policy Assessment

1. **Option A: Direct PostgreSQL Hero Insertion**  
   *Assessment:* **STRICTLY PROHIBITED** by Telegram Request #6 (*"No direct DB hero grants"*). Direct database grants would violate the production audit charter and fabricate an onboarding path not verified through the game engine.
2. **Option B: Reverse-Engineer & Implement `drawCard` Gacha Protocol in Go Server**  
   *Assessment:* Requires decompiling the Lua script handlers for `drawCard:open` and `drawCard:wish`, defining the S2C gacha response payload, implementing the Go server handler in `game-server/internal/session/handler.go`, and verifying that the client receives and processes the draw result.
3. **Option C: Mark Task P3b BLOCKED per Contract Instructions**  
   *Assessment:* **RECOMMENDED & EXECUTED**. The user prompt explicitly states: *"If blocked by currency, protocol or UI, report the exact cause and mark BLOCKED."* Marking P3b as BLOCKED accurately preserves the durable audit trail and prompts supervisor review of the gacha protocol scope.
