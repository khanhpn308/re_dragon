"""Durable Telegram launch output should survive an early process exit."""
from __future__ import annotations

import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT=Path(__file__).resolve().parent.parent
WRAPPER=ROOT/"scripts"/"telegram-supervised.sh"


class TelegramLauncherTests(unittest.TestCase):
    def test_durable_log_survives_failed_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            log=Path(tmp)/"secret"/"telegram.log"
            run=subprocess.run(["bash",str(WRAPPER),str(log),
                                "bash","-c","echo simulated-init-failure >&2; exit 42"],
                               text=True,capture_output=True,timeout=10)
            self.assertEqual(run.returncode,42)
            self.assertIn("simulated-init-failure",log.read_text())
            self.assertNotIn("simulated-init-failure",run.stdout)
            self.assertEqual(stat.S_IMODE(log.stat().st_mode),0o600)

    def test_successful_worker_output_is_persisted(self):
        with tempfile.TemporaryDirectory() as tmp:
            log=Path(tmp)/"telegram.log"
            run=subprocess.run(["bash",str(WRAPPER),str(log),"bash","-c",
                                "echo connected; echo warning >&2"],
                               text=True,capture_output=True,timeout=10)
            self.assertEqual(run.returncode,0)
            self.assertIn("connected",log.read_text())
            self.assertIn("warning",log.read_text())


if __name__=="__main__":
    unittest.main()
