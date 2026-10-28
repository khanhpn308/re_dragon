# Staged Unified Asset Integrity Report

**Project ID:** `5998ee8249b64cf9`  
**Milestone:** `verify-asset-integrity`  
**Date:** 2026-10-27  
**Status:** PASS (6/6 tests passing)

---

## 1. Executive Summary

Automated test suite `tests/test_staged_asset_integrity.py` executed against the staged asset tree in `staging/assets/` and the primary APK archives. All 6 automated test cases passed cleanly, demonstrating complete asset integrity, strict schema compliance, zero regressions on existing ReturnSaiyan heroes, and bit-for-bit immutability of original binary artifacts.

---

## 2. Test Execution Results

```text
test_integrated_candidate_heroes_and_collision_avoidance ... ok
test_original_binaries_immutability ... ok
test_pkm_texture_format_and_dual_placement_parity ... ok
test_preservation_of_all_128_original_returnsaiyan_heroes ... ok
test_staged_hero_xc_binary_schema_and_zero_delta ... ok
test_staged_spine_assets_and_json_validity ... ok

----------------------------------------------------------------------
Ran 6 tests in 2.222s

OK
```

---

## 3. Immutability & Safety Verification

The original game package and native library remain pristine:

| Target File | Expected SHA-256 | Actual SHA-256 | Immutability Status |
|---|---|---|---|
| `ReturnSaiyan-arm64.apk` | `69f500543fae0b9c301a6c871db40198dbba483ee18299081ef8b48aefb2c970` | `69f500543fae0b9c301a6c871db40198dbba483ee18299081ef8b48aefb2c970` | **UNTOUCHED** |
| `libaos_jogo.so` | `5e0aefcbf1b23aa2dc74e95b22aee90c17011a4814193b8b61d305747a668c0f` | `5e0aefcbf1b23aa2dc74e95b22aee90c17011a4814193b8b61d305747a668c0f` | **UNTOUCHED** |

---

## 4. `hero.xc` Binary Table Verification

- **Path:** `staging/assets/data/dataBin/hero.xc`
- **File Size:** 55,084 bytes
- **SHA-256:** `13e73693c3d0a8d15c69008435811c9d2e7b38c1c70ff5e0f6eb0bc8a16a0bec`
- **Schema:** 48 columns (Big-Endian binary layout validated in `aos::CHeroTable::init` and `aos::TabelasXC::TabelasXC`)
- **Total Hero Count:** 138 records (exact buffer consumption, delta 0 bytes)
- **Base Preservation:** All 128 original ReturnSaiyan records are 100% bit-for-bit identical to the source APK.
  - Hero `10060`: *Ultra Ego Vegeta* (Animation `1060`, Card `1060c`) — preserved.
  - Hero `10063`: *Legendary Broly (Fury)* (Animation `1063`, Card `1063c`) — preserved.
  - Hero `10064`: *Black Frieza* (Animation `1064`, Card `1064c`) — preserved.
  - Custom Marvel Heroes: `90001` (Iron Man), `90002` (Storm), `90003` (Wolverine), `90008` (Crystal) — preserved.
- **Candidate DB Global Integration:** All 10 candidate heroes integrated with collision-free slot allocations:
  - `10081`: *Super Saiyan 4 Gogeta* (Animation `1062`, Card `1062c`)
  - `10062`: *Vados* (Animation `1065`, Card `1065c`)
  - `10083`: *Towa* (Animation `1066`, Card `1066c`)
  - `10084`: *Toppo* (Animation `1067`, Card `1067c`)
  - `10065`: *Jiren* (Animation `1069`, Card `1069c`)
  - `10066`: *Shin* (Animation `1071`, Card `1071c`)
  - `10067`: *DC Majin Vegeta* (Animation `1072`, Card `1072c`)
  - `10068`: *DC Super Saiyan 3* (Animation `1073`, Card `1073c`)
  - `10069`: *Super Saiyan Blue Vegito* (Animation `1074`, Card `1074c`)
  - `10070`: *Arale* (Animation `1075`, Card `1075c`)

---

## 5. Spine & Texture Asset Verification

- **Actors Verified:** Exactly 21 actor IDs (`1062, 1065..1078, 1118, 1125, 1153, 2043, 2046, 3033`).
- **Asset Count:** Exactly 160 files staged under `staging/assets/data/GameData/spine/actor/data/`.
  - 40 binary `.xc` skeleton models (loaded by `aos::PacoteSpine::carregar`).
  - 40 `.atlas` texture atlas descriptors.
  - 40 `.json` spine animation descriptors (engine obfuscation byte `0x80` verified).
  - 40 `.pkm` ETC texture files (`ETG\x00\xc8\xe5\xfcw` proprietary engine format verified).
- **Dual-Placement Parity:** All 40 `.pkm` texture files are mirrored under `staging/assets/data/GameData/spine/actor/png/`. SHA-256 parity is 100% verified across both directory resolvers.

---

## 6. Primary Evidence Cross-Reference

- Test script: `tests/test_staged_asset_integrity.py`
- Evidence JSON: `evidence/asset_integrity_report.json`
- Binary reference: `libaos_jogo.so` (`aos::PacoteSpine::carregar` @ `0x00807068`, `aos::CHeroTable::init` @ `0x0072ef4c`)
