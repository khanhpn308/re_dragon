# RE Dragon autonomy pilot — frame fixture contract

This fixture is intentionally small and entirely synthetic. It is not sourced
from ReturnSaiyan and must never be interpreted as evidence of its protocol.

Frame format: exactly two bytes of **big-endian** unsigned payload length,
followed by that many payload bytes. Maximum length is 64. Truncated data and
surplus bytes must raise ValueError. Length 0 is valid. Functions must return
the payload bytes only.

Expected examples:
- `00 00` => empty payload
- `00 03 61 62 63` => b"abc"
- `00 01 ff` => b"\xff"
- `01 00` => ValueError (length exceeds max)
- `00 02 aa` => ValueError (truncated)
- `00 00 ff` => ValueError (trailing bytes)

This is an external fixture oracle for the pilot, not a game protocol claim.
