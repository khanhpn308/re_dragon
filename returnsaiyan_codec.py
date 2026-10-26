#!/usr/bin/env python3
"""
ReturnSaiyan Protocol Compatibility Model & Offline Codec
Fully reconstructed and validated against ARM64 disassembly of libaos_jogo.so
Target SHA-256: 5e0aefcbf1b23aa2dc74e95b22aee90c17011a4814193b8b61d305747a668c0f
"""

import struct
from typing import List, Tuple, Optional, Dict, Any, Callable

# ==============================================================================
# 1. Cryptographic Core (ARM64 Machine-Code Verified)
# ==============================================================================

class CryptoCore:
    """
    Direct machine-code replica of libaos_jogo.so cryptographic algorithms.
    """

    @staticmethod
    def gerar_chave_secreta(seed: int) -> int:
        """
        ARM64: aos::gerarChaveSecreta(unsigned int) at 0x007ec838
          7ec838: eor   w8, w0, w0, lsl #11
          7ec83c: mov   w9, #0xdf26
          7ec840: eor   w8, w8, w8, asr #8
          7ec844: movk  w9, #0x45e, lsl #16  (w9 = 0x045edf26)
          7ec848: eor   w0, w8, w9
          7ec84c: ret
        Caller:
          7ea360: strb  w0, [x19, #188]
        """
        seed &= 0xFFFFFFFF
        # eor w8, w0, w0, lsl #11
        w8 = (seed ^ ((seed << 11) & 0xFFFFFFFF)) & 0xFFFFFFFF

        # eor w8, w8, w8, asr #8 (Arithmetic shift right preserves sign)
        w8_signed = w8 if w8 < 0x80000000 else w8 - 0x100000000
        shifted = (w8_signed >> 8) & 0xFFFFFFFF
        w8 = (w8 ^ shifted) & 0xFFFFFFFF

        w9 = 0x045edf26
        w0 = (w8 ^ w9) & 0xFFFFFFFF
        return w0 & 0xFF

    @staticmethod
    def cifrar_c2s(data: bytes, key: int) -> bytes:
        """
        ARM64: aos::cifrarC2S(unsigned char* buf, size_t len, uint8_t key) at 0x007ec850
          C[0] = P[0]
          C[i] = C[i-1] ^ key ^ P[i]
        """
        if not data:
            return b""
        buf = bytearray(data)
        prev = key
        for i in range(len(buf)):
            pt = buf[i]
            ct = (prev ^ key ^ pt) & 0xFF
            buf[i] = ct
            prev = ct
        return bytes(buf)

    @staticmethod
    def decifrar_c2s(data: bytes, key: int) -> bytes:
        """
        ARM64: aos::decifrarC2S(unsigned char* buf, size_t len, uint8_t key) at 0x007ec874
          P[0] = C[0]
          P[i] = C[i-1] ^ key ^ C[i]
        """
        if not data:
            return b""
        buf = bytearray(data)
        prev = key
        for i in range(len(buf)):
            ct = buf[i]
            pt = (prev ^ key ^ ct) & 0xFF
            buf[i] = pt
            prev = ct
        return bytes(buf)

    @staticmethod
    def cifrar_s2c(data: bytes, key: int) -> bytes:
        """
        Server-to-Client Independent XOR encryption.
        P[i] ^ key
        """
        return bytes(b ^ key for b in data)

    @staticmethod
    def decifrar_s2c(data: bytes, key: int) -> bytes:
        """
        ARM64: threadRecepcao SIMD NEON + Scalar tail at 0x007ea4dc..0x007ea520
        Dual 128-bit NEON registers (q1, q2) xor with dup v0.16b, w8.
        Identical to byte-wise XOR with key.
        """
        return bytes(b ^ key for b in data)

    @staticmethod
    def decifrar_s2c_header(header_2b: bytes, key: int) -> int:
        """
        ARM64: 0x007ea420..0x007ea448
          w9 = hdr[0] ^ key
          w8 = hdr[1] ^ key
          bfi x22, x9, #8, #8  (Big-endian length)
        """
        assert len(header_2b) == 2
        b0 = header_2b[0] ^ key
        b1 = header_2b[1] ^ key
        return (b0 << 8) | b1


# ==============================================================================
# 2. Serialization & Deserialization
# ==============================================================================

