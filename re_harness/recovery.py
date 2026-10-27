"""Autonomous Recovery Engine for RE Dragon v0.8.

Provides standardized error classification, bounded exponential backoff,
pre-retry safety verification (preventing double execution), lease reconciliation,
and integration with the incident journal.
"""
from __future__ import annotations

import contextlib
import json
import math
import os
import random
import re
import signal
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from . import core, incidents, quota_guard

MARKER = "RE_DRAGON_RUN_STATE "
VALID_STATES = {"CONTINUE", "YIELD", "WAIT", "COMPLETE", "BLOCKED", "NEEDS_USER"}

RE_QUOTA = re.compile(
    r"(resource_exhausted|individual quota reached|quota exceeded|quota reached|"
    r"resets?\s+in\s+|rate limit exceeded|usage limit reached|weekly limit reached|too many requests)",
    re.I,
)

RE_AUTH_PERM = re.compile(
    r"(soft-denied|tool denied|action denied|tool permission|needs approval|"
    r"not allowed|authentication required|not authenticated|sign in|login required|"
    r"permission denied|requires approval|waiting for approval)",
    re.I,
)

RE_NETWORK = re.compile(
    r"(econnreset|etimedout|eai_again|temporary failure in name resolution|"
    r"network is unreachable|connection reset by peer|service unavailable|"
    r"502 bad gateway|503 service unavailable|remote end closed connection|"
    r"connection refused|socket hang up)",
    re.I,
)

RE_SQLITE_LOCK = re.compile(
    r"(database is locked|operationalerror:\s*database is locked|sqlite3\.busyerror|database table is locked)",
    re.I,
)

RE_OOM = re.compile(
    r"(java\.lang\.outofmemoryerror|java heap space|out of memory|killed\s+process|"
    r"memory limit exceeded|ghidra.*(?:low memory|out of ram))",
    re.I,
)

RE_TIMEOUT = re.compile(
    r"(watchdog process timeout|timeoutexpired|process timed out|command timed out)",
    re.I,
)


@dataclass
class ClassificationResult:
    category: str
    severity: str
    recoverable: bool
    suggested_status: str
    retry_delay: float
    error_summary: str
    requires_human: bool
    details: Dict[str, Any] = field(default_factory=dict)


def parse_marker(response_text: str) -> Tuple[Optional[str], str]:
    """Extract and validate RE_DRAGON_RUN_STATE marker from response text."""
    for line in reversed((response_text or "").splitlines()):
        trimmed = line.strip()
        if trimmed.startswith(MARKER):
            payload = trimmed[len(MARKER):].strip()
            try:
                data = json.loads(payload)
                state = data.get("state")
                note = str(data.get("note", ""))[:400]
                if state in VALID_STATES:
                    return state, note
            except (ValueError, TypeError, AttributeError):
                pass
            return None, "Invalid structured watchdog state marker"
    return None, "Agent did not emit the required structured watchdog state"


def reset_seconds_from_text(message: str) -> Optional[int]:
    """Extract quota reset delay from text (e.g. 'Resets in 2h 30m')."""
    match = re.search(r"\bResets?\s+in\s+((?:\d+\s*[dhms]\s*){1,4})", message or "", re.I)
    if not match:
        return None
    units = {"d": 86400, "h": 3600, "m": 60, "s": 1}
    values = re.findall(r"(\d+)\s*([dhms])", match.group(1), re.I)
    if not values:
        return None
    total = sum(int(v) * units[u.lower()] for v, u in values)
    return min(max(60, total), 8 * 86400)


def calculate_backoff(
    attempt: int,
    base_delay: float = 30.0,
    max_delay: float = 900.0,
    factor: float = 2.0,
    jitter: bool = True,
) -> float:
    """Calculate exponential backoff with optional uniform jitter."""
    attempt = max(1, attempt)
    delay = min(max_delay, base_delay * (factor ** (attempt - 1)))
    if jitter:
        # Add up to 20% jitter
        delay += random.uniform(0, delay * 0.2)
    return round(delay, 2)


