#!/usr/bin/env python3
"""
Packaging and Signing Pipeline for RS-UH-PROD-V1 Gate G5
Produces:
  - dist/ReturnSaiyan-UnifiedHeroes-signed.apk
  - .re_harness/production/RS-UH-PROD-V1/build-log.txt
  - Updates .re_harness/production/RS-UH-PROD-V1/build_manifest.json
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile

REPO_ROOT = Path("/home/khanh/returnsaiyan-re")
PROD_DIR = REPO_ROOT / ".re_harness" / "production" / "RS-UH-PROD-V1"
ORIG_APK = REPO_ROOT / "ReturnSaiyan-arm64.apk"
STAGING_DIR = PROD_DIR / "staging" / "assets"
DIST_DIR = REPO_ROOT / "dist"
KEYSTORE_PATH = DIST_DIR / "debug.keystore"
BUILD_LOG = PROD_DIR / "build-log.txt"
MANIFEST_FILE = PROD_DIR / "build_manifest.json"

UNALIGNED_APK = DIST_DIR / "ReturnSaiyan-UnifiedHeroes-unaligned.apk"
FINAL_APK = DIST_DIR / "ReturnSaiyan-UnifiedHeroes-signed.apk"

ORIG_SHA256 = "69f500543fae0b9c301a6c871db40198dbba483ee18299081ef8b48aefb2c970"

def sha256_path(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(1024 * 1024):
            h.update(chunk)
    return h.hexdigest()

def ensure_keystore(log_f):
    if not KEYSTORE_PATH.exists():
        log_f.write("Generating debug signing keystore...\n")
        cmd = [
            "keytool", "-genkeypair", "-v",
            "-keystore", str(KEYSTORE_PATH),
            "-storepass", "android",
            "-alias", "androiddebugkey",
            "-keypass", "android",
            "-keyalg", "RSA",
            "-keysize", "2048",
            "-validity", "10000",
            "-dname", "CN=Android Debug,O=Android,C=US"
        ]
        subprocess.check_call(cmd, stdout=log_f, stderr=log_f)
    else:
        log_f.write(f"Using existing keystore: {KEYSTORE_PATH}\n")

def main():
    DIST_DIR.mkdir(parents=True, exist_ok=True)
    with open(BUILD_LOG, "w") as log:
        log.write("=== RS-UH-PROD-V1 BUILD & PACKAGING PIPELINE LOG ===\n")
        log.write(f"Source APK: {ORIG_APK}\n")
        
        # 1. Check original APK hash
        initial_hash = sha256_path(ORIG_APK)
        log.write(f"Source APK SHA-256: {initial_hash}\n")
        assert initial_hash == ORIG_SHA256, f"Mismatch: {initial_hash} vs {ORIG_SHA256}"
        log.write("Source APK read-only preservation verified.\n\n")

        # 2. Gather staged files
        staged_files = {}
        for root, _, files in os.walk(STAGING_DIR):
            for fname in files:
                p = Path(root) / fname
                rel = p.relative_to(STAGING_DIR)
                arcname = f"assets/{rel.as_posix()}"
                staged_files[arcname] = p

        log.write(f"Collected {len(staged_files)} staged files from {STAGING_DIR}\n")

        # 3. Assemble unaligned APK
        if UNALIGNED_APK.exists():
            UNALIGNED_APK.unlink()

        preserved_count = 0
        replaced_count = 0
        added_count = 0

        with zipfile.ZipFile(ORIG_APK, "r") as src, zipfile.ZipFile(UNALIGNED_APK, "w", compression=zipfile.ZIP_DEFLATED) as dst:
            for item in src.infolist():
                if item.filename.startswith("META-INF/"):
                    continue
                if item.filename in staged_files:
                    staged_path = staged_files.pop(item.filename)
                    dst.write(staged_path, item.filename)
                    replaced_count += 1
                else:
                    data = src.read(item.filename)
                    dst.writestr(item, data)
                    preserved_count += 1

            for arcname, staged_path in staged_files.items():
                dst.write(staged_path, arcname)
                added_count += 1

        log.write(f"Assembly completed: preserved={preserved_count}, replaced={replaced_count}, added={added_count}\n")
        log.write(f"Total entries in unaligned APK: {preserved_count + replaced_count + added_count}\n\n")

        # 4. Zipalign
        temp_aligned = DIST_DIR / "temp-aligned.apk"
        if temp_aligned.exists():
            temp_aligned.unlink()
        if FINAL_APK.exists():
            FINAL_APK.unlink()

        log.write("Running zipalign -p -f 4...\n")
        cmd_align = ["zipalign", "-p", "-f", "4", str(UNALIGNED_APK), str(temp_aligned)]
        res_align = subprocess.run(cmd_align, capture_output=True, text=True)
        log.write(res_align.stdout + res_align.stderr)
        assert res_align.returncode == 0, f"zipalign failed: {res_align.stderr}"
        log.write("zipalign completed successfully.\n\n")

        # 5. Sign with apksigner
        ensure_keystore(log)
        log.write("Signing APK with apksigner...\n")
        cmd_sign = [
            "apksigner", "sign",
            "--ks", str(KEYSTORE_PATH),
            "--ks-pass", "pass:android",
            "--ks-key-alias", "androiddebugkey",
            "--key-pass", "pass:android",
            "--out", str(FINAL_APK),
            str(temp_aligned)
        ]
        res_sign = subprocess.run(cmd_sign, capture_output=True, text=True)
        log.write(res_sign.stdout + res_sign.stderr)
        assert res_sign.returncode == 0, f"apksigner failed: {res_sign.stderr}"
        log.write(f"apksigner completed successfully -> {FINAL_APK}\n\n")

        if temp_aligned.exists():
            temp_aligned.unlink()
        if UNALIGNED_APK.exists():
            UNALIGNED_APK.unlink()

        # 6. Verify signed APK
        log.write("Running apksigner verify --verbose --print-certs...\n")
        cmd_verify = ["apksigner", "verify", "--verbose", "--print-certs", str(FINAL_APK)]
        res_verify = subprocess.run(cmd_verify, capture_output=True, text=True)
        log.write(res_verify.stdout)
        assert res_verify.returncode == 0, f"apksigner verify failed: {res_verify.stderr}"

        final_sha256 = sha256_path(FINAL_APK)
        final_size = os.path.getsize(FINAL_APK)
        log.write(f"\nFinal APK: {FINAL_APK}\n")
        log.write(f"Final SHA-256: {final_sha256}\n")
        log.write(f"Final Size: {final_size} bytes\n")

        # 7. Check original APK hash again
        post_hash = sha256_path(ORIG_APK)
        assert post_hash == ORIG_SHA256, "Original APK was altered!"
        log.write(f"Post-build source APK SHA-256 verification: {post_hash} (UNMODIFIED)\n")

    # Update build_manifest.json
    with open(MANIFEST_FILE, "r") as f:
        manifest = json.load(f)

    manifest["package_output"] = {
        "apk_path": str(FINAL_APK),
        "sha256": final_sha256,
        "size_bytes": final_size,
        "entries": {
            "preserved": preserved_count,
            "replaced": replaced_count,
            "added": added_count,
            "total": preserved_count + replaced_count + added_count
        },
        "signing": {
            "keystore": str(KEYSTORE_PATH),
            "key_alias": "androiddebugkey",
            "v1_v2_v3_verified": True
        },
        "build_log": str(BUILD_LOG)
    }

    with open(MANIFEST_FILE, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"Build complete: {FINAL_APK}")
    print(f"SHA-256: {final_sha256}")
    print(f"Size: {final_size} bytes")
    print(f"Build log: {BUILD_LOG}")

if __name__ == "__main__":
    main()
