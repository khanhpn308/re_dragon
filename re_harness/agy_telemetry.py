"""Read-only Antigravity CLI account/quota telemetry for RE Dragon Telegram.

Account identity comes only from official AGY statusLine JSON for the pinned
conversation. No credential/keyring/token inspection. No raw CLI output logged.
"""
from __future__ import annotations

import argparse
import json
import math
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime

CACHE_NAME = "agy-telemetry.json"
MAX_CACHE_AGE = 900
MAX_BYTES = 65536
EMAIL = re.compile(r"^[^@\s]{1,100}@[a-zA-Z0-9.-]{3,100}$")
BUCKET = re.compile(r"^[A-Za-z0-9_-]{1,60}$")
VERSION = re.compile(r"(\d+)\.(\d+)\.(\d+)")


def cache_path(workspace):
    return Path(workspace).resolve() / ".re_harness" / CACHE_NAME


def mask_email(value):
    if not isinstance(value, str) or not EMAIL.fullmatch(value):
        return "UNKNOWN"
    name, domain = value.split("@", 1)
    return name[:2] + "***" + (name[-1:] if len(name) > 3 else "") + "@" + domain.lower()


def clean(value, limit=40):
    if not isinstance(value, str):
        return ""
    return "".join(ch for ch in value[:limit] if ch.isalnum() or ch in " ._-()/")


def parse_status_quota(raw):
    result = []
    if not isinstance(raw, dict):
        return result
    for key, row in list(raw.items())[:16]:
        if not isinstance(key, str) or not BUCKET.fullmatch(key) or not isinstance(row, dict):
            continue
        remaining = row.get("remaining_fraction")
        if (isinstance(remaining, bool) or not isinstance(remaining, (int, float))
                or not math.isfinite(remaining) or not 0 <= remaining <= 1):
            continue
        reset = row.get("reset_time")
        result.append({"name": key, "remaining": round(100 * remaining, 1),
                       "reset": reset if isinstance(reset, str) and len(reset) <= 40 else ""})
    return result


