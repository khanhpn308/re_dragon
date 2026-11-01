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
    """Distinguish Watchdog session identity from another local AGY session."""
    data = read_cache(workspace)
    if fresh_for_watchdog(workspace, data):
        return ("RE Dragon — /account\n"
                f"Tài khoản phiên Watchdog: {data.get('email') or 'UNKNOWN'}\n"
                f"Gói: {data.get('plan_tier') or 'UNKNOWN'}\n"
                f"Model: {data.get('model') or 'UNKNOWN'}\n"
                "Nguồn: statusLine cùng conversation_id, mới trong 15 phút.\n"
                "Không phải xác thực đăng nhập trực tuyến.")
    if (data and isinstance(data.get("observed_at"), (int, float)) and
            0 <= time.time() - data["observed_at"] <= MAX_CACHE_AGE and
            data.get("email") not in (None, "", "UNKNOWN")):
        return ("RE Dragon — /account\n"
                "Tài khoản phiên Watchdog: UNKNOWN\n"
                f"Tài khoản AGY cục bộ (phiên khác): {data['email']}\n"
                f"Gói: {data.get('plan_tier') or 'UNKNOWN'}\n"
                "Nguồn: statusLine CLI tương tác; KHÔNG xác minh tài khoản "
                "đang chạy trong Watchdog.")
    return ("RE Dragon — /account\n"
            "Tài khoản phiên Watchdog: UNKNOWN\n"
            "Chưa có statusLine telemetry mới. Hook này chạy trong CLI tương tác; "
            "headless có thể không phát dữ liệu.\n"
            "Thiết lập: python3 -m re_harness.agy_telemetry install")


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


def _write_json_private(path, data):
    path = Path(path)
    fd, tmp = tempfile.mkstemp(prefix=".re-dragon-", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            os.fchmod(output.fileno(), 0o600)
            json.dump(data, output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _telemetry_command(workspace, *, action, original_config=None):
    pieces = [sys.executable, str(Path(__file__).resolve()), action,
              "--workspace", str(Path(workspace).resolve())]
    if original_config is not None:
        pieces += ["--original-config", str(original_config)]
    return " ".join(shlex.quote(piece) for piece in pieces)


def install(workspace, *, chain_existing=False):
    """Opt-in statusLine installation; preserve existing scripts via explicit chaining."""
    settings = Path.home() / ".gemini" / "antigravity-cli" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    try:
        data = json.loads(settings.read_text(encoding="utf-8")) if settings.exists() else {}
    except ValueError:
        raise ValueError("settings.json không hợp lệ, không sửa file") from None
    if not isinstance(data, dict):
        raise ValueError("settings.json không phải JSON object; không sửa file")
    original = data.get("statusLine")
    if original is None:
        if chain_existing:
            raise ValueError("Không có statusLine để nối; dùng lệnh install thông thường")
        data["statusLine"] = {
            "type": "command",
            "command": _telemetry_command(workspace, action="capture"),
            "stack_with_default": True,
        }
    else:
        if not chain_existing:
            raise ValueError("Đã có statusLine; dùng install --chain-existing để giữ hook cũ")
        if not isinstance(original, dict):
            raise ValueError("statusLine không phải object; không sửa file")
        command = original.get("command")
        if (original.get("type", "command") != "command" or
                original.get("enabled", True) is False or
                not isinstance(command, str) or not command.strip() or
                len(command) > 4096):
            raise ValueError("statusLine hiện tại không khả dụng; không thay đổi")
        if "agy_telemetry.py" in command or "re_harness.agy_telemetry" in command:
            return "statusLine đã chứa telemetry hook; không cài lặp lại."
        original_config = settings.parent / "re-dragon-original-statusline.json"
        if original_config.exists():
            # Never overwrite prior backup or create recursive wrappers.
            raise ValueError("Đã có bản gốc statusLine từ lần nối trước; cần kiểm tra thủ công")
        command_to_chain = _telemetry_command(
            workspace, action="relay", original_config=original_config)
        new_line = dict(original)
        new_line["command"] = command_to_chain
        data["statusLine"] = new_line
    if settings.exists():
        backup = settings.with_name(settings.name + ".before-re-dragon")
        if backup.exists():
            backup = settings.with_name(settings.name + ".before-re-dragon-2")
        if backup.exists():
            raise ValueError("Hai bản sao lưu đã tồn tại; dừng để tránh ghi đè")
        shutil.copy2(settings, backup)
        os.chmod(backup, 0o600)
    if original is not None:
        _write_json_private(original_config, {"command": command})
    _write_json_private(settings, data)
    return ("Đã nối telemetry và giữ nguyên statusLine cũ."
            if original is not None else
            "Đã cài statusLine mới.")


def relay(workspace, original_config, raw, *, runner=subprocess.run):
    """Pass original JSON to prior renderer; forward its unchanged stdout."""
    path = Path(original_config)
    if path.is_symlink() or (path.stat().st_mode & 0o077):
        raise ValueError("Original hook configuration is not private")
    prior = json.loads(path.read_text(encoding="utf-8"))
    command = prior.get("command") if isinstance(prior, dict) else None
    if not isinstance(command, str) or not command.strip():
        raise ValueError("Missing original statusLine command")
    try:
        result = runner(["sh", "-c", command], input=raw, text=True,
                        capture_output=True, timeout=3, check=False)
        original_output = (result.stdout or "")[:8192]
    except (OSError, subprocess.TimeoutExpired):
        original_output = ""
    try:
        capture(workspace, json.loads(raw))
    except (ValueError, TypeError):
        pass
    return original_output


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("capture", "install", "relay"))
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--chain-existing", action="store_true")
    parser.add_argument("--original-config")
    args = parser.parse_args(argv)
    if args.action == "install":
        try:
            print(install(args.workspace, chain_existing=args.chain_existing))
            return 0
        except (OSError, ValueError) as exc:
            print("Không cài telemetry: " + str(exc), file=sys.stderr)
            return 2
    raw = sys.stdin.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        return 2
    if args.action == "relay":
        if not args.original_config:
            return 2
        try:
            sys.stdout.write(relay(args.workspace, args.original_config, raw))
        except (OSError, ValueError):
            return 2
        return 0
    try:
        capture(args.workspace, json.loads(raw))
    except (ValueError, TypeError):
        return 2
    print("RS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
