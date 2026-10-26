#!/usr/bin/env python3
"""
Test Suite for ReturnSaiyan P4.1 — Protocol Contract Consistency & State Machine Hardening.

Covers:
  1. Canonical Manifest Integrity (all 27 opcodes, strict name certainty, addresses, status).
  2. AST Parser Strictness (rejection of silent fallbacks, discrimination between COMPLETE,
     PARTIAL, and MALFORMED, bounds checking on count variables).
  3. ClientStateMachine Hardening (preconditions, invalid transition rejection, UI event triggers,
     server redirect rollback to DISCONNECTED, clean reconnect).
"""

import struct
import pytest
from typing import Dict, Any

from returnsaiyan_codec import (
    PacketReader,
    OpcodeRegistry,
    CANONICAL_OPCODE_MANIFEST,
    DynamicPacketDecoder,
    ClientStateMachine,
)


def pack_str(s: str) -> bytes:
    encoded = s.encode("utf-8")
    return struct.pack(">H", len(encoded)) + encoded


# ==============================================================================
# 1. Canonical Manifest Integrity & Epistemic Boundaries
# ==============================================================================

def test_p4_1_canonical_manifest_integrity():
    """
    Requirement 2: Ensure canonical manifest defines exactly 27 opcodes with
    AArch64 addresses, lambda names, schemas, and epistemic name certainty.
    """
    assert len(CANONICAL_OPCODE_MANIFEST) == 27

    verified_names = {
        0x01: "ROLE_LOGIN_RESPONSE",
        0x10: "PLAYER_STATS_SYNC",
        0x29: "CHAT_MESSAGE_UPDATE",
    }

    verified_opcodes_count = 0
    partial_opcodes_count = 0

    for opcode, meta in CANONICAL_OPCODE_MANIFEST.items():
        assert "name" in meta
        assert "name_certainty" in meta
        assert "lambda" in meta
        assert "handler_addr" in meta
        assert "vtable_addr" in meta
        assert "structure_type" in meta
        assert "status" in meta
        assert "schema" in meta

        # Verify address ranges in libaos_jogo.so
        assert 0x00750000 <= meta["handler_addr"] <= 0x00810000
        assert 0x01400000 <= meta["vtable_addr"] <= 0x01500000

        # Epistemic boundary: Only 0x01, 0x10, 0x29 have VERIFIED business names
        if opcode in verified_names:
            assert meta["name_certainty"] == "VERIFIED", f"Opcode 0x{opcode:02X} name certainty must be VERIFIED"
            assert meta["name"] == verified_names[opcode]
        else:
            assert meta["name_certainty"] == "INFERRED", f"Opcode 0x{opcode:02X} name certainty must be INFERRED"

        # Epistemic boundary: STATIC is VERIFIED, DYNAMIC is PARTIAL
        if meta["structure_type"] == "STATIC":
            assert meta["status"] == "VERIFIED"
            verified_opcodes_count += 1
        elif meta["structure_type"] == "DYNAMIC":
            assert meta["status"] == "PARTIAL"
            partial_opcodes_count += 1
        else:
            pytest.fail(f"Invalid structure_type {meta['structure_type']} for opcode 0x{opcode:02X}")

    assert verified_opcodes_count == 18
    assert partial_opcodes_count == 9


# ==============================================================================
# 2. AST Parser Strictness & Fallback Elimination
# ==============================================================================

def test_p4_1_ast_parser_rejects_silent_fallback_on_truncated_buffer():
    """
    Requirement 3: An AST decoder exception must never silently fall back to
    header-only parsing with parsed: True. Must return parsed: False and MALFORMED.
    """
    # Truncated 0x01: Header is valid ("SESSION_123", 2 roles), but payload cuts off mid-role
    b01_trunc = bytearray()
    b01_trunc.extend(pack_str("SESSION_123"))
    b01_trunc.append(2)  # role_count = 2
    b01_trunc.extend(struct.pack(">i", 1001))
    b01_trunc.extend(pack_str("IncompleteHero"))
    # Missing remaining role fields and character 2

    res01 = OpcodeRegistry.parse_payload(0x01, bytes(b01_trunc))
    assert res01["parsed"] is False
    assert res01["parse_status"] == "MALFORMED"
    assert res01["status"] == "MALFORMED"
    assert "error" in res01
    assert "Malformed or truncated dynamic AST payload" in res01["error"]

    # Truncated 0x10: 7 base stats valid, but stage_count = 5 with only 2 bytes following
    b10_trunc = bytearray()
    b10_trunc.extend(struct.pack(">i", 50))
    b10_trunc.extend(struct.pack(">q", 1000000))
    b10_trunc.extend(struct.pack(">i", 5000))
    b10_trunc.extend(struct.pack(">i", 5000))
    b10_trunc.extend(struct.pack(">i", 2000))
    b10_trunc.extend(struct.pack(">i", 2000))
    b10_trunc.extend(struct.pack(">i", 800))
    b10_trunc.extend(struct.pack(">i", 5))  # stage_count = 5
    b10_trunc.extend(b"\x01\x02")           # Only 2 bytes instead of 5 * 6 bytes

    res10 = OpcodeRegistry.parse_payload(0x10, bytes(b10_trunc))
    assert res10["parsed"] is False
    assert res10["parse_status"] == "MALFORMED"
    assert "Malformed or truncated dynamic AST payload" in res10["error"]