class PacketWriter:
    """
    Python replica of aos::EscritorPacote (0x007ec904).
    Wire layout:
      [0..1]: 16-bit Big-Endian payload length (total_bytes - 2)
      [2]:    8-bit Sequence number
      [3]:    8-bit Opcode
      [4..]:  Serialized fields
    """

    def __init__(self, opcode: int):
        self.opcode = opcode & 0xFF
        self.body = bytearray()

    def write_u8(self, val: int) -> 'PacketWriter':
        self.body.append(val & 0xFF)
        return self

    def write_i16(self, val: int) -> 'PacketWriter':
        self.body.extend(struct.pack(">h", val))
        return self

    def write_u16(self, val: int) -> 'PacketWriter':
        self.body.extend(struct.pack(">H", val))
        return self

    def write_i32(self, val: int) -> 'PacketWriter':
        self.body.extend(struct.pack(">i", val))
        return self

    def write_i64(self, val: int) -> 'PacketWriter':
        self.body.extend(struct.pack(">q", val))
        return self

    def write_str(self, val: str) -> 'PacketWriter':
        """
        aos::EscritorPacote::str: 2-byte big-endian length + UTF-8 payload.
        """
        encoded = val.encode("utf-8")
        self.write_u16(len(encoded))
        self.body.extend(encoded)
        return self

    def write_binary(self, val: bytes) -> 'PacketWriter':
        self.body.extend(val)
        return self

    def finalizar(self, seq: int) -> bytes:
        """
        ARM64: aos::EscritorPacote::finalizar(unsigned char seq) at 0x007ed1b8
        Total packet = [len_hi, len_lo, seq, opcode, body...]
        len = total_bytes - 2
        """
        total_len = len(self.body) + 4
        payload_len = total_len - 2
        assert payload_len <= 0xFFFF, "Packet size exceeds 16-bit length"

        packet = bytearray()
        packet.extend(struct.pack(">H", payload_len))
        packet.append(seq & 0xFF)
        packet.append(self.opcode)
        packet.extend(self.body)
        return bytes(packet)


class PacketReader:
    """
    Python replica of aos::LeitorPacote (0x007ed2ac..0x007ed810).
    Decodes fields sequentially from decrypted payload buffer.
    """

    def __init__(self, data: bytes):
        self.data = data
        self.offset = 0

    def remaining(self) -> int:
        return len(self.data) - self.offset

    def read_u8(self) -> int:
        if self.offset + 1 > len(self.data):
            raise IndexError("Unexpected end of packet buffer in read_u8")
        val = self.data[self.offset]
        self.offset += 1
        return val

    def read_i16(self) -> int:
        if self.offset + 2 > len(self.data):
            raise IndexError("Unexpected end of packet buffer in read_i16")
        val = struct.unpack_from(">h", self.data, self.offset)[0]
        self.offset += 2
        return val

    def read_u16(self) -> int:
        if self.offset + 2 > len(self.data):
            raise IndexError("Unexpected end of packet buffer in read_u16")
        val = struct.unpack_from(">H", self.data, self.offset)[0]
        self.offset += 2
        return val

    def read_i32(self) -> int:
        if self.offset + 4 > len(self.data):
            raise IndexError("Unexpected end of packet buffer in read_i32")
        val = struct.unpack_from(">i", self.data, self.offset)[0]
        self.offset += 4
        return val

    def read_i64(self) -> int:
        if self.offset + 8 > len(self.data):
            raise IndexError("Unexpected end of packet buffer in read_i64")
        val = struct.unpack_from(">q", self.data, self.offset)[0]
        self.offset += 8
        return val

    def read_str(self) -> str:
        """
        aos::LeitorPacote::str (0x007ed6c8):
        Reads 2-byte big-endian string length, then string bytes.
        """
        s_len = self.read_u16()
        if self.offset + s_len > len(self.data):
            raise IndexError(f"String of length {s_len} overflows packet buffer")
        s_bytes = self.data[self.offset : self.offset + s_len]
        self.offset += s_len
        return s_bytes.decode("utf-8", errors="replace")

    def read_binary(self, length: int) -> bytes:
        if self.offset + length > len(self.data):
            raise IndexError(f"Binary chunk of length {length} overflows packet buffer")
        chunk = self.data[self.offset : self.offset + length]
        self.offset += length
        return chunk


# ==============================================================================
# 3. Connection State & Sequence Tracking
# ==============================================================================

