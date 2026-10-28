#!/usr/bin/env python3
"""
Interactive Android E2E Test with Live Guest Login Flow
Automates client launch, UI tap on "Khách" (Guest Login),
captures network handshake and opcode flow with Go Game Server + PostgreSQL.
"""
from __future__ import annotations

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

LOGCAT_FILE = EVIDENCE_DIR / "interactive_logcat.txt"
SERVER_LOG = EVIDENCE_DIR / "interactive_server.log"
UPDATER_LOG = EVIDENCE_DIR / "interactive_updater.log"
SCREENSHOT_TITLE = EVIDENCE_DIR / "title_screen.png"
SCREENSHOT_POSTLOGIN = EVIDENCE_DIR / "post_login_screen.png"


def run():
    print(f"=== Starting Interactive Android E2E Gameplay Test on {DEVICE_ID} ===")

    # 1. Reverse port forwards
    subprocess.check_call(["adb", "-s", DEVICE_ID, "reverse", "tcp:30001", "tcp:30001"])
    subprocess.check_call(["adb", "-s", DEVICE_ID, "reverse", "tcp:30008", "tcp:30008"])
    print("ADB reverse tunnels active for :30001 and :30008.")

    # 2. Launch mock updater
    updater_f = open(UPDATER_LOG, "w")
    updater_proc = subprocess.Popen(["python3", str(UPDATER_SCRIPT)], stdout=updater_f, stderr=updater_f)

    # 3. Launch Go game server
    server_f = open(SERVER_LOG, "w")
    env = dict(os.environ, DATABASE_URL=DB_URL)
    server_proc = subprocess.Popen([str(SERVER_BIN)], env=env, stdout=server_f, stderr=server_f)

    time.sleep(2)  # Wait for socket listeners

    # 4. Stream logcat (do not hard-fail if logcat -c is blocked by device permissions)
    subprocess.call(["adb", "-s", DEVICE_ID, "logcat", "-c"])
    logcat_f = open(LOGCAT_FILE, "w")
    logcat_proc = subprocess.Popen(["adb", "-s", DEVICE_ID, "logcat", "-v", "time"], stdout=logcat_f, stderr=subprocess.DEVNULL)

    try:
        # 5. Launch app
        print("Launching game client...")
        subprocess.check_call(["adb", "-s", DEVICE_ID, "shell", "am", "start", "-n", ACTIVITY_NAME])

        # Wait for splash & title dialog
        print("Waiting 6 seconds for title screen to initialize...")
        time.sleep(6)

        # Capture title screenshot
        sc1 = subprocess.check_output(["adb", "-s", DEVICE_ID, "exec-out", "screencap", "-p"])
        SCREENSHOT_TITLE.write_bytes(sc1)
        print(f"Captured title screenshot: {SCREENSHOT_TITLE} ({len(sc1)} bytes)")

        # 6. Tap "Khách" (Guest login) at (900, 835)
        print("Tapping 'Khách' (Guest Login) button at (900, 835)...")
        subprocess.check_call(["adb", "-s", DEVICE_ID, "shell", "input", "tap", "900", "835"])

        # Wait for network login flow and role display
        print("Waiting 10 seconds for network authentication and server dispatch...")
        time.sleep(10)

        # 7. Capture post-login screenshot
        sc2 = subprocess.check_output(["adb", "-s", DEVICE_ID, "exec-out", "screencap", "-p"])
        SCREENSHOT_POSTLOGIN.write_bytes(sc2)
        print(f"Captured post-login screenshot: {SCREENSHOT_POSTLOGIN} ({len(sc2)} bytes)")

    finally:
        print("Cleaning up processes...")
        subprocess.call(["adb", "-s", DEVICE_ID, "shell", "am", "force-stop", PACKAGE_NAME])
        logcat_proc.terminate()
        logcat_f.close()
        server_proc.terminate()
        server_f.close()
        updater_proc.terminate()
        updater_f.close()

    print("Test run complete. Output files:")
    print(f"  Logcat:      {LOGCAT_FILE}")
    print(f"  Server log:  {SERVER_LOG}")
    print(f"  Updater log: {UPDATER_LOG}")


if __name__ == "__main__":
    run()
