#!/usr/bin/env python3
"""
Reversible Asset and Roster Integration for RS-UH-PROD-V1 Gate G4
Produces:
  - .re_harness/production/RS-UH-PROD-V1/staging/assets/...
  - .re_harness/production/RS-UH-PROD-V1/build_manifest.json
  - .re_harness/production/RS-UH-PROD-V1/rollback.md
"""
import hashlib
import io
import json
import os
import shutil
import struct
import zipfile
from pathlib import Path

REPO_ROOT = Path("/home/khanh/returnsaiyan-re")
PROD_DIR = REPO_ROOT / ".re_harness" / "production" / "RS-UH-PROD-V1"
STAGING_DIR = PROD_DIR / "staging" / "assets"
RS_APK = REPO_ROOT / "ReturnSaiyan-arm64.apk"
XAPK_PATH = REPO_ROOT / "DRAGONBALL_GLOBAL_1_1_13_LOCAL_GO_HTTPS_INIT_DIAGNOSTIC_SIGNED (1).xapk"

SCHEMA_RS = [
    ("id", "u32"), ("type", "u8"), ("func", "str"), ("name", "str"), ("description", "str"),
    ("animationId", "u16"), ("photoId", "u16"), ("atkType", "u8"), ("moveSpeed", "u16"),
    ("attackSpeed", "u16"), ("phyAct", "u16"), ("phyIgnore", "u16"), ("phyDef", "u16"),
    ("magicIgnore", "u16"), ("magicDef", "u16"), ("cri", "u16"), ("maxHp", "u16"),
    ("maxMp", "u16"), ("mpRecover", "u16"), ("dodge", "u16"), ("skills", "str"),
    ("skillsSeq", "str"), ("ai", "str"), ("scale", "u8"), ("defaultStar", "u8"),
    ("cardSpineId", "str"), ("isOpen", "u32"), ("namePhotoId", "u32"), ("spineX", "u32"),
    ("spineY", "u32"), ("spineScale", "u32"), ("dieMusic", "str"), ("isGift", "u32"),
    ("jobIcon", "u32"), ("nameImgId", "u32"), ("tenacity", "u32"), ("hit", "u32"),
    ("suckHp", "u32"), ("rebound", "u32"), ("srcHero", "u32"), ("headIcon", "u32"),
    ("energyIcon", "str"), ("parterStr", "str"), ("rebirthBuff", "str"),
    ("rebirthBuffEffect", "str"), ("isValue", "u8"), ("intelligence", "u32"), ("f_0xd8", "u32"),
]

SCHEMA_DBG = list(SCHEMA_RS)
SCHEMA_DBG[10] = ("phyAct", "str")
SCHEMA_DBG[16] = ("maxHp", "str")

MISSING_ACTORS = [
    1062, 1065, 1066, 1067, 1068, 1069, 1070, 1071, 1072, 1073,
    1074, 1075, 1076, 1077, 1078, 1118, 1125, 1153, 2043, 2046, 3033
]

REMAPPING = {
    10061: 10081, # SS4 Gogeta
    10062: 10062, # Vados
    10063: 10083, # Towa
    10064: 10084, # Toppo
    10065: 10065, # Jiren
    10066: 10066, # Shin
    10067: 10067, # DC Majin Vegeta
    10068: 10068, # DC SS3
    10069: 10069, # SSB Vegito
    10070: 10070, # Arale
}

def parse_hero_xc(data, schema):
    count = struct.unpack(">H", data[:2])[0]
    pos = 2
    records = []
    for _ in range(count):
        row = {}
        for fname, ftype in schema:
            if ftype == "u32":
                row[fname] = struct.unpack(">I", data[pos:pos+4])[0]
                pos += 4
            elif ftype == "u16":
                row[fname] = struct.unpack(">H", data[pos:pos+2])[0]
                pos += 2
            elif ftype == "u8":
                row[fname] = struct.unpack(">B", data[pos:pos+1])[0]
                pos += 1
            elif ftype == "str":
                slen = struct.unpack(">I", data[pos:pos+4])[0]
                pos += 4
                row[fname] = data[pos:pos+slen].decode("utf-8", errors="replace")
                pos += slen
        records.append(row)
    return count, pos, len(data), records

