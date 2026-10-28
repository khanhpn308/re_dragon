# P3: Chiến Đấu Branch Exploration and UI Path Comparison Report

**Project ID:** `e2ff7b42242746d4` (`RS-UH-V2-REAL-DUNGEON-COMBAT-E2E`)  
**Task Key:** `P3-chien-dau-navigation-trace`  
**Execution Run ID:** `20261028_045323`  
**Target Device:** Realme GT Master Edition (`RMX3461`, Serial: `10b3139c`)  
**Native Display:** 2412 x 1080 (Active Cocos2d-x canvas: 1920 x 1080, offset: `x=246`)  
**Execution Timestamp:** 2026-10-28T04:53:23Z to 2026-10-28T04:53:51Z  
**Verdict:** **PASS**

---

## 1. Executive Summary & Groundbreaking Discovery

Task `P3-chien-dau-navigation-trace` executed live physical Android exploration of the **Chiến đấu** branch from the Main Lobby on Realme GT Master Edition `RMX3461` (`10b3139c`) against the local Go game server (`30001`), mock updater (`30008`), and PostgreSQL database.

### 1.1 Discovery of Stage / Level Selection Architecture
1. **Observable State Transition:** Navigated from authenticated `MAIN_LOBBY` into `STAGE_SELECTION` (`guanqia_page`) using verified scene-anchored target coordinates (`chien_dau` at screen `(2041, 999)`, normalized `(0.935, 0.925)` in the 1920x1080 canvas).
2. **Native Runtime Confirmation:** Cocos2d-x engine logcat confirmed the native scene transition at `11:53:46.261`:
   ```
   10-28 11:53:36.800 D/cocos2d-x debug info(  630): --------------- Show : main
   10-28 11:53:46.261 D/cocos2d-x debug info(  630): --------------- Show : guanqia_page
   ```
   where `guanqia_page` is the native Stage / Level Selection interface (关卡页面 - Guan Qia / Stage Page) for the Main Story / Campaign chapters.
3. **Visual Structure of `guanqia_page`:**
   - **Header:** "Trái Đất" (Earth) title banner with Home navigation icon at `(0.04, 0.06)`.
   - **Top-Right Radar:** "Đội hình" (Formation / Team Lineup radar icon) at `(0.88, 0.06)`.
   - **Center:** Massive golden glowing emblem featuring Raditz, titled **"Saiyan Invasion"**, with star progress badge **"0 / 30"**.
   - **Bottom-Right:** Difficulty / Mode tabs **"Thường"** (Normal) at `(0.70, 0.95)` and **"Tinh anh"** (Elite) at `(0.85, 0.95)`.
4. **Architectural Comparison (Phó bản vs. Chiến đấu vs. Phiêu lưu):**
   - **Phó bản (`fuben_zhujiemian`):** Entered from `(1828, 976)`. Displays special instance modes: Phòng Thời Gian, Boss Thế giới, Điện Anh hùng, Phi thuyền, Tháp Karin, and Quân đoàn Ruy Băng Đỏ.
   - **Chiến đấu (`guanqia_page`):** Entered from `(2041, 999)`. Displays the main campaign progression stages (Chapter 1: Trái Đất - Saiyan Invasion).
   - **Phiêu lưu (`PHIEU_LUU`):** Flying cloud Goku with Goten & Trunks fusion dance ("Connecting Server...") and round "Go" button. **Neither Phó bản nor Chiến đấu navigates to Phiêu lưu.** Historical project `6181397b27b247e9` mistakenly captured Phiêu lưu and falsely claimed it was combat gameplay.

---

## 2. Primary Evidence Ledger

### 2.1 Screenshots & Visual Crops (2412 x 1080 Native RGBA)
| Artifact File | Size (Bytes) | SHA-256 Checksum | Description |
|---|---|---|---|
| `evidence/real_dungeon_combat/20261028_045323/01_main_lobby_pre.png` | 2,300,657 | `240fbaeb43a0667cb1cc4221c72a7b8d7c1c1f64c980057cd89dbf0d0b305481` | Verified baseline Main Lobby screen before Chiến đấu navigation |
| `evidence/real_dungeon_combat/20261028_045323/01_lobby_bottom_right_buttons.png` | 134,818 | `9ee47b11b50a3632f00dd5af19dee668ffbd8d1764a65ec8ec430ec1f331802c` | Cropped bottom-right action area showing Chiến đấu button |
| `evidence/real_dungeon_combat/20261028_045323/02_chien_dau_post.png` | 1,547,824 | `53e4e71ce5b245109002d6e2c71f5ae5260a66203405e04149c6074f0d78c219` | Screen captured after tapping Chiến đấu entry button, displaying Stage Selection (`guanqia_page`) |
| `evidence/real_dungeon_combat/20261028_045323/02_chien_dau_header.png` | 120,544 | `84b7ea9b3259015332d9f76466df504dab501d3eb6e8d492c935eb757ea6be47` | Cropped header showing "Trái Đất" and Home navigation icon |
| `evidence/real_dungeon_combat/20261028_045323/02_chien_dau_center.png` | 642,109 | `32ae834e46c0deae789b299d1c5a3009f3ab9024fb03ba81647334fd12a784f6` | Cropped central view showing Raditz "Saiyan Invasion" chapter badge and 0/30 stars |

### 2.2 System, Telemetry & Server Logs
| Artifact File | Description |
|---|---|
| `evidence/real_dungeon_combat/20261028_045323/logcat.log` | Android client logcat confirming Cocos2d-x `Show : main` -> `Show : guanqia_page` (`11:53:46.261`) |
| `evidence/real_dungeon_combat/20261028_045323/server.log` | Local Go server log confirming stable `conn-2` connection and Opcode 0x11 processing |
| `evidence/real_dungeon_combat/20261028_045323/updater.log` | Mock HTTP updater query log |
| `evidence/real_dungeon_combat/20261028_045323/p3_run_manifest.json` | Machine-readable SHA-256, timestamp, and state transition manifest |

---

## 3. Technical Analysis & UI Path Comparison

1. **Button Geometry:**
   - Screen: 2412x1080 (Active Cocos2d-x canvas: 1920x1080, `x_offset = 246`)
   - **Phó bản:** Screen `(1828, 976)` -> normalized `(0.824, 0.904)` -> opens `fuben_zhujiemian`
   - **Chiến đấu:** Screen `(2041, 999)` -> normalized `(0.935, 0.925)` -> opens `guanqia_page`
2. **Path Comparison:**
   | Feature | Phó bản (`P2`) | Chiến đấu (`P3`) | Phiêu lưu (Historical `6181397b27b247e9`) |
   |---|---|---|---|
   | Entry Coordinate | `(1828, 976)` | `(2041, 999)` | Non-dungeon world tap |
   | Cocos2d-x Scene | `fuben_zhujiemian` | `guanqia_page` | `map_cloud` / `damper_net` |
   | Content | 6 Dungeon instance cards | Main Campaign Chapter 1 (Trái Đất / Saiyan Invasion) | Cloud exploration ("Connecting Server...") |
   | Mode / Tabs | Instance modes (Time Chamber, etc.) | Thường (Normal) / Tinh anh (Elite) | VIP3 / VIP8 quick adventure |
   | Combat Entry | Sub-instance selection | Stage entry from chapter badge | None (non-combat exploration) |
3. **Reproducibility Command:**
   ```bash
   python3 tools/e2e_runner/real_dungeon_combat_runner.py p3
   ```
