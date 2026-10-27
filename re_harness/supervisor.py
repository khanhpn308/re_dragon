"""Independent Process Supervisor for RE Dragon v0.8.

Bridges OS supervisors (systemd, Windows Task Scheduler) with the Quota Watchdog.
Ensures single-runner exclusivity (preventing conflicts with tmux), differentiates
intentional stops (COMPLETE, BLOCKED, NEEDS_USER, PAUSED) from unexpected crashes,
and maintains robust heartbeat telemetry distinguishing liveness from progress.
"""
from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

from . import incidents, quota_guard, recovery, runtime_state

EXIT_COMPLETE = 0
EXIT_CRASH = 1
EXIT_BLOCKED = 10
EXIT_NEEDS_USER = 11
EXIT_PAUSED = 12

INTENTIONAL_EXITS = {EXIT_COMPLETE, EXIT_BLOCKED, EXIT_NEEDS_USER, EXIT_PAUSED}
MAX_SUPERVISOR_CRASH_RESTARTS = 5


def is_watchdog_locked(workspace: Union[str, Path]) -> bool:
    """Convenience helper to check if watchdog is locked in workspace."""
    return Supervisor(workspace).is_watchdog_locked()


class Supervisor:
    def __init__(self, workspace: Path | str, harness_state_dir: Optional[Path | str] = None, binary: str = "agy"):
        self.workspace = Path(workspace).expanduser().resolve()
        self.watch_dir = self.workspace / ".re_harness"
        self.watch_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.harness_state_dir = Path(harness_state_dir).expanduser().resolve() if harness_state_dir else self.workspace / ".re_harness_mvp"
        self.state_file = self.watch_dir / "quota-watchdog.json"
        self.watchdog_lock_file = self.watch_dir / "quota-watchdog.lock"
        self.supervisor_lock_file = self.watch_dir / "supervisor.lock"
        self.binary = binary
        self.active_child: Optional[subprocess.Popen] = None
        self._stop_requested = False
        self._consecutive_crashes = 0

    def is_watchdog_locked(self) -> bool:
        """Check if Watchdog is already running (e.g. inside tmux or standalone)."""
        if not self.watchdog_lock_file.exists():
            return False
        with self.watchdog_lock_file.open("a+") as handle:
            try:
                fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(handle, fcntl.LOCK_UN)
                return False
            except (BlockingIOError, OSError):
                return True

    def acquire_supervisor_lock(self):
        """Ensure only one supervisor runs per workspace."""
        handle = self.supervisor_lock_file.open("a+")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError) as exc:
            handle.close()
            raise RuntimeError("Another supervisor instance is already active for this workspace") from exc
        return handle

    def _handle_term(self, signum, frame):
        self._stop_requested = True
        if self.active_child and self.active_child.poll() is None:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self.active_child.pid, signal.SIGTERM)
        sys.exit(0)

    def status(self) -> Dict[str, Any]:
        """Inspect supervisor and watchdog status without locking."""
        watchdog_running = self.is_watchdog_locked()
        live = runtime_state.snapshot(self.watch_dir / "agent-runtime.json")
        state = {}
        if self.state_file.exists():
            try:
                state = json.loads(self.state_file.read_text(encoding="utf8"))
            except Exception:
                pass

        # Inspect task stall from Harness SQLite
        task_stall_seconds = None
        last_task_key = None
        if self.harness_state_dir.exists() and state.get("project_id"):
            try:
                from . import core
                with core.database(self.harness_state_dir) as db:
                    row = db.execute(
                        "SELECT task_key, updated_at FROM auto_tasks WHERE project_id=? ORDER BY updated_at DESC LIMIT 1",
                        (state["project_id"],),
                    ).fetchone()
                    if row:
                        last_task_key = row["task_key"]
                        # updated_at is ISO timestamp or string
                        try:
                            import datetime as dt
                            t = dt.datetime.fromisoformat(row["updated_at"]).timestamp()
                            task_stall_seconds = max(0, int(time.time() - t))
                        except Exception:
                            pass
            except Exception:
                pass

        return {
            "supervisor_mode": "ACTIVE" if not watchdog_running else "STANDBY (external watchdog running)",
            "watchdog_locked": watchdog_running,
            "watchdog_status": state.get("status", "NOT_CONFIGURED"),
            "project_id": state.get("project_id"),
            "conversation_id": state.get("conversation_id"),
            "last_reason": state.get("last_reason"),
            "agent_live": live,
            "last_task_key": last_task_key,
            "task_stall_seconds": task_stall_seconds,
            "heartbeat_is_progress_proof": False,
        }

    def run(self) -> int:
        """Main supervisor loop. Designed for systemd or Windows Task Scheduler."""
        lock_handle = self.acquire_supervisor_lock()
        signal.signal(signal.SIGTERM, self._handle_term)
        signal.signal(signal.SIGINT, self._handle_term)

        # Fail closed immediately if workspace binding is invalid or project is not active
        verify_workspace_binding(self.workspace, harness_state_dir=self.harness_state_dir)

        try:
            while not self._stop_requested:
                # 1. Check if Watchdog is already running in tmux or externally
                if self.is_watchdog_locked():
                    # Sleep and monitor; do not double-run
                    time.sleep(15)
                    continue

                # 2. Check current state in quota-watchdog.json
                state = {}
                if self.state_file.exists():
                    try:
                        state = json.loads(self.state_file.read_text(encoding="utf8"))
                    except Exception:
                        state = {}

                current_status = state.get("status")

                # If intentional stop, exit cleanly with appropriate code to inform systemd
                if current_status == "COMPLETE":
                    return EXIT_COMPLETE
                if current_status == "BLOCKED":
                    return EXIT_BLOCKED
                if current_status == "NEEDS_USER":
                    return EXIT_NEEDS_USER
                if current_status == "PAUSED":
                    return EXIT_PAUSED

                # 3. Launch Watchdog process
                cmd = [
                    sys.executable,
                    "-m",
                    "re_harness.quota_watchdog",
                    "run",
                    "--workspace",
                    str(self.workspace),
                    "--harness-state-dir",
                    str(self.harness_state_dir),
                    "--binary",
                    self.binary,
                ]

                proc = subprocess.Popen(cmd, cwd=self.workspace, start_new_session=True)
                self.active_child = proc

                exit_code = proc.wait()
                self.active_child = None

                if self._stop_requested:
                    return 0

                # Differentiate intentional stops from unexpected crashes
                if exit_code in INTENTIONAL_EXITS:
                    # Clean intentional termination
                    self._consecutive_crashes = 0
                    return exit_code

                # Non-zero crash
                self._consecutive_crashes += 1
                incidents.create_or_update_incident(
                    self.workspace,
                    state.get("project_id"),
                    "AGENT_CRASH",
                    f"Watchdog process crashed with exit code {exit_code} (crash #{self._consecutive_crashes})",
                    severity="ERROR",
                    details={"exit_code": exit_code, "consecutive_crashes": self._consecutive_crashes},
                )

                if self._consecutive_crashes >= MAX_SUPERVISOR_CRASH_RESTARTS:
                    incidents.create_or_update_incident(
                        self.workspace,
                        state.get("project_id"),
                        "AGENT_CRASH",
                        f"Supervisor crash restart budget ({MAX_SUPERVISOR_CRASH_RESTARTS}) exhausted; stopping supervisor",
                        severity="CRITICAL",
                    )
                    return EXIT_CRASH

                # Bounded backoff before restart
                delay = recovery.calculate_backoff(self._consecutive_crashes, base_delay=15.0, max_delay=300.0)
                time.sleep(delay)

            return 0
        finally:
            with contextlib.suppress(Exception):
                fcntl.flock(lock_handle, fcntl.LOCK_UN)
                lock_handle.close()


