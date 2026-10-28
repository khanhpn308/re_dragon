#!/usr/bin/env python3
"""
Regression and Packaging Verification Suite for ReturnSaiyan Unified Heroes APK
"""
import hashlib
from pathlib import Path
import struct
import unittest
import zipfile

REPO_ROOT = Path("/home/khanh/returnsaiyan-re")
ORIG_APK = REPO_ROOT / "ReturnSaiyan-arm64.apk"
PKG_APK = REPO_ROOT / "dist" / "ReturnSaiyan-UnifiedHeroes-signed.apk"
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

class PackagedApkRegressionTests(unittest.TestCase):

    def test_dex_and_native_binaries_unaltered(self):
        """Verify classes.dex and native libaos_jogo.so inside the packaged APK are 100% bitwise identical to original."""
        with zipfile.ZipFile(ORIG_APK, "r") as orig_z, zipfile.ZipFile(PKG_APK, "r") as pkg_z:
            for binary_entry in ["classes.dex", "lib/arm64-v8a/libaos_jogo.so", "AndroidManifest.xml"]:
                self.assertIn(binary_entry, pkg_z.namelist())
                orig_bytes = orig_z.read(binary_entry)
                pkg_bytes = pkg_z.read(binary_entry)
                self.assertEqual(hashlib.sha256(orig_bytes).hexdigest(), hashlib.sha256(pkg_bytes).hexdigest(), f"Mismatch in {binary_entry}")

    def test_packaged_hero_xc_integrity(self):
        """Verify hero.xc inside packaged APK is identical to staged unified table and contains 138 heroes."""
        with zipfile.ZipFile(PKG_APK, "r") as pkg_z:
            hero_data = pkg_z.read("assets/data/dataBin/hero.xc")
        staged_data = (STAGING_DIR / "data" / "dataBin" / "hero.xc").read_bytes()
        self.assertEqual(hashlib.sha256(hero_data).hexdigest(), hashlib.sha256(staged_data).hexdigest())

        count, pos, total_len, records = parse_hero_xc(hero_data)
        self.assertEqual(count, 138)
        self.assertEqual(pos, total_len)

    def test_spine_assets_in_packaged_apk(self):
        """Verify all staged Spine assets are successfully packaged inside the APK."""
        with zipfile.ZipFile(PKG_APK, "r") as pkg_z:
            pkg_names = set(pkg_z.namelist())

        for p in (STAGING_DIR / "data" / "GameData" / "spine" / "actor" / "data").glob("*"):
            rel_path = f"assets/data/GameData/spine/actor/data/{p.name}"
            self.assertIn(rel_path, pkg_names, f"Missing {rel_path} in APK")

        for p in (STAGING_DIR / "data" / "GameData" / "spine" / "actor" / "png").glob("*"):
            rel_path = f"assets/data/GameData/spine/actor/png/{p.name}"
            self.assertIn(rel_path, pkg_names, f"Missing {rel_path} in APK")

if __name__ == "__main__":
    unittest.main()
