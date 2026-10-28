# Evidence: Partition 2 — validate_header Decompilation
- **Target**: `validate_header` at virtual address `0x101240` (file offset `0x1240`)
- **Evidence ID**: `ev_3ef8e425fedf8f94f0e1ed76980f1880b4c6f9f7d46cac1ee8b26d6f2e4b4255`
- **Decompiler**: Ghidra 12.1.4
- **Normalized Pseudocode**:
```c
int validate_header(uint8_t *buffer, size_t size)
{
  if (size < 8) {
    return -1;
  }
  if (*(short *)buffer == 0x5352) {
    return ~-(uint)(*(ushort *)(buffer + 4) < 0x401) & 0xfffffffd;
  }
  return -2;
}
```
- **Semantics**:
  - `size < 8` returns `-1` (buffer smaller than header struct)
  - Magic byte mismatch (`!= 0x5352`) returns `-2`
  - Length check: if length <= 1024 (`0x400`), returns `0`; if length > 1024, returns `-3` (`0xfffffffd`).
- **Verification**: Exact match against `smoke_test/mini_elf.c` lines 24-35.