class WorkspaceBindingError(Exception):
    """Raised when workspace binding validation fails."""


def verify_workspace_binding(
    workspace: Path | str,
    expected_project_id: Optional[str] = None,
    harness_state_dir: Optional[Path | str] = None,
) -> Dict[str, Any]:
    """Verify that a workspace is a valid, active RE Dragon workspace.

    Guarantees:
    - Path exists and is a directory.
    - .re_harness/quota-watchdog.json exists and is valid.
    - Pinned project_id exists in SQLite auto_projects and status in ACTIVE.
    - Expected project_id matches if provided.
    - Resolves reliable python executable.
    """
    ws = Path(workspace).expanduser().resolve()
    if not ws.is_dir():
        raise WorkspaceBindingError(f"Workspace directory does not exist: {ws}")

    watch_dir = ws / ".re_harness"
    state_file = watch_dir / "quota-watchdog.json"
    if not state_file.is_file():
        raise WorkspaceBindingError(f"Missing quota-watchdog.json in workspace: {state_file}")

    try:
        data = json.loads(state_file.read_text(encoding="utf8"))
    except Exception as exc:
        raise WorkspaceBindingError(f"Corrupt quota-watchdog.json: {exc}")

    pid = data.get("project_id")
    if not pid or pid in {"PROJECT_ID", "CONVERSATION_ID"}:
        raise WorkspaceBindingError(f"Watchdog is not bound to a valid project_id (found: {pid!r})")

    if expected_project_id and pid != expected_project_id:
        raise WorkspaceBindingError(f"Project ID mismatch: expected {expected_project_id}, found {pid}")

    if harness_state_dir:
        db_dir = Path(harness_state_dir).expanduser().resolve()
    elif (ws / ".re_harness_mvp" / "state.sqlite3").is_file():
        db_dir = ws / ".re_harness_mvp"
    elif (ws / ".re_harness" / "state.sqlite3").is_file():
        db_dir = ws / ".re_harness"
    else:
        db_dir = ws / ".re_harness_mvp"

    db_file = db_dir / "state.sqlite3"
    if not db_file.is_file():
        raise WorkspaceBindingError(f"Harness database state.sqlite3 not found at {db_file}")

    import sqlite3
    with sqlite3.connect(db_file) as db:
        db.row_factory = sqlite3.Row
        proj = db.execute("SELECT id, goal, status FROM auto_projects WHERE id=?", (pid,)).fetchone()
        if not proj:
            raise WorkspaceBindingError(f"Pinned project '{pid}' not found in Harness database {db_file}")
        if proj["status"] not in quota_guard.ACTIVE:
            raise WorkspaceBindingError(f"Pinned project '{pid}' is '{proj['status']}'; supervisor requires an ACTIVE project")

    # Resolve python executable: check ws/.venv/bin/python, sys.executable, or python3
    py_candidate = ws / ".venv" / "bin" / "python"
    if py_candidate.is_file() and os.access(py_candidate, os.X_OK):
        py_bin = str(py_candidate)
    elif os.access(sys.executable, os.X_OK):
        py_bin = sys.executable
    else:
        py_bin = "/usr/bin/python3"

    return {
        "workspace": str(ws),
        "project_id": pid,
        "conversation_id": data.get("conversation_id"),
        "goal": proj["goal"],
        "project_status": proj["status"],
        "db_dir": str(db_dir),
        "python_bin": py_bin,
    }


