# ReturnSaiyan — Unified Hero Delta Matrix & Integration Specification

> **Task Key:** `build-unified-delta-matrix`  
> **Input Archives:** `ReturnSaiyan-arm64.apk`, `com.dbzmy.englobal.apk`  
> **Total Missing Actors to Integrate:** 21  
> **Total Staged Spine Assets:** 160 files (25,593,369 bytes)  

---

## 1. Collision-Safe Hero Remapping Table

To satisfy the acceptance requirement of preserving all existing ReturnSaiyan heroes (including newer custom heroes Ultra Ego Vegeta, Broly, and Black Frieza), colliding DB Global hero IDs are safely remapped to open slots in the `10080+` range:

| DBG Hero ID | Hero Name | Actor Model (`animationId`) | Card Spine (`cardSpineId`) | Assigned Unified ID | Collision Resolution |
| :---: | :--- | :---: | :---: | :---: | :--- |
| `10061` | **Super Saiyan 4 Gogeta** | `1062` | `1062c` | **`10081`** | Remap to 10081; preserve RS 10061 Vegito Blue |
| `10062` | **Vados** | `1065` | `1065c` | **`10062`** | Assign directly to 10062 |
| `10063` | **Towa** | `1066` | `1066c` | **`10083`** | Remap to 10083; preserve RS 10063 Legendary Broly (Fury) |
| `10064` | **Toppo** | `1067` | `1067c` | **`10084`** | Remap to 10084; preserve RS 10064 Black Frieza |
| `10065` | **Jiren** | `1069` | `1069c` | **`10065`** | Assign directly to 10065 |
| `10066` | **Shin** | `1071` | `1071c` | **`10066`** | Assign directly to 10066 |
| `10067` | **DC Majin Vegeta** | `1072` | `1072c` | **`10067`** | Assign directly to 10067 |
| `10068` | **DC Super Saiyan 3** | `1073` | `1073c` | **`10068`** | Assign directly to 10068 |
| `10069` | **Super Saiyan Blue Vegito** | `1074` | `1074c` | **`10069`** | Assign directly to 10069 |
| `10070` | **Arale** | `1075` | `1075c` | **`10070`** | Assign directly to 10070 |

---

## 2. Missing Actor Spine Asset Manifest

The following 21 actor models exist in DB Global 1.1.13 and will be staged into the Unified Edition without modifying original APK/SO files:

