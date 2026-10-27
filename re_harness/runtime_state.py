"""Live read-only process telemetry for the headless agent.

The watchdog writes this heartbeat while it owns the singleton lock. Status
readers never mutate leases or infer that a living process made task progress.
"""
from __future__ import annotations

import contextlib
import json
import os
import threading
import time
from pathlib import Path


def _proc_start(pid):
    try:
        txt = Path(f"/proc/{int(pid)}/stat").read_text()
        fields = txt.rsplit(")", 1)[1].strip().split()
        return fields[19]  # /proc stat field 22 (starttime)
    except (OSError, IndexError, ValueError):
        return None


def _atomic(path, data):
    path=Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp=path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data,f,ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.chmod(tmp,0o600)
    os.replace(tmp,path)


def snapshot(path, now=None):
    """Return live metadata only if the original PID is still alive."""
    try:
        data=json.loads(Path(path).read_text(encoding="utf-8"))
        if data.get("state") != "AGENT_RUNNING":
            return None
        actual=_proc_start(data["pid"])
        if not actual or str(actual)!=str(data["proc_start"]):
            return None
        now=time.time() if now is None else now
        return {
            "state":"AGENT_RUNNING", "pid":data["pid"],
            "elapsed_seconds":max(0,int(now-float(data["started_at"]))),
            "supervisor_heartbeat_at":data["heartbeat_at"],
            "heartbeat_age_seconds":max(0,int(now-float(data["heartbeat_at"]))),
            "heartbeat_is_progress_proof":False,
        }
    except (OSError,ValueError,TypeError,KeyError):
        return None


class AgentHeartbeat:
    def __init__(self,path,pid,interval=15):
        self.path=Path(path)
        self.pid=int(pid)
        self.interval=interval
        self.started=time.time()
        self.proc_start=_proc_start(self.pid)
        self._stop=threading.Event()
        self._thread=None

    def _write(self):
        if not self.proc_start or _proc_start(self.pid)!=self.proc_start:
            return False
        _atomic(self.path,{"state":"AGENT_RUNNING","pid":self.pid,
                "proc_start":self.proc_start,"started_at":self.started,
                "heartbeat_at":time.time()})
        return True

    def _run(self):
        while not self._stop.wait(self.interval):
            with contextlib.suppress(OSError):
                if not self._write():
                    break

    def __enter__(self):
        if self.proc_start and self._write():
            self._thread=threading.Thread(target=self._run,daemon=True,
                                          name="re-dragon-agent-heartbeat")
            self._thread.start()
        return self

    def __exit__(self,*exc):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        # Write a terminal record; do not erase evidence before status readers
        # have had an opportunity to observe it.
        with contextlib.suppress(OSError):
            _atomic(self.path,{"state":"AGENT_EXITED","pid":self.pid,
                               "ended_at":time.time()})
