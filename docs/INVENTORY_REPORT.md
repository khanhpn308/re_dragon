# ReturnSaiyan — Comprehensive Resource Inventory Report

> **Project:** ReturnSaiyan Unified Heroes Edition  
> **ReturnSaiyan APK SHA-256:** `69f500543fae0b9c301a6c871db40198dbba483ee18299081ef8b48aefb2c970`  
> **Dragon Ball Global 1.1.13 APK SHA-256:** `5de300eb71d37a52debfafd45f47049d590d73024ceddd7d1b061067e85a8c71`  
> **Task Key:** `inventory-resources`  

---

## 1. Executive Summary

This report provides an exhaustive, binary-backed manifest comparison between the playable **ReturnSaiyan** client (`ReturnSaiyan-arm64.apk`) and **Dragon Ball Global 1.1.13** (`com.dbzmy.englobal.apk`).

| Metric | ReturnSaiyan | DB Global 1.1.13 | Delta / Outcome |
| :--- | :---: | :---: | :--- |
| **Total Files in Archive** | 5897 | 5766 | +131 in ReturnSaiyan |
| **Spine Actor Assets** | 1265 | 748 | ReturnSaiyan has more animations per existing actor |
| **Unique Actor IDs** | 96 | 116 | **21 Missing Actors in RS**, **1 Unique Actor in RS** |
| **GameData Maps** | 21 | 21 | Identical 21 map zones (`.pkm`) |
| **Audio / Sound Files** | 195 | 195 | Identical 195 audio tracks (`.ogg`, `.mp3`) |
| **DataBin Tables (`.xc`)** | 39 | 38 | 39 in RS vs 38 in DBG (`hero.xc`, `buffs.xc`, etc.) |

---

## 2. Actor ID Delta Matrix

### 2.1 Missing Actors in ReturnSaiyan (21 Actors)
The following actor IDs exist in DB Global 1.1.13 but are absent from ReturnSaiyan. These represent candidate hero/monster models to integrate into the Unified Heroes Edition:

| Actor ID | File Count | Total Size (Bytes) | Representative Asset Files |
| :---: | :---: | :---: | :--- |
| **1062** | 8 | 1,547,577 | `1062.atlas, 1062.json, 1062.pkm, 1062.xc, ... (+4 more)` |
| **1065** | 8 | 1,639,100 | `1065.atlas, 1065.json, 1065.pkm, 1065.xc, ... (+4 more)` |
| **1066** | 8 | 1,538,547 | `1066.atlas, 1066.json, 1066.pkm, 1066.xc, ... (+4 more)` |
| **1067** | 8 | 1,496,363 | `1067.atlas, 1067.json, 1067.pkm, 1067.xc, ... (+4 more)` |
| **1068** | 4 | 431,060 | `1068.atlas, 1068.json, 1068.pkm, 1068.xc` |
| **1069** | 8 | 1,501,820 | `1069.atlas, 1069.json, 1069.pkm, 1069.xc, ... (+4 more)` |
| **1070** | 4 | 438,287 | `1070.atlas, 1070.json, 1070.pkm, 1070.xc` |
| **1071** | 8 | 1,485,149 | `1071.atlas, 1071.json, 1071.pkm, 1071.xc, ... (+4 more)` |
| **1072** | 8 | 1,693,162 | `1072.atlas, 1072.json, 1072.pkm, 1072.xc, ... (+4 more)` |
| **1073** | 8 | 1,829,559 | `1073.atlas, 1073.json, 1073.pkm, 1073.xc, ... (+4 more)` |
| **1074** | 8 | 1,044,115 | `1074.atlas, 1074.json, 1074.pkm, 1074.xc, ... (+4 more)` |
| **1075** | 8 | 681,043 | `1075.atlas, 1075.json, 1075.pkm, 1075.xc, ... (+4 more)` |
| **1076** | 8 | 1,111,931 | `1076.atlas, 1076.json, 1076.pkm, 1076.xc, ... (+4 more)` |
| **1077** | 8 | 981,420 | `1077.atlas, 1077.json, 1077.pkm, 1077.xc, ... (+4 more)` |
| **1078** | 8 | 993,897 | `1078.atlas, 1078.json, 1078.pkm, 1078.xc, ... (+4 more)` |
| **1118** | 8 | 1,235,726 | `1118.atlas, 1118.json, 1118.pkm, 1118.xc, ... (+4 more)` |
| **1125** | 8 | 1,126,319 | `1125.atlas, 1125.json, 1125.pkm, 1125.xc, ... (+4 more)` |
| **1153** | 8 | 1,277,246 | `1153.atlas, 1153.json, 1153.pkm, 1153.xc, ... (+4 more)` |
| **2043** | 8 | 1,219,719 | `2043.atlas, 2043.json, 2043.pkm, 2043.xc, ... (+4 more)` |
| **2046** | 8 | 1,262,130 | `2046.atlas, 2046.json, 2046.pkm, 2046.xc, ... (+4 more)` |
| **3033** | 8 | 1,059,199 | `3033.atlas, 3033.json, 3033.pkm, 3033.xc, ... (+4 more)` |

### 2.2 Unique Newer Actors in ReturnSaiyan (1 Actor)
Per project acceptance criteria, ReturnSaiyan's existing heroes must be strictly preserved without regression:

- **Actor `[1064]`**: Exists exclusively in ReturnSaiyan (`assets/data/GameData/spine/actor/data/1064*`). Must NOT be overwritten or corrupted.

### 2.3 Shared Actors (95 Actors)
Both clients share 95 actor models (IDs 1000 through 2033).

---

## 3. Asset Integrity and Format Findings

1. **Spine Data Format (`.xc`, `.atlas`):**
   - Skeletons and animation sequences use binary `.xc` encoding with identical internal byte signatures in both APKs.
   - Texture atlases (`.atlas`) share identical cryptographic hashes for common actors (e.g. `1000.atlas` CRC/SHA match).
2. **Textures (`.pkm`):**
   - Textures in both clients use standard Ericsson Texture Compression (ETC1) PKM containers under `spine/actor/png/` and `map/`.
3. **DataBin Layout (`assets/data/dataBin/hero.xc`):**
   - ReturnSaiyan defines **39** data tables; DB Global defines **38** data tables.
   - `hero.xc` in ReturnSaiyan contains 128 hero profiles; DB Global contains 131 hero profiles.

---

## 4. Verification Checkpoint
- [x] Both APK hashes computed and documented.
- [x] Complete file inventories mapped to functional categories.
- [x] Exact 21 missing actor IDs in DB Global identified.
- [x] Unique ReturnSaiyan actor ID (1064) verified for preservation.
- [x] Zero network or server interaction performed.
- [x] Original APK and SO left completely unmodified.
