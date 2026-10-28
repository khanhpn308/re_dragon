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

SERVER_LOG = DIAG_DIR / "server.log"
UPDATER_LOG = DIAG_DIR / "updater.log"
LOGCAT_LOG = DIAG_DIR / "logcat.log"

def test():
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
        print("Launching client app...")
        subprocess.check_call(["adb", "-s", DEVICE_ID, "shell", "am", "start", "-n", ACTIVITY_NAME])
        time.sleep(6)

        # 1. Tap Khách at (940, 835)
        print("1. Tapping 'Khách' at (940, 835)...")
        subprocess.check_call(["adb", "-s", DEVICE_ID, "shell", "input", "tap", "940", "835"])
        time.sleep(4)

        # 2. Tap server card at (1610, 276)
        print("2. Tapping server card at (1610, 276)...")
        subprocess.check_call(["adb", "-s", DEVICE_ID, "shell", "input", "tap", "1610", "276"])
        time.sleep(2)

        # 3. Tap close button at (1920, 130)
        print("3. Tapping close button at (1920, 130)...")
        subprocess.check_call(["adb", "-s", DEVICE_ID, "shell", "input", "tap", "1920", "130"])
        time.sleep(2)

        sc_title_return = subprocess.check_output(["adb", "-s", DEVICE_ID, "exec-out", "screencap", "-p"])
        (DIAG_DIR / "title_after_close.png").write_bytes(sc_title_return)
        print("Captured title_after_close.png")

        # 4. Tap center of Title Screen at (1200, 540) to enter game
        print("4. Tapping center of Title Screen at (1200, 540) to enter game...")
        subprocess.check_call(["adb", "-s", DEVICE_ID, "shell", "input", "tap", "1200", "540"])
        
        # 5. Wait 8s and observe
        for i in range(8):
            time.sleep(1)
            print(f"Waiting [{i+1}/8]...")

        sc_after_enter = subprocess.check_output(["adb", "-s", DEVICE_ID, "exec-out", "screencap", "-p"])
        (DIAG_DIR / "after_enter.png").write_bytes(sc_after_enter)
        print("Captured after_enter.png")

    finally:
        subprocess.call(["adb", "-s", DEVICE_ID, "shell", "am", "force-stop", PACKAGE_NAME])
        lc_proc.terminate()
        lc_f.close()
        srv_proc.terminate()
        srv_f.close()
        up_proc.terminate()
        up_f.close()

if __name__ == "__main__":
    test()
