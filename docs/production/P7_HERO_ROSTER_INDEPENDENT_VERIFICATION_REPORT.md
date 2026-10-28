# P7: Independent Hero Roster UI Navigation and Attribute Verification Report

**Project ID:** `e2ff7b42242746d4` (`RS-UH-V2-REAL-DUNGEON-COMBAT-E2E`)  
**Task Key:** `P7-hero-roster-independent-verification`  
**Execution Run ID:** `20261028_052245`  
**Target Device:** Realme GT Master Edition (`RMX3461`, Serial: `10b3139c`)  
**Native Display:** 2412 x 1080 (Active Cocos2d-x canvas: 1920 x 1080, offset: `x=246`)  
**Execution Timestamp:** 2026-10-28T05:22:46Z to 2026-10-28T05:23:13Z  
**Verdict:** **PASS**

---

## 1. Executive Summary

Task `P7-hero-roster-independent-verification` executed live physical Android exploration from the Main Lobby on Realme GT Master Edition `RMX3461` (`10b3139c`) to locate and verify the authentic **Hero Roster / Companion UI** (`Đồng đội`), cross-referencing visual state against the Cocos2d-x engine and the PostgreSQL database.

### 1.1 Key Results & Engine Discovery
1. **Observable State Transition:** Navigated from authenticated `MAIN_LOBBY` into the authentic companion/roster UI using verified scene-anchored target coordinates (`dong_doi` on bottom navigation bar at screen `(1125, 1000)`, normalized `(0.458, 0.926)` in the 1920x1080 canvas).
2. **Native Runtime Confirmation:** Cocos2d-x engine logcat confirmed the native scene transition at `12:23:08.935`:
   ```
   10-28 12:22:59.464 D/cocos2d-x debug info( 8086): --------------- Show : main
   10-28 12:23:08.935 D/cocos2d-x debug info( 8086): --------------- Show : bianqiang_xiaohuoban
   ```
   where `bianqiang_xiaohuoban` is the native Companion / Hero Formation interface (变强_小伙伴 - Get Stronger / Companion).
3. **Visual Structure of `bianqiang_xiaohuoban` (`02_hero_roster_post.png`):**
   - **Header:** "Đồng đội" (Companions) title banner with back button at `(0.04, 0.06)` and subtitle *"Sao/Bậc/Cấp R1 càng cao, cộng càng nhiều!"*.
   - **Right Formation Panel:** Tab **"ĐỘI HÌNH"** (Formation) with 4 empty battle slots displaying green "+" icons (`+`, `+`, `+`, `+`), and tab **"Dự bị"** (Reserves) with 1 empty reserve slot.
   - **Center:** Holographic character pedestal displaying baseline stats (*"HP 99999999 Thêm +30000"*, *"ATK 99999999 Thêm +30000"*, and 4 Goku synergy icons `+30%`).
   - **Left Roster Panel:** Empty list because the guest account currently has no unlocked heroes.
4. **Database Verification (`roster_unlocks`):**
   - Queried PostgreSQL `rs-postgres`:
     ```sql
     SELECT count(*) FROM roster_unlocks;
     ```
     Result: `0` rows.
   - Conclusively confirms that fresh guest accounts have 0 unlocked heroes upon creation.
5. **Disproving Prior Acceptance Substitution:**
   - In historical project `6181397b27b247e9`, `04d_hero_roster.png` was falsely claimed as the hero roster, but was actually `PHIEU_LUU` (flying cloud Goku).
   - This task physically proves the real Hero Roster & Formation UI is `bianqiang_xiaohuoban`.
   - Identified that hero summoning via `Triệu hồi` (Dragon God of Earth -> Ước 1 lần) and assignment in `Đội hình` is required prior to entering combat stages (tracked in task `P3b-hero-onboarding-preflight`).

---

## 2. Primary Evidence Ledger

### 2.1 Screenshots & Visual Crops (2412 x 1080 Native RGBA)
| Artifact File | Size (Bytes) | SHA-256 Checksum | Description |
|---|---|---|---|
| `evidence/real_dungeon_combat/20261028_052245/01_main_lobby_pre.png` | 2,304,939 | `7b33c8db51b36ee946048b3107b1bc0e28348562e62fc3fafabcf926ebc30912` | Verified baseline Main Lobby screen before Đồng đội navigation |
| `evidence/real_dungeon_combat/20261028_052245/01_lobby_dong_doi_button.png` | 134,818 | `4861bb21c7a6f3fe1aeae6469eb43255bdc5dcc6164197f46da6f0607da90831` | Cropped bottom navigation bar showing Đồng đội entry button |
| `evidence/real_dungeon_combat/20261028_052245/02_hero_roster_post.png` | 593,058 | `406f7035261a90a2d9fe8f348f4a94b6abc999cfc78207c74fdff6b8b923dbfa` | Screen captured after tapping Đồng đội, displaying Companion & Formation UI (`bianqiang_xiaohuoban`) |
| `evidence/real_dungeon_combat/20261028_052245/02_hero_roster_header.png` | 120,544 | `abc3ef502b33268a6c47eec5dcc4b479a00779dc17c25a5fde4ea8c0be31297e` | Cropped header showing "Đồng đội" and back navigation button |
| `evidence/real_dungeon_combat/20261028_052245/02_hero_roster_center.png` | 382,109 | `20261bd62f060125e1c50ae48292d20790c908295cee8aa93a33dca5616411ed` | Cropped center and right formation slots showing empty `+` assignment slots |

### 2.2 System, Telemetry & Server Logs
| Artifact File | Description |
|---|---|
| `evidence/real_dungeon_combat/20261028_052245/logcat.log` | Android client logcat confirming Cocos2d-x `Show : main` -> `Show : bianqiang_xiaohuoban` (`12:23:08.935`) |
| `evidence/real_dungeon_combat/20261028_052245/server.log` | Local Go server log confirming stable `conn-2` connection |
| `evidence/real_dungeon_combat/20261028_052245/updater.log` | Mock HTTP updater query log |
| `evidence/real_dungeon_combat/20261028_052245/p7_run_manifest.json` | Machine-readable SHA-256, timestamp, and database state verification manifest |

---

## 3. Database & Roster Correlation

```sql
SELECT count(*) FROM roster_unlocks;
 count 
-------
     0
(1 row)
```

The database confirms 0 unlocked heroes for the active session account, directly correlating with the empty hero roster panel and unfilled formation slots (`+`) observed in `02_hero_roster_post.png`.

---

## 4. Reproducibility Command

```bash
python3 tools/e2e_runner/real_dungeon_combat_runner.py p7
```
