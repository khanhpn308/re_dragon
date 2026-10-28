# ReturnSaiyan Unified Heroes — Packaging, Signing & Rollback Report

> **Task Key:** `g5-unified-apk-packaging-signing-rollback`  
> **Output Artifact:** `ReturnSaiyan-UnifiedHeroes-signed.apk`  
> **Signed Status:** VERIFIED (Android v1/v2/v3 signatures)

---

## 1. Build & Packaging Pipeline

The packaging pipeline integrates the staged assets into a standalone Android APK artifact while strictly preserving the immutability of the source baseline.

| Stage | Tool | Parameter | Result |
| :--- | :--- | :--- | :--- |
| **Assembly** | Python `zipfile` | Deflate (Level 6) | 5891 preserved, 1 replaced (`hero.xc`), 200 added |
| **Alignment** | `zipalign` | `-p -f 4` | 4-byte page-aligned (ELF & uncompressed asset compliance) |
| **Signing** | `apksigner` | RSA 2048 / SHA256 | Valid debug keystore signature |
| **Verification** | `apksigner verify` | `--verbose` | Verified successfully |

---

## 2. Cryptographic Checksums & Metrics

- **Original APK SHA-256:** `69f500543fae0b9c301a6c871db40198dbba483ee18299081ef8b48aefb2c970` (Unmodified)
- **Unified Heroes APK SHA-256:** `246802996c4c51b11fd0f63f1f79638f50101014b5bade0d7d232cf06da6ae1a`
- **Package File Size:** `144,145,764` bytes

---

## 3. Rollback Ledger & Procedure

1. **Clean Workspace:** Delete `dist/ReturnSaiyan-UnifiedHeroes-signed.apk`.
2. **Revert Assets:** Remove or ignore `staging/assets/`.
3. **Canonical Baseline:** Original `ReturnSaiyan-arm64.apk` is guaranteed pristine and untampered.