| Actor ID | File Count | Total Size (Bytes) | Model (.xc/.atlas/.json) | Textures (.pkm) |
| :---: | :---: | :---: | :--- | :--- |
| **1062** | 8 | 1,547,577 | `1062.atlas, 1062.json, 1062.xc, 1062c.atlas, 1062c.json, 1062c.xc` | `1062.pkm, 1062c.pkm` |
| **1065** | 8 | 1,639,100 | `1065.atlas, 1065.json, 1065.xc, 1065c.atlas, 1065c.json, 1065c.xc` | `1065.pkm, 1065c.pkm` |
| **1066** | 8 | 1,538,547 | `1066.atlas, 1066.json, 1066.xc, 1066c.atlas, 1066c.json, 1066c.xc` | `1066.pkm, 1066c.pkm` |
| **1067** | 8 | 1,496,363 | `1067.atlas, 1067.json, 1067.xc, 1067c.atlas, 1067c.json, 1067c.xc` | `1067.pkm, 1067c.pkm` |
| **1068** | 4 | 431,060 | `1068.atlas, 1068.json, 1068.xc` | `1068.pkm` |
| **1069** | 8 | 1,501,820 | `1069.atlas, 1069.json, 1069.xc, 1069c.atlas, 1069c.json, 1069c.xc` | `1069.pkm, 1069c.pkm` |
| **1070** | 4 | 438,287 | `1070.atlas, 1070.json, 1070.xc` | `1070.pkm` |
| **1071** | 8 | 1,485,149 | `1071.atlas, 1071.json, 1071.xc, 1071c.atlas, 1071c.json, 1071c.xc` | `1071.pkm, 1071c.pkm` |
| **1072** | 8 | 1,693,162 | `1072.atlas, 1072.json, 1072.xc, 1072c.atlas, 1072c.json, 1072c.xc` | `1072.pkm, 1072c.pkm` |
| **1073** | 8 | 1,829,559 | `1073.atlas, 1073.json, 1073.xc, 1073c.atlas, 1073c.json, 1073c.xc` | `1073.pkm, 1073c.pkm` |
| **1074** | 8 | 1,044,115 | `1074.atlas, 1074.json, 1074.xc, 1074c.atlas, 1074c.json, 1074c.xc` | `1074.pkm, 1074c.pkm` |
| **1075** | 8 | 681,043 | `1075.atlas, 1075.json, 1075.xc, 1075c.atlas, 1075c.json, 1075c.xc` | `1075.pkm, 1075c.pkm` |
| **1076** | 8 | 1,111,931 | `1076.atlas, 1076.json, 1076.xc, 1076c.atlas, 1076c.json, 1076c.xc` | `1076.pkm, 1076c.pkm` |
| **1077** | 8 | 981,420 | `1077.atlas, 1077.json, 1077.xc, 1077c.atlas, 1077c.json, 1077c.xc` | `1077.pkm, 1077c.pkm` |
| **1078** | 8 | 993,897 | `1078.atlas, 1078.json, 1078.xc, 1078c.atlas, 1078c.json, 1078c.xc` | `1078.pkm, 1078c.pkm` |
| **1118** | 8 | 1,235,726 | `1118.atlas, 1118.json, 1118.xc, 1118c.atlas, 1118c.json, 1118c.xc` | `1118.pkm, 1118c.pkm` |
| **1125** | 8 | 1,126,319 | `1125.atlas, 1125.json, 1125.xc, 1125c.atlas, 1125c.json, 1125c.xc` | `1125.pkm, 1125c.pkm` |
| **1153** | 8 | 1,277,246 | `1153.atlas, 1153.json, 1153.xc, 1153c.atlas, 1153c.json, 1153c.xc` | `1153.pkm, 1153c.pkm` |
| **2043** | 8 | 1,219,719 | `2043.atlas, 2043.json, 2043.xc, 2043c.atlas, 2043c.json, 2043c.xc` | `2043.pkm, 2043c.pkm` |
| **2046** | 8 | 1,262,130 | `2046.atlas, 2046.json, 2046.xc, 2046c.atlas, 2046c.json, 2046c.xc` | `2046.pkm, 2046c.pkm` |
| **3033** | 8 | 1,059,199 | `3033.atlas, 3033.json, 3033.xc, 3033c.atlas, 3033c.json, 3033c.xc` | `3033.pkm, 3033c.pkm` |

---

## 3. Asset Placement & Encoding Rules

1. **Spine Data Files (`.xc`, `.atlas`, `.json`):**
   - Placed into `assets/data/GameData/spine/actor/data/`.
2. **Textures (`.pkm`):**
   - Placed into BOTH `assets/data/GameData/spine/actor/png/` (standard ReturnSaiyan layout) AND `assets/data/GameData/spine/actor/data/` (DB Global legacy layout) to ensure universal Cocos2d-x texture resolver compatibility.
3. **DataBin Re-encoding (`hero.xc`):**
   - String-encoded `phyAct` and `maxHp` fields from DB Global records are parsed via `int()` and re-encoded as 16-bit big-endian unsigned integers (`>H`), strictly adhering to ReturnSaiyan's 48-column binary specification proven in `libaos_jogo.so`.

---

## 4. Verification Checkpoint
- [x] All 21 missing DB Global actor models mapped with exact file listings.
- [x] Remapping matrix resolves all ID collisions while preserving ReturnSaiyan heroes.
- [x] Dual-placement strategy for `.pkm` textures defined.
- [x] Binary re-encoding specification verified against `libaos_jogo.so`.
- [x] Zero modification of original APK or SO files.
