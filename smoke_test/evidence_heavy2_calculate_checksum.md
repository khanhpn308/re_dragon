# Evidence: heavy-decompile-2 — calculate_checksum Decompilation
- **Target**: `calculate_checksum` at virtual address `0x101210` (file offset `0x1210`)
- **Evidence ID**: `ev_05525e0717397fb5c1cf49b32cd4b8d7190deb73475725480e3138d4e4f4b69c`
- **Decompiler**: Ghidra 12.1.4
- **Normalized Pseudocode**:
```c
uint16_t calculate_checksum(uint8_t *data, size_t len)
{
  byte bVar1;
  ushort uVar2;
  byte *pbVar3;
  
  if (len != 0) {
    pbVar3 = data + len;
    uVar2 = 0;
    do {
      bVar1 = *data;
      data = data + 1;
      uVar2 = uVar2 + bVar1 ^ (ushort)bVar1 + (ushort)bVar1;
    } while (pbVar3 != data);
    return uVar2;
  }
  return 0;
}
```
- **Algorithm Analysis**:
  Iterates over data buffer of length `len`.
  Accumulator initialized to 0.
  For each byte `b`: `acc = (acc + b) ^ (b << 1)`.
  Returns 16-bit truncated integer.
- **Verification**: Exact match against primary C source in `smoke_test/mini_elf.c` lines 16-22.
