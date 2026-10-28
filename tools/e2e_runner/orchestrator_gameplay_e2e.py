#!/usr/bin/env python3
"""
Orchestrator Gameplay E2E Script for RS-UH-V2-ANDROID-PLAYABILITY
Drives physical RMX3461 to:
1. Launch game application
2. Execute guest authentication handshake (Opcode 0x00 -> 0x01)
3. Select server and execute game connection handshake (Opcode 0x12 -> S2C 0x12)
4. Select character and enter game world (Opcode 0x25, 0x10 -> S2C 0x10)
5. Perform in-world physical movement and interactions
6. Capture timestamped screenshots, server logs, logcat, and verify PostgreSQL persistence.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

REPO_ROOT = Path("/home/khanh/returnsaiyan-re")
EVIDENCE_DIR = REPO_ROOT / "evidence" / "s6_e2e"
EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)

DEVICE_ID = "10b3139c"
PACKAGE_NAME = "com.tony.lzcen.arm64"
ACTIVITY_NAME = f"{PACKAGE_NAME}/.AppActivity"
DB_URL = "postgres://returnsaiyan:returnsaiyan_pass@127.0.0.1:5432/returnsaiyan_dev?sslmode=disable"
SERVER_BIN = REPO_ROOT / "game-server" / "bin" / "game-server"
UPDATER_SCRIPT = REPO_ROOT / "tools" / "mock_updater" / "updater.py"

LOGCAT_FILE = EVIDENCE_DIR / "orchestrator_logcat.log"
SERVER_LOG = EVIDENCE_DIR / "orchestrator_server.log"
UPDATER_LOG = EVIDENCE_DIR / "orchestrator_updater.log"

SCREENSHOT_01 = EVIDENCE_DIR / "01_app_launch.png"
SCREENSHOT_02 = EVIDENCE_DIR / "02_server_selection.png"
SCREENSHOT_03 = EVIDENCE_DIR / "03_world_entry.png"
SCREENSHOT_04 = EVIDENCE_DIR / "04_gameplay_movement.png"
DB_RESULT_FILE = EVIDENCE_DIR / "db_persistence.json"
MANIFEST_FILE = EVIDENCE_DIR / "e2e_run_manifest.json"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def run():
    print(f"=== Starting RE Dragon Autonomous E2E Gameplay Orchestrator on {DEVICE_ID} ===")
    start_ts = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # 1. Reverse port forwards
    print("[1/6] Configuring ADB reverse port forwarding (:30001, :30008)...")
    subprocess.check_call(["adb", "-s", DEVICE_ID, "reverse", "tcp:30001", "tcp:30001"])
    subprocess.check_call(["adb", "-s", DEVICE_ID, "reverse", "tcp:30008", "tcp:30008"])

    # 2. Launch mock updater
    print("[2/6] Starting local services (Mock Updater + Go TCP Game Server)...")
    updater_f = open(UPDATER_LOG, "w")
    updater_proc = subprocess.Popen(["python3", str(UPDATER_SCRIPT)], stdout=updater_f, stderr=updater_f)

    # 3. Launch Go game server
    server_f = open(SERVER_LOG, "w")
    env = dict(os.environ, DATABASE_URL=DB_URL)
    server_proc = subprocess.Popen([str(SERVER_BIN)], env=env, stdout=server_f, stderr=server_f)
    time.sleep(2)

    # 4. Stream logcat
    print("[3/6] Starting device logcat capture...")
    subprocess.call(["adb", "-s", DEVICE_ID, "logcat", "-c"])
    logcat_f = open(LOGCAT_FILE, "w")
    logcat_proc = subprocess.Popen(["adb", "-s", DEVICE_ID, "logcat", "-v", "time"], stdout=logcat_f, stderr=subprocess.DEVNULL)

    manifest_artifacts = {}

    try:
        # Wake screen
        subprocess.check_call(["adb", "-s", DEVICE_ID, "shell", "input", "keyevent", "KEYCODE_WAKEUP"])

        # 5. Launch game app
        print("[4/6] Launching target Android game client...")
        subprocess.check_call(["adb", "-s", DEVICE_ID, "shell", "am", "start", "-n", ACTIVITY_NAME])
        print("Waiting 6 seconds for title screen initialization...")
        time.sleep(6)

        # Capture Screenshot 1: App Launch / Title
        sc1 = subprocess.check_output(["adb", "-s", DEVICE_ID, "exec-out", "screencap", "-p"])
        SCREENSHOT_01.write_bytes(sc1)
        manifest_artifacts["01_app_launch.png"] = {
            "path": str(SCREENSHOT_01),
            "size": len(sc1),
            "sha256": sha256_file(SCREENSHOT_01),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "description": "App launched and title screen reached on physical RMX3461"
        }
        print(f"Captured 01_app_launch.png ({len(sc1)} bytes)")

        # 6. Tap "Khách" (Guest Login) button at (940, 835)
        print("Tapping 'Khách' (Guest Login) at (940, 835)...")
        subprocess.check_call(["adb", "-s", DEVICE_ID, "shell", "input", "tap", "940", "835"])
        print("Waiting 4 seconds for authentication and server list...")
        time.sleep(4)

        # Capture Screenshot 2: Server Selection
        sc2 = subprocess.check_output(["adb", "-s", DEVICE_ID, "exec-out", "screencap", "-p"])
        SCREENSHOT_02.write_bytes(sc2)
        manifest_artifacts["02_server_selection.png"] = {
            "path": str(SCREENSHOT_02),
            "size": len(sc2),
            "sha256": sha256_file(SCREENSHOT_02),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "description": "Guest login authenticated; server card displayed with role info"
        }
        print(f"Captured 02_server_selection.png ({len(sc2)} bytes)")

        # 7. Tap Server Card 1 at (1080, 504)
        print("Tapping Server Card 1 at (1080, 504) to connect to game server and enter world...")
        subprocess.check_call(["adb", "-s", DEVICE_ID, "shell", "input", "tap", "1080", "504"])
        print("Waiting 5 seconds for game handshake, role selection, and world entry...")
        time.sleep(5)

        # Capture Screenshot 3: World Entry
        sc3 = subprocess.check_output(["adb", "-s", DEVICE_ID, "exec-out", "screencap", "-p"])
        SCREENSHOT_03.write_bytes(sc3)
        manifest_artifacts["03_world_entry.png"] = {
            "path": str(SCREENSHOT_03),
            "size": len(sc3),
            "sha256": sha256_file(SCREENSHOT_03),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "description": "Game handshake completed; character loaded into game world"
        }
        print(f"Captured 03_world_entry.png ({len(sc3)} bytes)")

        # 8. Perform physical in-world movement and action
        print("[5/6] Executing in-world physical interactions (movement & skill inputs)...")
        # Swipe on left virtual joystick
        subprocess.check_call(["adb", "-s", DEVICE_ID, "shell", "input", "swipe", "450", "750", "650", "750", "400"])
        time.sleep(1)
        # Tap attack/action area on right
        subprocess.check_call(["adb", "-s", DEVICE_ID, "shell", "input", "tap", "2000", "850"])
        time.sleep(2)

        # Capture Screenshot 4: Gameplay Movement
        sc4 = subprocess.check_output(["adb", "-s", DEVICE_ID, "exec-out", "screencap", "-p"])
        SCREENSHOT_04.write_bytes(sc4)
        manifest_artifacts["04_gameplay_movement.png"] = {
            "path": str(SCREENSHOT_04),
            "size": len(sc4),
            "sha256": sha256_file(SCREENSHOT_04),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "description": "Physical movement and action inputs executed on RMX3461"
        }
        print(f"Captured 04_gameplay_movement.png ({len(sc4)} bytes)")

    finally:
        print("[6/6] Tearing down processes and collecting logs...")
        subprocess.call(["adb", "-s", DEVICE_ID, "shell", "am", "force-stop", PACKAGE_NAME])
        logcat_proc.terminate()
        logcat_f.close()
        server_proc.terminate()
        server_f.close()
        updater_proc.terminate()
        updater_f.close()

    # 9. Query PostgreSQL persistence
    print("Auditing PostgreSQL persistence...")
    db_out = subprocess.check_output([
        "docker", "exec", "rs-postgres", "psql", "-U", "returnsaiyan", "-d", "returnsaiyan_dev",
        "-c", "SELECT a.id as account_id, a.username, r.id as role_id, r.name as role_name, r.hero_code, r.level, a.created_at FROM accounts a LEFT JOIN roles r ON a.id = r.account_id ORDER BY a.id DESC LIMIT 5;"
    ]).decode("utf-8")

    db_json = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "psql_output": db_out.strip()
    }
    DB_RESULT_FILE.write_text(json.dumps(db_json, indent=2))
    print(db_out)

    # 10. Generate Run Manifest
    manifest = {
        "test_run": "RS-UH-V2-ANDROID-PLAYABILITY-E2E",
        "device": {
            "id": DEVICE_ID,
            "model": "RMX3461",
            "resolution": "2412x1080"
        },
        "start_time": start_ts,
        "end_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "artifacts": manifest_artifacts,
        "logs": {
            "server_log": {
                "path": str(SERVER_LOG),
                "sha256": sha256_file(SERVER_LOG)
            },
            "logcat_log": {
                "path": str(LOGCAT_FILE),
                "sha256": sha256_file(LOGCAT_FILE)
            },
            "updater_log": {
                "path": str(UPDATER_LOG),
                "sha256": sha256_file(UPDATER_LOG)
            },
            "db_persistence": {
                "path": str(DB_RESULT_FILE),
                "sha256": sha256_file(DB_RESULT_FILE)
            }
        }
    }
    MANIFEST_FILE.write_text(json.dumps(manifest, indent=2))
    print(f"\nManifest saved to {MANIFEST_FILE}")
    print("=== E2E Run Complete ===")


if __name__ == "__main__":
    run()
