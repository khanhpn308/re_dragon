"""Offline Windows survey dispatcher tests: NEVER click a real desktop."""
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from re_harness import windows_worker_dispatch as worker


class WindowsWorkerDispatchTests(unittest.TestCase):
    def test_click_requires_explicit_coordinates(self):
        with self.assertRaises(ValueError):
            worker.command("click", r"C:\work\worker.ps1")
        with self.assertRaises(ValueError):
            worker.command("click", r"C:\work\worker.ps1", x=-1, y=100)
        with self.assertRaises(ValueError):
            worker.command("capture", r"C:\work\worker.ps1", x=1)

    def test_click_is_explicit_and_pinned_to_game(self):
        argv = worker.command("click", r"C:\work\worker.ps1", x=101, y=202)
        self.assertEqual(argv[:5], [
            "powershell.exe", "-NoProfile", "-NonInteractive",
            "-ExecutionPolicy", "Bypass"
        ])
        self.assertEqual(argv[argv.index("-ProcessName") + 1], "DragonBall")
        self.assertEqual(argv[-5:], ["-X", "101", "-Y", "202", "-EnableInput"])

    def test_probe_never_enables_input(self):
        for action in ("probe", "capture", "fingerprint"):
            self.assertNotIn("-EnableInput", worker.command(
                action, r"C:\work\worker.ps1"))
        with self.assertRaises(ValueError):
            worker.command("probe", r"C:\work\worker.ps1", process_name="bad;name")

    def test_bad_output_is_never_verification(self):
        for raw, code in [("", 0), ("not JSON", 0),
                          ('{"schema":"other","status":"OBSERVED"}', 0),
                          ('{"schema":"re-dragon.windows-worker.v1","status":"OBSERVED"}', 1)]:
            result = worker.parse_result(raw, code)
            self.assertEqual(result["status"], "BLOCKED")

    def test_proper_output_is_only_observation(self):
        payload = {
            "schema": "re-dragon.windows-worker.v1", "status": "OBSERVED",
            "action": "capture", "pid": 4212,
            "before": {"sha256": "123abc", "path": "C:\\evidence\\before.png"},
        }
        result = worker.parse_result(json.dumps(payload), 0)
        self.assertEqual(result["evidence_status"], "AGENT_OBSERVED")
        self.assertEqual(result["acceptance_status"], "NOT_VERIFIED")

    def test_missing_process_provenance_blocks(self):
        raw = json.dumps({"schema": "re-dragon.windows-worker.v1",
                          "status": "OBSERVED", "action": "probe"})
        self.assertEqual(worker.parse_result(raw, 0)["status"], "BLOCKED")

    def test_wsl_script_path_conversion(self):
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "worker.ps1"
            script.write_text("# test", encoding="utf-8")
            seen = []
            def runner(args, **kwargs):
                seen.append(args)
                return subprocess.CompletedProcess(args, 0, "C:\\work\\worker.ps1\n", "")
            self.assertEqual(worker.convert_script_path(
                script, windows=False, runner=runner), r"C:\work\worker.ps1")
            self.assertEqual(seen[0][0:2], ["wslpath", "-w"])

    def test_no_shell_string_interpolation(self):
        argv = worker.command("capture", r"C:\Game Files\worker.ps1",
                              process_name="DragonBall")
        self.assertIsInstance(argv, list)
        self.assertEqual(argv[argv.index("-File") + 1],
                         r"C:\Game Files\worker.ps1")

    def test_mocked_dispatch_does_not_assert_gameplay_success(self):
        calls = []
        def fake_runner(args, **kwargs):
            calls.append(args)
            raw = json.dumps({"schema": "re-dragon.windows-worker.v1",
                              "status": "OBSERVED", "action": "probe",
                              "pid": 777, "foreground": True})
            return subprocess.CompletedProcess(args, 0, raw, "")
        result = worker.run_once("probe", path_converter=lambda _: r"C:\w.ps1",
                                 runner=fake_runner)
        self.assertEqual(result["acceptance_status"], "NOT_VERIFIED")
        self.assertNotIn("-EnableInput", calls[0])

    def test_one_action_timeout_does_not_change_harness(self):
        def fake_runner(*args, **kwargs):
            raise subprocess.TimeoutExpired("powershell.exe", 60)
        outcome = worker.run_once("probe", path_converter=lambda _: r"C:\w.ps1",
                                  runner=fake_runner)
        self.assertEqual(outcome["status"], "BLOCKED")
        self.assertEqual(outcome["error"], "WINDOWS_PRIMITIVE_TIMEOUT")
