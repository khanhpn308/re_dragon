# Evidence: Partition 1 — process_packet Decompilation
- **Target**: `process_packet` at virtual address `0x101280` (file offset `0x1280`)
- **Evidence ID**: `ev_39460428ece147d88911507924d2c4a24aafd8a9801d5c7f827fd1c58fac97a6`
- **Decompiler**: Ghidra 12.1.4
- **Normalized Pseudocode**:
```c
int process_packet(uint8_t *buffer, size_t size)
{
  byte bVar1;
  byte *pbVar2;
  ushort uVar3;
  
  if (size < 8) {
    return -1;
  }
  if (*(short *)buffer != 0x5352) {
    return -2;
  }
  if (0x400 < *(ushort *)(buffer + 4)) {
    return -3;
  }
  if (size == 8) {
    uVar3 = 0;
  }
  else {
    pbVar2 = buffer + 8;
    uVar3 = 0;
    do {
      bVar1 = *pbVar2;
      pbVar2 = pbVar2 + 1;
      uVar3 = uVar3 + bVar1 ^ (ushort)bVar1 + (ushort)bVar1;
    } while (buffer + size != pbVar2);
  }
  if (*(ushort *)(buffer + 6) == uVar3) {
    return (int)buffer[2];
  }
  return -4;
}
```
- **Verification**: Exact match against primary C source in `smoke_test/mini_elf.c` lines 34-52.
