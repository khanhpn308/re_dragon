"""Unit tests for Backup and Rollback Integrity in re_harness.backup_util."""
from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from re_harness import autonomy, backup_util, core


class BackupUtilTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.workspace = Path(self.temp_dir.name) / "workspace"
        self.workspace.mkdir(parents=True)
        self.backup_dir = Path(self.temp_dir.name) / "backups"
        self.backup_dir.mkdir(parents=True)

        self.harness_dir = self.workspace / ".re_harness"
        self.harness_dir.mkdir(parents=True)

        # Initialize harness database in WAL mode
        with core.database(self.harness_dir) as db:
            autonomy.migrate(db)
            db.execute("PRAGMA journal_mode=WAL")
            proj = autonomy.start(db, "Production Test Goal", "Acceptance gates")
            self.project_id = proj["project_id"]
            autonomy.plan(db, self.project_id, [
                {"key": "T1", "title": "Test Task 1", "acceptance": "A1", "kind": "ANALYZE"}
            ])

        # Create mock quota-watchdog-state.json
        self.state_file = self.harness_dir / "quota-watchdog-state.json"
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump({
                "status": "RUNNING",
                "project_id": self.project_id,
                "conversation_id": "conv-1234",
            }, f)

    def test_create_safe_backup_succeeds_with_manifest_and_checksums(self):
        manifest = backup_util.create_safe_backup(
            workspace=self.workspace,
            backup_dir=self.backup_dir,
            backup_label="pre_rollout",
        )

        self.assertEqual(manifest["version"], "v0.8")
        self.assertTrue(Path(manifest["backup_dir"]).exists())

        # Verify backup files exist
        backup_db = Path(manifest["backup_dir"]) / manifest["database"]["filename"]
        self.assertTrue(backup_db.exists())
        self.assertEqual(manifest["database"]["sha256"], backup_util.compute_sha256(backup_db))

        backup_state = Path(manifest["backup_dir"]) / "quota-watchdog-state.json"
        self.assertTrue(backup_state.exists())
        self.assertEqual(manifest["watchdog_state"]["sha256"], backup_util.compute_sha256(backup_state))

        # Verify backup database passes PRAGMA integrity_check
        with sqlite3.connect(str(backup_db)) as conn:
            res = conn.execute("PRAGMA integrity_check").fetchone()
            self.assertEqual(res[0], "ok")
            # Verify data is readable
            row = conn.execute("SELECT goal FROM auto_projects WHERE id=?", (self.project_id,)).fetchone()
            self.assertEqual(row[0], "Production Test Goal")

    def test_verify_and_restore_backup_restores_cleanly(self):
        # 1. Create backup
        manifest = backup_util.create_safe_backup(
            workspace=self.workspace,
            backup_dir=self.backup_dir,
        )
        snap_dir = manifest["backup_dir"]

        # 2. Modify original database to simulate a bad change
        with core.database(self.harness_dir) as db:
            db.execute("UPDATE auto_projects SET goal='Corrupted Goal' WHERE id=?", (self.project_id,))

        with core.database(self.harness_dir) as db:
            row = db.execute("SELECT goal FROM auto_projects WHERE id=?", (self.project_id,)).fetchone()
            self.assertEqual(row["goal"], "Corrupted Goal")

        # 3. Restore backup
        restore_res = backup_util.verify_and_restore_backup(
            backup_snapshot_dir=snap_dir,
            workspace=self.workspace,
        )
        self.assertTrue(restore_res["restored"])

        # 4. Verify original goal is restored
        with core.database(self.harness_dir) as db:
            row = db.execute("SELECT goal FROM auto_projects WHERE id=?", (self.project_id,)).fetchone()
            self.assertEqual(row["goal"], "Production Test Goal")

    def test_restore_fails_closed_on_tampered_checksum(self):
        manifest = backup_util.create_safe_backup(
            workspace=self.workspace,
            backup_dir=self.backup_dir,
        )
        snap_dir = Path(manifest["backup_dir"])

        # Tamper with the backup database
        backup_db = snap_dir / manifest["database"]["filename"]
        with open(backup_db, "a") as f:
            f.write("tampered")

        # Restore must fail with BackupError
        with self.assertRaises(backup_util.BackupError) as ctx:
            backup_util.verify_and_restore_backup(
                backup_snapshot_dir=snap_dir,
                workspace=self.workspace,
            )
        self.assertIn("Database checksum mismatch", str(ctx.exception))

    def test_restore_fails_on_missing_manifest(self):
        empty_dir = self.backup_dir / "empty_backup"
        empty_dir.mkdir()

        with self.assertRaises(backup_util.BackupError) as ctx:
            backup_util.verify_and_restore_backup(
                backup_snapshot_dir=empty_dir,
                workspace=self.workspace,
            )
        self.assertIn("Missing backup manifest", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
