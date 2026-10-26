#!/usr/bin/env python3
"""
P2 Comprehensive Test Suite for ReturnSaiyan Protocol Compatibility Model
Testing cryptographic reversibility, sequence rollover, TCP stream fragmentation/coalescing,
and opcode deserialization against ARM64 machine-code ground truth.
"""

import struct
from returnsaiyan_codec import (
    CryptoCore,
    PacketWriter,
    PacketReader,
    ConnectionState,
    StreamDecoder,
    OpcodeRegistry,
)

def test_key_derivation_math():
    print("[TEST 1] Key Derivation Math & Bitwise Verification...")
    seeds = [
        0x00000000, 0x12345678, 0x7FFFFFFF, 0x80000000,
        0xAABBCCDD, 0xDEADBEEF, 0xFFFFFFFF, 0x045edf26
    ]
    for s in seeds:
        k = CryptoCore.gerar_chave_secreta(s)
        assert 0 <= k <= 255, f"Key out of byte range: {k}"
        
        # Cross-verify with raw bitwise formula
        w8 = (s ^ ((s << 11) & 0xFFFFFFFF)) & 0xFFFFFFFF
        w8_signed = w8 if w8 < 0x80000000 else w8 - 0x100000000
        shifted = (w8_signed >> 8) & 0xFFFFFFFF
        w8 = (w8 ^ shifted) & 0xFFFFFFFF
        expected = ((w8 ^ 0x045edf26) & 0xFF)
        assert k == expected, f"Mismatch for seed 0x{s:08X}: got {k}, expected {expected}"
    print("  -> PASS: All seed vectors match arithmetic right-shift formula exactly.")


def test_c2s_reversibility():
    print("[TEST 2] C2S Chained-XOR Reversibility & Boundary Cases...")
    key = 0x7B
    test_cases = [
        b"",
        b"\x00",
        b"\xFF",
        b"\x12\x34",
        b"A" * 31,
        b"B" * 32,
        b"C" * 33,
        b"Variable length packet payload test vector with special symbols !@#$%^&*()_+" * 20
    ]
    for pt in test_cases:
        ct = CryptoCore.cifrar_c2s(pt, key)
        recovered = CryptoCore.decifrar_c2s(ct, key)
        assert recovered == pt, f"Decryption failed for length {len(pt)}"
        if len(pt) > 0:
            assert ct[0] == pt[0], f"C[0] must equal P[0]: got {ct[0]} != {pt[0]}"
    print("  -> PASS: C2S Chained-XOR perfectly reversible across all buffer sizes.")


def test_sequence_number_rollover():
    print("[TEST 3] Sequence Number Modulo 256 Rollover Behavior...")
    conn = ConnectionState()
    # Initialize with greeting
    greeting = ConnectionState.construct_server_greeting(0x12345678)
    conn.process_server_handshake(greeting)
    assert conn.seq == 0

    observed_seqs = []
    for i in range(300):
        expected_seq = i % 256
        writer = PacketWriter(opcode=0x27).write_i32(i)
        enc_packet = conn.send_packet(writer)
        
        # Decrypt packet to verify plain header
        dec_packet = CryptoCore.decifrar_c2s(enc_packet, conn.key)
        # Layout: [len_hi, len_lo, seq, opcode, payload...]
        pkt_len = struct.unpack_from(">H", dec_packet, 0)[0]
        pkt_seq = dec_packet[2]
        pkt_op = dec_packet[3]
        
        assert pkt_seq == expected_seq, f"Step {i}: expected seq {expected_seq}, got {pkt_seq}"
        assert pkt_op == 0x27
        assert pkt_len == len(dec_packet) - 2
        observed_seqs.append(pkt_seq)

    # Check rollover point specifically
    assert observed_seqs[255] == 255
    assert observed_seqs[256] == 0
    assert observed_seqs[257] == 1
    print("  -> PASS: Sequence number wraps around at 255 -> 0 as proven by ARM64 strb.")


