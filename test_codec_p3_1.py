#!/usr/bin/env python3
"""
P3.1 Packet Schema Reconciliation & Independent Verification Suite
Tests all 27 opcodes against ARM64 disassembly ground truth from libaos_jogo.so.
Special audit focus on the 13 reconciled opcodes:
  0x00, 0x01, 0x04, 0x08, 0x0A, 0x10, 0x12, 0x21, 0x25, 0x2A, 0x2C, 0x2F, 0x30.
Validates:
  - Strict distinction between STATIC (VERIFIED) and DYNAMIC (PARTIAL) schemas.
  - Header decoding and variable body preservation for count loops.
  - Exact field counts and data types matching AArch64 LeitorPacote calls.
Target SHA-256: 5e0aefcbf1b23aa2dc74e95b22aee90c17011a4814193b8b61d305747a668c0f
"""

import struct
import pytest
from returnsaiyan_codec import (
    CryptoCore,
    PacketWriter,
    PacketReader,
    ConnectionState,
    StreamDecoder,
    OpcodeRegistry,
)

# Ground-truth Manifest extracted directly from AArch64 machine instructions:
# (Opcode, Lambda, Handler Address, Vtable Address, Structure Type, Status, Schema)
EXPECTED_27_MANIFEST = {
    0x00: ("$_5", 0x007f06c8, 0x014f0e60, "STATIC", "VERIFIED", ["str"]),
    0x01: ("$_6", 0x007f0a0c, 0x014f0ee0, "DYNAMIC", "PARTIAL", ["str", "u8"]),
    0x04: ("$_7", 0x007f4ba4, 0x014f0f60, "STATIC", "VERIFIED", ["str", "str"]),
    0x05: ("$_8", 0x007f4de4, 0x014f0fe0, "STATIC", "VERIFIED", ["str"]),
    0x07: ("$_9", 0x007f5060, 0x014f1060, "STATIC", "VERIFIED", ["u8", "str"]),
    0x08: ("$_10", 0x007f5604, 0x014f10e0, "STATIC", "VERIFIED", ["u8"]),
    0x0A: ("$_11", 0x007f5690, 0x014f1160, "STATIC", "VERIFIED", ["str"]),
    0x10: ("$_13", 0x007f5a8c, 0x014f1260, "DYNAMIC", "PARTIAL", ["i32", "i64", "i32", "i32", "i32", "i32", "i32", "i32", "u8", "u8", "i32", "u8", "str"]),
    0x12: ("$_12", 0x007f57b0, 0x014f11e0, "STATIC", "VERIFIED", ["u8", "str"]),
    0x20: ("$_14", 0x007f7078, 0x014f12e0, "DYNAMIC", "PARTIAL", ["i16", "i64", "i32", "i16", "i16", "i32", "i64"]),
    0x21: ("$_15", 0x007f7b9c, 0x014f1360, "DYNAMIC", "PARTIAL", ["str", "i32", "u8", "i32", "u8", "u8", "u8", "i32", "u8"]),
    0x25: ("$_16", 0x007f7f00, 0x014f13e0, "STATIC", "VERIFIED", ["i64", "i32", "i16", "i16", "u8", "i32"]),
    0x26: ("$_17", 0x007f8058, 0x014f1460, "STATIC", "VERIFIED", ["str", "u8", "str", "u8"]),
    0x27: ("$_18", 0x007f85c8, 0x014f14e0, "STATIC", "VERIFIED", ["i32"]),
    0x28: ("$_19", 0x007f94c4, 0x014f1560, "STATIC", "VERIFIED", ["i32"]),
    0x29: ("chat_$_1", 0x0075eca4, 0x014efa88, "STATIC", "VERIFIED", ["i64", "str", "u8", "str", "str", "u8", "str", "str"]),
    0x2A: ("$_20", 0x007f9c2c, 0x014f15e0, "DYNAMIC", "PARTIAL", ["u8", "i32", "i32", "i32"]),
    0x2B: ("$_21", 0x007fd6fc, 0x014f16d0, "DYNAMIC", "PARTIAL", ["str", "u8", "u8", "i32", "i32"]),
    0x2C: ("$_28", 0x0080203c, 0x014f1a50, "STATIC", "VERIFIED", ["i64", "u8", "i16", "i32", "i32", "str", "i64", "i16"]),
    0x2D: ("$_22", 0x007fed18, 0x014f1750, "DYNAMIC", "PARTIAL", ["u8", "u8", "i32", "i32", "i16"]),
    0x2E: ("$_23", 0x007ffc28, 0x014f17d0, "STATIC", "VERIFIED", ["u8", "str", "str", "str", "str", "str"]),
    0x2F: ("$_29", 0x00803800, 0x014f1ad0, "DYNAMIC", "PARTIAL", ["u8", "u8", "str"]),
    0x30: ("$_24", 0x00800864, 0x014f1850, "STATIC", "VERIFIED", ["u8", "u8"]),
    0x31: ("$_30", 0x00806184, 0x014f1b50, "STATIC", "VERIFIED", ["i32", "str"]),
    0x32: ("$_25", 0x00800f04, 0x014f18d0, "DYNAMIC", "PARTIAL", ["u8", "u8", "u8", "u8", "u8", "i32", "u8"]),
    0x33: ("$_26", 0x00801828, 0x014f1950, "STATIC", "VERIFIED", ["u8", "str"]),
    0x43: ("$_27", 0x00801bac, 0x014f19d0, "STATIC", "VERIFIED", ["u8", "u8", "i32", "u8", "u8", "u8", "u8", "i32"]),
}