def capture(workspace, payload):
    """Capture only allowlisted fields from official CLI statusLine stdin."""
    if not isinstance(payload, dict) or payload.get("product") != "antigravity":
        return False
    session = payload.get("conversation_id") or payload.get("session_id")
    if (not isinstance(session, str) or not 1 <= len(session) <= 128
            or not re.fullmatch(r"[a-zA-Z0-9_-]+", session)):
        return False
    model = payload.get("model")
    record = {
        "source": "AGY_STATUS_LINE",
        "observed_at": time.time(),
        "conversation_id": session,
        "email": mask_email(payload.get("email")),
        "plan_tier": clean(payload.get("plan_tier")),
        "agent_state": clean(payload.get("agent_state")),
        "model": clean(model.get("display_name")) if isinstance(model, dict) else "",
        "quota": parse_status_quota(payload.get("quota")),
    }
    dest = cache_path(workspace)
    dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    os.chmod(dest.parent, 0o700)
    fd, temp = tempfile.mkstemp(prefix=".agy-telemetry-", dir=str(dest.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump(record, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, dest)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return True


def read_cache(workspace):
    file = cache_path(workspace)
    try:
        if file.is_symlink() or (file.stat().st_mode & 0o077):
            return None
        result = json.loads(file.read_text(encoding="utf-8"))
        if isinstance(result, dict) and result.get("source") == "AGY_STATUS_LINE":
            return result
    except (FileNotFoundError, OSError, ValueError):
        pass
    return None


def fresh_for_watchdog(workspace, data):
    if not data or not isinstance(data.get("observed_at"), (int, float)):
        return False
    if not 0 <= time.time() - data["observed_at"] <= MAX_CACHE_AGE:
        return False
    try:
        watcher = json.loads((Path(workspace).resolve() / ".re_harness" /
                              "quota-watchdog.json").read_text(encoding="utf-8"))
        return bool(watcher.get("conversation_id") and
                    watcher["conversation_id"] == data.get("conversation_id"))
    except (OSError, ValueError, AttributeError):
        return False


def account_text(workspace):
    data = read_cache(workspace)
    if not fresh_for_watchdog(workspace, data):
        return ("RE Dragon — /account\nTài khoản: UNKNOWN\n"
                "Chưa có statusLine telemetry mới khớp phiên Watchdog.\n"
                "Thiết lập: python3 -m re_harness.agy_telemetry install")
    return ("RE Dragon — /account\n"
            f"Tài khoản: {data.get('email') or 'UNKNOWN'}\n"
            f"Gói: {data.get('plan_tier') or 'UNKNOWN'}\n"
            f"Model: {data.get('model') or 'UNKNOWN'}\n"
            "Nguồn: AGY statusLine gần nhất; không xác nhận đăng nhập trực tuyến.")


def format_buckets(rows, source):
    if not rows:
        return "RE Dragon — /usage\nQuota: UNKNOWN (không có dữ liệu)"
    lines = [f"RE Dragon — /usage ({source})"]
    for row in rows[:12]:
        line = f"{clean(row['name'], 65)}: còn {row['remaining']:.1f}%"
        reset = row.get("reset")
        if isinstance(reset, str) and len(reset) <= 40:
            try:
                datetime.fromisoformat(reset.replace("Z", "+00:00"))
            except ValueError:
                pass
            else:
                line += f" | reset {reset}"
        lines.append(line)
    return "\n".join(lines)[:3200]


def parse_native_usage(raw):
    try:
        data = json.loads(raw)
        if data.get("status") != "SUCCESS" or data.get("command", {}).get("name") != "usage":
            return []
        if data.get("num_turns") not in (None, 0):
            return []
        groups = data["command"]["data"]["groups"]
        if not isinstance(groups, list):
            return []
    except (ValueError, TypeError, KeyError, AttributeError):
        return []
    results = []
    for group in groups[:10]:
        if not isinstance(group, dict) or not isinstance(group.get("buckets"), list):
            continue
        label = clean(group.get("name") or group.get("display_name"), 24)
        for b in group["buckets"][:10]:
            if not isinstance(b, dict):
                continue
            key = b.get("window") or b.get("id")
            fraction = b.get("remaining_fraction")
            if (not isinstance(key, str) or isinstance(fraction, bool)
                    or not isinstance(fraction, (int, float)) or not math.isfinite(fraction)
                    or not 0 <= fraction <= 1):
                continue
            results.append({"name": label + " " + clean(key, 20),
                            "remaining": round(100 * fraction, 1),
                            "reset": b.get("reset_time")})
    return results


def usage_text(workspace, *, running=False, runner=subprocess.run, which=shutil.which):
    data = read_cache(workspace)
    if fresh_for_watchdog(workspace, data) and data.get("quota"):
        return format_buckets(data["quota"], "AGY statusLine")
    if running:
        return ("RE Dragon — /usage\nQuota: UNKNOWN. Agent đang chạy;"
                " không mở phiên CLI thứ hai. Cần statusLine telemetry của đúng phiên.")
    binary = which("agy")
    if not binary:
        return "RE Dragon — /usage\nQuota: UNKNOWN (agy không có trong PATH)"
    try:
        ver = runner([binary, "--version"], capture_output=True, text=True,
                     stdin=subprocess.DEVNULL, timeout=5, check=False)
        match = VERSION.search(ver.stdout or "")
        if ver.returncode or not match or tuple(map(int, match.groups())) < (1, 1, 11):
            return "RE Dragon — /usage\nQuota: UNKNOWN (CLI quá cũ hoặc không rõ phiên bản)"
        result = runner([binary, "-p", "/usage", "--output-format", "json"],
                        capture_output=True, text=True, stdin=subprocess.DEVNULL,
                        timeout=18, check=False)
        if result.returncode or len(result.stdout or "") > MAX_BYTES:
            return "RE Dragon — /usage\nQuota: UNKNOWN (truy vấn CLI thất bại)"
        rows = parse_native_usage(result.stdout)
    except (OSError, subprocess.TimeoutExpired):
        return "RE Dragon — /usage\nQuota: UNKNOWN (CLI không phản hồi)"
    return format_buckets(rows, "AGY /usage")


def install(workspace):
    """Explicit one-time opt-in; never overwrite the user's existing statusLine."""
    settings = Path.home() / ".gemini" / "antigravity-cli" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(settings.read_text(encoding="utf-8")) if settings.exists() else {}
    except ValueError:
        raise ValueError("settings.json không hợp lệ, không sửa file") from None
    if not isinstance(data, dict) or "statusLine" in data:
        raise ValueError("Đã có statusLine hoặc settings không hợp lệ; không ghi đè")
    command = (shlex.quote(sys.executable) + " " + shlex.quote(str(Path(__file__).resolve()))
               + " capture --workspace " + shlex.quote(str(Path(workspace).resolve())))
    data["statusLine"] = {"type": "command", "command": command, "stack_with_default": True}
    if settings.exists():
        backup = settings.with_name(settings.name + ".before-re-dragon")
        if not backup.exists():
            shutil.copy2(settings, backup)
    fd, temp = tempfile.mkstemp(prefix=".agy-settings-", dir=str(settings.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            os.fchmod(handle.fileno(), 0o600)
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp, settings)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return "Đã thiết lập statusLine cho phiên agy khởi động hoặc reload sau này."


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("capture", "install"))
    parser.add_argument("--workspace", default=".")
    args = parser.parse_args(argv)
    if args.action == "install":
        print(install(args.workspace))
        return 0
    raw = sys.stdin.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        return 2
    try:
        capture(args.workspace, json.loads(raw))
    except ValueError:
        return 2
    print("RS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