def test_p4_1_ast_parser_count_bounds_checking():
    """
    Requirement 3: Malicious or corrupt count fields exceeding remaining bytes
    must be trapped before allocating arrays or looping.
    """
    # 0x01: role_count = 250 with only 4 bytes remaining
    b01_bad_count = pack_str("SESSION_TEST") + bytes([250, 0x00, 0x01, 0x02, 0x03])
    res01 = OpcodeRegistry.parse_payload(0x01, b01_bad_count)
    assert res01["parsed"] is False
    assert res01["parse_status"] == "MALFORMED"
    assert "exceeds remaining buffer capacity" in res01["error"]

    # 0x20: waypoint_count = 10000 with 0 bytes remaining
    b20_bad_count = bytearray()
    b20_bad_count.extend(struct.pack(">h", 1))       # move_type = 1
    b20_bad_count.extend(struct.pack(">q", 9999))    # entity_id
    b20_bad_count.extend(struct.pack(">i", 101))     # map_id
    b20_bad_count.extend(struct.pack(">h", 100))     # pos_x
    b20_bad_count.extend(struct.pack(">h", 200))     # pos_y
    b20_bad_count.extend(struct.pack(">i", 10))      # target_tile
    b20_bad_count.extend(struct.pack(">i", 10000))   # waypoint_count = 10000
    # 0 bytes follow

    res20 = OpcodeRegistry.parse_payload(0x20, bytes(b20_bad_count))
    assert res20["parsed"] is False
    assert res20["parse_status"] == "MALFORMED"
    assert "exceeds remaining buffer capacity" in res20["error"]

    # 0x21: skill_count = 50 with only 4 bytes remaining
    b21_bad_count = bytearray()
    b21_bad_count.extend(pack_str("hero_bad_count"))
    b21_bad_count.extend(struct.pack(">i", 1))
    b21_bad_count.append(10)
    b21_bad_count.extend(struct.pack(">i", 500))
    b21_bad_count.append(1)
    b21_bad_count.append(1)
    b21_bad_count.append(0)
    b21_bad_count.extend(struct.pack(">i", 2000))
    b21_bad_count.append(1)
    b21_bad_count.append(50)  # skill_count = 50 (requires 50 * 5 = 250 bytes)
    b21_bad_count.extend(b"\x00\x01\x02\x03")

    res21 = OpcodeRegistry.parse_payload(0x21, bytes(b21_bad_count))
    assert res21["parsed"] is False
    assert res21["parse_status"] == "MALFORMED"
    assert "exceeds remaining buffer capacity" in res21["error"]


def test_p4_1_parse_status_complete_vs_partial():
    """
    Requirement 3: Distinguish COMPLETE (exact AST parse with 0 trailing bytes)
    from PARTIAL (valid AST parse with trailing payload).
    """
    # Clean 0x01 with 0 announcements and 0 trailing bytes
    b01_clean = bytearray()
    b01_clean.extend(pack_str("SESSION_CLEAN"))
    b01_clean.append(0)  # 0 roles
    b01_clean.extend(pack_str("host.game.com"))
    b01_clean.extend(struct.pack(">h", 0))  # 0 announcements

    res01_clean = OpcodeRegistry.parse_payload(0x01, bytes(b01_clean))
    assert res01_clean["parsed"] is True
    assert res01_clean["parse_status"] == "COMPLETE"
    assert res01_clean["remaining_bytes"] == 0

    # 0x01 with 10 trailing bytes -> PARTIAL
    b01_partial = bytes(b01_clean) + b"\xDE\xAD\xBE\xEF" * 2 + b"\x11\x22"
    res01_partial = OpcodeRegistry.parse_payload(0x01, b01_partial)
    assert res01_partial["parsed"] is True
    assert res01_partial["parse_status"] == "PARTIAL"
    assert res01_partial["remaining_bytes"] == 10


# ==============================================================================
# 3. Hardened Client State Machine & Precondition Verification
# ==============================================================================

