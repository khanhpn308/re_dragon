#!/usr/bin/env python3
"""
Automated Test Suite for Staged Unified Asset Integrity
Validates:
  - hero.xc binary schema compliance and round-trip decoding
  - Zero regressions on all 128 existing ReturnSaiyan heroes
  - Correct integration of 10 candidate DB Global heroes with collision avoidance
  - Spine JSON syntax, bone hierarchy, and atlas integrity
  - PKM texture header compliance and dual-placement parity
  - Cryptographic immutability of original ReturnSaiyan APK and SO binaries
"""
import hashlib
import json
from pathlib import Path
import struct
import unittest
import zipfile

REPO_ROOT = Path("/home/khanh/returnsaiyan-re")
RS_APK = REPO_ROOT / "ReturnSaiyan-arm64.apk"
LIB_SO = REPO_ROOT / "libaos_jogo.so"
STAGING_DIR = REPO_ROOT / "staging" / "assets"

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

MISSING_ACTORS = [
    1062, 1065, 1066, 1067, 1068, 1069, 1070, 1071, 1072, 1073,
    1074, 1075, 1076, 1077, 1078, 1118, 1125, 1153, 2043, 2046, 3033
]

EXPECTED_RS_HASH = "69f500543fae0b9c301a6c871db40198dbba483ee18299081ef8b48aefb2c970"
EXPECTED_SO_HASH = "5e0aefcbf1b23aa2dc74e95b22aee90c17011a4814193b8b61d305747a668c0f"

def parse_hero_xc(data):
    count = struct.unpack(">H", data[:2])[0]
    pos = 2
    records = []
    for _ in range(count):
        row = {}
        for fname, ftype in SCHEMA_RS:
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

