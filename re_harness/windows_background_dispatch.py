"""Experimental background Unity window survey; no foreground activation.

PrintWindow may fail for GPU rendering; PostMessage may be ignored by Unity.
Never equate API success or image hash changes with gameplay acceptance.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

from . import windows_worker_dispatch as w

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "windows_background_worker.ps1"
ACTIONS = {"probe", "capture", "click"}


def command(action, script, *, process_name="DragonBall", x=None, y=None,
            enable_input=False, shell="powershell.exe"):
    if action not in ACTIONS:
        raise ValueError("Unsupported background action")
    if not w.PROCESS.fullmatch(process_name):
        raise ValueError("Invalid process")
    argv = [shell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-File", str(script), "-Action", action, "-ProcessName", process_name]
    if action == "click":
        if not enable_input:
            raise ValueError("Background click requires explicit --enable-input")
        if not (type(x) is int and type(y) is int and
                0 <= x <= 32767 and 0 <= y <= 32767):
            raise ValueError("Background click needs valid client coordinates")
        argv += ["-X", str(x), "-Y", str(y), "-EnableInput"]
    elif x is not None or y is not None or enable_input:
        raise ValueError("Input parameters only permitted for click")
    return argv


def parse_result(stdout, returncode, action):
    lines = [s.strip().lstrip("\ufeff") for s in (stdout or "").splitlines() if s.strip()]
    if not lines:
        return {"status": "BLOCKED", "error": "NO_BACKGROUND_WORKER_RESULT",
                "input_dispatched": None if action == "click" else False}
    try:
        data = json.loads(lines[-1])
    except (ValueError, TypeError):
        return {"status": "BLOCKED", "error": "INVALID_BACKGROUND_WORKER_JSON",
                "input_dispatched": None if action == "click" else False}
    if (not isinstance(data, dict) or data.get("schema") != "re-dragon.windows-background.v1"
            or data.get("action") != action):
        return {"status": "BLOCKED", "error": "INVALID_BACKGROUND_WORKER_SCHEMA",
                "input_dispatched": None if action == "click" else False}
    base = {
        "action": action, "status": "BLOCKED",
        "input_dispatched": data.get("input_dispatched") if
            isinstance(data.get("input_dispatched"), bool) else None,
        "gameplay_verified": False,
        "background_method": "PrintWindow/PostMessage",
    }
    if returncode != 0 or data.get("status") != "OBSERVED":
        base["error"] = str(data.get("error") or "BACKGROUND_WORKER_BLOCKED")[:240]
        return base
    if type(data.get("pid")) is not int or data.get("gameplay_verified") is not False:
        base["error"] = "BAD_BACKGROUND_OBSERVATION"
        return base
    if action in {"capture", "click"}:
        before = data.get("before")
        if (not isinstance(before, dict) or
                not isinstance(before.get("sha256"), str) or
                len(before["sha256"]) != 64):
            base["error"] = "BACKGROUND_CAPTURE_EVIDENCE_MISSING"
            return base
    if action == "click":
        after = data.get("after")
        if (not isinstance(after, dict) or
                not isinstance(after.get("sha256"), str) or
                len(after["sha256"]) != 64 or
                data.get("input_dispatched") is not True):
            base["error"] = "BACKGROUND_CLICK_EVIDENCE_INCOMPLETE"
            return base
    data["status"] = "OBSERVED"
    data["evidence_status"] = "BACKGROUND_EXPERIMENT_ONLY"
    data["acceptance_status"] = "NOT_VERIFIED"
    data["gameplay_verified"] = False
    return data


def run_once(action, *, script=SCRIPT, process_name="DragonBall", x=None, y=None,
             enable_input=False, runner=subprocess.run,
             path_converter=w.convert_script_path):
    if action not in ACTIONS:
        raise ValueError("Unsupported action")
    argv = command(action, path_converter(script), process_name=process_name,
                   x=x, y=y, enable_input=enable_input)
    try:
        outcome = runner(argv, capture_output=True, text=True,
                         timeout=60, check=False)
    except subprocess.TimeoutExpired:
        return {"status": "BLOCKED", "error": "BACKGROUND_PRIMITIVE_TIMEOUT",
                "input_dispatched": None if action == "click" else False,
                "gameplay_verified": False}
    except OSError:
        return {"status": "BLOCKED", "error": "WINDOWS_INTEROP_UNAVAILABLE",
                "input_dispatched": None if action == "click" else False,
                "gameplay_verified": False}
    return parse_result(outcome.stdout, outcome.returncode, action)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Unity background API compatibility pilot")
    parser.add_argument("action", choices=sorted(ACTIONS))
    parser.add_argument("--x", type=int)
    parser.add_argument("--y", type=int)
    parser.add_argument("--enable-input", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = run_once(args.action, x=args.x, y=args.y,
                          enable_input=args.enable_input)
    except (ValueError, RuntimeError) as exc:
        result = {"status": "BLOCKED", "error": str(exc)[:240],
                  "gameplay_verified": False}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("status") == "OBSERVED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
