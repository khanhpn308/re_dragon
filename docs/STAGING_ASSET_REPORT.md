# ReturnSaiyan — Reversible Staged Asset Tree Report

> **Task Key:** `stage-unified-heroes-tree`  
> **Staged Tree Directory:** [`staging/assets/`](file:///home/khanh/returnsaiyan-re/staging/assets)  
> **Total Staged Spine Files:** 160 files (25,593,369 bytes)  
> **Unified Hero Roster:** 138 heroes (128 preserved RS + 10 integrated DBG)  
> **Rebuilt `hero.xc` SHA-256:** `13e73693c3d0a8d15c69008435811c9d2e7b38c1c70ff5e0f6eb0bc8a16a0bec`  

---

## 1. Executive Summary

A complete, non-destructive, and reversible staging environment has been created under `staging/assets/`.
- Original `ReturnSaiyan-arm64.apk` and `libaos_jogo.so` remain completely untouched.
- All 21 missing DB Global actor spine models have been extracted and dual-placed to guarantee path compatibility across both ReturnSaiyan and legacy asset resolvers.
- `hero.xc` has been re-encoded in ReturnSaiyan's strict 48-column big-endian binary schema, cleanly expanding the playable roster from 128 to 138 heroes.

---

## 2. Integrated Candidate Heroes Roster

| Unified Hero ID | Original DBG ID | Hero Name | Actor Model (`animationId`) | Card Spine | Death Sound | Re-encoded Stats (`phyAct`/`maxHp`) |
| :---: | :---: | :--- | :---: | :---: | :--- | :---: |
| **`10081`** | `10061` | **Super Saiyan 4 Gogeta** | `1062` | `1062c` | `Die_young_woman` | `85` / `4320` |
| **`10062`** | `10062` | **Vados** | `1065` | `1065c` | `Die_young_woman` | `180` / `2000` |
| **`10083`** | `10063` | **Towa** | `1066` | `1066c` | `Die_young_woman` | `136` / `3500` |
| **`10084`** | `10064` | **Toppo** | `1067` | `1067c` | `Die_young_woman` | `170` / `4000` |
| **`10065`** | `10065` | **Jiren** | `1069` | `1069c` | `Die_young_woman` | `210` / `4000` |
| **`10066`** | `10066` | **Shin** | `1071` | `1071c` | `Die_young_woman` | `180` / `4300` |
| **`10067`** | `10067` | **DC Majin Vegeta ** | `1072` | `1072c` | `Die_young_men` | `230` / `4200` |
| **`10068`** | `10068` | **DC Super Saiyan 3 ** | `1073` | `1073c` | `Die_young_men` | `185` / `4000` |
| **`10069`** | `10069` | **Super Saiyan Blue Vegito** | `1074` | `1074c` | `Die_young_men` | `190` / `4010` |
| **`10070`** | `10070` | **Arale** | `1075` | `1075c` | `Die_young_men` | `110` / `6354` |

---

## 3. Strict Preservation Verification

The following ReturnSaiyan unique custom heroes were verified in-place with zero ID collisions:
- **`10060`**: Ultra Ego Vegeta (Actor `1060`, Card `1060c`)
- **`10063`**: Legendary Broly (Fury) (Actor `1063`, Card `1063c`)
- **`10064`**: Black Frieza (Actor `1064`, Card `1064c`)
- **`90001..90009`**: Custom Marvel event heroes (`Iron Man`, `Storm`, `Wolverine`, `Crystal`)

---

## 4. Verification Checkpoint
- [x] 160 spine asset files staged into `staging/assets/data/GameData/spine/actor/data/`.
- [x] PKM textures dual-placed into `staging/assets/data/GameData/spine/actor/png/`.
- [x] Rebuilt `hero.xc` serialized and verified with exact 0 bytes delta against `libaos_jogo.so` specification.
- [x] All 10 candidate DB Global heroes integrated with collision-safe remapping.
- [x] All 128 original ReturnSaiyan heroes verified intact.
- [x] Reversible staging tree isolated; original APK and SO unmodified.
