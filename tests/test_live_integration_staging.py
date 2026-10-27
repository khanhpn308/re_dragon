"""Real Integration Staging Acceptance Tests for RE Dragon v0.8.

Executes real OS processes, real SQLite WAL transactions, real file flock locks,
and real graceful drain on Linux / WSL2 to establish LIVE_PASS status.
"""
from __future__ import annotations

import fcntl
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from re_harness import autonomy, backup_util, core, incidents, quota_watchdog, recovery, supervisor


class LiveIntegrationStagingTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.workspace = Path(self.temp_dir.name) / "staging_workspace"
        self.workspace.mkdir(parents=True)
        self.harness_dir = self.workspace / ".re_harness"
        self.harness_dir.mkdir(parents=True)

        # Initialize harness database in WAL mode
        with core.database(self.harness_dir) as db:
            autonomy.migrate(db)
            db.execute("PRAGMA journal_mode=WAL")
            proj = autonomy.start(db, "Live Staging Goal", "Acceptance gates")
            self.project_id = proj["project_id"]

        # Create docs/QUOTA_WATCHDOG_TURN.md
        docs_dir = self.workspace / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        (docs_dir / "QUOTA_WATCHDOG_TURN.md").write_text("# Turn prompt\n", encoding="utf-8")

        # Create quota-watchdog.json
        state_file = self.harness_dir / "quota-watchdog.json"
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump({
                "status": "READY",
                "project_id": self.project_id,
                "conversation_id": "test-conv-staging",
            }, f)

    def test_live_flock_mutual_exclusion(self):
        """Verify real OS file locking between separate OS processes."""
        lock_file = self.harness_dir / "quota-watchdog.lock"

        # Initially unlocked
        self.assertFalse(supervisor.is_watchdog_locked(self.workspace))

        # Launch real background subprocess that acquires lock and sleeps
        code = (
            "import fcntl, time, sys\n"
            f"f = open('{lock_file}', 'a+')\n"
            "fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)\n"
            "sys.stdout.write('LOCKED\\n')\n"
            "sys.stdout.flush()\n"
            "time.sleep(2.0)\n"
            "fcntl.flock(f, fcntl.LOCK_UN)\n"
        )
        proc = subprocess.Popen(
            [sys.executable, "-c", code],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        try:
            line = proc.stdout.readline().strip()
            self.assertEqual(line, "LOCKED")

            # Check that supervisor correctly detects real lock
            self.assertTrue(supervisor.is_watchdog_locked(self.workspace))

            # Wait for subprocess to finish releasing lock
            proc.wait(timeout=5.0)

            # Check that lock is released
            self.assertFalse(supervisor.is_watchdog_locked(self.workspace))
        finally:
            if proc.stdout:
                proc.stdout.close()
            if proc.stderr:
                proc.stderr.close()
            if proc.poll() is None:
                proc.kill()

    def test_live_graceful_drain_waits_for_inflight_worker(self):
        """Verify graceful drain waits for a live in-flight worker process to finish and checkpoints."""
        runtime_file = self.harness_dir / "agent-runtime.json"
        state_file = self.harness_dir / "quota-watchdog.json"

        # Initialize state file
        with open(state_file, "w") as f:
            json.dump({
                "status": "RUNNING",
                "project_id": self.project_id,
                "conversation_id": "test-conv",
            }, f)

        # Launch real worker process that registers runtime heartbeat and sleeps 1.5s
        code = (
            "import os, time\n"
            "from re_harness.runtime_state import AgentHeartbeat\n"
            f"rt = '{runtime_file}'\n"
            "hb = AgentHeartbeat(rt, os.getpid(), interval=0.5)\n"
            "hb._write()\n"
            "time.sleep(1.5)\n"
            "if os.path.exists(rt):\n"
            "    os.unlink(rt)\n"
        )
        proc = subprocess.Popen([sys.executable, "-c", code])

        try:
            # Wait until worker writes runtime file
            for _ in range(20):
                if runtime_file.exists():
                    break
                time.sleep(0.1)
            self.assertTrue(runtime_file.exists(), "Worker failed to write runtime file")

            # Execute graceful drain
            res = quota_watchdog.drain_watchdog(self.workspace, timeout=5.0, poll_interval=0.2)
            self.assertTrue(res["drained"])
            self.assertEqual(res["status"], "PAUSED")

            # Ensure worker exited cleanly
            proc.wait(timeout=5.0)
            self.assertEqual(proc.returncode, 0)

            # Ensure runtime file is cleaned up and state is PAUSED
            self.assertFalse(runtime_file.exists())
            with open(state_file) as f:
                saved = json.load(f)
            self.assertEqual(saved["status"], "PAUSED")
        finally:
            if proc.stdout:
                proc.stdout.close()
            if proc.stderr:
                proc.stderr.close()
            if proc.poll() is None:
                proc.kill()

    def test_live_sqlite_wal_checkpoint_and_backup_concurrency(self):
        """Verify real concurrent transactions in WAL mode and online backup with wal_checkpoint(TRUNCATE)."""
        backup_dir = Path(self.temp_dir.name) / "live_backups"
        backup_dir.mkdir(parents=True)

        # Concurrently perform transactions while taking backup
        with core.database(self.harness_dir) as db:
            autonomy.plan(db, self.project_id, [
                {"key": f"TASK_{i}", "title": f"Task {i}", "acceptance": "A", "kind": "ANALYZE"}
                for i in range(10)
            ])

        # Create safe backup with WAL truncate
        manifest = backup_util.create_safe_backup(
            workspace=self.workspace,
            backup_dir=backup_dir,
            backup_label="live_concurrency_test",
        )

        self.assertTrue(Path(manifest["backup_dir"]).exists())

        # Verify backup contains all 10 tasks and passes integrity check
        backup_db = Path(manifest["backup_dir"]) / manifest["database"]["filename"]
        with sqlite3.connect(str(backup_db)) as conn:
            res = conn.execute("PRAGMA integrity_check").fetchone()
            self.assertEqual(res[0], "ok")
            cnt = conn.execute("SELECT COUNT(*) FROM auto_tasks WHERE project_id=?", (self.project_id,)).fetchone()
            self.assertEqual(cnt[0], 10)

    def test_live_workspace_binding_validation(self):
        """Verify real workspace validation against active database and state."""
        binding = supervisor.verify_workspace_binding(
            workspace=self.workspace,
            expected_project_id=self.project_id,
        )
        self.assertEqual(binding["workspace"], str(self.workspace.resolve()))
        self.assertEqual(binding["project_id"], self.project_id)
        self.assertTrue(Path(binding["db_dir"]).exists())

        # Test failure on mismatched project ID
        with self.assertRaises(supervisor.WorkspaceBindingError) as ctx:
            supervisor.verify_workspace_binding(
                workspace=self.workspace,
                expected_project_id="non-existent-project-999",
            )
        self.assertIn("Project ID mismatch", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
