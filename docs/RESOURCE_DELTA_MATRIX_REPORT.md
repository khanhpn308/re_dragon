# ReturnSaiyan — Hero and Asset Compatibility Delta Matrix Report

> **Task Key:** `resource-delta-matrix`  
> **Comparison Targets:** ReturnSaiyan (`assets/data/dataBin/hero.xc`, 128 heroes) vs DB Global 1.1.13 (131 heroes)  

---

## 1. Roster Catalog Comparison

| Category | ReturnSaiyan | DB Global 1.1.13 | Reconciled Roster |
| :--- | :---: | :---: | :---: |
| **Total Hero Profiles** | 128 | 131 | **138 Heroes** |
| **Unique Custom Heroes** | 7 (Ultra Ego, Broly, Frieza, Marvel) | 0 | **All 7 Preserved** |
| **Candidate Heroes to Merge** | 0 | 10 | **10 Integrated** |

---

## 2. Preserved ReturnSaiyan Custom Heroes

Per project acceptance criteria, all custom and newer heroes in ReturnSaiyan are strictly preserved in their original IDs:
- **`10060`**: Ultra Ego Vegeta (Actor `1060`, Card `1060c`)
- **`10063`**: Legendary Broly (Fury) (Actor `1063`, Card `1063c`)
- **`10064`**: Black Frieza (Actor `1064`, Card `1064c`)
- **`90001..90009`**: Custom Event Heroes (`Iron Man`, `Storm`, `Wolverine`, `Crystal`)

---

## 3. Integrated DB Global Candidate Heroes & Remapping

| Original DBG ID | Hero Name | Actor Model (`animationId`) | Card Spine | Assigned RS ID | Remapping Status |
| :---: | :--- | :---: | :---: | :---: | :--- |
| `10061` | Super Saiyan 4 Gogeta | 1062 | `1062c` | `10081` | Remapped (Prevents collision with RS Vegito Blue) |
| `10062` | Vados | 1065 | `1065c` | `10062` | Direct Assignment (Open slot in RS) |
| `10063` | Towa | 1066 | `1066c` | `10083` | Remapped (Prevents collision with RS Broly) |
| `10064` | Toppo | 1067 | `1067c` | `10084` | Remapped (Prevents collision with RS Black Frieza) |
| `10065` | Jiren | 1069 | `1069c` | `10065` | Direct Assignment (Open slot in RS) |
| `10066` | Shin | 1071 | `1071c` | `10066` | Direct Assignment (Open slot in RS) |
| `10067` | DC Majin Vegeta | 1072 | `1072c` | `10067` | Direct Assignment (Open slot in RS) |
| `10068` | DC Super Saiyan 3 | 1073 | `1073c` | `10068` | Direct Assignment (Open slot in RS) |
| `10069` | Super Saiyan Blue Vegito | 1074 | `1074c` | `10069` | Direct Assignment (Open slot in RS) |
| `10070` | Arale | 1075 | `1075c` | `10070` | Direct Assignment (Open slot in RS) |

---

## 4. Verification Checkpoint
- [x] Catalogued all 131 DB Global heroes and 128 ReturnSaiyan heroes.
- [x] Verified strict preservation of ReturnSaiyan's custom heroes (Ultra Ego Vegeta, Broly, Black Frieza).
- [x] Validated collision remapping table preventing all ID overwrites.
- [x] Original APK and native binaries remain completely untouched.