def is_pid_alive(pid: int) -> bool:
    """Check if process with given PID is currently alive."""
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def terminate_pid_group(pid: int, grace_seconds: float = 2.0) -> None:
    """Safely terminate a process group with SIGTERM then SIGKILL if needed."""
    if not pid or pid <= 0:
        return
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(pid, signal.SIGTERM)
    start = time.time()
    while time.time() - start < grace_seconds:
        if not is_pid_alive(pid):
            return
        time.sleep(0.1)
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(pid, signal.SIGKILL)


def classify_turn(
    outcome: Dict[str, Any],
    previous_state: Optional[Dict[str, Any]] = None,
    current_attempt: int = 1,
    harness_state_dir: Optional[Path | str] = None,
) -> ClassificationResult:
    """Standardized failure classification for an Antigravity turn outcome.

    Returns ClassificationResult indicating recovery viability and backoff.
    """
    code = outcome.get("code", 0)
    data = outcome.get("data") or {}
    if not isinstance(data, dict):
        data = {}
    cli_status = str(data.get("status") or "").upper()
    response = str(data.get("response") or "")
    stderr = str(outcome.get("stderr") or "")
    combined_err = f"{data.get('error', '')}\n{stderr}\n{response}".strip()

    # 1. Permission or Authentication Denial (FAIL CLOSED - NEVER AUTO-RETRY)
    if RE_AUTH_PERM.search(combined_err):
        return ClassificationResult(
            category="AUTH_OR_PERMISSION",
            severity="CRITICAL",
            recoverable=False,
            suggested_status="NEEDS_USER",
            retry_delay=0.0,
            error_summary="Tool permission or authentication required; manual resolution needed",
            requires_human=True,
            details={"code": code, "cli_status": cli_status, "error": combined_err[:400]},
        )

    # 2. Quota Exhaustion
    if RE_QUOTA.search(combined_err):
        delay = reset_seconds_from_text(combined_err) or 900
        return ClassificationResult(
            category="QUOTA_EXHAUSTED",
            severity="INFO",
            recoverable=True,
            suggested_status="WAIT_QUOTA",
            retry_delay=float(delay + 60),  # reported delay + 60s grace
            error_summary="Provider quota exhausted; waiting for reported reset",
            requires_human=False,
            details={"reset_delay": delay},
        )

    # 3. Resource Exhaustion (Ghidra OOM / SIGKILL code 137)
    if code == 137 or RE_OOM.search(combined_err):
        backoff = calculate_backoff(current_attempt, base_delay=60.0, max_delay=600.0)
        return ClassificationResult(
            category="RESOURCE_EXHAUSTION",
            severity="ERROR",
            recoverable=True,
            suggested_status="WAIT_RETRY",
            retry_delay=backoff,
            error_summary="Resource limit reached (OOM/Ghidra RAM); backoff for resource release",
            requires_human=False,
            details={"exit_code": code, "attempt": current_attempt},
        )

    # 4. SQLite Concurrency / Lock
    if RE_SQLITE_LOCK.search(combined_err):
        backoff = calculate_backoff(current_attempt, base_delay=3.0, max_delay=30.0, factor=2.0)
        return ClassificationResult(
            category="SQLITE_LOCK",
            severity="WARNING",
            recoverable=True,
            suggested_status="WAIT_RETRY",
            retry_delay=backoff,
            error_summary="SQLite database is locked; brief backoff retry",
            requires_human=False,
            details={"attempt": current_attempt},
        )

    # 5. Network / Transport Fault
    if RE_NETWORK.search(combined_err):
        backoff = calculate_backoff(current_attempt, base_delay=30.0, max_delay=300.0)
        return ClassificationResult(
            category="NETWORK_TRANSIENT",
            severity="WARNING",
            recoverable=True,
            suggested_status="WAIT_RETRY",
            retry_delay=backoff,
            error_summary="Transient transport or network error; bounded backoff retry",
            requires_human=False,
            details={"attempt": current_attempt},
        )

    # 6. Process Timeout
    if code == 124 or RE_TIMEOUT.search(combined_err):
        backoff = calculate_backoff(current_attempt, base_delay=60.0, max_delay=300.0)
        return ClassificationResult(
            category="TIMEOUT",
            severity="WARNING",
            recoverable=True,
            suggested_status="WAIT_RETRY",
            retry_delay=backoff,
            error_summary="Watchdog or CLI process timeout; bounded retry after process termination",
            requires_human=False,
            details={"exit_code": code, "attempt": current_attempt},
        )

    # 7. Clean Success with valid marker
    if code == 0 and cli_status == "SUCCESS":
        marker_state, note = parse_marker(response)
        if marker_state is not None:
            return ClassificationResult(
                category="SUCCESS_WITH_MARKER",
                severity="INFO",
                recoverable=True,
                suggested_status=marker_state,
                retry_delay=0.0,
                error_summary=note or "Agent turn successfully checkpointed",
                requires_human=marker_state in {"BLOCKED", "NEEDS_USER"},
                details={"marker_state": marker_state, "note": note},
            )
        # Missing or malformed marker
        backoff = calculate_backoff(current_attempt, base_delay=60.0, max_delay=240.0, factor=2.0)
        return ClassificationResult(
            category="MISSING_MARKER",
            severity="WARNING",
            recoverable=True,
            suggested_status="WAIT_RETRY",
            retry_delay=backoff,
            error_summary=note or "CLI SUCCESS omitted required structured state marker",
            requires_human=False,
            details={"attempt": current_attempt, "note": note},
        )

    # 8. Unhandled Agent Crash (code != 0)
    if code != 0:
        backoff = calculate_backoff(current_attempt, base_delay=30.0, max_delay=180.0)
        return ClassificationResult(
            category="AGENT_CRASH",
            severity="ERROR",
            recoverable=True,
            suggested_status="WAIT_RETRY",
            retry_delay=backoff,
            error_summary=f"Agent CLI exited with non-zero code {code}",
            requires_human=False,
            details={"exit_code": code, "stderr": stderr[-400:], "attempt": current_attempt},
        )

    # 9. Unexpected error fallback
    return ClassificationResult(
        category="UNEXPECTED_ERROR",
        severity="ERROR",
        recoverable=False,
        suggested_status="ERROR",
        retry_delay=0.0,
        error_summary="Unexpected execution error; operator inspection required",
        requires_human=True,
        details={"code": code, "cli_status": cli_status, "stderr": stderr[:400]},
    )