class ConnectionState:
    """
    Maintains session cryptography, handshake negotiation, and sequence counters.
    Matches aos::Conexao memory offsets:
      [this + 188]: uint8_t key (chave)
      [this + 189]: uint8_t seq (sequence counter)
    """

    def __init__(self):
        self.seed: Optional[int] = None
        self.key: Optional[int] = None
        self.seq: int = 0  # strb wzr, [x19, #189] at 0x7e9f50
        self.handshake_complete: bool = False

    def process_server_handshake(self, greeting_7b: bytes) -> int:
        """
        Processes the initial 7-byte greeting packet from server.
        ARM64: 0x7ea274..0x7ea360
          bytes 0..2: Ignored by client
          bytes 3..6: seed = ntohl(*(uint32_t*)(buf + 3))
          key = gerarChaveSecreta(seed)
        """
        if len(greeting_7b) != 7:
            raise ValueError(f"Handshake greeting must be exactly 7 bytes, got {len(greeting_7b)}")

        self.seed = struct.unpack_from(">I", greeting_7b, 3)[0]
        self.key = CryptoCore.gerar_chave_secreta(self.seed)
        self.handshake_complete = True
        return self.key

    def send_packet(self, writer: PacketWriter) -> bytes:
        """
        Emulates aos::Conexao::enviar (0x007ea7e8):
          curr_seq = this->seq
          this->seq = (this->seq + 1) & 0xFF  (strb modulo 256 wrap-around)
          packet = writer.finalizar(curr_seq)
          encrypted = cifrarC2S(packet, this->key)
        """
        if not self.handshake_complete or self.key is None:
            raise RuntimeError("Cannot send packet before handshake completion")

        curr_seq = self.seq
        self.seq = (self.seq + 1) & 0xFF  # Proven by 0x7ea81c: add w8, w9, #1; strb

        unencrypted = writer.finalizar(curr_seq)
        return CryptoCore.cifrar_c2s(unencrypted, self.key)

    @staticmethod
    def construct_server_greeting(seed: int, prefix_3b: bytes = b"\x00\x05\x00") -> bytes:
        """
        Constructs a 7-byte server greeting packet.
        Default prefix b'\\x00\\x05\\x00' matches standard S2C unencrypted framing hypothesis.
        """
        assert len(prefix_3b) == 3, "Handshake prefix must be 3 bytes"
        return prefix_3b + struct.pack(">I", seed)


# ==============================================================================
# 4. Stream Decoder (TCP Fragmentation & Concatenation Reassembly)
# ==============================================================================

class StreamDecoder:
    """
    Faithful emulation of aos::Conexao::threadRecepcao socket streaming logic.
    Handles TCP segment fragmentation (arbitrary chunk feeds) and packet coalescing.
    """

    STATE_HANDSHAKE = 0
    STATE_HEADER = 1
    STATE_PAYLOAD = 2

    def __init__(self, conn_state: ConnectionState):
        self.conn = conn_state
        self.state = self.STATE_HANDSHAKE
        self.buf = bytearray()
        self.expected_len = 7  # Initial 7-byte handshake

    def feed(self, chunk: bytes) -> List[Tuple[int, bytes]]:
        """
        Feeds arbitrary TCP chunk bytes into the reassembly engine.
        Returns a list of complete decoded (opcode, payload_bytes) tuples.
        """
        self.buf.extend(chunk)
        packets: List[Tuple[int, bytes]] = []

        while True:
            if self.state == self.STATE_HANDSHAKE:
                if len(self.buf) < 7:
                    break
                greeting = bytes(self.buf[:7])
                del self.buf[:7]
                self.conn.process_server_handshake(greeting)
                self.state = self.STATE_HEADER
                self.expected_len = 2

            elif self.state == self.STATE_HEADER:
                if len(self.buf) < 2:
                    break
                hdr = bytes(self.buf[:2])
                del self.buf[:2]
                assert self.conn.key is not None
                payload_len = CryptoCore.decifrar_s2c_header(hdr, self.conn.key)
                self.expected_len = payload_len
                self.state = self.STATE_PAYLOAD

            elif self.state == self.STATE_PAYLOAD:
                if len(self.buf) < self.expected_len:
                    break
                raw_payload = bytes(self.buf[:self.expected_len])
                del self.buf[:self.expected_len]
                assert self.conn.key is not None

                # Decrypt payload using NEON SIMD / Scalar XOR
                decrypted = CryptoCore.decifrar_s2c(raw_payload, self.conn.key)
                if len(decrypted) > 0:
                    opcode = decrypted[0]
                    payload_body = decrypted[1:]
                    packets.append((opcode, payload_body))

                # Loop back to wait for next 2-byte header
                self.state = self.STATE_HEADER
                self.expected_len = 2

        return packets