AUDITED_13_OPCODES = [
    0x00, 0x01, 0x04, 0x08, 0x0A, 0x10, 0x12, 0x21, 0x25, 0x2A, 0x2C, 0x2F, 0x30
]

def pack_str(s: str) -> bytes:
    encoded = s.encode("utf-8")
    return struct.pack(">H", len(encoded)) + encoded


def test_manifest_cross_verification():
    """
    Requirement 6: Cross-verify all 27 opcodes between schema manifest, codec, and evidence.
    """
    print("[P3.1 TEST 1] Verifying all 27 Opcodes against AArch64 Manifest...")
    assert len(OpcodeRegistry.OPCODES) == 27
    assert len(EXPECTED_27_MANIFEST) == 27

    for op, (exp_lambda, exp_handler, exp_vtable, exp_type, exp_status, exp_schema) in EXPECTED_27_MANIFEST.items():
        assert op in OpcodeRegistry.OPCODES, f"Opcode 0x{op:02X} missing in OpcodeRegistry"
        meta = OpcodeRegistry.OPCODES[op]
        assert meta["lambda"] == exp_lambda, f"Opcode 0x{op:02X} lambda mismatch"
        assert meta["handler_addr"] == exp_handler, f"Opcode 0x{op:02X} handler addr mismatch"
        assert meta["vtable_addr"] == exp_vtable, f"Opcode 0x{op:02X} vtable addr mismatch"
        assert meta["structure_type"] == exp_type, f"Opcode 0x{op:02X} structure type mismatch"
        assert meta["status"] == exp_status, f"Opcode 0x{op:02X} status mismatch"
        assert meta["schema"] == exp_schema, f"Opcode 0x{op:02X} schema mismatch: {meta['schema']} vs {exp_schema}"

    print("  -> PASS: All 27 opcodes match AArch64 machine-code ground truth exactly.")


