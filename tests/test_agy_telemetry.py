"""Offline tests for safe Telegram Antigravity account/quota telemetry."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from re_harness import agy_telemetry as telemetry


class AgyTelemetryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.tmp.name)
        state = self.workspace / ".re_harness"
        state.mkdir()
        (state / "quota-watchdog.json").write_text(
            json.dumps({"conversation_id": "abc123"}), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_capture_masks_email_and_reports_quota(self):
        self.assertTrue(telemetry.capture(self.workspace, {
            "product": "antigravity", "conversation_id": "abc123",
            "email": "someone@gmail.com", "plan_tier": "Pro",
            "model": {"display_name": "Gemini"},
            "quota": {"gemini-5h": {
                "remaining_fraction": 0.8,
                "reset_time": "2026-11-02T00:00:00Z"}}
        }))
        self.assertIn("so***e@gmail.com", telemetry.account_text(self.workspace))
        self.assertNotIn("someone@gmail.com", telemetry.account_text(self.workspace))
        self.assertIn("80.0%", telemetry.usage_text(self.workspace, which=lambda _: None))
        self.assertEqual(telemetry.cache_path(self.workspace).stat().st_mode & 0o777, 0o600)

    def test_wrong_conversation_cannot_identify_user(self):
        telemetry.capture(self.workspace, {
            "product": "antigravity", "conversation_id": "different",
            "email": "other@example.com"})
        self.assertIn("UNKNOWN", telemetry.account_text(self.workspace))
        self.assertNotIn("other@example.com", telemetry.account_text(self.workspace))

    def test_other_product_rejected(self):
        self.assertFalse(telemetry.capture(self.workspace, {
            "product": "unknown", "conversation_id": "abc123",
            "email": "other@example.com"}))
        self.assertIsNone(telemetry.read_cache(self.workspace))

    def test_native_usage_requires_read_only_command(self):
        data = {"status": "SUCCESS", "num_turns": 0,
                "command": {"name": "usage", "data": {"groups": [
                    {"name": "Gemini", "buckets": [
                        {"id": "gemini-5h", "window": "5h",
                         "remaining_fraction": 0.875,
                         "reset_time": "2026-11-02T00:00:00Z"}]}]}}}
        rows = telemetry.parse_native_usage(json.dumps(data))
        self.assertIn("87.5%", telemetry.format_buckets(rows, "test"))
        data["num_turns"] = 1
        self.assertEqual([], telemetry.parse_native_usage(json.dumps(data)))

    def test_running_does_not_start_another_cli(self):
        def fail(*args, **kwargs):
            self.fail("Unexpected process spawn")
        self.assertIn("UNKNOWN", telemetry.usage_text(
            self.workspace, running=True, runner=fail))

    def test_old_cli_cannot_be_queried(self):
        calls = []
        def runner(args, **kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args, 0, "agy 1.1.10", "")
        self.assertIn("UNKNOWN", telemetry.usage_text(
            self.workspace, runner=runner, which=lambda _: "/bin/agy"))
        self.assertEqual(len(calls), 1)

    def test_install_will_not_replace_statusline(self):
        home = self.workspace / "home"
        config = home / ".gemini" / "antigravity-cli" / "settings.json"
        config.parent.mkdir(parents=True)
        config.write_text(json.dumps({"statusLine": {
            "type": "command", "command": "existing-hook"}}), encoding="utf-8")
        with patch.object(Path, "home", return_value=home):
            with self.assertRaisesRegex(ValueError, "statusLine"):
                telemetry.install(self.workspace)
        self.assertEqual(json.loads(config.read_text())["statusLine"]["command"], "existing-hook")


if __name__ == "__main__":
    unittest.main()
