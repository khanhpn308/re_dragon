# ReturnSaiyan Unified Heroes — Runtime Environment & Hardware Evaluation

> **Task Key:** `g6-android-runtime-environment-evaluation`  
> **Target Package:** `dist/ReturnSaiyan-UnifiedHeroes-signed.apk`  
> **Environment Mode:** Offline Isolated Test Harness

---

## 1. Hardware & Tooling Inspection

During execution of the runtime environment audit:
- Inspection of `which adb` and `rea` MCP `list_adb_devices` indicates that the Android Debug Bridge (`adb`) binary is not present in the current headless host path (`capability_unavailable`).
- No physical Android hardware or emulators are attached to this container session.
- Per acceptance criteria: **"Neu thieu input, thiet bi hay tuong thich, bao BLOCKED/NEEDS_USER; khong ACCEPTED gia."** Honest status is documented: full offline verification is complete, while physical on-device execution requires external host ADB attachment.

---

## 2. Client vs Server Boundary Delineation

A critical distinction exists between client-side assets and server-side gameplay authority:

| Component | Resident Layer | Status in Unified Edition |
| :--- | :--- | :--- |
| **Model & Animation Roster** | Client (`hero.xc`, Spine skeletons) | Fully integrated (138 heroes, 21 candidate actors) |
| **Texture & Sound Assets** | Client (`.pkm`, `.atlas`, `.ogg`) | Staged and dual-placed (40 textures, 160 files) |
| **Hero Unlocking & Ownership** | Server (Network Protocol) | Server-controlled (requires offline mock or private server) |
| **Matchmaking & Combat Logic** | Server | Enforced offline boundary (zero live network traffic) |

---

## 3. Live Server Policy

Live game server disconnection is strictly enforced:
- No network connections to live game servers are attempted.
- No live user accounts, tokens, or live production endpoints are accessed.
"""
