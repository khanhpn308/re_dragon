# Evidence: Symbol Table & Calling Conventions
- **Target**: `smoke_test/mini_elf.elf`
- **Symbols**:
  - `calculate_checksum`: `0x0000000000001210`, Size: 43 bytes, Type: FUNC, Bind: GLOBAL
  - `validate_header`: `0x0000000000001240`, Size: 54 bytes, Type: FUNC, Bind: GLOBAL
  - `process_packet`: `0x0000000000001280`, Size: 108 bytes, Type: FUNC, Bind: GLOBAL
  - `main`: `0x0000000000001080`, Size: 156 bytes, Type: FUNC, Bind: GLOBAL
- **Calling Convention**: System V AMD64 ABI (rdi, rsi, rdx, rcx, r8, r9)
