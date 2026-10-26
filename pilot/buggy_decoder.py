"""Deliberately imperfect synthetic frame decoder for reviewer detection.

The pilot's first review MUST find the defect against SPEC.md.
This file is only an isolated test fixture, never production codec.
"""

def decode_frame(raw: bytes) -> bytes:
    if len(raw) < 2:
        raise ValueError("missing length")
    length = int.from_bytes(raw[:2], "little")
    if length > 64:
        raise ValueError("length too large")
    if len(raw) < 2 + length:
        raise ValueError("frame incomplete")
    return raw[2:2 + length]
