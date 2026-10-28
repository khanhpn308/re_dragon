# Evidence: ELF Metadata & Segment Inspection
- **File**: `smoke_test/mini_elf.elf`
- **Class**: ELF64 Little-Endian, x86-64
- **Type**: DYN (PIE)
- **Entry Point**: `0x1120`
- **Segments**: 13 Program Headers
  - Code segment: Offset 0x1000, Flags: R E, VirtAddr 0x1000
  - Read-only data: Offset 0x2000, Flags: R, VirtAddr 0x2000
  - Data/BSS: Offset 0x2db0, Flags: RW, VirtAddr 0x3db0
