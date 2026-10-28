# Architectural Audit: Server-Controlled Boundaries & Unsupported Hero Features

**Project ID:** `5998ee8249b64cf9`  
**Milestone:** `audit-unsupported-features`  
**Target Binary:** `libaos_jogo.so` (SHA-256 `5e0aefcbf1b23aa2dc74e95b22aee90c17011a4814193b8b61d305747a668c0f`)  
**Package:** `ReturnSaiyan-arm64.apk` (SHA-256 `69f500543fae0b9c301a6c871db40198dbba483ee18299081ef8b48aefb2c970`)  
**Status:** PASS / AUDITED

---

## 1. Executive Summary

This audit establishes the binary-backed demarcation between **client-renderable assets** and **server-authoritative game state** within the ReturnSaiyan client engine (`libaos_jogo.so`). It catalogues the engine protocol handlers, disassembles the packet ingestion routines for roles and items, evaluates feature compatibility across versions, and confirms adherence to network safety rules.

---

## 2. Binary Protocol Architecture (`libaos_jogo.so`)

The client's network communication is centralized under `aos::CProtocolManager` and its packet registration routine `registrarTratadores`:

- **Registration Routine:** `aos::CProtocolManager::registrarTratadores()` at `0x007ede44` (size `0x914` bytes).
- **Packet Reader:** `aos::LeitorPacote`.
- **Dispatcher Method:** `aos::Conexao::registrar(unsigned char opcode, std::function<void(aos::LeitorPacote&)>)`.

### Registered Server-to-Client (S2C) Opcodes
The routine registers 26 distinct message handler callbacks:
`0x00`, `0x01`, `0x04`, `0x05`, `0x07`, `0x08`, `0x0a`, `0x10`, `0x12`, `0x20`, `0x21`, `0x25`, `0x26`, `0x27`, `0x28`, `0x2a`, `0x2b`, `0x2c`, `0x2d`, `0x2e`, `0x2f`, `0x30`, `0x31`, `0x32`, `0x33`, `0x43`.

---

## 3. Disassembly Analysis: Role & Inventory Synchronization

### A. Role Selection & Hero Unlock Synchronization (`0x08` / `0x0a`)
- **Symbol:** `aos::CProtocolManager::getRoleSimpleInfoByIndex(int)` at `0x007ef354`.
- **Data Structure:** `aos::SGameRoleSimpleInfo` (element size: `104` / `0x68` bytes).
- **Container:** `std::vector<aos::SGameRoleSimpleInfo>` stored at offset `[this + 560]`.
- **Mechanism:** On session connection / login, the server sends an opcode `0x08` or `0x0a` payload containing an array of unlocked player characters. The client allocates `SGameRoleSimpleInfo` structs via `std::allocator::construct` and populates the role vector. The client UI determines which characters the player may select or field based solely on this vector.

### B. Inventory & Item Synchronization (`0x10`)
- **Handler Callback:** `_ZNSt6__ndk110__function6__funcIZN3aos16CProtocolManager19registrarTratadoresEvE4$_14NS_9allocatorIS4_EEFvRNS2_12LeitorPacoteEEEclES8_` at `0x007f7078`.
- **Protocol Loop:**
  1. `LeitorPacote::i16()`: Total item count.
  2. Per item:
     - `LeitorPacote::i64()` -> `std::to_string` (unique instance UUID).
     - `LeitorPacote::i32()`: Template item ID.
     - `LeitorPacote::i16()`: Bag slot index.
     - `LeitorPacote::i16()`: Stack quantity.
     - `LeitorPacote::i32()`: Expiration timestamp.
  3. Binds item state to `aos::CBagManager::setItem(...)` (`0x00685420`).

---

## 4. Client-Renderable vs Server-Controlled Demarcation

| Feature Domain | Client Engine Authority (`libaos_jogo.so`) | Server Backend Authority | Offline Staging Status |
|---|---|---|---|
| **Spine Skeleton & Mesh** | Decodes `.xc` binary models via `aos::PacoteSpine::carregar` (`0x00807068`). | None. Client manages rendering and bone transforms. | **Fully Functional** |
| **Texture & Sprites** | Resolves PKM (`ETG\x00\xc8\xe5\xfcw`) textures via `data/` and `png/`. | None. Handled by OpenGL ES / Cocos2d-x backend. | **Fully Functional** |
| **Portrait & Card Art** | Reads `cardSpineId` from `hero.xc` and loads card spines (`1062c`, etc.). | None. Displayed in hero gallery and roster screens. | **Fully Functional** |
| **Character Attributes** | Initializes base stats from `hero.xc` via `aos::CHeroTable::init` (`0x0072ef4c`). | Validates stats during online combat; calculates live damage. | **Fully Functional** (client-side base stats) |
| **Character Unlocking / Gacha** | Renders hero models in showcase; displays lock/unlock overlays. | **Authoritative**: Server must transmit `SGameRoleSimpleInfo` / gacha packet `0x20`. | **Server-Controlled** |
| **Skill Scripts & Buffs** | Executes client animations, audio triggers, and VFX (`useSkill` @ `0x6e25fc`). | **Authoritative**: Server calculates damage rolls, cooldowns, and network state sync. | **Client Visuals Functional** |

---

## 5. Compatibility & Unsupported Features Matrix

| Feature / Issue | Description & Engine Impact | Resolution / Current Status |
|---|---|---|
| **`hero.xc` Schema Divergence** | DB Global used `str` for `phyAct` / `maxHp`, causing crash in ReturnSaiyan `u16` parser (`aos::CHeroTable::init`). | **RESOLVED**: Re-encoded in big-endian `u16`, producing zero delta against ReturnSaiyan specification. |
| **Hero ID Collisions** | DB Global IDs `10061`, `10063`, `10064` clashed with ReturnSaiyan exclusive heroes (Vegito Blue, Broly, Black Frieza). | **RESOLVED**: Remapped DB Global candidates to unallocated IDs `10081`, `10083`, `10084`. |
| **Texture Resolver Divergence** | ReturnSaiyan queries `spine/actor/png/` while DB Global placed textures in `spine/actor/data/`. | **RESOLVED**: Dual-placed all 40 PKM texture files in both paths. |
| **Spine Encryption Compatibility** | Both clients use identical `0x80` byte obfuscation and `ETG\x00\xc8\xe5\xfcw` texture header. | **VERIFIED COMPATIBLE**: Engine decryptor handles staged assets seamlessly. |
| **Audio Compatibility** | All 195 sound files match identically between ReturnSaiyan and DB Global. | **VERIFIED COMPATIBLE**: No missing sound triggers. |
| **Online Hero Unlocking** | Unlocking new heroes in official online sessions requires server-side gacha/unlock packet emission. | **DOCUMENTED BOUNDARY**: Cannot unlock on live servers without server backend support. |

---

## 6. Security & Safety Compliance

- **Live Server Isolation:** In strict compliance with AGENTS.md, no network sockets or HTTP/TCP requests have been made to live game infrastructure or third-party authentication services.
- **Binary Immutability:** Neither `ReturnSaiyan-arm64.apk` nor `libaos_jogo.so` have been patched or altered. All work is cleanly isolated to the staged asset directory `staging/assets/`.
- **No Spoofing:** No authentication tokens, credentials, or fake player state were generated.
