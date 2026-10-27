"""Unit tests for Independent Process Supervisor in re_harness.supervisor."""
from __future__ import annotations

import fcntl
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from re_harness import supervisor


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.workspace = Path(self.temp_dir.name)
        self.watch_dir = self.workspace / ".re_harness"
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self.sup = supervisor.Supervisor(self.workspace)

    def test_watchdog_lock_detection(self):
        # Unlocked initially
        self.assertFalse(self.sup.is_watchdog_locked())

        # Acquire lock manually
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

        # Second instance must raise RuntimeError
        sup2 = supervisor.Supervisor(self.workspace)
        with self.assertRaises(RuntimeError):
            sup2.acquire_supervisor_lock()

        handle1.close()

    def test_supervisor_status_reporting(self):
        state_file = self.watch_dir / "quota-watchdog.json"
        state_file.write_text(
            json.dumps({"status": "CONTINUE", "project_id": "proj-xyz", "attempts": 5}),
            encoding="utf8",
        )
        st = self.sup.status()
        self.assertEqual(st["watchdog_status"], "CONTINUE")
        self.assertEqual(st["project_id"], "proj-xyz")
        self.assertFalse(st["heartbeat_is_progress_proof"])

    def test_config_generators(self):
        unit = supervisor.generate_systemd_unit(self.workspace)
        self.assertIn("Description=RE Dragon", unit)
        self.assertIn("RestartPreventExitStatus=0 10 11 12", unit)
        self.assertIn(str(self.workspace), unit)

        xml = supervisor.generate_windows_task_xml(self.workspace, distro="Ubuntu", user="testuser")
        self.assertIn("<Task", xml)
        self.assertIn("-d Ubuntu -u testuser", xml)
        self.assertIn(str(self.workspace), xml)

    @patch("subprocess.Popen")
    def test_run_stops_on_intentional_exit_codes(self, mock_popen):
        # Return NEEDS_USER (11)
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
