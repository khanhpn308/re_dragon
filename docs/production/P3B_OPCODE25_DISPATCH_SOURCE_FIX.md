# P3b Opcode 0x25 dispatch — bounded source remediation

**State: PARTIAL_SOURCE_FIX, GACHA STILL BLOCKED.** The code change only
separates complete length-prefixed ASCII C2S commands (such as observed
`drawCard:open:1`) from the existing binary `SkillCast` branch.

- Source: `evidence/real_dungeon_combat/20261028_061547/server.log`,
  at 13:16:10.706 `drawCard:open:1` was received on 0x25.
- Before: `handler.go` decoded both RPC and combat inside
  `handleSkillCast()` and silently discarded colon-delimited commands.
- After: `handleOpcode25()` checks the *entire* length-prefixed payload.
  Text RPC goes to `handleClientRPC()`; binary combat stays in
  `handleSkillCast()`. Unimplemented `drawCard` is explicitly logged
  as BLOCKED, with no fabricated S2C response.
- The 0x25 naming is a Go server assumption, not an authoritative
  classification of the original client protocol.
- `bianqiang_niudan.lua:271` reports `mType=nil`, but the recorded Lua
  error precedes the alleged summon tap, so the causal link is unverified.

**Still needed (non-negotiable):** local Lua/bytecode callback evidence that
initializes `mType`; actual x1 wish request, resource cost, authoritative
S2C response fields and framing; physical RMX3461 summon/ownership E2E.
CI test success does not certify any of those.

This change does not touch PostgreSQL, Harness, APK, original V1 evidence,
server-side combat formulas or protected client resources.
