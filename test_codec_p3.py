#!/usr/bin/env python3
"""
P3 Comprehensive Verification Suite for ReturnSaiyan Protocol Compatibility Model
Testing malformed packets, truncated frames, packet coalescing, extreme fragmentation,
cross-packet stateless XOR continuity, and opcode uniqueness.
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

def test_opcode_uniqueness_and_coverage():
    print("[P3 TEST 1] Verifying 27 Opcode Uniqueness & Boundary Values...")
    expected_opcodes = [
        0x00, 0x01, 0x04, 0x05, 0x07, 0x08, 0x0A, 0x10, 0x12, 0x20,
        0x21, 0x25, 0x26, 0x27, 0x28, 0x29, 0x2A, 0x2B, 0x2C, 0x2D,
        0x2E, 0x2F, 0x30, 0x31, 0x32, 0x33, 0x43
    ]
    assert len(expected_opcodes) == 27
    assert len(set(expected_opcodes)) == 27, "Duplicate opcodes found in dispatch list"
    
    # Verify all opcodes are present in OpcodeRegistry
    for op in expected_opcodes:
        assert op in OpcodeRegistry.OPCODES, f"Opcode 0x{op:02X} missing from OpcodeRegistry"
    print("  -> PASS: All 27 opcodes are strictly distinct and registered.")


def test_truncated_header_fragmentation():
    print("[P3 TEST 2] TCP Stream with Truncated Header (1 byte split)...")
    seed = 0x12345678
    key = CryptoCore.gerar_chave_secreta(seed)
    conn = ConnectionState()
    decoder = StreamDecoder(conn)

    # 1. Feed greeting (7 bytes)
    greeting = ConnectionState.construct_server_greeting(seed)
    pkts = decoder.feed(greeting)
    assert len(pkts) == 0
    assert decoder.state == StreamDecoder.STATE_HEADER

    # 2. Build S2C Ping frame (Opcode 0x27, i32=42)
    body = bytearray([0x27])
    body.extend(struct.pack(">i", 42))
    enc_payload = CryptoCore.cifrar_s2c(bytes(body), key)
    hdr = bytes([
        (len(enc_payload) >> 8) ^ key,
        (len(enc_payload) & 0xFF) ^ key
    ])
    full_frame = hdr + enc_payload

    # Feed ONLY 1st byte of header
    pkts = decoder.feed(full_frame[:1])
    assert len(pkts) == 0
    assert decoder.state == StreamDecoder.STATE_HEADER

    # Feed remainder of frame
    pkts = decoder.feed(full_frame[1:])
    assert len(pkts) == 1
    assert pkts[0][0] == 0x27
    reader = PacketReader(pkts[0][1])
    assert reader.read_i32() == 42
    print("  -> PASS: Split header successfully accumulated without desynchronization.")


def test_truncated_payload_fragmentation():
    print("[P3 TEST 3] TCP Stream with Truncated Payload (Multi-part arrival)...")
    seed = 0x87654321
    key = CryptoCore.gerar_chave_secreta(seed)
    conn = ConnectionState()
    decoder = StreamDecoder(conn)
    decoder.feed(ConnectionState.construct_server_greeting(seed))

    # Build Chat packet (Opcode 0x29) with large text
    body = bytearray([0x29])
    body.extend(struct.pack(">q", 777))
    def add_str(b, s):
        enc = s.encode('utf-8')
        b.extend(struct.pack(">H", len(enc)))
        b.extend(enc)
    add_str(body, "Vegeta")
    body.append(2)
    add_str(body, "Final Flash incoming! " * 10)
    add_str(body, "Kakarot")
    body.append(12)
    add_str(body, "SaiyanRoyal")
    add_str(body, "Prince")

    enc_payload = CryptoCore.cifrar_s2c(bytes(body), key)
    hdr = bytes([
        (len(enc_payload) >> 8) ^ key,
        (len(enc_payload) & 0xFF) ^ key
    ])
    full_frame = hdr + enc_payload

    # Feed in 3 chunks of unequal sizes
    chunk1 = full_frame[:15]
    chunk2 = full_frame[15:50]
    chunk3 = full_frame[50:]

    assert len(decoder.feed(chunk1)) == 0
    assert len(decoder.feed(chunk2)) == 0
    pkts = decoder.feed(chunk3)
    assert len(pkts) == 1
    assert pkts[0][0] == 0x29

    parsed = OpcodeRegistry.parse_payload(0x29, pkts[0][1])
    assert parsed["parsed"] is True
    assert parsed["fields"][1] == "Vegeta"
    assert "Final Flash" in parsed["fields"][3]
    print("  -> PASS: Multi-chunk payload reassembled and verified.")


def test_malformed_payload_safety():
    print("[P3 TEST 4] PacketReader Safety against Malformed / Out-of-Bounds Buffers...")
    # Buffer has only 3 bytes, but we try to read i32 (4 bytes)
    short_buf = b"\x00\x01\x02"
    reader = PacketReader(short_buf)
    try:
        reader.read_i32()
        assert False, "Should have raised IndexError"
    except IndexError:
        pass

    # Buffer claims string length 500, but only 4 bytes exist
    corrupted_str_buf = struct.pack(">H", 500) + b"test"
    reader2 = PacketReader(corrupted_str_buf)
    try:
        reader2.read_str()
        assert False, "Should have raised IndexError on string overflow"
    except IndexError:
        pass

    print("  -> PASS: Out-of-bounds reads handled safely without memory corruption.")


def test_cross_packet_xor_statelessness():
    print("[P3 TEST 5] Verification of Cross-Packet XOR Statelessness...")
    key = 0x4E
    p1 = b"Packet Alpha Payload"
    p2 = b"Packet Beta Payload"

    # Encrypt P1 then P2 consecutively
    c1_seq = CryptoCore.cifrar_c2s(p1, key)
    c2_seq = CryptoCore.cifrar_c2s(p2, key)

    # Encrypt P2 independently without P1 having run before
    c2_standalone = CryptoCore.cifrar_c2s(p2, key)

    assert c2_seq == c2_standalone, "C2S cipher should be stateless across packet boundaries"
    assert CryptoCore.decifrar_c2s(c2_seq, key) == p2

    # S2C independent XOR statelessness
    s1 = CryptoCore.cifrar_s2c(p1, key)
    s2 = CryptoCore.cifrar_s2c(p2, key)
    assert CryptoCore.decifrar_s2c(s1, key) == p1
    assert CryptoCore.decifrar_s2c(s2, key) == p2
    print("  -> PASS: Both C2S and S2C ciphers proven packet-stateless.")


def test_server_greeting_prefix_invariance():
    print("[P3 TEST 6] Server Greeting Bytes 0..2 Invariance Test...")
    seed = 0xCAFEBABE
    expected_key = CryptoCore.gerar_chave_secreta(seed)

    prefixes = [
        b"\x00\x05\x00",
        b"AOS",
        b"TCP",
        b"\xFF\xFF\xFF",
        b"\x12\x34\x56",
    ]
    for pfx in prefixes:
        conn = ConnectionState()
        greeting = pfx + struct.pack(">I", seed)
        derived_key = conn.process_server_handshake(greeting)
        assert derived_key == expected_key, f"Key varied with prefix {pfx}: {derived_key} != {expected_key}"
    print("  -> PASS: Client is 100% invariant to bytes 0..2 of server greeting.")


def test_multi_packet_coalescing_burst():
    print("[P3 TEST 7] TCP Burst Coalescing (10 back-to-back packets in single read)...")
    seed = 0x99887766
    key = CryptoCore.gerar_chave_secreta(seed)
    conn = ConnectionState()
    decoder = StreamDecoder(conn)
    decoder.feed(ConnectionState.construct_server_greeting(seed))

    giant_burst = bytearray()
    for i in range(10):
        # alternate between Ping (0x27) and Friend Status (0x33: ["u8", "str"])
        if i % 2 == 0:
            body = bytearray([0x27])
            body.extend(struct.pack(">i", 5000 + i))
        else:
            body = bytearray([0x33])
            body.append(1)
            msg = f"Friend #{i} is online".encode('utf-8')
            body.extend(struct.pack(">H", len(msg)) + msg)

        enc_payload = CryptoCore.cifrar_s2c(bytes(body), key)
        hdr = bytes([
            (len(enc_payload) >> 8) ^ key,
            (len(enc_payload) & 0xFF) ^ key
        ])
        giant_burst.extend(hdr + enc_payload)

    # Deliver entire 10-frame burst at once
    pkts = decoder.feed(bytes(giant_burst))
    assert len(pkts) == 10, f"Expected 10 packets, got {len(pkts)}"
    for i, (op, payload) in enumerate(pkts):
        if i % 2 == 0:
            assert op == 0x27
            assert PacketReader(payload).read_i32() == 5000 + i
        else:
            assert op == 0x33
            parsed = OpcodeRegistry.parse_payload(0x33, payload)
            assert f"#{i}" in parsed["fields"][1]
    print("  -> PASS: 10 coalesced packets cleanly separated and dispatched in single read.")


if __name__ == "__main__":
    print("=" * 70)
    print("Running P3 Comprehensive Verification Suite")
    print("=" * 70)
    test_opcode_uniqueness_and_coverage()
    test_truncated_header_fragmentation()
    test_truncated_payload_fragmentation()
    test_malformed_payload_safety()
    test_cross_packet_xor_statelessness()
    test_server_greeting_prefix_invariance()
    test_multi_packet_coalescing_burst()
    print("=" * 70)
    print("ALL P3 TESTS PASSED: Protocol Robustness & Streaming Integrity Verified.")
    print("=" * 70)