def test_p4_1_state_machine_disconnected_rejection():
    """
    Requirement 4: DISCONNECTED client must reject all incoming packets
    with ERR_NOT_CONNECTED.
    """
    csm = ClientStateMachine()
    assert csm.state == ClientStateMachine.STATE_DISCONNECTED

    # Attempt to deliver Opcode 0x04 while DISCONNECTED
    b04 = pack_str("tok") + pack_str("usr")
    res = csm.on_packet(0x04, b04)
    assert res["transitioned"] is False
    assert res["code"] == "ERR_NOT_CONNECTED"
    assert csm.state == ClientStateMachine.STATE_DISCONNECTED

    # Handshake completes
    h_res = csm.on_handshake_complete(seed=0x12345678, key=0x7B)
    assert h_res["transitioned"] is True
    assert csm.state == ClientStateMachine.STATE_HANDSHAKE_COMPLETE


def test_p4_1_state_machine_precondition_violations():
    """
    Requirement 4: Prevent invalid state jumps (e.g. jumping directly into
    world with 0x10 or gameplay packets without authenticating and selecting roles).
    """
    csm = ClientStateMachine()
    csm.on_handshake_complete(seed=0x11223344, key=0x55)
    assert csm.state == ClientStateMachine.STATE_HANDSHAKE_COMPLETE

    # 1. In HANDSHAKE_COMPLETE, cannot send 0x10 (Player Stats)
    b10 = bytearray()
    b10.extend(struct.pack(">i", 1))
    b10.extend(struct.pack(">q", 0))
    b10.extend(struct.pack(">iiiii", 500, 500, 200, 200, 50))
    b10.extend(struct.pack(">i", 0))  # stage_count = 0
    b10.append(1)
    b10.extend(pack_str("Novice"))
    b10.extend(struct.pack(">ii", 200, 200))

    res_10 = csm.on_packet(0x10, bytes(b10))
    assert res_10["transitioned"] is False
    assert res_10["code"] == "ERR_PRECONDITION_FAILED"
    assert "invalid in state HANDSHAKE_COMPLETE" in res_10["error"]
    assert csm.state == ClientStateMachine.STATE_HANDSHAKE_COMPLETE

    # 2. In HANDSHAKE_COMPLETE, cannot send 0x20 (Movement)
    b20 = bytearray()
    b20.extend(struct.pack(">hqhhii", 1, 1001, 201, 100, 200, 10))
    b20.extend(struct.pack(">i", 0))
    res_20 = csm.on_packet(0x20, bytes(b20))
    assert res_20["transitioned"] is False
    assert res_20["code"] == "ERR_PRECONDITION_FAILED"

    # 3. Authenticate with 0x04
    b04 = pack_str("tok_abc") + pack_str("usr_xyz")
    res_04 = csm.on_packet(0x04, b04)
    assert res_04["transitioned"] is True
    assert csm.state == ClientStateMachine.STATE_AUTHENTICATED

    # 4. In AUTHENTICATED, still cannot jump directly to 0x10
    res_10_auth = csm.on_packet(0x10, bytes(b10))
    assert res_10_auth["transitioned"] is False
    assert res_10_auth["code"] == "ERR_PRECONDITION_FAILED"
    assert csm.state == ClientStateMachine.STATE_AUTHENTICATED


def test_p4_1_state_machine_valid_full_lifecycle():
    """
    Requirement 4: Verify the full valid progression from DISCONNECTED to IN_GAME_MAIN
    and combat synchronization, asserting exact UI events and side effects.
    """
    csm = ClientStateMachine()

    # Step 1: Handshake
    csm.on_handshake_complete(seed=0xAABBCCDD, key=0x33)
    assert csm.state == ClientStateMachine.STATE_HANDSHAKE_COMPLETE

    # Step 2: Authenticate (0x04)
    res_auth = csm.on_packet(0x04, pack_str("session_tok_1") + pack_str("goku_user"))
    assert res_auth["transitioned"] is True
    assert csm.state == ClientStateMachine.STATE_AUTHENTICATED

    # Step 3: Role Login (0x01) -> Fires (2, "fuwuqi") -> ROLE_SELECTION
    b01 = bytearray()
    b01.extend(pack_str("SESSION_ESTABLISHED"))
    b01.append(1)  # 1 role
    b01.extend(struct.pack(">i", 777))
    b01.extend(pack_str("SonGoku"))
    b01.extend(pack_str("Saiyan"))
    b01.extend(struct.pack(">h", 80))
    b01.append(1)  # gender
    b01.append(2)  # hair
    b01.append(7)  # equip
    b01.extend(pack_str("DragonTeam"))
    b01.append(5)  # vip
    b01.append(1)  # is_default
    b01.extend(struct.pack(">i", 1700000000))
    b01.extend(pack_str("srv1.returnsaiyan.com"))
    b01.extend(struct.pack(">h", 0))

    res_role = csm.on_packet(0x01, bytes(b01))
    assert res_role["transitioned"] is True
    assert csm.state == ClientStateMachine.STATE_ROLE_SELECTION
    assert len(csm.roles) == 1
    assert csm.session_token == "SESSION_ESTABLISHED"
    assert (2, "fuwuqi") in csm.ui_events

    # Step 4: World Enter / Stats Sync (0x10) -> Fires (2, "main") -> IN_GAME_MAIN
    b10 = bytearray()
    b10.extend(struct.pack(">i", 80))
    b10.extend(struct.pack(">q", 5000000))
    b10.extend(struct.pack(">iiiii", 20000, 20000, 10000, 10000, 3000))
    b10.extend(struct.pack(">i", 0))  # stage_count = 0
    b10.append(2)
    b10.extend(pack_str("SonGoku"))
    b10.extend(struct.pack(">ii", 10000, 10000))

    res_world = csm.on_packet(0x10, bytes(b10))
    assert res_world["transitioned"] is True
    assert csm.state == ClientStateMachine.STATE_IN_GAME_MAIN
    assert (2, "main") in csm.ui_events
    assert csm.player_stats["base_stats"]["level"] == 80

    # Step 5: In-game Inventory Update (0x2A)
    # Sub-Op 1: Gold Update
    b2A_gold = bytes([0x01]) + struct.pack(">i", 7500000)
    csm.on_packet(0x2A, b2A_gold)
    assert csm.inventory["gold"] == 7500000

    # Sub-Op 3: Diamonds Update
    b2A_dia = bytes([0x03]) + struct.pack(">i", 1500)
    csm.on_packet(0x2A, b2A_dia)
    assert csm.inventory["diamonds"] == 1500


