#!/usr/bin/env python3
import os
import subprocess
import time
from pathlib import Path
from PIL import Image, ImageChops

REPO_ROOT = Path("/home/khanh/returnsaiyan-re")
DEVICE_ID = "10b3139c"
PACKAGE_NAME = "com.tony.lzcen.arm64"
ACTIVITY_NAME = f"{PACKAGE_NAME}/.AppActivity"
SERVER_BIN = REPO_ROOT / "game-server" / "bin" / "game-server"
UPDATER_SCRIPT = REPO_ROOT / "tools" / "mock_updater" / "updater.py"
DB_URL = "postgres://returnsaiyan:returnsaiyan_pass@127.0.0.1:5432/returnsaiyan_dev?sslmode=disable"
DIAG_DIR = REPO_ROOT / "evidence" / "diag" / "last_login_test"
DIAG_DIR.mkdir(parents=True, exist_ok=True)

SERVER_LOG = DIAG_DIR / "server.log"
UPDATER_LOG = DIAG_DIR / "updater.log"
LOGCAT_LOG = DIAG_DIR / "logcat.log"

def run():
    subprocess.check_call(["adb", "-s", DEVICE_ID, "reverse", "tcp:30001", "tcp:30001"])
    subprocess.check_call(["adb", "-s", DEVICE_ID, "reverse", "tcp:30008", "tcp:30008"])

    up_f = open(UPDATER_LOG, "w")
    up_proc = subprocess.Popen(["python3", str(UPDATER_SCRIPT)], stdout=up_f, stderr=up_f)

    srv_f = open(SERVER_LOG, "w")
    env = dict(os.environ, DATABASE_URL=DB_URL)
    srv_proc = subprocess.Popen([str(SERVER_BIN)], env=env, stdout=srv_f, stderr=srv_f)
    time.sleep(2)

    subprocess.call(["adb", "-s", DEVICE_ID, "logcat", "-c"])
    lc_f = open(LOGCAT_LOG, "w")
    lc_proc = subprocess.Popen(["adb", "-s", DEVICE_ID, "logcat", "-v", "time"], stdout=lc_f, stderr=subprocess.DEVNULL)

    try:
        subprocess.check_call(["adb", "-s", DEVICE_ID, "shell", "input", "keyevent", "KEYCODE_WAKEUP"])
        print("Launching client...")
        subprocess.check_call(["adb", "-s", DEVICE_ID, "shell", "am", "start", "-n", ACTIVITY_NAME])
        time.sleep(6)

        # 1. Tap Khách
        print("Tapping 'Khách' at (940, 835)...")
        subprocess.check_call(["adb", "-s", DEVICE_ID, "shell", "input", "tap", "940", "835"])
        time.sleep(4)

        sc1_bytes = subprocess.check_output(["adb", "-s", DEVICE_ID, "exec-out", "screencap", "-p"])
        (DIAG_DIR / "01_roles.png").write_bytes(sc1_bytes)
        im1 = Image.open(DIAG_DIR / "01_roles.png").convert("RGB")
        print("Captured 01_roles.png")

        # 2. Tap lastLoginInfoPanel at (1278, 267)
        print("Tapping lastLoginInfoPanel at (1278, 267)...")
        subprocess.check_call(["adb", "-s", DEVICE_ID, "shell", "input", "tap", "1278", "267"])
        time.sleep(4)

        sc2_bytes = subprocess.check_output(["adb", "-s", DEVICE_ID, "exec-out", "screencap", "-p"])
        (DIAG_DIR / "02_after_panel.png").write_bytes(sc2_bytes)
        im2 = Image.open(DIAG_DIR / "02_after_panel.png").convert("RGB")
        diff = ImageChops.difference(im1, im2)
        print("Diff bbox after lastLoginInfoPanel tap (1278, 267):", diff.getbbox())

        # Check server log
        time.sleep(2)
        with open(SERVER_LOG) as f:
            print("--- Server log tail ---")
            for line in f.readlines()[-15:]:
                print("  ", line.strip())

    finally:
        subprocess.call(["adb", "-s", DEVICE_ID, "shell", "am", "force-stop", PACKAGE_NAME])
        lc_proc.terminate()
        lc_f.close()
        srv_proc.terminate()
        srv_f.close()
        up_proc.terminate()
        up_f.close()

if __name__ == "__main__":
    run()
