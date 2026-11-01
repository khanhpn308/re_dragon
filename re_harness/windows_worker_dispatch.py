"""Dispatch one Windows game survey primitive from the existing WSL/Windows Harness.

Windows desktop interaction occurs only in scripts/windows_game_worker.ps1.
This module never starts a game, approves a task, or infers gameplay semantics.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess

ACTIONS = {"probe", "capture", "click", "fingerprint"}
PROCESS = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "windows_game_worker.ps1"


def convert_script_path(path, *, windows=None, runner=subprocess.run):
    """Obtain the Windows path to a known local script; no shell interpolation."""
    path = Path(path).resolve()
    if not path.is_file() or path.suffix.lower() != ".ps1":
        raise ValueError("Windows survey worker script is missing")
    if windows is None:
        windows = os.name == "nt"
    if windows:
        return str(path)
    try:
        result = runner(
            ["wslpath", "-w", str(path)], capture_output=True, text=True,
            timeout=5, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("WSL path conversion unavailable; run in WSL2 with wslpath") from exc
    value = (result.stdout or "").strip()
    # A script on /mnt/c/... maps to C:\\..., but a normal WSL2 repo under
    # /home/... maps to \\\\wsl.localhost\\<distro>\\home\\... instead.
    # Both are valid Windows paths. The old drive-only guard made every local
    # WSL ext4 checkout fail before PowerShell was invoked.
    drive_path = bool(re.match(r"^[A-Za-z]:\\", value))
    wsl_unc_path = bool(re.match(
        r"^\\\\(?:wsl\.localhost|wsl\$)\\[^\\/]+\\", value, re.IGNORECASE
    ))
    if result.returncode or not (drive_path or wsl_unc_path):
        raise RuntimeError(
            "Unable to convert worker script to a Windows path "
            "(expected drive path or WSL UNC path; wslpath exit="
            + str(result.returncode) + ")"
        )
    return value


def command(action, script_windows, *, process_name="DragonBall",
            x=None, y=None, evidence_directory=None, shell="powershell.exe"):
    if action not in ACTIONS:
        raise ValueError("Unsupported worker action")
    if not PROCESS.fullmatch(process_name):
        raise ValueError("Invalid process name")
    argv = [shell, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
            "-File", script_windows, "-Action", action, "-ProcessName", process_name]
    if evidence_directory:
        if not isinstance(evidence_directory, str) or any(
                s in evidence_directory for s in ("\n", "\r", '"', "'")):
            raise ValueError("Invalid Windows evidence directory")
        argv += ["-EvidenceDirectory", evidence_directory]
    if action == "click":
        if not (type(x) is int and type(y) is int and x >= 0 and y >= 0):
            raise ValueError("Click requires non-negative integer client coordinates")
        argv += ["-X", str(x), "-Y", str(y), "-EnableInput"]
    elif x is not None or y is not None:
        raise ValueError("Coordinates are allowed only for click")
    return argv


def parse_result(stdout, returncode):
    """Fail closed: no synthetic success for malformed/missing Windows evidence."""
    lines = [line.strip().lstrip("\ufeff") for line in (stdout or "").splitlines()
             if line.strip()]
    if not lines:
        return {"status": "BLOCKED", "error": "WINDOWS_WORKER_NO_JSON",
                "exit_code": returncode}
    try:
        payload = json.loads(lines[-1])
    except (TypeError, ValueError):
        return {"status": "BLOCKED", "error": "WINDOWS_WORKER_INVALID_JSON",
                "exit_code": returncode}
    if not isinstance(payload, dict) or payload.get("schema") != "re-dragon.windows-worker.v1":
        return {"status": "BLOCKED", "error": "WINDOWS_WORKER_WRONG_SCHEMA",
                "exit_code": returncode}
    if returncode != 0 or payload.get("status") != "OBSERVED":
        return {"status": "BLOCKED", "error": str(payload.get("error") or
                "WINDOWS_WORKER_FAILED")[:250], "exit_code": returncode}
    if payload.get("action") not in ACTIONS or type(payload.get("pid")) is not int:
        return {"status": "BLOCKED", "error": "WINDOWS_WORKER_INVALID_PROVENANCE",
                "exit_code": returncode}
    payload["evidence_status"] = "AGENT_OBSERVED"
    payload["acceptance_status"] = "NOT_VERIFIED"
    return payload


def run_once(action, *, script=SCRIPT, process_name="DragonBall", x=None,
             y=None, evidence_directory=None, shell="powershell.exe",
             path_converter=convert_script_path, runner=subprocess.run):
    script_windows = path_converter(script)
    argv = command(action, script_windows, process_name=process_name, x=x, y=y,
                   evidence_directory=evidence_directory, shell=shell)
    try:
        completed = runner(argv, capture_output=True, text=True,
                           timeout=60, check=False)
        return parse_result(completed.stdout, completed.returncode)
    except subprocess.TimeoutExpired:
        return {"status": "BLOCKED", "error": "WINDOWS_PRIMITIVE_TIMEOUT",
                "note": "Only this single Windows action timed out; Harness task remains checkpointed"}
    except OSError as exc:
        return {"status": "BLOCKED", "error": "WINDOWS_INTEROP_UNAVAILABLE",
                "note": type(exc).__name__}


def main(argv=None):
    parser = argparse.ArgumentParser(description="One Windows UI survey primitive")
    parser.add_argument("action", choices=sorted(ACTIONS))
    parser.add_argument("--process-name", default="DragonBall")
    parser.add_argument("--x", type=int)
    parser.add_argument("--y", type=int)
    parser.add_argument("--evidence-directory", help="Windows absolute path; default LOCALAPPDATA")
    parser.add_argument("--shell", default="powershell.exe")
    args = parser.parse_args(argv)
    try:
        outcome = run_once(args.action, process_name=args.process_name,
                           x=args.x, y=args.y, shell=args.shell,
                           evidence_directory=args.evidence_directory)
    except (ValueError, RuntimeError) as exc:
        outcome = {"status": "BLOCKED", "error": str(exc)[:250]}
    print(json.dumps(outcome, ensure_ascii=False))
    return 0 if outcome.get("status") == "OBSERVED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