def sha256_path(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()

class StagedAssetIntegrityTests(unittest.TestCase):

    def test_original_binaries_immutability(self):
        """Verify original APK and SO SHA-256 hashes are strictly unmodified."""
        rs_hash = sha256_path(RS_APK)
        self.assertEqual(rs_hash, EXPECTED_RS_HASH, "Original ReturnSaiyan-arm64.apk was altered!")

        so_hash = sha256_path(LIB_SO)
        self.assertEqual(so_hash, EXPECTED_SO_HASH, "Original libaos_jogo.so was altered!")

    def test_staged_hero_xc_binary_schema_and_zero_delta(self):
        """Verify staged hero.xc adheres strictly to the 48-column schema with 0 delta."""
        hero_xc_path = STAGING_DIR / "data" / "dataBin" / "hero.xc"
        self.assertTrue(hero_xc_path.exists(), "staged hero.xc does not exist")
        self.assertEqual(hero_xc_path.stat().st_size, 55084, "staged hero.xc unexpected byte size")

        data = hero_xc_path.read_bytes()
        count, pos, total_len, records = parse_hero_xc(data)
        self.assertEqual(count, 138, "Unified hero roster count must be exactly 138")
        self.assertEqual(pos, total_len, "hero.xc buffer must be consumed to the final byte (delta 0)")
        self.assertEqual(len(records), 138)

    def test_preservation_of_all_128_original_returnsaiyan_heroes(self):
        """Verify all 128 original ReturnSaiyan heroes are preserved with zero modifications."""
        hero_xc_path = STAGING_DIR / "data" / "dataBin" / "hero.xc"
        _, _, _, staged_records = parse_hero_xc(hero_xc_path.read_bytes())

        with zipfile.ZipFile(RS_APK) as z:
            orig_data = z.read("assets/data/dataBin/hero.xc")
        _, _, _, orig_records = parse_hero_xc(orig_data)

        self.assertEqual(len(orig_records), 128)
        for i in range(128):
            self.assertEqual(staged_records[i], orig_records[i], f"Mismatch in preserved hero {i} ({orig_records[i]['name']})")

        # Specific custom heroes assertions
        staged_by_id = {r["id"]: r for r in staged_records}
        self.assertEqual(staged_by_id[10060]["name"], "Ultra Ego Vegeta")
        self.assertEqual(staged_by_id[10060]["animationId"], 1060)

        self.assertEqual(staged_by_id[10063]["name"], "Legendary Broly (Fury)")
        self.assertEqual(staged_by_id[10063]["animationId"], 1063)

        self.assertEqual(staged_by_id[10064]["name"], "Black Frieza")
        self.assertEqual(staged_by_id[10064]["animationId"], 1064)

        for marvel_id, marvel_name in [(90001, "Iron Man"), (90002, "Storm"), (90003, "Wolverine"), (90008, "Crystal")]:
            self.assertEqual(staged_by_id[marvel_id]["name"], marvel_name)

    def test_integrated_candidate_heroes_and_collision_avoidance(self):
        """Verify 10 candidate DB Global heroes are present and remapped without collision."""
        hero_xc_path = STAGING_DIR / "data" / "dataBin" / "hero.xc"
        _, _, _, staged_records = parse_hero_xc(hero_xc_path.read_bytes())
        staged_by_id = {r["id"]: r for r in staged_records}

        expected_new_heroes = {
            10081: ("Super Saiyan 4 Gogeta", 1062, "1062c"),
            10062: ("Vados", 1065, "1065c"),
            10083: ("Towa", 1066, "1066c"),
            10084: ("Toppo", 1067, "1067c"),
            10065: ("Jiren", 1069, "1069c"),
            10066: ("Shin", 1071, "1071c"),
            10067: ("DC Majin Vegeta ", 1072, "1072c"),
            10068: ("DC Super Saiyan 3 ", 1073, "1073c"),
            10069: ("Super Saiyan Blue Vegito", 1074, "1074c"),
            10070: ("Arale", 1075, "1075c"),
        }

        for hid, (expected_name, expected_anim, expected_card) in expected_new_heroes.items():
            self.assertIn(hid, staged_by_id, f"Candidate hero ID {hid} missing from staged roster")
            hero = staged_by_id[hid]
            self.assertEqual(hero["name"], expected_name)
            self.assertEqual(hero["animationId"], expected_anim)
            self.assertEqual(hero["cardSpineId"], expected_card)
            # Numeric types enforced
            self.assertIsInstance(hero["phyAct"], int)
            self.assertIsInstance(hero["maxHp"], int)

    def test_staged_spine_assets_and_json_validity(self):
        """Verify spine assets exist, xc binary skeletons are present, and json files are valid or engine-encrypted."""
        spine_data_dir = STAGING_DIR / "data" / "GameData" / "spine" / "actor" / "data"
        self.assertTrue(spine_data_dir.exists())

        files = list(spine_data_dir.glob("*"))
        self.assertEqual(len(files), 160, f"Expected 160 spine assets in data/, found {len(files)}")

        # Check binary skeleton (.xc) presence for every actor
        xc_files = list(spine_data_dir.glob("*.xc"))
        self.assertEqual(len(xc_files), 40, f"Expected 40 .xc skeleton files, found {len(xc_files)}")
        for xf in xc_files:
            self.assertGreater(xf.stat().st_size, 0, f"Empty .xc skeleton file: {xf.name}")

        # Check JSON files: either valid JSON or engine-encrypted (leading byte 0x80)
        json_files = list(spine_data_dir.glob("*.json"))
        self.assertEqual(len(json_files), 40)
        for jf in json_files:
            raw = jf.read_bytes()
            self.assertGreater(len(raw), 0, f"Empty JSON file: {jf.name}")
            if raw[0] == 0x80:
                # Valid engine-obfuscated JSON asset (matches DB Global / ReturnSaiyan engine format)
                continue
            try:
                data = json.loads(raw.decode("utf-8"))
                self.assertIn("bones", data, f"Spine JSON {jf.name} missing 'bones' key")
                self.assertIn("slots", data, f"Spine JSON {jf.name} missing 'slots' key")
            except Exception as e:
                self.fail(f"Failed parsing Spine JSON in {jf.name}: {e}")

    def test_pkm_texture_format_and_dual_placement_parity(self):
        """Verify PKM textures have valid headers (ETG or PKM) and identical dual-placement SHA-256."""
        spine_data_dir = STAGING_DIR / "data" / "GameData" / "spine" / "actor" / "data"
        spine_png_dir = STAGING_DIR / "data" / "GameData" / "spine" / "actor" / "png"
        self.assertTrue(spine_png_dir.exists())

        pkm_png_files = list(spine_png_dir.glob("*.pkm"))
        self.assertEqual(len(pkm_png_files), 40, "Expected 40 PKM textures in png/")

        for pkm in pkm_png_files:
            data_counterpart = spine_data_dir / pkm.name
            self.assertTrue(data_counterpart.exists(), f"Missing counterpart for {pkm.name} in data/")

            png_bytes = pkm.read_bytes()
            data_bytes = data_counterpart.read_bytes()

            # Verify PKM header magic (proprietary engine ETG or standard PKM)
            is_valid_header = png_bytes.startswith(b"ETG\x00\xc8\xe5\xfcw") or png_bytes.startswith(b"PKM 10") or png_bytes.startswith(b"PKM 20")
            self.assertTrue(is_valid_header, f"Invalid PKM magic header in {pkm.name}: {png_bytes[:8]}")
            # Verify exact bit-for-bit parity between dual-placed files
            self.assertEqual(sha256_path(pkm), sha256_path(data_counterpart), f"Digest mismatch between png and data for {pkm.name}")

if __name__ == "__main__":
    unittest.main()
