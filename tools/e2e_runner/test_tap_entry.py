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

        sc1 = subprocess.check_output(["adb", "-s", DEVICE_ID, "exec-out", "screencap", "-p"])
        (DIAG_DIR / "01_title.png").write_bytes(sc1)
        print("Captured 01_title.png")

        print("Tapping 'Khách' at (940, 835)...")
        subprocess.check_call(["adb", "-s", DEVICE_ID, "shell", "input", "tap", "940", "835"])
        time.sleep(4)

        sc2 = subprocess.check_output(["adb", "-s", DEVICE_ID, "exec-out", "screencap", "-p"])
        (DIAG_DIR / "02_fuwuqi.png").write_bytes(sc2)
        print("Captured 02_fuwuqi.png")

        print("Tapping server banner / entry at (1320, 270)...")
        subprocess.check_call(["adb", "-s", DEVICE_ID, "shell", "input", "tap", "1320", "270"])
        time.sleep(4)

        sc3 = subprocess.check_output(["adb", "-s", DEVICE_ID, "exec-out", "screencap", "-p"])
        (DIAG_DIR / "03_post_tap.png").write_bytes(sc3)
        print("Captured 03_post_tap.png")

        print("Tapping potential enter/start button at (1200, 850)...")
        subprocess.check_call(["adb", "-s", DEVICE_ID, "shell", "input", "tap", "1200", "850"])
        time.sleep(4)

        sc4 = subprocess.check_output(["adb", "-s", DEVICE_ID, "exec-out", "screencap", "-p"])
        (DIAG_DIR / "04_world_or_char.png").write_bytes(sc4)
        print("Captured 04_world_or_char.png")

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
