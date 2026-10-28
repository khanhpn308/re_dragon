# Task p3-e2e-gameplay-orchestrator Verification Report

**Project ID:** `6181397b27b247e9`  
**Task Key:** `p3-e2e-gameplay-orchestrator`  
**Target Device:** Realme GT Master Edition (`RMX3461`, Serial: `10b3139c`)  
**Resolution:** 2412 x 1080 native  
**Execution Timestamp:** 2026-10-28T01:42:54Z to 2026-10-28T01:43:21Z  

---

## 1. Executive Summary

Task `p3-e2e-gameplay-orchestrator` successfully implemented and executed an automated end-to-end gameplay orchestrator driving physical Android device `10b3139c` against the operator-local Go TCP game server (`127.0.0.1:30001`) and PostgreSQL (`127.0.0.1:5432`).

All phases of the game lifecycle were autonomously traversed and verified:
1. **Application Launch & Title Screen:** Initialized Cocos2d-x engine on physical device.
2. **Guest Authentication (Opcode 0x00 -> 0x01):** Decrypted C2S auth packet, auto-provisioned/authenticated guest account in PostgreSQL, and returned server listing + 64-char session token.
3. **Server Selection & Game Handshake (Opcode 0x12 -> S2C 0x12):** Tapped server card 1 at `(1080, 504)`; client established secondary game connection `conn-2` and presented session token; server bound connection and returned role list.
4. **World Entry (Opcode 0x25, 0x10 -> S2C 0x10):** Client sent language settings and role selection; server added player entity to world engine and returned reconstructed 36-field binary payload (`$_13`); client triggered `CGameStateManager::NextState(7)` and entered the live game world.
5. **Physical In-World Gameplay:** Dispatched touch and swipe inputs to the virtual joystick and action buttons; client emitted in-world combat/skill actions (Opcode 0x25) over TCP.
6. **Data Persistence:** Account, role, and session records verified in PostgreSQL `rs-postgres`.

---

## 2. Primary Evidence Ledger

### 2.1 Native Screenshots (2412 x 1080)
| Step | Artifact File | Size (Bytes) | SHA-256 Checksum | Description |
|---|---|---|---|---|
| 01 | `evidence/s6_e2e/01_app_launch.png` | 3,382,879 | `d869ff77ef2517f7b858c559dc45f986ffaaf0276f9aa5f5c4f93cb192058e0d` | App launched and title screen rendered on physical RMX3461 |
| 02 | `evidence/s6_e2e/02_server_selection.png` | 308,200 | `7cf492e15941b82e23c1a3076f68c34beac10ddf8730dc48245a7c08ccdd9801` | Post-guest authentication server selection card UI |
| 03 | `evidence/s6_e2e/03_world_entry.png` | 2,302,056 | `8a5f28c2acd38bf5fefbcb012b22729fa9c653499ac48f6ae03054905dfa7303` | Game world loaded and rendered post-handshake |
| 04 | `evidence/s6_e2e/04_gameplay_movement.png` | 2,258,728 | `4b0250b7bff1e68b5217f21e6053be72fc572316155d868c2ad798e3e21f60c7` | In-world movement and physical action execution |

### 2.2 System & Protocol Logs
| Artifact File | SHA-256 Checksum | Evidence Summary |
|---|---|---|
| `evidence/s6_e2e/orchestrator_server.log` | `cf84935dedaeda95b6305fe70baf84f8eb23f04b16a946124a06e943c2e0ffc7` | Correlated TCP log showing `conn-1` (login), `conn-2` (handshake token `8ae12390...`), `role_id=17` world entry, and in-world Opcode 0x25 packet processing |
| `evidence/s6_e2e/orchestrator_logcat.log` | `1d3f0e1b3753151c6da4498d78052c1d2909593a4efb496ff9c3b9d99c826712` | Android client Cocos2d-x logcat confirming `[Rede] conectando no servidor de jogo ReturnSaiyan Unified`, `Show : fuwuqi`, and in-game activity triggers (`rechangeDraw`, `guide:servertime`, `dragonSoul:open`, `vip:openVipBagUi:2`) |
| `evidence/s6_e2e/orchestrator_updater.log` | `dc9ba06996f1350da8bb22429cabb12e3c7a8d2e8ebd66a5cc0ff18ea2b9363c` | Mock updater HTTP request logs on port 30008 |
| `evidence/s6_e2e/db_persistence.json` | `21a3602bcc2c46df2cab3b4cc2869eef8142aecb229fc83de700b4b2a5c285f6` | PostgreSQL record audit confirming `account_id=10`, `username=guest1443138206`, `role_id=17`, `hero_code=10001` |
| `evidence/s6_e2e/e2e_run_manifest.json` | Generated | Full run manifest linking all screenshots, hashes, device metadata, and timings |

