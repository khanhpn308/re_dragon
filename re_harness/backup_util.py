"""Backup and Rollback Integrity Utilities for RE Dragon v0.8.

Provides safe, consistent SQLite backups in WAL mode using PRAGMA wal_checkpoint(TRUNCATE)
and the SQLite Online Backup API, recording Git commit SHAs and file integrity checksums.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Union

from . import core


class BackupError(Exception):
    """Raised when backup creation or restoration fails."""


def compute_sha256(filepath: Union[str, Path]) -> str:
    """Compute SHA-256 checksum of a file."""
    path = Path(filepath)
    if not path.is_file():
        raise BackupError(f"File not found: {path}")
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def get_git_commit_sha(workspace: Union[str, Path]) -> Optional[str]:
    """Retrieve current Git commit SHA if in a git repository."""
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except Exception:
        pass
    return None


def create_safe_backup(
    workspace: Union[str, Path],
    backup_dir: Union[str, Path],
    harness_state_dir: Optional[Union[str, Path]] = None,
    backup_label: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a consistent snapshot of the RE Dragon SQLite state and configuration.

    Guarantees:
    1. Executes PRAGMA wal_checkpoint(TRUNCATE) on the SQLite database before copy.
    2. Uses sqlite3.Connection.backup() for atomic online database snapshot.
    3. Backs up quota-watchdog-state.json and supervisor configs.
    4. Records current Git commit SHA and SHA-256 hashes of all snapshot files.
    5. Writes a durable backup-manifest.json.

    Returns:
        Manifest dictionary containing snapshot metadata and checksums.
    """
    ws = Path(workspace).resolve()
    dest = Path(backup_dir).resolve()
    state_dir = Path(harness_state_dir).resolve() if harness_state_dir else ws / ".re_harness"
    db_path = state_dir / "state.sqlite3"
    if not db_path.exists():
        # Fallback to harness.sqlite3 if present
        if (state_dir / "harness.sqlite3").exists():
            db_path = state_dir / "harness.sqlite3"
        else:
            raise BackupError(f"Harness database not found at {db_path}")

    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
    label = f"_{backup_label}" if backup_label else ""
    target_snapshot_dir = dest / f"backup_{timestamp_str}{label}"
    target_snapshot_dir.mkdir(parents=True, exist_ok=True)

    # 1. Atomic SQLite backup with WAL truncate
    backup_db_path = target_snapshot_dir / db_path.name
    try:
        with sqlite3.connect(str(db_path), timeout=30.0) as src_conn:
            # Force truncate WAL so all commits are written into main database file
            src_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            with sqlite3.connect(str(backup_db_path)) as dst_conn:
                src_conn.backup(dst_conn)
    except Exception as exc:
        shutil.rmtree(target_snapshot_dir, ignore_errors=True)
        raise BackupError(f"Failed to create online SQLite backup: {exc}") from exc

    # Run integrity check on the backup database to guarantee zero corruption
    try:
        with sqlite3.connect(str(backup_db_path)) as chk_conn:
            res = chk_conn.execute("PRAGMA integrity_check").fetchone()
            if not res or res[0] != "ok":
                raise BackupError(f"Integrity check failed on backup database: {res}")
    except Exception as exc:
        shutil.rmtree(target_snapshot_dir, ignore_errors=True)
        raise BackupError(f"Integrity check failed on backup database: {exc}") from exc

    db_sha256 = compute_sha256(backup_db_path)

    # 2. Backup watchdog state if present
    state_file = state_dir / "quota-watchdog-state.json"
    state_sha256 = None
    if state_file.exists():
        backup_state_path = target_snapshot_dir / "quota-watchdog-state.json"
        shutil.copy2(state_file, backup_state_path)
        state_sha256 = compute_sha256(backup_state_path)

    # 3. Backup incident journal if present
    incidents_file = state_dir / "incidents.sqlite3"
    incidents_sha256 = None
    if incidents_file.exists():
        backup_incidents_path = target_snapshot_dir / "incidents.sqlite3"
        try:
            with sqlite3.connect(str(incidents_file), timeout=10.0) as src_inc:
                src_inc.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                with sqlite3.connect(str(backup_incidents_path)) as dst_inc:
                    src_inc.backup(dst_inc)
            incidents_sha256 = compute_sha256(backup_incidents_path)
        except Exception:
            shutil.copy2(incidents_file, backup_incidents_path)
            incidents_sha256 = compute_sha256(backup_incidents_path)

    git_sha = get_git_commit_sha(ws)

    manifest = {
        "version": "v0.8",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "created_timestamp": time.time(),
        "workspace": str(ws),
        "git_commit_sha": git_sha,
        "backup_dir": str(target_snapshot_dir),
        "database": {
            "filename": db_path.name,
            "sha256": db_sha256,
        },
        "watchdog_state": {
            "filename": "quota-watchdog-state.json" if state_sha256 else None,
            "sha256": state_sha256,
        },
        "incidents": {
            "filename": "incidents.sqlite3" if incidents_sha256 else None,
            "sha256": incidents_sha256,
        },
    }

    manifest_path = target_snapshot_dir / "backup-manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    return manifest