def generate_systemd_unit(
    workspace: Path | str,
    expected_project_id: Optional[str] = None,
    harness_state_dir: Optional[Path | str] = None,
) -> str:
    binding = verify_workspace_binding(workspace, expected_project_id=expected_project_id, harness_state_dir=harness_state_dir)
    ws = binding["workspace"]
    py = binding["python_bin"]
    pid = binding["project_id"]
    return f"""[Unit]
Description=RE Dragon Autonomous Reliability Supervisor (Project {pid})
Documentation=https://github.com/khanhpn308/re_dragon
After=network.target

[Service]
Type=simple
WorkingDirectory={ws}
ExecStart={py} -m re_harness.supervisor run --workspace {ws}
Restart=on-failure
RestartPreventExitStatus=0 10 11 12
RestartSec=30
KillMode=process
TimeoutStopSec=30

[Install]
WantedBy=default.target
"""


def generate_windows_task_xml(
    workspace: Path | str,
    distro: str = "Ubuntu",
    user: Optional[str] = None,
    expected_project_id: Optional[str] = None,
    harness_state_dir: Optional[Path | str] = None,
) -> str:
    binding = verify_workspace_binding(workspace, expected_project_id=expected_project_id, harness_state_dir=harness_state_dir)
    ws = binding["workspace"]
    py = binding["python_bin"]
    pid = binding["project_id"]
    user_name = user or os.environ.get("USER", "khanh")
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>RE Dragon Autonomous Reliability Supervisor (Project {pid})</Description>
    <URI>\\RE Dragon\\ReliabilitySupervisor_{pid}</URI>
  </RegistrationInfo>
  <Triggers>
    <LogonTrigger>
      <Enabled>true</Enabled>
    </LogonTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>true</RunOnlyIfNetworkAvailable>
    <IdleSettings>
      <StopOnIdleEnd>false</StopOnIdleEnd>
      <RestartOnIdle>false</RestartOnIdle>
    </IdleSettings>
    <ExecutionTimeLimit>P3D</ExecutionTimeLimit>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>wsl.exe</Command>
      <Arguments>-d {distro} -u {user_name} -- bash -c "cd {ws} && {py} -m re_harness.supervisor run --workspace {ws}"</Arguments>
    </Exec>
  </Actions>
</Task>
"""


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="RE Dragon Process Supervisor")
    parser.add_argument("action", choices=("run", "status", "generate-config"))
    parser.add_argument("--workspace", default=".")
    parser.add_argument("--harness-state-dir", default="")
    parser.add_argument("--binary", default="agy")
    parser.add_argument("--distro", default="Ubuntu")
    parser.add_argument("--user", default="khanh")
    parser.add_argument("--expected-project-id", default="")
    args = parser.parse_args(argv)

    root = Path(args.workspace).expanduser().resolve()
    supervisor = Supervisor(root, harness_state_dir=args.harness_state_dir, binary=args.binary)

    if args.action == "status":
        st = supervisor.status()
        print(json.dumps(st, indent=2, ensure_ascii=False))
        return 0

    if args.action == "generate-config":
        systemd_unit = generate_systemd_unit(
            root, expected_project_id=args.expected_project_id or None, harness_state_dir=args.harness_state_dir or None
        )
        windows_xml = generate_windows_task_xml(
            root, distro=args.distro, user=args.user, expected_project_id=args.expected_project_id or None, harness_state_dir=args.harness_state_dir or None
        )
        print("=== systemd unit (copy to ~/.config/systemd/user/re-dragon.service) ===")
        print(systemd_unit)
        print("\n=== Windows Task Scheduler XML ===")
        print(windows_xml)
        return 0

    if args.action == "run":
        return supervisor.run()

    return 0


if __name__ == "__main__":
    sys.exit(main())