def test_audited_13_opcodes_reconciliation():
    """
    Requirement 1-4: Audit each of the 13 opcodes with independent synthetic test vectors.
    """
    print("[P3.1 TEST 2] Auditing the 13 Discrepant Opcodes with Independent Vectors...")

    # 1. Opcode 0x00 (Notice): STATIC, exactly 1 str
    b00 = pack_str("Notice: Server maintenance at 02:00 UTC")
    res00 = OpcodeRegistry.parse_payload(0x00, b00)
    assert res00["parsed"] is True
    assert res00["structure_type"] == "STATIC"
    assert res00["status"] == "VERIFIED"
    assert len(res00["fields"]) == 1
    assert "maintenance" in res00["fields"][0]

    # 2. Opcode 0x01 (Role Login Response): DYNAMIC, header [str, u8] + dynamic role loop
    b01 = bytearray()
    b01.extend(pack_str("Welcome back Saiyan!"))
    b01.append(2)  # 2 characters in list
    # Character 1: i32, str, str, i16, u8...
    b01.extend(struct.pack(">i", 1001))
    b01.extend(pack_str("Goku"))
    b01.extend(pack_str("Warrior"))
    b01.extend(struct.pack(">h", 90))
    # Character 2:
    b01.extend(struct.pack(">i", 1002))
    b01.extend(pack_str("Vegeta"))
    b01.extend(pack_str("Prince"))
    b01.extend(struct.pack(">h", 88))

    res01 = OpcodeRegistry.parse_payload(0x01, bytes(b01))
    assert res01["parsed"] is True
    assert res01["structure_type"] == "DYNAMIC"
    assert res01["status"] == "PARTIAL"
    assert res01["fields"] == ["Welcome back Saiyan!", 2]
    assert "raw_variable_payload" in res01
    assert res01["dynamic_body_length"] > 0

    # 3. Opcode 0x04 (Account Info): STATIC, exactly 2 strings
    b04 = pack_str("session_tok_998877") + pack_str("usr_goku_01")
    res04 = OpcodeRegistry.parse_payload(0x04, b04)
    assert res04["parsed"] is True
    assert res04["structure_type"] == "STATIC"
    assert res04["fields"] == ["session_tok_998877", "usr_goku_01"]

    # 4. Opcode 0x08 (Change Psw Result): STATIC, exactly 1 u8
    b08 = bytes([0x00])  # SUCCESS
    res08 = OpcodeRegistry.parse_payload(0x08, b08)
    assert res08["parsed"] is True
    assert res08["structure_type"] == "STATIC"
    assert res08["fields"] == [0]

    # 5. Opcode 0x0A (Reg Account Result): STATIC, exactly 1 str
    b0A = pack_str("ACCOUNT_CREATED_SUCCESS")
    res0A = OpcodeRegistry.parse_payload(0x0A, b0A)
    assert res0A["parsed"] is True
    assert res0A["structure_type"] == "STATIC"
    assert res0A["fields"] == ["ACCOUNT_CREATED_SUCCESS"]

    # 6. Opcode 0x10 (Player Stats Sync): DYNAMIC, header 13 fields + trailing buff blocks
    b10 = bytearray()
    b10.extend(struct.pack(">i", 100))        # level
    b10.extend(struct.pack(">q", 5000000))    # exp
    b10.extend(struct.pack(">i", 25000))      # hp
    b10.extend(struct.pack(">i", 25000))      # max_hp
    b10.extend(struct.pack(">i", 12000))      # ki
    b10.extend(struct.pack(">i", 12000))      # max_ki
    b10.extend(struct.pack(">i", 3500))       # atk
    b10.extend(struct.pack(">i", 2100))       # def
    b10.append(1)                             # transform_state
    b10.append(5)                             # buff_count
    b10.extend(struct.pack(">i", 120))        # speed
    b10.append(3)                             # aura_type
    b10.extend(pack_str("Super Saiyan 3"))    # form_name
    # Dynamic trailing buff blocks (e.g. 5 buffs * 8 bytes = 40 bytes)
    b10.extend(b"\xAA" * 40)

    res10 = OpcodeRegistry.parse_payload(0x10, bytes(b10))
    assert res10["parsed"] is True
    assert res10["structure_type"] == "DYNAMIC"
    assert res10["status"] == "PARTIAL"
    assert res10["fields"][0] == 100
    assert res10["fields"][1] == 5000000
    assert res10["fields"][12] == "Super Saiyan 3"
    assert res10["dynamic_body_length"] == 40

    # 7. Opcode 0x12 (Entity Spawn Position): STATIC, 2 fields [u8, str]
    b12 = bytearray([0x01]) + pack_str("Map_Namek_Zone_4")
    res12 = OpcodeRegistry.parse_payload(0x12, bytes(b12))
    assert res12["parsed"] is True
    assert res12["structure_type"] == "STATIC"
    assert res12["fields"] == [1, "Map_Namek_Zone_4"]

    # 8. Opcode 0x21 (Battle State Update): DYNAMIC, header 9 fields + dynamic battle units
    b21 = bytearray()
    b21.extend(pack_str("TournamentOfPower_Arena"))
    b21.extend(struct.pack(">i", 1))    # round
    b21.append(10)                       # active_units
    b21.extend(struct.pack(">i", 120))  # timer
    b21.append(1)                        # weather
    b21.append(0)                        # bgm_id
    b21.append(2)                        # teams_count
    b21.extend(struct.pack(">i", 9999)) # score
    b21.append(0)                        # sudden_death
    # Dynamic battle entity payload
    b21.extend(b"\xFF\xFE\xFD\xFC" * 16)

    res21 = OpcodeRegistry.parse_payload(0x21, bytes(b21))
    assert res21["parsed"] is True
    assert res21["structure_type"] == "DYNAMIC"
    assert res21["fields"][0] == "TournamentOfPower_Arena"
    assert res21["dynamic_body_length"] == 64

    # 9. Opcode 0x25 (Skill Cast Event): STATIC, 6 fields: i64, i32, i16, i16, u8, i32
    b25 = bytearray()
    b25.extend(struct.pack(">q", 88888888))  # caster_id
    b25.extend(struct.pack(">i", 401))       # skill_id (Kamehameha)
    b25.extend(struct.pack(">h", 1250))      # target_x
    b25.extend(struct.pack(">h", 3400))      # target_y
    b25.append(5)                            # skill_tier
    b25.extend(struct.pack(">i", 16843009))  # timestamp
    res25 = OpcodeRegistry.parse_payload(0x25, bytes(b25))
    assert res25["parsed"] is True
    assert res25["structure_type"] == "STATIC"
    assert res25["fields"] == [88888888, 401, 1250, 3400, 5, 16843009]

    # 10. Opcode 0x2A (Inventory Item Update): DYNAMIC, header [u8, i32, i32, i32] + item slots
    b2A = bytearray()
    b2A.append(1)                            # bag_type (Bag 1)
    b2A.extend(struct.pack(">i", 50))        # max_slots
    b2A.extend(struct.pack(">i", 3))         # used_slots
    b2A.extend(struct.pack(">i", 1000000))   # gold
    # 3 dynamic item slot definitions
    b2A.extend(b"\x01\x02\x03\x04" * 12)

    res2A = OpcodeRegistry.parse_payload(0x2A, bytes(b2A))
    assert res2A["parsed"] is True
    assert res2A["structure_type"] == "DYNAMIC"
    assert res2A["fields"] == [1, 50, 3, 1000000]
    assert res2A["dynamic_body_length"] == 48

    # 11. Opcode 0x2C (Guild Member Info): STATIC, 8 fields: i64, u8, i16, i32, i32, str, i64, i16
    b2C = bytearray()
    b2C.extend(struct.pack(">q", 555666777)) # guild_id
    b2C.append(2)                            # member_role (Officer)
    b2C.extend(struct.pack(">h", 95))        # level
    b2C.extend(struct.pack(">i", 150000))    # contribution
    b2C.extend(struct.pack(">i", 2))         # status (online)
    b2C.extend(pack_str("Trunks"))           # member_name
    b2C.extend(struct.pack(">q", 123456789)) # joined_timestamp
    b2C.extend(struct.pack(">h", 12))        # vip_rank
    res2C = OpcodeRegistry.parse_payload(0x2C, bytes(b2C))
    assert res2C["parsed"] is True
    assert res2C["structure_type"] == "STATIC"
    assert res2C["fields"] == [555666777, 2, 95, 150000, 2, "Trunks", 123456789, 12]

    # 12. Opcode 0x2F (Mail Attachment): DYNAMIC, header [u8, u8, str] + dynamic mail items
    b2F = bytearray()
    b2F.append(0)                            # system_mail_category
    b2F.append(4)                            # unread_mail_count
    b2F.extend(pack_str("Season 1 Arena Rewards"))
    # dynamic mail attachment records
    b2F.extend(b"\x11\x22\x33\x44" * 8)

    res2F = OpcodeRegistry.parse_payload(0x2F, bytes(b2F))
    assert res2F["parsed"] is True
    assert res2F["structure_type"] == "DYNAMIC"
    assert res2F["fields"] == [0, 4, "Season 1 Arena Rewards"]
    assert res2F["dynamic_body_length"] == 32

    # 13. Opcode 0x30 (Party Team Update): STATIC, 2 fields [u8, u8]
    b30 = bytes([0x03, 0x01])  # 3 party members, leader ready
    res30 = OpcodeRegistry.parse_payload(0x30, b30)
    assert res30["parsed"] is True
    assert res30["structure_type"] == "STATIC"
    assert res30["fields"] == [3, 1]

    print("  -> PASS: All 13 audited opcodes pass with reconciled schemas and exact ARM64 semantics.")


