"""Offline tests: background compatibility cannot be silently treated as gameplay."""
import json
import subprocess
import unittest
from unittest.mock import patch

from re_harness import windows_background_dispatch as b


class BackgroundDispatchTests(unittest.TestCase):
    def test_probe_and_capture_never_enable_click(self):
        for action in ("probe", "capture"):
            args = b.command(action, r"C:\worker.ps1")
            self.assertNotIn("-EnableInput", args)
            self.assertNotIn("-X", args)
        with self.assertRaisesRegex(ValueError, "Input parameters"):
            b.command("capture", r"C:\worker.ps1", enable_input=True)

    def test_explicit_click_opt_in(self):
        with self.assertRaisesRegex(ValueError, "explicit"):
            b.command("click", r"C:\worker.ps1", x=50, y=70)
        args = b.command("click", r"C:\worker.ps1",
                         x=50, y=70, enable_input=True)
        self.assertEqual(args[-5:], ["-X", "50", "-Y", "70", "-EnableInput"])
        with self.assertRaises(ValueError):
            b.command("click", r"C:\worker.ps1", x=-1, y=3, enable_input=True)

    def test_capture_is_observed_not_gameplay(self):
        payload = {
            "schema":"re-dragon.windows-background.v1",
            "action":"capture", "pid":55, "status":"OBSERVED",
            "gameplay_verified":False,"input_dispatched":False,
            "before":{"sha256":"a"*64,"path":r"C:\evidence\before.png"},
        }
        result = b.parse_result(json.dumps(payload), 0, "capture")
        self.assertEqual(result["status"], "OBSERVED")
        self.assertIs(result["gameplay_verified"], False)
        self.assertEqual(result["acceptance_status"], "NOT_VERIFIED")

    def test_missing_capture_hash_blocks(self):
        payload = {
            "schema":"re-dragon.windows-background.v1",
            "action":"capture", "pid":55, "status":"OBSERVED",
            "gameplay_verified":False,"before":{"sha256":"abc"},
        }
        result = b.parse_result(json.dumps(payload), 0, "capture")
        self.assertEqual(result["status"], "BLOCKED")

    def test_printwindow_blocked_has_no_mouse_effect(self):
        payload = {
            "schema":"re-dragon.windows-background.v1",
            "action":"capture","status":"BLOCKED",
            "input_dispatched":False,
            "error":"PRINTWINDOW_UNUSABLE_FRAME"
        }
        result = b.parse_result(json.dumps(payload), 2, "capture")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIs(result["input_dispatched"], False)

    def test_click_api_accepted_not_gameplay_verified(self):
        payload = {
            "schema":"re-dragon.windows-background.v1",
            "action":"click","pid":55,"status":"OBSERVED",
            "input_dispatched":True,"gameplay_verified":False,
            "before":{"sha256":"a"*64},"after":{"sha256":"b"*64},
            "visual_changed":True,
        }
        result = b.parse_result(json.dumps(payload), 0, "click")
        self.assertEqual(result["status"], "OBSERVED")
        self.assertIs(result["gameplay_verified"], False)
        self.assertEqual(result["acceptance_status"], "NOT_VERIFIED")

    def test_click_timeout_is_unknown_not_safe_to_retry(self):
        def timeout(*args, **kwargs):
            raise subprocess.TimeoutExpired("powershell", 60)
        result = b.run_once("click", x=10, y=20, enable_input=True,
                            runner=timeout, path_converter=lambda _: r"C:\worker.ps1")
        self.assertEqual(result["status"], "BLOCKED")
        self.assertIsNone(result["input_dispatched"])

    def test_no_global_click_via_command(self):
        args = b.command("capture",r"C:\worker.ps1")
        self.assertNotIn("SetForegroundWindow", " ".join(args))
        self.assertNotIn("SetCursorPos", " ".join(args))