def test_p4_1_state_machine_server_redirect_and_rollback():
    """
    Requirement 4: Opcode 0x05 (SERVER_REDIRECT) must set redirect_host,
    rollback to DISCONNECTED, and require a reconnect.
    """
    csm = ClientStateMachine()
    csm.on_handshake_complete(seed=0x1234, key=0x56)
    csm.on_packet(0x04, pack_str("tok") + pack_str("usr"))
    assert csm.state == ClientStateMachine.STATE_AUTHENTICATED

    # Server sends 0x05 redirecting to login-mirror-2.returnsaiyan.com
    b05 = pack_str("login-mirror-2.returnsaiyan.com")
    res_redir = csm.on_packet(0x05, b05)

    assert res_redir["transitioned"] is True
    assert res_redir["new_state"] == ClientStateMachine.STATE_DISCONNECTED
    assert res_redir["action"] == "RECONNECT_REQUIRED"
    assert res_redir["redirect_host"] == "login-mirror-2.returnsaiyan.com"
    assert csm.state == ClientStateMachine.STATE_DISCONNECTED
    assert csm.redirect_host == "login-mirror-2.returnsaiyan.com"

    # Subsequent packets in DISCONNECTED are rejected
    res_rej = csm.on_packet(0x04, b05)
    assert res_rej["transitioned"] is False
    assert res_rej["code"] == "ERR_NOT_CONNECTED"

    # Clean reconnection to new host
    csm.on_handshake_complete(seed=0x5678, key=0x99)
    assert csm.state == ClientStateMachine.STATE_HANDSHAKE_COMPLETE


def test_p4_1_state_machine_disconnect_clean_reset():
    """
    Requirement 4: disconnect() method clears all volatile state and allows
    clean idempotent reset.
    """
    csm = ClientStateMachine()
    csm.on_handshake_complete(seed=0x1, key=0x2)
    csm.session_token = "ACTIVE_TOKEN"
    csm.roles = [{"name": "Goku"}]
    csm.inventory["gold"] = 999999
    csm.ui_events.append((2, "fuwuqi"))

    csm.disconnect()
    assert csm.state == ClientStateMachine.STATE_DISCONNECTED
    assert csm.session_token is None
    assert csm.roles == []
    assert csm.inventory["gold"] == 0
    assert csm.ui_events == []
    assert csm.redirect_host is None


if __name__ == "__main__":
    print("=" * 70)
    print("Starting P4.1 Protocol Contract Consistency & State Machine Hardening Suite")
    print("=" * 70)
    test_p4_1_canonical_manifest_integrity()
    test_p4_1_ast_parser_rejects_silent_fallback_on_truncated_buffer()
    test_p4_1_ast_parser_count_bounds_checking()
    test_p4_1_parse_status_complete_vs_partial()
    test_p4_1_state_machine_disconnected_rejection()
    test_p4_1_state_machine_precondition_violations()
    test_p4_1_state_machine_valid_full_lifecycle()
    test_p4_1_state_machine_server_redirect_and_rollback()
    test_p4_1_state_machine_disconnect_clean_reset()
    print("=" * 70)
    print("ALL P4.1 TESTS PASSED: Contract consistency and state machine hardened.")
    print("=" * 70)
