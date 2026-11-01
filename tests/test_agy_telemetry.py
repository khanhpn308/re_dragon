"""Tests for read-only Telegram AGY account/quota telemetry."""
import json
from pathlib import Path
import subprocess
from unittest.mock import patch

import pytest

from re_harness import agy_telemetry as telemetry


@pytest.fixture()
def workspace(tmp_path):
    state = tmp_path / ".re_harness"
    state.mkdir()
    (state / "quota-watchdog.json").write_text(
        json.dumps({"conversation_id": "abc123"}), encoding="utf-8")
    return tmp_path


def test_masked_account_and_status_line_quota(workspace):
    assert telemetry.capture(workspace, {
        "product": "antigravity", "conversation_id": "abc123",
        "email": "someone@gmail.com", "plan_tier": "Pro",
        "model": {"display_name": "Gemini"},
        "quota": {"gemini-5h": {
            "remaining_fraction": 0.8, "reset_time": "2026-11-02T00:00:00Z"}}
    })
    assert "so***e@gmail.com" in telemetry.account_text(workspace)
    assert "someone@gmail.com" not in telemetry.account_text(workspace)
    assert "80.0%" in telemetry.usage_text(workspace, which=lambda _: None)
    assert telemetry.cache_path(workspace).stat().st_mode & 0o777 == 0o600


def test_mismatched_conversation_does_not_identify_active_user(workspace):
    telemetry.capture(workspace, {
        "product": "antigravity", "conversation_id": "different",
        "email": "someone@gmail.com"})
    assert "UNKNOWN" in telemetry.account_text(workspace)
    assert "someone" not in telemetry.account_text(workspace)


def test_non_agy_status_line_rejected(workspace):
    assert not telemetry.capture(workspace, {
        "product": "unknown", "conversation_id": "abc123",
        "email": "someone@gmail.com"})
    assert telemetry.read_cache(workspace) is None


def test_native_usage_rejects_model_turn(workspace):
    data = {"status": "SUCCESS", "num_turns": 0, "command": {
        "name": "usage", "data": {"groups": [
            {"name": "Gemini", "buckets": [
                {"id": "gemini-5h", "window": "5h",
                 "remaining_fraction": 0.875,
                 "reset_time": "2026-11-02T00:00:00Z"}]}]}}}
    assert "87.5%" in telemetry.format_buckets(
        telemetry.parse_native_usage(json.dumps(data)), "test")
    data["num_turns"] = 1
    assert telemetry.parse_native_usage(json.dumps(data)) == []


def test_usage_does_not_spawn_second_cli_when_agent_running(workspace):
    def runner(*args, **kwargs):
        raise AssertionError("Should not spawn agy")
    assert "UNKNOWN" in telemetry.usage_text(
        workspace, running=True, runner=runner)


def test_legacy_cli_cannot_start_usage_probe(workspace):
    calls = []
    def runner(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, "agy 1.1.10", "")
    result = telemetry.usage_text(
        workspace, runner=runner, which=lambda _: "/bin/agy")
    assert "UNKNOWN" in result
    assert len(calls) == 1


def test_install_keeps_existing_statusline(tmp_path):
    settings = tmp_path / ".gemini" / "antigravity-cli" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"statusLine": {"type": "command",
        "command": "my-custom-script"}}), encoding="utf-8")
    with patch.object(Path, "home", return_value=tmp_path):
        with pytest.raises(ValueError, match="statusLine"):
            telemetry.install(tmp_path)
    assert json.loads(settings.read_text())["statusLine"]["command"] == "my-custom-script"