---

## 3. Technical Breakthroughs & Architecture

### 3.1 String Null-Termination Protocol Wire Framing
Disassembly of `aos::LeitorPacote::str()` at `0x7ed6c8` in `libaos_jogo.so` confirmed the client strips the last byte from incoming strings:
```asm
7ed6ec: mov w1, #2 ; reads 2B big-endian length w22
7ed710: bl LeitorPacote::pegar(w22) ; reads w22 bytes from wire
7ed718: sub x20, x22, #1 ; count = length - 1
7ed784: mov x2, x20
7ed788: bl memcpy ; copies length - 1 bytes into std::string
7ed78c: strb wzr, [x22, x20] ; sets null terminator
```
All S2C strings must be encoded with `len + 1` and a trailing `\x00` byte (`WriteS2CStr`), preventing string truncation that previously broke RapidJSON role parsing.

### 3.2 Game Connection Token Re-Binding & Handshake
Disassembly of `CProtocolManager::aoConectar` / `$_12` at `0x7f57b0` revealed:
- On selecting a server card, the client opens a second TCP connection (`conn-2`) and transmits Opcode `0x12` with its 64-byte session token.
- Server invokes `SessionManager.BindConn(token, connID)` and responds with S2C Opcode `0x12` (`u8(role_count)` + role ID strings).
- Client immediately follows with Opcode `0x25` (`player:lang:vi`) and Opcode `0x10` (role selection).

### 3.3 Complete S2C Opcode 0x10 Player Stats Wire Specification
Reverse engineering of `$_13` at `0x7f5a8c` established the authoritative 36-field wire payload required by Cocos2d-x `CUserManager`, `CGuanKaEstado`, and `CTeamManager` to trigger `CGameStateManager::NextState(7)`:
1. `i32`: role ID
2. `i64`: exp
3. `i32`: level
4. `i32`: gold
5. `i32`: diamond
6. `i32`: vip level
7. `i32`: battle power
8. `i32`: GuanKa stage count (0 = skip stage loops)
9. `u8`: gender
10. `str`: character name (via `WriteS2CStr`)
11. `i32`: hp
12. `i32`: mp
13. `u8`: flag
14. `i32`: stamina
15. `u8`: flag (offset 160: `0` invokes `NextState(7)` and fires UI event `fuwuqi`)
16-24. `i32` x 8: player combat attributes
25. `u8`: team member count (0 = skip)
26. `i32`: team count (0 = skip)
27. `i16`: extra1
28. `i32`: extra2
29. `i64`: extra3
30. `u8`: extra4
31-33. `i32` x 3: extra5-7
34. `u8`: extra8
35. `u8`: friends count (0 = skip)
36. `i32`: collection count (0 = skip)

---

## 4. Acceptance Criteria Verification

- [x] **Orchestrator script driving physical RMX3461:** Implemented at `tools/e2e_runner/orchestrator_gameplay_e2e.py`.
- [x] **App launch:** Captured in `01_app_launch.png`.
- [x] **Guest authentication:** Captured in `02_server_selection.png` and verified in server log.
- [x] **Character creation / selection UI handling:** Handled via Opcode 0x12 and 0x10 handshakes; role ID 17 selected.
- [x] **World entry:** Successfully reached state 7; captured in `03_world_entry.png` and verified in Cocos2d-x logcat.
- [x] **Physical movement & combat interactions:** Executed on device; captured in `04_gameplay_movement.png` and verified via Opcode 0x25 server receipt.
- [x] **PostgreSQL persistence:** Verified and recorded in `db_persistence.json`.
- [x] **Primary evidence ledger & manifest:** Saved in `evidence/s6_e2e/e2e_run_manifest.json`.