class SafetyCheckError(Exception):
    """Raised when pre-retry safety invariants are violated."""


def verify_pre_retry_safety(
    workspace: Path | str,
    project_id: str,
    harness_state_dir: Path | str,
    previous_pid: Optional[int] = None,
) -> Dict[str, Any]:
    """Verify safety invariants before permitting an autonomous recovery retry.

    Invariants checked:
    1. Previous child PID is completely terminated (no concurrent CLI).
    2. SQLite database is intact, accessible, and not locked.
    3. Pinned project exists in SQLite and is currently ACTIVE.
    4. Expired task leases are safely reclaimed without losing completed work.

    Raises:
        SafetyCheckError: if any invariant is violated.
    Returns:
        dict with project and task health summary.
    """
    root = Path(workspace).resolve()
    db_dir = Path(harness_state_dir).resolve()

    # 1. Verify previous PID is dead
    if previous_pid and is_pid_alive(previous_pid):
        terminate_pid_group(previous_pid)
        if is_pid_alive(previous_pid):
            raise SafetyCheckError(
                f"Previous CLI PID {previous_pid} is still alive after termination; "
                "refusing retry to prevent split-brain double execution"
            )

    # 2. Inspect SQLite project checkpoint
    try:
        info = quota_guard.inspect(db_dir, project_id)
    except quota_guard.ProjectGateError as exc:
        raise SafetyCheckError(f"Harness project guard check failed: {exc}") from exc

    if info["project_id"] != project_id:
        raise SafetyCheckError(
            f"Project identity mismatch (pinned: {project_id}, found: {info['project_id']})"
        )

    if info["project_status"] not in quota_guard.ACTIVE:
        raise SafetyCheckError(
            f"Project {project_id} is in status '{info['project_status']}'; "
            "cannot auto-retry a non-active project"
        )

    # 3. Clean up expired task leases to prevent stuck tasks or duplicate side-effects
    try:
        from . import autonomy
        with core.database(db_dir) as db:
            autonomy._expire(db, project_id)
    except Exception as exc:
        raise SafetyCheckError(f"Failed to reconcile task leases: {exc}") from exc

    return {
        "project_id": project_id,
        "project_status": info["project_status"],
        "goal": info["goal"],
        "task_counts": info["task_status_counts"],
        "safe_to_retry": True,
    }