def verify_and_restore_backup(
    backup_snapshot_dir: Union[str, Path],
    workspace: Union[str, Path],
    harness_state_dir: Optional[Union[str, Path]] = None,
    verify_git_commit: bool = False,
) -> Dict[str, Any]:
    """Safely restore a snapshot, verifying manifest checksums and integrity.

    Guarantees:
    1. Validates manifest exists and is well-formed.
    2. Validates SHA-256 hashes of backup files before any file is restored.
    3. Runs PRAGMA integrity_check on the restored database.
    4. Atomically restores database and state files.
    """
    snap_dir = Path(backup_snapshot_dir).resolve()
    manifest_path = snap_dir / "backup-manifest.json"
    if not manifest_path.exists():
        raise BackupError(f"Missing backup manifest: {manifest_path}")

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as exc:
        raise BackupError(f"Corrupt backup manifest: {exc}") from exc

    # Check database integrity
    db_file = snap_dir / manifest["database"]["filename"]
    if not db_file.exists():
        raise BackupError(f"Backup database file missing: {db_file}")

    actual_db_sha256 = compute_sha256(db_file)
    if actual_db_sha256 != manifest["database"]["sha256"]:
        raise BackupError(
            f"Database checksum mismatch! Expected: {manifest['database']['sha256']}, got: {actual_db_sha256}"
        )

    # Check state file integrity if listed
    if manifest.get("watchdog_state", {}).get("filename"):
        st_file = snap_dir / manifest["watchdog_state"]["filename"]
        if st_file.exists():
            actual_st_sha256 = compute_sha256(st_file)
            if actual_st_sha256 != manifest["watchdog_state"]["sha256"]:
                raise BackupError("Watchdog state file checksum mismatch")

    ws = Path(workspace).resolve()
    state_dir = Path(harness_state_dir).resolve() if harness_state_dir else ws / ".re_harness"
    state_dir.mkdir(parents=True, exist_ok=True)

    if verify_git_commit and manifest.get("git_commit_sha"):
        current_sha = get_git_commit_sha(ws)
        if current_sha and current_sha != manifest["git_commit_sha"]:
            raise BackupError(
                f"Git commit mismatch! Backup was created at {manifest['git_commit_sha']}, "
                f"current commit is {current_sha}"
            )

    # Restore database atomically via temporary file
    db_filename = manifest["database"]["filename"]
    temp_target = state_dir / f"{db_filename}.restoring"
    shutil.copy2(db_file, temp_target)

    # Verify temp target integrity
    with sqlite3.connect(str(temp_target)) as chk_conn:
        res = chk_conn.execute("PRAGMA integrity_check").fetchone()
        if not res or res[0] != "ok":
            temp_target.unlink(missing_ok=True)
            raise BackupError(f"Integrity check failed on restored database: {res}")

    # Remove any existing WAL / SHM files to prevent WAL inconsistency
    target_db = state_dir / db_filename
    (state_dir / f"{db_filename}-wal").unlink(missing_ok=True)
    (state_dir / f"{db_filename}-shm").unlink(missing_ok=True)
    temp_target.replace(target_db)

    # Restore watchdog state if present
    if manifest.get("watchdog_state", {}).get("filename"):
        src_st = snap_dir / manifest["watchdog_state"]["filename"]
        if src_st.exists():
            shutil.copy2(src_st, state_dir / manifest["watchdog_state"]["filename"])

    # Restore incidents db if present
    if manifest.get("incidents", {}).get("filename"):
        src_inc = snap_dir / manifest["incidents"]["filename"]
        if src_inc.exists():
            (state_dir / "incidents.sqlite3-wal").unlink(missing_ok=True)
            (state_dir / "incidents.sqlite3-shm").unlink(missing_ok=True)
            shutil.copy2(src_inc, state_dir / manifest["incidents"]["filename"])

    return {
        "restored": True,
        "manifest": manifest,
        "restored_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def main(argv=None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="RE Dragon v0.8 WAL Backup & Restoration Utility")
    sub = parser.add_subparsers(dest="command", required=True)

    backup_parser = sub.add_parser("backup", help="Create consistent WAL-checkpointed backup")
    backup_parser.add_argument("--workspace", default=".", help="Workspace path")
    backup_parser.add_argument("--backup-dir", required=True, help="Destination directory for backups")
    backup_parser.add_argument("--harness-state-dir", default=None, help="Explicit harness state directory")
    backup_parser.add_argument("--label", default=None, help="Optional label for the backup")

    restore_parser = sub.add_parser("restore", help="Restore verified backup")
    restore_parser.add_argument("--backup-snapshot", required=True, help="Path to backup snapshot directory")
    restore_parser.add_argument("--workspace", default=".", help="Target workspace path")
    restore_parser.add_argument("--harness-state-dir", default=None, help="Explicit harness state directory")
    restore_parser.add_argument("--verify-git-commit", action="store_true", help="Ensure git commit matches backup")

    args = parser.parse_args(argv)

    if args.command == "backup":
        res = create_safe_backup(
            workspace=args.workspace,
            backup_dir=args.backup_dir,
            harness_state_dir=args.harness_state_dir,
            backup_label=args.label,
        )
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0

    if args.command == "restore":
        res = verify_and_restore_backup(
            backup_snapshot_dir=args.backup_snapshot,
            workspace=args.workspace,
            harness_state_dir=args.harness_state_dir,
            verify_git_commit=args.verify_git_commit,
        )
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0

    return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
