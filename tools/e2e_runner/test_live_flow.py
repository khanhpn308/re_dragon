#!/usr/bin/env python3
import os
import subprocess
import time
from pathlib import Path

REPO_ROOT = Path("/home/khanh/returnsaiyan-re")
DEVICE_ID = "10b3139c"
PACKAGE_NAME = "com.tony.lzcen.arm64"
ACTIVITY_NAME = f"{PACKAGE_NAME}/.AppActivity"
SERVER_BIN = REPO_ROOT / "game-server" / "bin" / "game-server"
UPDATER_SCRIPT = REPO_ROOT / "tools" / "mock_updater" / "updater.py"
DB_URL = "postgres://returnsaiyan:returnsaiyan_pass@127.0.0.1:5432/returnsaiyan_dev?sslmode=disable"
DIAG_DIR = REPO_ROOT / "evidence" / "diag"
DIAG_DIR.mkdir(parents=True, exist_ok=True)

SERVER_LOG = DIAG_DIR / "live_server.log"
UPDATER_LOG = DIAG_DIR / "live_updater.log"
LOGCAT_LOG = DIAG_DIR / "live_logcat.log"

def run_flow():
    print("--- 1. Setting up ADB reverse tunnels ---")
    subprocess.check_call(["adb", "-s", DEVICE_ID, "reverse", "tcp:30001", "tcp:30001"])
    subprocess.check_call(["adb", "-s", DEVICE_ID, "reverse", "tcp:30008", "tcp:30008"])

    print("--- 2. Starting background services ---")
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
        print("--- 3. Launching game client ---")
        subprocess.check_call(["adb", "-s", DEVICE_ID, "shell", "am", "start", "-n", ACTIVITY_NAME])
        time.sleep(6)

        sc1 = subprocess.check_output(["adb", "-s", DEVICE_ID, "exec-out", "screencap", "-p"])
        (DIAG_DIR / "flow_01_title.png").write_bytes(sc1)
        print("Captured flow_01_title.png")

        print("--- 4. Tapping 'Khách' at (940, 835) ---")
        subprocess.check_call(["adb", "-s", DEVICE_ID, "shell", "input", "tap", "940", "835"])
        time.sleep(4)

        sc2 = subprocess.check_output(["adb", "-s", DEVICE_ID, "exec-out", "screencap", "-p"])
        (DIAG_DIR / "flow_02_fuwuqi.png").write_bytes(sc2)
        print("Captured flow_02_fuwuqi.png")

        print("--- 5. Tapping server card entry at (1610, 276) ---")
        subprocess.check_call(["adb", "-s", DEVICE_ID, "shell", "input", "tap", "1610", "276"])
        time.sleep(3)

        sc3 = subprocess.check_output(["adb", "-s", DEVICE_ID, "exec-out", "screencap", "-p"])
        (DIAG_DIR / "flow_03_after_card.png").write_bytes(sc3)
        print("Captured flow_03_after_card.png")

        print("--- 6. Checking if Android Back key closes fuwuqi dialog ---")
        subprocess.check_call(["adb", "-s", DEVICE_ID, "shell", "input", "keyevent", "4"]) # KEYCODE_BACK
        time.sleep(3)

        sc4 = subprocess.check_output(["adb", "-s", DEVICE_ID, "exec-out", "screencap", "-p"])
        (DIAG_DIR / "flow_04_after_back.png").write_bytes(sc4)
        print("Captured flow_04_after_back.png")

        print("--- 7. Observing for 5 more seconds ---")
        time.sleep(5)

    finally:
        print("--- Cleaning up ---")
        subprocess.call(["adb", "-s", DEVICE_ID, "shell", "am", "force-stop", PACKAGE_NAME])
        lc_proc.terminate()
        lc_f.close()
        srv_proc.terminate()
        srv_f.close()
        up_proc.terminate()
        up_f.close()

if __name__ == "__main__":
    run_flow()