def test_malformed_and_truncated_reconciled_packets():
    """
    Requirement 5: Test edge cases, malformed payloads and truncation on reconciled opcodes.
    """
    print("[P3.1 TEST 3] Testing Malformed and Truncated Payloads on Reconciled Opcodes...")

    # 1. Truncated STATIC packet (0x25 expects 6 fields, 26 bytes minimum)
    b25_truncated = bytes(10)  # Only 10 bytes provided
    res25_err = OpcodeRegistry.parse_payload(0x25, b25_truncated)
    assert res25_err["parsed"] is False
    assert "error" in res25_err

    # 2. Truncated string in STATIC packet (0x00 specifies string length 20, but only 5 bytes follow)
    b00_bad_str = struct.pack(">H", 20) + b"short"
    res00_err = OpcodeRegistry.parse_payload(0x00, b00_bad_str)
    assert res00_err["parsed"] is False
    assert "error" in res00_err

    # 3. Truncated DYNAMIC header (0x01 expects [str, u8], give empty string without u8)
    b01_bad_hdr = pack_str("Hello")  # missing trailing u8
    res01_err = OpcodeRegistry.parse_payload(0x01, b01_bad_hdr)
    assert res01_err["parsed"] is False
    assert "error" in res01_err

    # 4. Unknown opcode rejection
    res_unk = OpcodeRegistry.parse_payload(0x99, b"\x00\x00")
    assert res_unk["parsed"] is False
    assert "not registered" in res_unk["error"]

    print("  -> PASS: Error handling and truncation gracefully caught without exceptions.")


if __name__ == "__main__":
    print("=" * 70)
    print("Starting P3.1 Schema Reconciliation & Independent Verification Suite")
    print("=" * 70)
    test_manifest_cross_verification()
    test_audited_13_opcodes_reconciliation()
    test_malformed_and_truncated_reconciled_packets()
    print("=" * 70)
    print("ALL P3.1 TESTS PASSED: Schema Reconciliation & Epistemic Boundaries Verified.")
    print("=" * 70)
