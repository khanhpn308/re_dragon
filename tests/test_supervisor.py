"""Unit tests for Independent Process Supervisor in re_harness.supervisor."""
from __future__ import annotations

import fcntl
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from re_harness import autonomy, core, supervisor


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.workspace = Path(self.temp_dir.name)
        self.watch_dir = self.workspace / ".re_harness"
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self.harness_dir = self.workspace / ".re_harness_mvp"
        with core.database(self.harness_dir) as db:
            autonomy.migrate(db)
            self.pid = autonomy.start(db, "Production Goal", "Acceptance gates")["project_id"]

        self.state_file = self.watch_dir / "quota-watchdog.json"
        self.state_file.write_text(
            json.dumps({"status": "CONTINUE", "project_id": self.pid, "attempts": 5, "conversation_id": "c-1234"}),
            encoding="utf8",
        )
        self.sup = supervisor.Supervisor(self.workspace, harness_state_dir=self.harness_dir)

    def test_watchdog_lock_detection(self):
        self.assertFalse(self.sup.is_watchdog_locked())
        lock_file = self.watch_dir / "quota-watchdog.lock"
        handle = lock_file.open("a+")
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)

        try:
            self.assertTrue(self.sup.is_watchdog_locked())
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)
            handle.close()

        self.assertFalse(self.sup.is_watchdog_locked())

    def test_supervisor_lock_exclusivity(self):
        handle1 = self.sup.acquire_supervisor_lock()
        self.assertIsNotNone(handle1)

        sup2 = supervisor.Supervisor(self.workspace)
        with self.assertRaises(RuntimeError):
            sup2.acquire_supervisor_lock()

        handle1.close()

    def test_supervisor_status_reporting(self):
        st = self.sup.status()
        self.assertEqual(st["watchdog_status"], "CONTINUE")
        self.assertEqual(st["project_id"], self.pid)
        self.assertFalse(st["heartbeat_is_progress_proof"])

    def test_workspace_binding_validation(self):
        # Valid binding
        binding = supervisor.verify_workspace_binding(self.workspace, harness_state_dir=self.harness_dir)
        self.assertEqual(binding["project_id"], self.pid)

        # Expected project ID match
        supervisor.verify_workspace_binding(self.workspace, expected_project_id=self.pid, harness_state_dir=self.harness_dir)

        # Expected project ID mismatch
        with self.assertRaises(supervisor.WorkspaceBindingError):
            supervisor.verify_workspace_binding(self.workspace, expected_project_id="other-pid", harness_state_dir=self.harness_dir)

        # Non-existent workspace
        with self.assertRaises(supervisor.WorkspaceBindingError):
            supervisor.verify_workspace_binding(self.workspace / "missing")

        # Project is ACCEPTED/closed -> fail closed
        with core.database(self.harness_dir) as db:
            db.execute("UPDATE auto_projects SET status='ACCEPTED' WHERE id=?", (self.pid,))
        with self.assertRaises(supervisor.WorkspaceBindingError):
            supervisor.verify_workspace_binding(self.workspace, harness_state_dir=self.harness_dir)

    def test_config_generators(self):
        unit = supervisor.generate_systemd_unit(self.workspace, harness_state_dir=self.harness_dir)
        self.assertIn("Description=RE Dragon", unit)
        self.assertIn("RestartPreventExitStatus=0 10 11 12", unit)
        self.assertIn(str(self.workspace), unit)
        self.assertIn(self.pid, unit)

        xml = supervisor.generate_windows_task_xml(self.workspace, distro="Ubuntu", user="testuser", harness_state_dir=self.harness_dir)
        self.assertIn("<Task", xml)
        self.assertIn("-d Ubuntu -u testuser", xml)
        self.assertIn(str(self.workspace), xml)
        self.assertIn(self.pid, xml)

    @patch("subprocess.Popen")
    def test_run_stops_on_intentional_exit_codes(self, mock_popen):
        proc = MagicMock()
        proc.wait.return_value = supervisor.EXIT_NEEDS_USER
        mock_popen.return_value = proc

        res = self.sup.run()
        self.assertEqual(res, supervisor.EXIT_NEEDS_USER)
        self.assertEqual(mock_popen.call_count, 1)

    @patch("subprocess.Popen")
    def test_run_stops_on_complete_exit(self, mock_popen):
        proc = MagicMock()
        proc.wait.return_value = supervisor.EXIT_COMPLETE
        mock_popen.return_value = proc

        res = self.sup.run()
        self.assertEqual(res, supervisor.EXIT_COMPLETE)
        self.assertEqual(mock_popen.call_count, 1)


if __name__ == "__main__":
    unittest.main()
