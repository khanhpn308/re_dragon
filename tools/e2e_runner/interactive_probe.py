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
DIAG_DIR = REPO_ROOT / "evidence" / "diag" / "probe"
DIAG_DIR.mkdir(parents=True, exist_ok=True)

SERVER_LOG = DIAG_DIR / "server.log"
UPDATER_LOG = DIAG_DIR / "updater.log"
LOGCAT_LOG = DIAG_DIR / "logcat.log"

def run_probe():
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
        print("Launching client...")
        subprocess.check_call(["adb", "-s", DEVICE_ID, "shell", "am", "start", "-n", ACTIVITY_NAME])
        time.sleep(6)

        # 1. Tap Khách
        print("Tapping 'Khách' at (940, 835)...")
        subprocess.check_call(["adb", "-s", DEVICE_ID, "shell", "input", "tap", "940", "835"])
        time.sleep(4)

        base_bytes = subprocess.check_output(["adb", "-s", DEVICE_ID, "exec-out", "screencap", "-p"])
        base_path = DIAG_DIR / "00_fuwuqi_base.png"
        base_path.write_bytes(base_bytes)
        base_img = Image.open(base_path).convert("RGB")
        print(f"Captured base screen ({len(base_bytes)} bytes)")

        # Targets to probe
        targets = [
            ("tab1_recent", 550, 200),
            ("tab2_zone", 550, 320),
            ("card_body", 1150, 260),
            ("card_left", 900, 260),
            ("card_btn", 1610, 276),
            ("last_login_panel", 1320, 380),
            ("center_screen", 1200, 540),
            ("bottom_center", 1200, 950),
            ("top_right_btn1", 1985, 120),
            ("top_right_btn2", 1985, 200),
            ("top_left_corner", 300, 100),
            ("outside_left", 150, 540),
            ("outside_right", 2250, 540),
        ]

        current_img = base_img
        for name, x, y in targets:
            print(f"Probing target '{name}' at ({x}, {y})...")
            subprocess.check_call(["adb", "-s", DEVICE_ID, "shell", "input", "tap", str(x), str(y)])
            time.sleep(2)
            new_bytes = subprocess.check_output(["adb", "-s", DEVICE_ID, "exec-out", "screencap", "-p"])
            new_path = DIAG_DIR / f"probe_{name}.png"
            new_path.write_bytes(new_bytes)
            new_img = Image.open(new_path).convert("RGB")

            diff = ImageChops.difference(current_img, new_img)
            bbox = diff.getbbox()
            if bbox:
                print(f"  ===> SCREEN CHANGED on '{name}'! BBox: {bbox}")
                current_img = new_img
                # Check server log to see if any packet was emitted!
                with open(SERVER_LOG) as f:
                    content = f.read()
                    if "OpcodeEnterWorld" in content or "0x50" in content or "enter" in content.lower():
                        print(f"  ===> SERVER LOG SHOWS ACTIVITY! {content.strip().splitlines()[-3:]}")
            else:
                print(f"  (no visual change)")

    finally:
        subprocess.call(["adb", "-s", DEVICE_ID, "shell", "am", "force-stop", PACKAGE_NAME])
        lc_proc.terminate()
        lc_f.close()
        srv_proc.terminate()
        srv_f.close()
        up_proc.terminate()
        up_f.close()

if __name__ == "__main__":
    run_probe()
