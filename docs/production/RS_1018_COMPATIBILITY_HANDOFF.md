# RE Dragon — ReturnSaiyan 1.0.18 compatibility handoff

**Status:** STATIC_SOURCE_FINDINGS / V2_H0_INPUT / NOT_RUNTIME_VERIFIED
**Date:** 2026-10-27
**Scope:** Read-only client compatibility audit; does not authorize V1 modifications, APK rebuilding, connections to third-party live game servers, or a V2 acceptance verdict.
**Authoritative project charter:** Pin the approved RS-UH-PROD-V2 charter SHA and H0/S1–S6 rules; do not override charter scope by this note.

## Why this handoff exists

The previously created ChatGPT Markdown report was difficult for the operator to preview/download. This GitHub note captures its principal findings and supplies the Agent with durable, repository-accessible task requirements. **This is an abridged handoff; independently re-verify against the local APK files before claiming VERIFIED.** The local binary APKs must stay outside Git.

## Inputs and reported offline identities

| Local artifact | Bytes | SHA-256 | Android version |
|---|---:|---|---|
| ReturnSaiyan-arm64.apk (V1 original baseline) | 137590901 | `69f500543fae0b9c301a6c871db40198dbba483ee18299081ef8b48aefb2c970` | 1.0.17, code 18 |
| ReturnSaiyan-arm64(1).apk (candidate) | 137655244 | `77228a8494d102c03d95f0eb4c4d45a82dcf0e4bf071618acf0336d4c1c15134` | 1.0.18, code 19 |
| ReturnSaiyan-UnifiedHeroes-signed(1).apk (G8 output) | 144145764 | `ff09e65a9f89c4773d6de904ce00443860feb3331a905fcd9508ea287685d583` | 1.0.17, code 18 |

All three report package `com.tony.lzcen.arm64`. Local WSL staging suggestion: `.re_harness/inputs/rs_v2_1018/`; first confirm paths and SHA-256 and update the Harness evidence record. **This directory is local, not the GitHub repo.** Uploaded ChatGPT files do not automatically appear on the user's WSL.

## Prior static comparison findings (recheck)

- ZIP entries: 5897 in baseline vs 5899 in candidate. `assets/versao_apk.txt` and manifest version change 1.0.17→1.0.18.
- Original baseline and candidate `assets/data/dataBin/hero.xc` were byte-identical (reported SHA-256 `068a0f335352a9f075cfeaa234eab6729997dbde48196dc1f4a8676817ff79bc`). Candidate does not contain G8 donor union.
- Native `lib/arm64-v8a/libaos_jogo.so` changed: old SHA-256 `5e0aefcbf1b23aa2dc74e95b22aee90c17011a4814193b8b61d305747a668c0f` vs new `bb38ce4101807edd968a26d590c4a7b2756c83cc7c0f97e84e5652b0da0814bb`; a changed binary does *not* establish a protocol semantic change.
- `skills.xc`, `buffs.xc`, a battle skill Lua script and effect resources changed; evaluate cross-version effects on hero/skill mapping.
- The existing `assets/config.properties` was reported unchanged and still refers to `jogo.returnsaiyan.com.br:30008` and login port `30001`. Those upstream addresses are *not* the planned controlled Go V2 service. Do not call upstream endpoints to perform the audit.
- G8 Unified `hero.xc` changed but reported embedded `versions.txt` retained the baseline hero MD5: embedded `ee14ac0086d119781f7028509977f41e`, bundled hero file `31fa230ef6804906e857159c8619c5e0`. This is a **potential asset update/integrity issue**, not a proven cause of runtime updater failure.
- A mismatch in the `versions.txt` self-reference was reported in all three APKs; do not treat it as a new V1 regression without evidence.
- Source 1.0.17 and candidate 1.0.18 were reported signed by the same certificate fingerprint `52b48e0f01b831d0323694f807a108b554dbd4166938a932cc54f12418ec9dcd`, while G8 APK used a different debug certificate `63046881cb343ac5e3eee5f9217a63c2b5707ea5d41577edeeb0fb00a16ada21`. Signature mismatch prevents ordinary overwrite, absent valid lineage. Do not uninstall or clear app data without backup.

## Requested Orchestrator goal: H0-1.0.18-COMPATIBILITY-AUDIT

1. Identify all three local APKs by content hash; snapshot accepted V1 G8 evidence and protect originals.
2. Compare versioned updater/config/version-manifest behavior, native TCP framing/handshake, auth, sessions and role-world dispatch. Every claim needs a pinned source SHA and evidence. Unknown fields remain UNKNOWN.
3. Verify 1.0.18 skill/buff/effect deltas and compatibility with V1's 128 original + 3 custom heroes and 14 donor SERVER_GATED assets. Preserve canonical hero identifiers and no ambiguous overwrite of `hero.xc`.
4. Review whether 1.0.18 should become the V2 **candidate** base; do not silently swap it for accepted G8 APK or imply it is already Unified.
5. When later authorized by S1–S3, route update/auth/TCP traffic to privately controlled Go endpoints. Do not reuse historical online accounts or third-party live servers.
6. Produce an immutable evidence ledger, differences, risks, scoped options and independent reviewer verdict; only then propose a rebuilt client with its own hash, signing strategy and real Android runtime tests.
7. Keep approved V2 charter acceptance and 5,000-CCU S5/S6 requirements unchanged. H0 only audits; **no runtime test/rebuild is authorized by this document**.

## Scope and limitations

The report covers offline comparisons; no APK execution, updated APK signing-block validation, live server handshake, real gameplay, or proof that version 1.0.18 is the globally newest release. Do not falsely mark V2 PLAYABLE or GO on these facts alone.
