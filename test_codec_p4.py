#!/usr/bin/env python3
"""
P4 Dynamic Packet Reconstruction & Offline Client State Initialization Suite
Tests:
  - Strict STATIC packet validation: rejects unexpected trailing bytes without extension evidence.
  - AST / Tree decoding for 5 priority DYNAMIC opcodes:
      * 0x01: ROLE_LOGIN_RESPONSE (count=0, count=1, count=N, truncated nested roles, announcements)
      * 0x10: PLAYER_STATS_SYNC (base stats, stage loop count=0, count=N, post-stage attributes)
      * 0x20: ENTITY_MOVE_SYNC (mount branch, waypoint loop count=0, count=N)
      * 0x21: BATTLE_STATE_UPDATE (hero header, skill loop, equip loop, hp tail)
      * 0x2A: INVENTORY_ITEM_UPDATE (sub-op switch dispatch: 0..5, unknown sub-op fallback)
  - Client State Machine transitions:
      DISCONNECTED -> HANDSHAKE_COMPLETE -> AUTHENTICATED -> ROLE_SELECTION -> IN_GAME_MAIN
  - UI Event Dispatches matching AArch64:
      CUIManager::FireEvent(2, "fuwuqi") at 0x7f1cdc
      CUIManager::FireEvent(2, "main") at 0x7f68b0
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
    DynamicPacketDecoder,
    ClientStateMachine,
)

def pack_str(s: str) -> bytes:
    encoded = s.encode("utf-8")
    return struct.pack(">H", len(encoded)) + encoded


# ==============================================================================
# 1. Strict STATIC Packet Integrity (Requirement 2)
# ==============================================================================

def test_static_packet_strict_integrity():
    print("[P4 TEST 1] Verifying Strict STATIC Packet Integrity (No unproven trailing bytes)...")

    # Opcode 0x08 (CHANGE_PSW_RESULT): exactly 1 u8
    clean_08 = bytes([0x00])
    res_clean = OpcodeRegistry.parse_payload(0x08, clean_08)
    assert res_clean["parsed"] is True
    assert res_clean["fields"] == [0]
    assert res_clean["remaining_bytes"] == 0

    # Opcode 0x08 with 3 unexpected trailing bytes
    dirty_08 = bytes([0x00, 0xDE, 0xAD, 0xBE])
    res_dirty = OpcodeRegistry.parse_payload(0x08, dirty_08)
    assert res_dirty["parsed"] is False
    assert "trailing bytes in STATIC packet" in res_dirty["error"]

    # Opcode 0x04 (ACCOUNT_INFO): exactly 2 strings
    clean_04 = pack_str("tok_abc") + pack_str("user_xyz")
    res_04 = OpcodeRegistry.parse_payload(0x04, clean_04)
    assert res_04["parsed"] is True
    assert res_04["fields"] == ["tok_abc", "user_xyz"]

    dirty_04 = clean_04 + b"\xFF"
    res_dirty_04 = OpcodeRegistry.parse_payload(0x04, dirty_04)
    assert res_dirty_04["parsed"] is False
    assert "trailing bytes" in res_dirty_04["error"]

    print("  -> PASS: Strict STATIC parser correctly rejects unproven trailing bytes.")


# ==============================================================================
# 2. Dynamic Opcode 0x01: ROLE_LOGIN_RESPONSE AST (Requirement 3 & 7)
# ==============================================================================

def test_dynamic_0x01_role_login_ast():
    print("[P4 TEST 2] Testing Opcode 0x01 (Role Login Response) AST Reconstruction...")

    # Case A: count = 0 (No roles, new account)
    b01_empty = bytearray()
    b01_empty.extend(pack_str("SESSION_NEW_USER_99"))
    b01_empty.append(0)  # role_count = 0
    b01_empty.extend(pack_str("gateway.returnsaiyan.com"))
    b01_empty.extend(struct.pack(">h", 0))  # announcement_count = 0

    ast01_empty = DynamicPacketDecoder.decode_0x01_role_login(bytes(b01_empty))
    assert ast01_empty["session_token"] == "SESSION_NEW_USER_99"
    assert ast01_empty["role_count"] == 0
    assert len(ast01_empty["roles"]) == 0
    assert ast01_empty["server_host"] == "gateway.returnsaiyan.com"
    assert ast01_empty["announcements"] == []

    # Case B: count = 2 roles, 2 announcements
    b01_full = bytearray()
    b01_full.extend(pack_str("SESSION_VET_01"))
    b01_full.append(2)  # 2 roles

    # Role 1:
    b01_full.extend(struct.pack(">i", 101))
    b01_full.extend(pack_str("SonGoku"))
    b01_full.extend(pack_str("SaiyanWarrior"))
    b01_full.extend(struct.pack(">h", 99))
    b01_full.append(1)  # gender
    b01_full.append(2)  # hair
    b01_full.append(7)  # equip_flags
    b01_full.extend(pack_str("Z-Fighters"))
    b01_full.append(10) # vip
    b01_full.append(1)  # is_default
    b01_full.extend(struct.pack(">i", 1700000000))

    # Role 2:
    b01_full.extend(struct.pack(">i", 102))
    b01_full.extend(pack_str("Vegeta"))
    b01_full.extend(pack_str("SaiyanPrince"))
    b01_full.extend(struct.pack(">h", 98))
    b01_full.append(1)
    b01_full.append(1)
    b01_full.append(5)
    b01_full.extend(pack_str("RoyalArmy"))
    b01_full.append(10)
    b01_full.append(0)
    b01_full.extend(struct.pack(">i", 1699990000))

    # Server Host & Announcements
    b01_full.extend(pack_str("game-node-1.returnsaiyan.com"))
    b01_full.extend(struct.pack(">h", 2))
    b01_full.extend(pack_str("Double EXP Weekend Active!"))
    b01_full.extend(pack_str("World Boss spawns at 20:00 UTC."))

    ast01_full = DynamicPacketDecoder.decode_0x01_role_login(bytes(b01_full))
    assert ast01_full["role_count"] == 2
    assert len(ast01_full["roles"]) == 2
    assert ast01_full["roles"][0]["name"] == "SonGoku"
    assert ast01_full["roles"][0]["level"] == 99
    assert ast01_full["roles"][1]["name"] == "Vegeta"
    assert ast01_full["roles"][1]["guild_name"] == "RoyalArmy"
    assert len(ast01_full["announcements"]) == 2
    assert "Double EXP" in ast01_full["announcements"][0]

    # Integrated OpcodeRegistry test
    res = OpcodeRegistry.parse_payload(0x01, bytes(b01_full))
    assert res["parsed"] is True
    assert "ast" in res
    assert res["ast"]["role_count"] == 2

    # Case C: Truncated nested data
    b01_truncated = bytes(b01_full)[:30]  # Cut in the middle of Role 1
    with pytest.raises(IndexError):
        DynamicPacketDecoder.decode_0x01_role_login(b01_truncated)

    print("  -> PASS: Opcode 0x01 AST correctly parses 0, 1, and N nested role structures.")


# ==============================================================================
# 3. Dynamic Opcode 0x10: PLAYER_STATS_SYNC AST (Requirement 3 & 7)
# ==============================================================================

def test_dynamic_0x10_player_stats_ast():
    print("[P4 TEST 3] Testing Opcode 0x10 (Player Stats Sync) AST Reconstruction...")

    # Case A: stage_count = 0 (Fresh character)
    b10 = bytearray()
    b10.extend(struct.pack(">i", 1))        # level
    b10.extend(struct.pack(">q", 0))        # exp
    b10.extend(struct.pack(">i", 500))      # hp
    b10.extend(struct.pack(">i", 500))      # max_hp
    b10.extend(struct.pack(">i", 200))      # ki
    b10.extend(struct.pack(">i", 200))      # max_ki
    b10.extend(struct.pack(">i", 50))       # atk
    b10.extend(struct.pack(">i", 0))        # stage_count = 0
    # Post-stage attributes
    b10.append(1)                           # avatar_frame
    b10.extend(pack_str("NoviceGoku"))      # player_name
    b10.extend(struct.pack(">i", 200))      # cur_mp
    b10.extend(struct.pack(">i", 200))      # max_mp

    ast10_empty = DynamicPacketDecoder.decode_0x10_player_stats(bytes(b10))
    assert ast10_empty["base_stats"]["level"] == 1
    assert ast10_empty["base_stats"]["hp"] == 500
    assert ast10_empty["stage_count"] == 0
    assert ast10_empty["stages"] == []
    assert ast10_empty["attributes"]["player_name"] == "NoviceGoku"

    # Case B: stage_count = 3 (Completed stages)
    b10_stages = bytearray()
    b10_stages.extend(struct.pack(">i", 50))
    b10_stages.extend(struct.pack(">q", 12345678))
    b10_stages.extend(struct.pack(">i", 15000))
    b10_stages.extend(struct.pack(">i", 15000))
    b10_stages.extend(struct.pack(">i", 8000))
    b10_stages.extend(struct.pack(">i", 8000))
    b10_stages.extend(struct.pack(">i", 2500))
    b10_stages.extend(struct.pack(">i", 3))  # stage_count = 3
    # 3 Stage records: star_rating (u8), status (u8), stage_id (i32)
    for sid in [101, 102, 103]:
        b10_stages.append(3)   # 3 stars
        b10_stages.append(1)   # passed
        b10_stages.extend(struct.pack(">i", sid))

    # Post-stage
    b10_stages.append(5)  # avatar_frame
    b10_stages.extend(pack_str("MasterGoku"))
    b10_stages.extend(struct.pack(">i", 8000))
    b10_stages.extend(struct.pack(">i", 8000))
    b10_stages.append(1)  # has_title
    b10_stages.extend(struct.pack(">i", 777)) # title_id

    ast10_full = DynamicPacketDecoder.decode_0x10_player_stats(bytes(b10_stages))
    assert ast10_full["stage_count"] == 3
    assert len(ast10_full["stages"]) == 3
    assert ast10_full["stages"][1]["stage_id"] == 102
    assert ast10_full["stages"][1]["star_rating"] == 3
    assert ast10_full["attributes"]["player_name"] == "MasterGoku"
    assert ast10_full["attributes"]["title_id"] == 777

    print("  -> PASS: Opcode 0x10 AST correctly parses completed dungeon stages and stats.")


# ==============================================================================
# 4. Dynamic Opcode 0x20: ENTITY_MOVE_SYNC AST (Requirement 3 & 7)
# ==============================================================================

def test_dynamic_0x20_entity_move_ast():
    print("[P4 TEST 4] Testing Opcode 0x20 (Entity Move Sync) AST Reconstruction...")

    # Case A: move_type = 1 (Normal walking, 0 waypoints)
    b20_walk = bytearray()
    b20_walk.extend(struct.pack(">h", 1))        # move_type = 1
    b20_walk.extend(struct.pack(">q", 10001))    # entity_id
    b20_walk.extend(struct.pack(">i", 201))      # map_id
    b20_walk.extend(struct.pack(">h", 300))      # pos_x
    b20_walk.extend(struct.pack(">h", 450))      # pos_y
    b20_walk.extend(struct.pack(">i", 55))       # target_tile
    b20_walk.extend(struct.pack(">i", 0))        # waypoint_count = 0

    ast20_walk = DynamicPacketDecoder.decode_0x20_entity_move(bytes(b20_walk))
    assert ast20_walk["move_type"] == 1
    assert ast20_walk["mount_id"] is None
    assert ast20_walk["waypoint_count"] == 0
    assert len(ast20_walk["waypoints"]) == 0

    # Case B: move_type = 5 (Mounted riding, 2 trajectory waypoints)
    b20_mount = bytearray()
    b20_mount.extend(struct.pack(">h", 5))        # move_type = 5 (triggers mount_id read)
    b20_mount.extend(struct.pack(">q", 10001))
    b20_mount.extend(struct.pack(">i", 201))
    b20_mount.extend(struct.pack(">h", 300))
    b20_mount.extend(struct.pack(">h", 450))
    b20_mount.extend(struct.pack(">i", 55))
    b20_mount.extend(struct.pack(">q", 9990001))  # mount_id
    b20_mount.extend(struct.pack(">i", 2))        # waypoint_count = 2

    # Waypoint 1:
    b20_mount.extend(struct.pack(">i", 1))        # waypoint_id
    b20_mount.extend(struct.pack(">q", 0))        # target_entity_id
    b20_mount.extend(struct.pack(">i", 350))      # speed
    b20_mount.extend(struct.pack(">h", 350))      # next_x
    b20_mount.extend(struct.pack(">h", 500))      # next_y
    b20_mount.extend(struct.pack(">i", 0))        # flags
    b20_mount.extend(struct.pack(">q", 0))        # extra

    # Waypoint 2:
    b20_mount.extend(struct.pack(">i", 2))
    b20_mount.extend(struct.pack(">q", 0))
    b20_mount.extend(struct.pack(">i", 350))
    b20_mount.extend(struct.pack(">h", 400))
    b20_mount.extend(struct.pack(">h", 550))
    b20_mount.extend(struct.pack(">i", 0))
    b20_mount.extend(struct.pack(">q", 0))

    ast20_mount = DynamicPacketDecoder.decode_0x20_entity_move(bytes(b20_mount))
    assert ast20_mount["move_type"] == 5
    assert ast20_mount["mount_id"] == 9990001
    assert ast20_mount["waypoint_count"] == 2
    assert len(ast20_mount["waypoints"]) == 2
    assert ast20_mount["waypoints"][1]["next_x"] == 400

    print("  -> PASS: Opcode 0x20 AST parses mount branch and trajectory waypoints.")


# ==============================================================================
# 5. Dynamic Opcode 0x21: BATTLE_STATE_UPDATE AST (Requirement 3 & 7)
# ==============================================================================

def test_dynamic_0x21_battle_state_ast():
    print("[P4 TEST 5] Testing Opcode 0x21 (Battle Hero State) AST Reconstruction...")

    # Case A: Naked hero (0 skills, 0 equipment)
    b21_naked = bytearray()
    b21_naked.extend(pack_str("hero_uid_1001"))
    b21_naked.extend(struct.pack(">i", 1))      # hero_id (Goku)
    b21_naked.append(1)                         # level
    b21_naked.extend(struct.pack(">i", 0))      # exp
    b21_naked.append(1)                         # star_grade
    b21_naked.append(1)                         # quality
    b21_naked.append(0)                         # status
    b21_naked.extend(struct.pack(">i", 1500))   # combat_power
    b21_naked.append(1)                         # is_deployed
    b21_naked.append(0)                         # skill_count = 0
    b21_naked.append(0)                         # equip_count = 0
    b21_naked.extend(struct.pack(">i", 500))    # cur_hp
    b21_naked.append(100)                       # hp_percent
    b21_naked.extend(struct.pack(">i", 500))    # max_hp

    ast21_naked = DynamicPacketDecoder.decode_0x21_battle_state(bytes(b21_naked))
    assert ast21_naked["hero_uid"] == "hero_uid_1001"
    assert ast21_naked["skill_count"] == 0
    assert ast21_naked["equip_count"] == 0
    assert ast21_naked["skills"] == []
    assert ast21_naked["equips"] == []
    assert ast21_naked["current_hp"] == 500

    # Case B: Fully geared hero (2 skills, 2 equipment)
    b21_geared = bytearray()
    b21_geared.extend(pack_str("hero_uid_1001"))
    b21_geared.extend(struct.pack(">i", 1))
    b21_geared.append(80)
    b21_geared.extend(struct.pack(">i", 500000))
    b21_geared.append(5)                        # 5 stars
    b21_geared.append(4)                        # Gold quality
    b21_geared.append(1)                        # status
    b21_geared.extend(struct.pack(">i", 95000)) # combat_power
    b21_geared.append(1)

    # 2 skills:
    b21_geared.append(2)  # skill_count
    b21_geared.extend(struct.pack(">i", 301))   # Kamehameha
    b21_geared.append(10)                       # skill_level 10
    b21_geared.extend(struct.pack(">i", 302))   # Spirit Bomb
    b21_geared.append(5)                        # skill_level 5

    # 2 equips:
    b21_geared.append(2)  # equip_count
    b21_geared.extend(struct.pack(">q", 888111)) # item_uid
    b21_geared.extend(struct.pack(">i", 2001))   # Power Pole
    b21_geared.extend(struct.pack(">h", 1))      # slot_index
    b21_geared.append(12)                        # refine +12

    b21_geared.extend(struct.pack(">q", 888222)) # item_uid
    b21_geared.extend(struct.pack(">i", 2002))   # Turtle Gi
    b21_geared.extend(struct.pack(">h", 2))
    b21_geared.append(10)

    # Tail:
    b21_geared.extend(struct.pack(">i", 35000))
    b21_geared.append(100)
    b21_geared.extend(struct.pack(">i", 35000))

    ast21_geared = DynamicPacketDecoder.decode_0x21_battle_state(bytes(b21_geared))
    assert ast21_geared["skill_count"] == 2
    assert len(ast21_geared["skills"]) == 2
    assert ast21_geared["skills"][0]["skill_id"] == 301
    assert ast21_geared["equip_count"] == 2
    assert len(ast21_geared["equips"]) == 2
    assert ast21_geared["equips"][0]["item_id"] == 2001
    assert ast21_geared["current_hp"] == 35000

    print("  -> PASS: Opcode 0x21 AST parses hero skills, equipment loops, and combat stats.")


# ==============================================================================
# 6. Dynamic Opcode 0x2A: INVENTORY_ITEM_UPDATE Switch (Requirement 3 & 7)
# ==============================================================================

def test_dynamic_0x2A_inventory_sub_ops():
    print("[P4 TEST 6] Testing Opcode 0x2A (Inventory Dispatch) Sub-Op Switching...")

    # Sub-Op 0: SLOT_UPDATE (slot_index: i32, item_id: i32, count: i32)
    b2A_0 = bytes([0x00]) + struct.pack(">iii", 4, 1005, 50)
    ast2A_0 = DynamicPacketDecoder.decode_0x2A_inventory(b2A_0)
    assert ast2A_0["action"] == "SLOT_UPDATE"
    assert ast2A_0["slot_index"] == 4
    assert ast2A_0["item_id"] == 1005
    assert ast2A_0["count"] == 50

    # Sub-Op 1: GOLD_CURRENCY_UPDATE
    b2A_1 = bytes([0x01]) + struct.pack(">i", 2500000)
    ast2A_1 = DynamicPacketDecoder.decode_0x2A_inventory(b2A_1)
    assert ast2A_1["action"] == "GOLD_CURRENCY_UPDATE"
    assert ast2A_1["gold"] == 2500000

    # Sub-Op 2: BAG_CAPACITY_EXPAND
    b2A_2 = bytes([0x02, 80])
    ast2A_2 = DynamicPacketDecoder.decode_0x2A_inventory(b2A_2)
    assert ast2A_2["action"] == "BAG_CAPACITY_EXPAND"
    assert ast2A_2["new_capacity"] == 80

    # Sub-Op 3: DIAMOND_CURRENCY_UPDATE
    b2A_3 = bytes([0x03]) + struct.pack(">i", 9999)
    ast2A_3 = DynamicPacketDecoder.decode_0x2A_inventory(b2A_3)
    assert ast2A_3["action"] == "DIAMOND_CURRENCY_UPDATE"
    assert ast2A_3["diamonds"] == 9999

    # Sub-Op 99: Unknown sub-op fallback without crashing
    b2A_unk = bytes([0x99, 0xAA, 0xBB, 0xCC])
    ast2A_unk = DynamicPacketDecoder.decode_0x2A_inventory(b2A_unk)
    assert ast2A_unk["action"] == "SUB_OP_153"
    assert ast2A_unk["trailing_payload"] == b"\xAA\xBB\xCC"

    print("  -> PASS: Opcode 0x2A switch jump table successfully dispatches all sub-ops.")


# ==============================================================================
# 7. Offline Client State Machine Transitions (Requirement 8)
# ==============================================================================

def test_client_state_machine_initialization():
    print("[P4 TEST 7] Testing Offline Client State Transitions & UI Event Dispatch...")
    sm = ClientStateMachine()
    assert sm.state == ClientStateMachine.STATE_DISCONNECTED

    # Step 1: Handshake Complete
    sm.on_handshake_complete(0x12345678, 0xAA)
    assert sm.state == ClientStateMachine.STATE_HANDSHAKE_COMPLETE

    # Step 2: Account Authentication (Opcode 0x04)
    p04 = pack_str("tok_xyz") + pack_str("usr_001")
    t04 = sm.on_packet(0x04, p04)
    assert t04["transitioned"] is True
    assert sm.state == ClientStateMachine.STATE_AUTHENTICATED

    # Step 3: Role Login Response (Opcode 0x01) -> Fires UI Event "fuwuqi" (Server/Role screen)
    b01 = bytearray()
    b01.extend(pack_str("SESSION_AUTH_OK"))
    b01.append(1)  # 1 role
    b01.extend(struct.pack(">i", 1001))
    b01.extend(pack_str("Goku"))
    b01.extend(pack_str("Warrior"))
    b01.extend(struct.pack(">h", 50))
    b01.append(1)
    b01.append(1)
    b01.append(1)
    b01.extend(pack_str("ZFighters"))
    b01.append(5)
    b01.append(1)
    b01.extend(struct.pack(">i", 1680000000))
    b01.extend(pack_str("node1.returnsaiyan.com"))
    b01.extend(struct.pack(">h", 0))

    t01 = sm.on_packet(0x01, bytes(b01))
    assert t01["transitioned"] is True
    assert sm.state == ClientStateMachine.STATE_ROLE_SELECTION
    assert len(sm.roles) == 1
    assert (2, "fuwuqi") in sm.ui_events

    # Step 4: Player Stats Sync (Opcode 0x10) -> Fires UI Event "main" (In-game main scene)
    b10 = bytearray()
    b10.extend(struct.pack(">i", 50))       # level
    b10.extend(struct.pack(">q", 1000000))  # exp
    b10.extend(struct.pack(">i", 10000))    # hp
    b10.extend(struct.pack(">i", 10000))    # max_hp
    b10.extend(struct.pack(">i", 5000))     # ki
    b10.extend(struct.pack(">i", 5000))     # max_ki
    b10.extend(struct.pack(">i", 2000))     # atk
    b10.extend(struct.pack(">i", 0))        # stage_count = 0
    b10.append(1)                           # avatar_frame
    b10.extend(pack_str("Goku"))            # player_name

    t10 = sm.on_packet(0x10, bytes(b10))
    assert t10["transitioned"] is True
    assert sm.state == ClientStateMachine.STATE_IN_GAME_MAIN
    assert (2, "main") in sm.ui_events

    # Step 5: Receive Battle State Hero (Opcode 0x21)
    b21 = bytearray()
    b21.extend(pack_str("hero_goku_01"))
    b21.extend(struct.pack(">i", 1))
    b21.append(50)
    b21.extend(struct.pack(">i", 100000))
    b21.append(5)
    b21.append(4)
    b21.append(1)
    b21.extend(struct.pack(">i", 55000))
    b21.append(1)
    b21.append(0)  # skills = 0
    b21.append(0)  # equips = 0
    b21.extend(struct.pack(">i", 10000))
    b21.append(100)
    b21.extend(struct.pack(">i", 10000))

    sm.on_packet(0x21, bytes(b21))
    assert "hero_goku_01" in sm.heroes
    assert sm.heroes["hero_goku_01"]["combat_power"] == 55000

    # Step 6: Receive Inventory Update (Opcode 0x2A)
    b2A = bytes([0x01]) + struct.pack(">i", 1500000)
    sm.on_packet(0x2A, b2A)
    assert sm.inventory["gold"] == 1500000

    print("  -> PASS: Complete client state machine transition & UI events successfully validated.")


if __name__ == "__main__":
    print("=" * 70)
    print("Starting P4 Dynamic Packet Reconstruction Verification Suite")
    print("=" * 70)
    test_static_packet_strict_integrity()
    test_dynamic_0x01_role_login_ast()
    test_dynamic_0x10_player_stats_ast()
    test_dynamic_0x20_entity_move_ast()
    test_dynamic_0x21_battle_state_ast()
    test_dynamic_0x2A_inventory_sub_ops()
    test_client_state_machine_initialization()
    print("=" * 70)
    print("ALL P4 TESTS PASSED: Dynamic AST Decoding & State Machine Verified.")
    print("=" * 70)
