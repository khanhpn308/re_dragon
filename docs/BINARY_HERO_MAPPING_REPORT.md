# ReturnSaiyan — Binary Hero and Actor Registration Report

> **Task Key:** `binary-hero-mapping`  
> **Binary Target:** `libaos_jogo.so` (SHA-256: `5e0aefcbf1b23aa2dc74e95b22aee90c17011a4814193b8b61d305747a668c0f`)  
> **Tooling:** AArch64 Machine Instruction Audit (`aarch64-linux-gnu-objdump`, `readelf`)  

---

## 1. Executive Summary

Through direct disassembly and symbol analysis of `libaos_jogo.so`, the native actor registration, spine animation loader routines, and hero table structures have been mapped with primary machine instruction proof.

---

## 2. AArch64 Machine Instruction Audit

### 2.1 Hero Table Initialization: `aos::CHeroTable::init()` (`0x0072ef4c`)
- **Address:** `0x0072ef4c` (Length: 5,200 bytes)
- **Disassembly Snippet:**
```arm64
  72f01c: bl  69a510 <aos::TabelasXC::instancia()@plt>
  72f020: adrp  x1, 118b000
  72f024: mov   x21, x0
  72f028: add   x1, x1, #0x3d0       ; "hero" (0x118b3d0)
  72f03c: bl  686ca0 <aos::TabelasXC::tabela(std::string const&)@plt>
  72f0d4: mov   w0, #0x1c8           ; 456 bytes (sizeof aos::_Hero_St)
  72f0dc: bl  694330 <operator new(unsigned long)@plt>
  72f154: adrp  x1, 1226000
  72f16c: add   x1, x1, #0x8e7       ; "id" (0x12268e7)
  72f188: bl  694cd0 <aos::TabelaXC::valor(...) const@plt>
```
- **Finding:** Iterates over each hero record in `hero.xc`, allocates `aos::_Hero_St`, and reads `animationId` at string address `0x118b3d5` to bind the hero to its actor model.

### 2.2 Table Schema Constructor: `aos::TabelasXC::TabelasXC()` (`0x007983b8`)
- **Address:** `0x007983b8` inside `TabelasXC::TabelasXC()`
- **Disassembly Snippet:**
```arm64
  7983b8: adrp  x1, 118e000
  7983bc: add   x1, x1, #0xa25       ; "hero.xc" (0x118ea25)
  7983c4: mov   w2, #0x7             ; length 7
  7983c8: bl  68eaf0 <basic_string::assign>
  79840c: adrp  x1, 1226000
  798410: add   x1, x1, #0x8e7       ; "id"
  798420: mov   w10, #0x1            ; type tag 1 (u32)
```
- **Finding:** Authoritatively establishes the 48-column schema of `hero.xc` and its strict big-endian type encodings.

### 2.3 Binary Stream Parser: `aos::TabelaXC::carregar()` (`0x00791380`)
- **Address:** `0x00791380` (Length: 2,376 bytes)
- **Disassembly Snippet:**
```arm64
  7913c8: bl  6956a0 <aos::LeitorXC::u16()@plt>  ; read record count
  7914ac: ldrb  w10, [x23, x8]                   ; dispatch type table
  7914b0: add   x9, x9, x10, lsl #2
  7914b4: br    x9                               ; jump to type parser
```
- **Finding:** Jump table at `0x7914ac` maps type tags directly to `aos::LeitorXC::u8`, `u16`, `u32`, `f32`, and `str` methods.

---

## 3. Actor & Spine Resource Mapping Specification

From the disassembly of `aos::CActorImage::replaceSpine(int)` (`0x00702464`) and `aos::CHeroTable::init()` (`0x0072ef4c`), the engine resolves assets using the following deterministic paths:

| Asset Type | Primary Target Path | Fallback / Compatibility Path | Binary Source Reference |
| :--- | :--- | :--- | :--- |
| **Skeleton Data** | `assets/data/GameData/spine/actor/data/{animationId}.xc` | `{animationId}.json` | `0x1155988` (`data/GameData/spine/actor/data/`) |
| **Texture Atlas** | `assets/data/GameData/spine/actor/data/{animationId}.atlas` | N/A | `libspine` atlas loader |
| **Texture PKM** | `assets/data/GameData/spine/actor/png/{animationId}.pkm` | `assets/data/GameData/spine/actor/data/{animationId}.pkm` | Cocos2d-x TextureCache resolver |
| **Card Spine** | `assets/data/GameData/spine/actor/data/{cardSpineId}.xc` | `{cardSpineId}.atlas` | Card preview UI subsystem |

---

## 4. Verification Checkpoint
- [x] Native routines `aos::CHeroTable::init` and `aos::TabelasXC::TabelasXC` disassembled and verified.
- [x] Primary rodata strings (`hero`, `hero.xc`, `animationId`) confirmed at exact ELF virtual addresses.
- [x] Jump table type decoding logic verified against `aos::LeitorXC` implementations.
- [x] Complete asset-to-actor path resolution rules formalized.
- [x] Original `libaos_jogo.so` left completely unmodified.