# ==============================================================================
# 5. Opcode Registry & Schema Parsers (Reconciled with AArch64 Machine Code)
# ==============================================================================

class OpcodeRegistry:
    """
    Recovered and Reconciled Opcode Dispatch Table from libaos_jogo.so.
    Registrations:
      - 26 opcodes in CProtocolManager::registrarTratadores (0x007ede44)
      - 1 opcode in aos::registrarChat (0x0075eed4)
    Distinguishes:
      - STATIC (VERIFIED): Deterministic unconditional field sequence.
      - DYNAMIC (PARTIAL): Verified header fields, followed by count-controlled loops
                           or branch-dependent payload attributes.
    """

    OPCODES: Dict[int, Dict[str, Any]] = {
        0x00: {
            "name": "MSG_BOX_NOTICE",
            "lambda": "$_5",
            "handler_addr": 0x007f06c8,
            "vtable_addr": 0x014f0e60,
            "structure_type": "STATIC",
            "status": "VERIFIED",
            "schema": ["str"],
            "description": "Server announcement notice dialog",
        },
        0x01: {
            "name": "ROLE_LOGIN_RESPONSE",
            "lambda": "$_6",
            "handler_addr": 0x007f0a0c,
            "vtable_addr": 0x014f0ee0,
            "structure_type": "DYNAMIC",
            "status": "PARTIAL",
            "schema": ["str", "u8"],
            "description": "Login message & role list (header + character array loop)",
        },
        0x04: {
            "name": "ACCOUNT_INFO",
            "lambda": "$_7",
            "handler_addr": 0x007f4ba4,
            "vtable_addr": 0x014f0f60,
            "structure_type": "STATIC",
            "status": "VERIFIED",
            "schema": ["str", "str"],
            "description": "Account token & credential validation",
        },
        0x05: {
            "name": "SERVER_REDIRECT",
            "lambda": "$_8",
            "handler_addr": 0x007f4de4,
            "vtable_addr": 0x014f0fe0,
            "structure_type": "STATIC",
            "status": "VERIFIED",
            "schema": ["str"],
            "description": "Server redirection host string",
        },
        0x07: {
            "name": "SYSTEM_PROMPT",
            "lambda": "$_9",
            "handler_addr": 0x007f5060,
            "vtable_addr": 0x014f1060,
            "structure_type": "STATIC",
            "status": "VERIFIED",
            "schema": ["u8", "str"],
            "description": "System popup prompt with prompt type code",
        },
        0x08: {
            "name": "CHANGE_PSW_RESULT",
            "lambda": "$_10",
            "handler_addr": 0x007f5604,
            "vtable_addr": 0x014f10e0,
            "structure_type": "STATIC",
            "status": "VERIFIED",
            "schema": ["u8"],
            "description": "Change password response status code (tail-call LeitorPacote::u8)",
        },
        0x0A: {
            "name": "REG_ACCOUNT_RESULT",
            "lambda": "$_11",
            "handler_addr": 0x007f5690,
            "vtable_addr": 0x014f1160,
            "structure_type": "STATIC",
            "status": "VERIFIED",
            "schema": ["str"],
            "description": "Account registration response message",
        },
        0x10: {
            "name": "PLAYER_STATS_SYNC",
            "lambda": "$_13",
            "handler_addr": 0x007f5a8c,
            "vtable_addr": 0x014f1260,
            "structure_type": "DYNAMIC",
            "status": "PARTIAL",
            "schema": ["i32", "i64", "i32", "i32", "i32", "i32", "i32", "i32", "u8", "u8", "i32", "u8", "str"],
            "description": "Player base attributes followed by conditional buff branches (62 calls)",
        },
        0x12: {
            "name": "ENTITY_SPAWN_POSITION",
            "lambda": "$_12",
            "handler_addr": 0x007f57b0,
            "vtable_addr": 0x014f11e0,
            "structure_type": "STATIC",
            "status": "VERIFIED",
            "schema": ["u8", "str"],
            "description": "Entity map zone spawn coordinates",
        },
        0x20: {
            "name": "ENTITY_MOVE_SYNC",
            "lambda": "$_14",
            "handler_addr": 0x007f7078,
            "vtable_addr": 0x014f12e0,
            "structure_type": "DYNAMIC",
            "status": "PARTIAL",
            "schema": ["i16", "i64", "i32", "i16", "i16", "i32", "i64"],
            "description": "Entity movement synchronization trajectory",
        },
        0x21: {
            "name": "BATTLE_STATE_UPDATE",
            "lambda": "$_15",
            "handler_addr": 0x007f7b9c,
            "vtable_addr": 0x014f1360,
            "structure_type": "DYNAMIC",
            "status": "PARTIAL",
            "schema": ["str", "i32", "u8", "i32", "u8", "u8", "u8", "i32", "u8"],
            "description": "Battle environment header with entity & effect loops (20 calls)",
        },
        0x25: {
            "name": "SKILL_CAST_EVENT",
            "lambda": "$_16",
            "handler_addr": 0x007f7f00,
            "vtable_addr": 0x014f13e0,
            "structure_type": "STATIC",
            "status": "VERIFIED",
            "schema": ["i64", "i32", "i16", "i16", "u8", "i32"],
            "description": "Skill invocation event (caster, skill, coords, level, timestamp)",
        },
        0x26: {
            "name": "RESOURCE_TRANSFER",
            "lambda": "$_17",
            "handler_addr": 0x007f8058,
            "vtable_addr": 0x014f1460,
            "structure_type": "STATIC",
            "status": "VERIFIED",
            "schema": ["str", "u8", "str", "u8"],
            "description": "Resource asset manifest metadata",
        },
        0x27: {
            "name": "HEARTBEAT_PING",
            "lambda": "$_18",
            "handler_addr": 0x007f85c8,
            "vtable_addr": 0x014f14e0,
            "structure_type": "STATIC",
            "status": "VERIFIED",
            "schema": ["i32"],
            "description": "Heartbeat Ping (timestamp)",
        },
        0x28: {
            "name": "HEARTBEAT_PONG",
            "lambda": "$_19",
            "handler_addr": 0x007f94c4,
            "vtable_addr": 0x014f1560,
            "structure_type": "STATIC",
            "status": "VERIFIED",
            "schema": ["i32"],
            "description": "Heartbeat Pong (timestamp echo)",
        },
        0x29: {
            "name": "CHAT_MESSAGE_UPDATE",
            "lambda": "chat_$_1",
            "handler_addr": 0x0075eca4,
            "vtable_addr": 0x014efa88,
            "structure_type": "STATIC",
            "status": "VERIFIED",
            "schema": ["i64", "str", "u8", "str", "str", "u8", "str", "str"],
            "description": "Chat message update from CChatManager::receberChatUpdate",
        },
        0x2A: {
            "name": "INVENTORY_ITEM_UPDATE",
            "lambda": "$_20",
            "handler_addr": 0x007f9c2c,
            "vtable_addr": 0x014f15e0,
            "structure_type": "DYNAMIC",
            "status": "PARTIAL",
            "schema": ["u8", "i32", "i32", "i32"],
            "description": "Inventory container header with slot item array (41 calls)",
        },
        0x2B: {
            "name": "QUEST_PROGRESS_UPDATE",
            "lambda": "$_21",
            "handler_addr": 0x007fd6fc,
            "vtable_addr": 0x014f16d0,
            "structure_type": "DYNAMIC",
            "status": "PARTIAL",
            "schema": ["str", "u8", "u8", "i32", "i32"],
            "description": "Quest progress tracking with objective lists (13 calls)",
        },
        0x2C: {
            "name": "GUILD_MEMBER_INFO",
            "lambda": "$_28",
            "handler_addr": 0x0080203c,
            "vtable_addr": 0x014f1a50,
            "structure_type": "STATIC",
            "status": "VERIFIED",
            "schema": ["i64", "u8", "i16", "i32", "i32", "str", "i64", "i16"],
            "description": "Guild member information record",
        },
        0x2D: {
            "name": "SPECIAL_ACTION_NOTIFY",
            "lambda": "$_22",
            "handler_addr": 0x007fed18,
            "vtable_addr": 0x014f1750,
            "structure_type": "DYNAMIC",
            "status": "PARTIAL",
            "schema": ["u8", "u8", "i32", "i32", "i16"],
            "description": "Special action / event dispatch notification (10 calls)",
        },
        0x2E: {
            "name": "ACTION_STATUS_CONFIRM",
            "lambda": "$_23",
            "handler_addr": 0x007ffc28,
            "vtable_addr": 0x014f17d0,
            "structure_type": "STATIC",
            "status": "VERIFIED",
            "schema": ["u8", "str", "str", "str", "str", "str"],
            "description": "Action status code with 5 string parameters",
        },
        0x2F: {
            "name": "MAIL_ATTACHMENT_UPDATE",
            "lambda": "$_29",
            "handler_addr": 0x00803800,
            "vtable_addr": 0x014f1ad0,
            "structure_type": "DYNAMIC",
            "status": "PARTIAL",
            "schema": ["u8", "u8", "str"],
            "description": "Mailbox header with dynamic mail items loop (41 calls)",
        },
        0x30: {
            "name": "PARTY_TEAM_UPDATE",
            "lambda": "$_24",
            "handler_addr": 0x00800864,
            "vtable_addr": 0x014f1850,
            "structure_type": "STATIC",
            "status": "VERIFIED",
            "schema": ["u8", "u8"],
            "description": "Party member count and team state",
        },
        0x31: {
            "name": "SUB_ACTION_STATUS",
            "lambda": "$_30",
            "handler_addr": 0x00806184,
            "vtable_addr": 0x014f1b50,
            "structure_type": "STATIC",
            "status": "VERIFIED",
            "schema": ["i32", "str"],
            "description": "Sub-action error code and diagnostic string",
        },
        0x32: {
            "name": "TOAST_NOTIFICATION",
            "lambda": "$_25",
            "handler_addr": 0x00800f04,
            "vtable_addr": 0x014f18d0,
            "structure_type": "DYNAMIC",
            "status": "PARTIAL",
            "schema": ["u8", "u8", "u8", "u8", "u8", "i32", "u8"],
            "description": "Toast notification popup attributes (18 calls)",
        },
        0x33: {
            "name": "FRIEND_STATUS_UPDATE",
            "lambda": "$_26",
            "handler_addr": 0x00801828,
            "vtable_addr": 0x014f1950,
            "structure_type": "STATIC",
            "status": "VERIFIED",
            "schema": ["u8", "str"],
            "description": "Friend online status and nickname",
        },
        0x43: {
            "name": "MARKET_TRADE_ORDER",
            "lambda": "$_27",
            "handler_addr": 0x00801bac,
            "vtable_addr": 0x014f19d0,
            "structure_type": "STATIC",
            "status": "VERIFIED",
            "schema": ["u8", "u8", "i32", "u8", "u8", "u8", "u8", "i32"],
            "description": "Market auction transaction status",
        },
    }

    @classmethod
    def parse_payload(cls, opcode: int, payload: bytes) -> Dict[str, Any]:
        """
        Parses a decrypted payload using the recovered schema for the given opcode.
        Robustly handles both STATIC verified schemas and DYNAMIC partial schemas.
        """
        meta = cls.OPCODES.get(opcode)
        if not meta:
            return {
                "opcode": opcode,
                "raw_hex": payload.hex(),
                "parsed": False,
                "error": f"Opcode 0x{opcode:02X} not registered in protocol dispatch table"
            }

        reader = PacketReader(payload)
        fields = []
        try:
            for field_type in meta["schema"]:
                if field_type == "u8":
                    fields.append(reader.read_u8())
                elif field_type == "i16":
                    fields.append(reader.read_i16())
                elif field_type == "u16":
                    fields.append(reader.read_u16())
                elif field_type == "i32":
                    fields.append(reader.read_i32())
                elif field_type == "i64":
                    fields.append(reader.read_i64())
                elif field_type == "str":
                    fields.append(reader.read_str())
                elif field_type == "binario":
                    rem = reader.remaining()
                    fields.append(reader.read_binary(rem))

            remaining_bytes = reader.remaining()
            result: Dict[str, Any] = {
                "opcode": opcode,
                "name": meta["name"],
                "lambda": meta["lambda"],
                "handler_addr": hex(meta["handler_addr"]),
                "structure_type": meta["structure_type"],
                "status": meta["status"],
                "fields": fields,
                "remaining_bytes": remaining_bytes,
                "parsed": True,
            }

            if meta["structure_type"] == "DYNAMIC" and remaining_bytes > 0:
                result["raw_variable_payload"] = reader.read_binary(remaining_bytes)
                result["dynamic_body_length"] = remaining_bytes

            return result
        except Exception as e:
            return {
                "opcode": opcode,
                "name": meta["name"],
                "lambda": meta["lambda"],
                "structure_type": meta["structure_type"],
                "status": meta["status"],
                "error": str(e),
                "partial_fields": fields,
                "parsed": False,
            }