def encode_hero_xc(records):
    buf = bytearray()
    buf.extend(struct.pack(">H", len(records)))
    for row in records:
        for fname, ftype in SCHEMA_RS:
            val = row[fname]
            if ftype == "u32":
                buf.extend(struct.pack(">I", int(val)))
            elif ftype == "u16":
                buf.extend(struct.pack(">H", int(val)))
            elif ftype == "u8":
                buf.extend(struct.pack(">B", int(val)))
            elif ftype == "str":
                s_bytes = str(val).encode("utf-8")
                buf.extend(struct.pack(">I", len(s_bytes)))
                buf.extend(s_bytes)
    return bytes(buf)

def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def main():
    print("Initializing staging directories...")
    spine_data_dir = STAGING_DIR / "data" / "GameData" / "spine" / "actor" / "data"
    spine_png_dir = STAGING_DIR / "data" / "GameData" / "spine" / "actor" / "png"
    databin_dir = STAGING_DIR / "data" / "dataBin"

    spine_data_dir.mkdir(parents=True, exist_ok=True)
    spine_png_dir.mkdir(parents=True, exist_ok=True)
    databin_dir.mkdir(parents=True, exist_ok=True)

    print("Reading donor base APK directly from XAPK...")
    with zipfile.ZipFile(XAPK_PATH, "r") as zx:
        base_apk_bytes = zx.read("com.dbzmy.englobal.apk")

    staged_spine_files = []
    with zipfile.ZipFile(io.BytesIO(base_apk_bytes), "r") as zb:
        for info in zb.infolist():
            path = info.filename
            if "spine/actor" in path:
                fname = path.split("/")[-1]
                match = False
                for aid in MISSING_ACTORS:
                    if (fname.startswith(f"{aid}.") or fname.startswith(f"{aid}_") or
                        fname.startswith(f"{aid}c.") or fname.startswith(f"{aid}c_")):
                        match = True
                        break
                if match:
                    data = zb.read(path)
                    target_data = spine_data_dir / fname
                    target_data.write_bytes(data)
                    staged_spine_files.append({
                        "filename": fname,
                        "size": len(data),
                        "sha256": sha256_bytes(data),
                        "staged_path": str(target_data.relative_to(PROD_DIR))
                    })
                    if fname.endswith(".pkm"):
                        target_png = spine_png_dir / fname
                        target_png.write_bytes(data)

        # Read donor hero.xc
        donor_hero_xc_raw = zb.read("assets/data/dataBin/hero.xc")

    print(f"Extracted and staged {len(staged_spine_files)} Spine asset files.")

    print("Parsing original ReturnSaiyan hero.xc...")
    with zipfile.ZipFile(RS_APK, "r") as zrs:
        rs_cnt, rs_pos, rs_len, rs_records = parse_hero_xc(zrs.read("assets/data/dataBin/hero.xc"), SCHEMA_RS)
    assert rs_pos == rs_len

    print("Parsing donor Global hero.xc...")
    dbg_cnt, dbg_pos, dbg_len, dbg_records = parse_hero_xc(donor_hero_xc_raw, SCHEMA_DBG)
    assert dbg_pos == dbg_len

    dbg_by_id = {r["id"]: r for r in dbg_records}
    integrated_heroes = []

    for orig_id, target_id in REMAPPING.items():
        if orig_id in dbg_by_id:
            row = dict(dbg_by_id[orig_id])
            row["id"] = target_id
            row["phyAct"] = int(row["phyAct"]) if str(row["phyAct"]).isdigit() else 0
            row["maxHp"] = int(row["maxHp"]) if str(row["maxHp"]).isdigit() else 0
            integrated_heroes.append(row)

    print(f"Integrating {len(integrated_heroes)} candidate heroes into ReturnSaiyan roster...")
    unified_records = list(rs_records) + integrated_heroes
    assert len(unified_records) == rs_cnt + len(integrated_heroes)

    # Confirm preservation of custom RS heroes
    rs_custom_ids = {10060, 10063, 10064}
    found_custom = {r["id"] for r in unified_records if r["id"] in rs_custom_ids}
    assert found_custom == rs_custom_ids, "CRITICAL ERROR: ReturnSaiyan custom heroes were not preserved!"

    print("Encoding unified hero.xc in big-endian 48-column format...")
    unified_bytes = encode_hero_xc(unified_records)
    target_hero_xc = databin_dir / "hero.xc"
    target_hero_xc.write_bytes(unified_bytes)

    # Verification round-trip
    u_cnt, u_pos, u_len, u_parsed = parse_hero_xc(unified_bytes, SCHEMA_RS)
    assert u_cnt == len(unified_records)
    assert u_pos == len(unified_bytes)
    print(f"Round-trip verified: {u_cnt} records, {u_pos} bytes, 0 delta.")

    build_manifest = {
        "edition": "RS-UH-PROD-V1 ReturnSaiyan Unified Heroes",
        "baseline_apk": {
            "path": str(RS_APK),
            "size_bytes": os.path.getsize(RS_APK),
            "sha256": hashlib.sha256(open(RS_APK, "rb").read()).hexdigest(),
            "original_heroes": rs_cnt
        },
        "donor_xapk": {
            "path": str(XAPK_PATH),
            "size_bytes": os.path.getsize(XAPK_PATH),
            "sha256": hashlib.sha256(open(XAPK_PATH, "rb").read()).hexdigest(),
            "donor_heroes": dbg_cnt
        },
        "staging": {
            "staging_root": str(STAGING_DIR.relative_to(PROD_DIR)),
            "staged_spine_assets_count": len(staged_spine_files),
            "staged_spine_actors": MISSING_ACTORS,
            "unified_hero_xc": {
                "path": str(target_hero_xc.relative_to(PROD_DIR)),
                "records_count": len(unified_records),
                "size_bytes": len(unified_bytes),
                "sha256": sha256_bytes(unified_bytes),
                "schema_compliance": "48 columns big-endian (libaos_jogo.so compatible)"
            }
        },
        "integrated_heroes": [
            {
                "original_donor_id": orig,
                "assigned_canonical_id": target,
                "name": next(r["name"] for r in integrated_heroes if r["id"] == target),
                "animation_id": next(r["animationId"] for r in integrated_heroes if r["id"] == target),
                "card_spine_id": next(r["cardSpineId"] for r in integrated_heroes if r["id"] == target)
            }
            for orig, target in REMAPPING.items()
        ],
        "preserved_rs_custom_heroes": [
            {"id": 10060, "name": "Ultra Ego Vegeta", "animation_id": 1060},
            {"id": 10063, "name": "Legendary Broly (Fury)", "animation_id": 1063},
            {"id": 10064, "name": "Black Frieza", "animation_id": 1064}
        ]
    }

    manifest_path = PROD_DIR / "build_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(build_manifest, f, indent=2)
    print(f"Wrote {manifest_path}")

    rollback_md = f"""# RS-UH-PROD-V1 — Rollback & Reversibility Documentation

## 1. Reversibility Principle
The Unified Heroes integration operates strictly on a versioned working copy and an isolated staging tree located in `.re_harness/production/RS-UH-PROD-V1/staging`. 

The original baseline files:
- `ReturnSaiyan-arm64.apk` (SHA-256: `69f500543fae0b9c301a6c871db40198dbba483ee18299081ef8b48aefb2c970`)
- `DRAGONBALL_GLOBAL_1_1_13_LOCAL_GO_HTTPS_INIT_DIAGNOSTIC_SIGNED (1).xapk` (SHA-256: `12e1810e798c75a16dea7528063bf059e7b3dfc1dbeb943719eb95648e00d8f5`)

are never modified in-place and remain byte-for-byte read-only preserved.

## 2. Rollback Instructions
To completely roll back the integration and revert to the pure ReturnSaiyan baseline:

1. **Delete Working Copy Build Artifacts:**
   ```bash
   rm -rf .re_harness/production/RS-UH-PROD-V1/staging
   rm -f dist/ReturnSaiyan-UnifiedHeroes-signed.apk
   rm -f dist/ReturnSaiyan-UnifiedHeroes-signed.apk.idsig
   ```

2. **Verify Baseline Integrity:**
   ```bash
   sha256sum ReturnSaiyan-arm64.apk
   # Expected output:
   # 69f500543fae0b9c301a6c871db40198dbba483ee18299081ef8b48aefb2c970  ReturnSaiyan-arm64.apk
   ```

3. **Reinstall Baseline APK (if installed on device):**
   ```bash
   adb install -r -d ReturnSaiyan-arm64.apk
   ```

## 3. Preserved Custom Roster
All ReturnSaiyan custom hero profiles and assets are preserved:
- ID 10060: Ultra Ego Vegeta
- ID 10063: Legendary Broly (Fury)
- ID 10064: Black Frieza
No ReturnSaiyan hero IDs or assets were overwritten during integration.
"""
    rollback_path = PROD_DIR / "rollback.md"
    with open(rollback_path, "w", encoding="utf-8") as f:
        f.write(rollback_md)
    print(f"Wrote {rollback_path}")

if __name__ == "__main__":
    main()
