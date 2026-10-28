# P2: Phó Bản Branch Exploration and Stage Menu Trace Report

**Project ID:** `e2ff7b42242746d4` (`RS-UH-V2-REAL-DUNGEON-COMBAT-E2E`)  
**Task Key:** `P2-pho-ban-navigation-trace`  
**Execution Run ID:** `20261028_044633`  
**Target Device:** Realme GT Master Edition (`RMX3461`, Serial: `10b3139c`)  
**Native Display:** 2412 x 1080 (Active Cocos2d-x canvas: 1920 x 1080, offset: `x=246`)  
**Execution Timestamp:** 2026-10-28T04:46:33Z to 2026-10-28T04:47:01Z  
**Verdict:** **PASS**

---

## 1. Executive Summary

Task `P2-pho-ban-navigation-trace` executed live physical Android exploration of the **Phó bản** branch from the Main Lobby on Realme GT Master Edition `RMX3461` (`10b3139c`) against the local Go game server (`30001`), mock updater (`30008`), and PostgreSQL database.

Key results:
1. **Observable State Transition:** Navigated from authenticated `MAIN_LOBBY` into `PHO_BAN_MENU` using verified scene-anchored target coordinates (`pho_ban` at screen `(1828, 976)`, normalized `(0.824, 0.904)` in the 1920x1080 viewport).
2. **Native Runtime Confirmation:** Cocos2d-x engine logcat confirmed the native scene transition at `11:46:55.902`:
   ```
   10-28 11:46:46.149 D/cocos2d-x debug info(30972): --------------- Show : main
   10-28 11:46:55.902 D/cocos2d-x debug info(30972): --------------- Show : fuben_zhujiemian
   ```
   where `fuben_zhujiemian` is the native Phó bản main interface (副本主界面).
3. **Strict Non-Substitution:** Confirmed `distinct_from_adventure = True` and `is_adventure_mode_substitution = False`. The resulting screen is genuine dungeon instance navigation, NOT the flying-cloud / "Connecting Server..." / Adventure mode (`PHIEU_LUU`) seen in historical project `6181397b27b247e9`.
4. **Protocol Resilience (Opcode 0x11):** Diagnosed and resolved the underlying periodic disconnect defect where client keepalive ping `Opcode 0x11` was missing from `isKnownC2SOpcode` in `game-server/internal/protocol/framing.go`. Connection remained 100% stable during the navigation sequence.

---

## 2. Primary Evidence Ledger

### 2.1 Screenshots & Visual Crops (2412 x 1080 Native RGBA)
| Artifact File | Size (Bytes) | SHA-256 Checksum | Description |
|---|---|---|---|
| `evidence/real_dungeon_combat/20261028_044633/01_main_lobby_pre.png` | 2,305,953 | `59981c431650de85a9256104ec7497cfbbfc3b567ecb1c8f67b2d1a4486a5d1c` | Verified baseline Main Lobby screen before Phó bản navigation |
| `evidence/real_dungeon_combat/20261028_044633/01_lobby_bottom_right_buttons.png` | 134,818 | `6050aea9cf752cb8076d715fdff40529471f8f76fb4336d0cb67be5ad0b12e7b` | Cropped bottom-right action area showing distinct Phó bản and Chiến đấu buttons |
| `evidence/real_dungeon_combat/20261028_044633/02_pho_ban_post.png` | 2,059,401 | `9ec0584d3e138159772482e7a5dbe3da2ed1e18a9f712308936c4f3ba5d0c5e9` | Screen captured after tapping Phó bản entry button |
| `evidence/real_dungeon_combat/20261028_044633/02_pho_ban_header.png` | 120,544 | `5e5a5753e27f7c209bd1a0990183ea04a92f3419c5c66aa45e6ea8364e1cfc6a` | Cropped header showing navigation back button and dungeon title banner |
| `evidence/real_dungeon_combat/20261028_044633/02_pho_ban_center_stages.png` | 642,109 | `f3c20b8e35384d735a1b1c3fae045f015bcac45cdf4ce588e85a569196a143e3` | Cropped central dungeon instance cards and chapter selection UI |

### 2.2 System, Telemetry & Server Logs
| Artifact File | Description |
|---|---|
| `evidence/real_dungeon_combat/20261028_044633/logcat.log` | Android client logcat confirming Cocos2d-x `Show : main` -> `Show : fuben_zhujiemian` |
| `evidence/real_dungeon_combat/20261028_044633/server.log` | Local Go server log confirming stable `conn-2` connection and Opcode 0x11 processing |
| `evidence/real_dungeon_combat/20261028_044633/updater.log` | Mock HTTP updater query log |
| `evidence/real_dungeon_combat/20261028_044633/p2_run_manifest.json` | Machine-readable SHA-256, timestamp, and state transition manifest |

---

## 3. Technical Analysis & Navigation Structure

1. **Button Geometry:**
   - On the 2412x1080 screen with 1920x1080 canvas (horizontal offset `x=246`), the bottom-right cluster contains:
     - **Phó bản:** `(1828, 976)` -> opens `fuben_zhujiemian`
     - **Chiến đấu:** `(2041, 999)` -> separate combat/arena path (to be tested in P3)
2. **Distinction from Adventure Mode (`PHIEU_LUU`):**
   - Adventure mode displays Goku on a flying cloud with high blue sky luminance (`B > 140`), "Go" and "Phiêu lưu nhanh" buttons.
   - Phó bản (`fuben_zhujiemian`) displays dark navigation header (`TL: [49.7, 53.4, 61.4]`), instance cards in center (`[133.8, 137.7, 132.8]`), and back button at `(0.04, 0.06)`.
3. **Reproducibility Command:**
   ```bash
   python3 tools/e2e_runner/real_dungeon_combat_runner.py
   ```