def test_tcp_fragmentation_and_reassembly():
    print("[TEST 4] TCP Stream Fragmentation (1-byte incremental feeding)...")
    server_seed = 0xAABBCCDD
    key = CryptoCore.gerar_chave_secreta(server_seed)
    
    # Construct 3 S2C server frames:
    # 1. Server greeting (7 bytes)
    greeting = ConnectionState.construct_server_greeting(server_seed)
    
    # 2. Chat packet (Opcode 0x29)
    # [i64, str, u8, str, str, u8, str, str]
    body29 = bytearray()
    body29.append(0x29) # opcode
    body29.extend(struct.pack(">q", 1001)) # channel id
    def add_str(b, s):
        enc = s.encode('utf-8')
        b.extend(struct.pack(">H", len(enc)))
        b.extend(enc)
    add_str(body29, "Goku")
    body29.append(1) # chat type
    add_str(body29, "Kamehameha!")
    add_str(body29, "TargetAll")
    body29.append(10) # VIP
    add_str(body29, "Z-Warriors")
    add_str(body29, "SuperSaiyan")
    
    enc_payload29 = CryptoCore.cifrar_s2c(bytes(body29), key)
    hdr29 = bytes([
        (len(enc_payload29) >> 8) ^ key,
        (len(enc_payload29) & 0xFF) ^ key
    ])
    frame29 = hdr29 + enc_payload29

    # 3. Heartbeat Pong packet (Opcode 0x28)
    # [opcode=0x28, i32=99999]
    body28 = bytearray([0x28])
    body28.extend(struct.pack(">i", 99999))
    enc_payload28 = CryptoCore.cifrar_s2c(bytes(body28), key)
    hdr28 = bytes([
        (len(enc_payload28) >> 8) ^ key,
        (len(enc_payload28) & 0xFF) ^ key
    ])
    frame28 = hdr28 + enc_payload28

    full_stream = greeting + frame29 + frame28
    
    # Feed stream byte-by-byte (maximum fragmentation scenario)
    conn = ConnectionState()
    decoder = StreamDecoder(conn)
    decoded_packets = []
    for byte_val in full_stream:
        chunk = bytes([byte_val])
        pkts = decoder.feed(chunk)
        if pkts:
            decoded_packets.extend(pkts)

    assert len(decoded_packets) == 2, f"Expected 2 data packets, got {len(decoded_packets)}"
    assert decoded_packets[0][0] == 0x29
    assert decoded_packets[1][0] == 0x28

    # Verify chat packet content
    parsed29 = OpcodeRegistry.parse_payload(0x29, decoded_packets[0][1])
    assert parsed29["parsed"] is True
    assert parsed29["fields"][0] == 1001
    assert parsed29["fields"][1] == "Goku"
    assert parsed29["fields"][3] == "Kamehameha!"
    print("  -> PASS: Extreme 1-byte fragmentation reassembled with 100% integrity.")


def test_tcp_concatenation_coalescing():
    print("[TEST 5] TCP Frame Concatenation & Multi-packet Coalescing...")
    server_seed = 0x55667788
    key = CryptoCore.gerar_chave_secreta(server_seed)
    
    greeting = ConnectionState.construct_server_greeting(server_seed)
    
    # Create 5 back-to-back Ping packets (Opcode 0x27)
    concatenated_stream = bytearray(greeting)
    for ping_id in range(5):
        body = bytearray([0x27])
        body.extend(struct.pack(">i", 1000 + ping_id))
        enc_payload = CryptoCore.cifrar_s2c(bytes(body), key)
        hdr = bytes([
            (len(enc_payload) >> 8) ^ key,
            (len(enc_payload) & 0xFF) ^ key
        ])
        concatenated_stream.extend(hdr + enc_payload)

    # Feed entire multi-frame payload in a single socket read
    conn = ConnectionState()
    decoder = StreamDecoder(conn)
    pkts = decoder.feed(bytes(concatenated_stream))

    assert len(pkts) == 5, f"Expected 5 coalesced packets, got {len(pkts)}"
    for i, (op, payload) in enumerate(pkts):
        assert op == 0x27
        reader = PacketReader(payload)
        val = reader.read_i32()
        assert val == 1000 + i
    print("  -> PASS: 5 concatenated TCP frames separated cleanly in single feed.")


def test_opcode_registry_schemas():
    print("[TEST 6] Testing Recovered Opcode Registry Schemas...")
    def pack_str(s):
        enc = s.encode('utf-8')
        return struct.pack(">H", len(enc)) + enc

    # Test Opcode 0x00 (Notice): ["str"] (reconciled with AArch64 $_5)
    body00 = bytearray()
    body00.extend(pack_str("Server is currently undergoing scheduled maintenance."))
    parsed00 = OpcodeRegistry.parse_payload(0x00, bytes(body00))
    assert parsed00["parsed"] is True
    assert "maintenance" in parsed00["fields"][0]
    assert parsed00["status"] == "VERIFIED"

    # Test Opcode 0x07 (System Prompt): ["u8", "str"]
    body07 = bytearray([0x01])
    body07.extend(pack_str("Connection established successfully."))
    parsed07 = OpcodeRegistry.parse_payload(0x07, bytes(body07))
    assert parsed07["parsed"] is True
    assert parsed07["fields"] == [1, "Connection established successfully."]

    # Test Opcode 0x30 (Party Team Update): ["u8", "u8"] (reconciled with AArch64 $_24)
    body30 = bytes([0x04, 0x01])
    parsed30 = OpcodeRegistry.parse_payload(0x30, body30)
    assert parsed30["parsed"] is True
    assert parsed30["fields"] == [4, 1]

    print("  -> PASS: Opcode schemas verified against deserializer signatures.")


if __name__ == "__main__":
    print("=" * 70)
    print("Starting P2 Protocol Compatibility Model Verification Suite")
    print("=" * 70)
    test_key_derivation_math()
    test_c2s_reversibility()
    test_sequence_number_rollover()
    test_tcp_fragmentation_and_reassembly()
    test_tcp_concatenation_coalescing()
    test_opcode_registry_schemas()
    print("=" * 70)
    print("ALL TESTS PASSED: Protocol Compatibility Model Verified Offline.")
    print("=" * 70)
