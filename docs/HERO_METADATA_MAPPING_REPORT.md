# ReturnSaiyan — Hero Metadata and Binary Schema Mapping Report

> **Task Key:** `hero-metadata-mapping`  
> **Target Binary:** `libaos_jogo.so` (AArch64, Android ELF)  
> **Target Data Tables:** `assets/data/dataBin/hero.xc` (ReturnSaiyan vs DB Global 1.1.13)  

---

## 1. Binary Disassembly Proof (`libaos_jogo.so`)

Through AArch64 disassembly of `libaos_jogo.so`, the native loader routines and schema definitions were pinpointed:

### 1.1 Loader Routine: `aos::CHeroTable::init()` (`0x0072ef4c`)
- Invokes `aos::TabelasXC::instancia()` at `0x72f01c`.
- Requests the `"hero"` table via `aos::TabelasXC::tabela("hero")` at `0x72f03c`.
- Iterates over the table rows, instantiating `aos::_Hero_St` (size `0x1c8` = 456 bytes) via `operator new` at `0x72f0dc`.
- Populates fields using `aos::TabelaXC::valor(row, columnName)` where `columnName` is queried from static strings.
- Reads `animationId` (0x118b3d5) to bind the actor spine model to the hero record.

### 1.2 Table Schema Definition: `aos::TabelasXC::TabelasXC()` (`0x007983b8`)
- At `0x7983b8`, loads string `"hero.xc"` (`0x118ea25`) and registers 48 columns with explicit type tags.
- Jump table dispatch at `0x7914ac` handles the binary type tags:
  - **Tag 1 (`u32`):** Reads 4-byte big-endian int via `aos::LeitorXC::u32()` (`0x69fea0`).
  - **Tag 3 (`u16`):** Reads 2-byte big-endian unsigned short via `aos::LeitorXC::u16()` (`0x6956a0`).
  - **Tag 5 (`u8`):** Reads 1-byte unsigned char via `aos::LeitorXC::u8()` (`0x67d6e0`).
  - **Tag 7 (`str`):** Reads 4-byte length prefix + UTF-8 payload via `aos::LeitorXC::str()` (`0x67b920`).

---

## 2. Binary Schema Divergence Discovery

| Field | Order | ReturnSaiyan Schema | DB Global 1.1.13 Schema | Compatibility Impact |
| :--- | :---: | :---: | :---: | :--- |
| `id` | 0 | `u32` (4B) | `u32` (4B) | Identical |
| `type` | 1 | `u8` (1B) | `u8` (1B) | Identical |
| `func`..`description` | 2..4 | `str` | `str` | Identical |
| `animationId` | 5 | `u16` (2B) | `u16` (2B) | **Identical (Direct Spine Actor Link)** |
| `photoId` | 6 | `u16` (2B) | `u16` (2B) | Identical |
| `atkType` | 7 | `u8` (1B) | `u8` (1B) | Identical |
| `moveSpeed`, `attackSpeed` | 8..9 | `u16` (2B) | `u16` (2B) | Identical |
| **`phyAct`** | 10 | **`u16` (2B binary)** | **`str` (string encoded)** | **CRITICAL: Direct file replacement causes engine crash** |
| `phyIgnore`..`cri` | 11..15 | `u16` (2B) | `u16` (2B) | Identical |
| **`maxHp`** | 16 | **`u16` (2B binary)** | **`str` (string encoded)** | **CRITICAL: Direct file replacement causes engine crash** |
| `maxMp`..`f_0xd8` | 17..47 | Same (`u16`, `str`, `u8`, `u32`) | Same | Identical |

> [!WARNING]
> Replacing ReturnSaiyan's `hero.xc` directly with DB Global's `hero.xc` would immediately crash the ReturnSaiyan client because `libaos_jogo.so` expects `phyAct` and `maxHp` as 16-bit binary integers, whereas DB Global encodes them as strings. Reversible integration must re-encode DB Global hero records into ReturnSaiyan's binary format.

---

## 3. Hero Reconciliation & Preservation Matrix

### 3.1 Preserved ReturnSaiyan Exclusive Heroes
Per acceptance criteria, all existing ReturnSaiyan heroes must remain intact and playable:
- **Hero ID 10060:** `Ultra Ego Vegeta` (Actor spine model `1060`, Card spine `1060c`).
- **Hero ID 10063:** `Legendary Broly (Fury)` (Actor spine model `1063`, Card spine `1063c`).
- **Hero ID 10064:** `Black Frieza` (Actor spine model `1064`, Card spine `1064c`).
- **Hero IDs 90001..90009:** Custom event heroes (`Iron Man`, `Storm`, `Wolverine`, `Crystal`).

### 3.2 Candidate DB Global Heroes to Integrate
| DBG Hero ID | Hero Name | Actor Model (`animationId`) | Card Spine (`cardSpineId`) | Death Sound (`dieMusic`) | Collision Status |
| :---: | :--- | :---: | :---: | :--- | :--- |
| `10061` | Super Saiyan 4 Gogeta | 1062 | `1062c` | `Die_young_men` | Collides with RS Vegito Blue (Remap to 10081) |
| `10062` | Vados | 1065 | `1065c` | `Die_young_woman` | Available (No collision in RS) |
| `10063` | Towa | 1066 | `1066c` | `Die_young_woman` | Collides with RS Broly (Remap to 10083) |
| `10064` | Toppo | 1067 | `1067c` | `Die_young_men` | Collides with RS Black Frieza (Remap to 10084) |
| `10065` | Jiren | 1069 | `1069c` | `Die_young_woman` | Available (No collision in RS) |
| `10066` | Shin | 1071 | `1071c` | `Die_young_woman` | Available (No collision in RS) |
| `10067` | DC Majin Vegeta | 1072 | `1072c` | `Die_young_men` | Available (No collision in RS) |
| `10068` | DC Super Saiyan 3 | 1073 | `1073c` | `Die_young_men` | Available (No collision in RS) |
| `10069` | Super Saiyan Blue Vegito | 1074 | `1074c` | `Die_young_men` | Available (No collision in RS) |
| `10070` | Arale | 1075 | `1075c` | `Die_young_men` | Available (No collision in RS) |

---

## 4. Verification Checkpoint
- [x] Reverse-engineered exact 48-column schema of `hero.xc` from `libaos_jogo.so`.
- [x] Validated parser on ReturnSaiyan `hero.xc` (128 records, 50,601 bytes, delta 0).
- [x] Validated parser on DB Global `hero.xc` (131 records, 54,140 bytes, delta 0).
- [x] Identified critical schema divergence (`phyAct`/`maxHp` u16 vs str).
- [x] Verified ReturnSaiyan custom hero preservation targets (Ultra Ego Vegeta, Broly, Black Frieza).
- [x] Defined safe remapping strategy for DB Global heroes to prevent ID collisions.
- [x] Zero live network or live game server interaction performed.
