"""Unit tests for the harness workspace-profile core."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.harness.errors import HarnessError
from scripts.harness.workspace_profile import (
    DEFAULT_PROFILE,
    ProfileError,
    deep_merge,
    load_workspace_profile,
    validate_profile,
)


def write_local_profile(root, payload):
    config = root / "config"
    config.mkdir(exist_ok=True)
    (config / "workspace_profile.local.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )


def test_profile_error_is_a_harness_error():
    assert issubclass(ProfileError, HarnessError)


def test_deep_merge_overrides_nested_keys_without_mutating_base():
    base = {"gpu": {"max_user_gpus": 1, "enabled": False}, "display": {"summary_language": "en"}}
    override = {"gpu": {"max_user_gpus": 4}}
    merged = deep_merge(base, override)
    assert merged["gpu"]["max_user_gpus"] == 4
    assert merged["gpu"]["enabled"] is False
    assert base["gpu"]["max_user_gpus"] == 1


def test_validate_profile_rejects_non_string_auto_order_entries():
    profile = json.loads(json.dumps(DEFAULT_PROFILE))
    profile["gpu"]["auto_order"] = [{"oops": True}]
    with pytest.raises(ProfileError, match="auto_order"):
        validate_profile(profile)


def test_validate_profile_rejects_non_bool_agent_limits_enabled():
    profile = json.loads(json.dumps(DEFAULT_PROFILE))
    profile["agent_limits"]["enabled"] = "yes"
    with pytest.raises(ProfileError, match="enabled"):
        validate_profile(profile)


def test_load_workspace_profile_defaults_when_no_config(tmp_path):
    profile = load_workspace_profile(tmp_path)
    assert profile["gpu"]["max_user_gpus"] == DEFAULT_PROFILE["gpu"]["max_user_gpus"]
    assert profile["_meta"]["local_present"] is False


def test_load_workspace_profile_malformed_local_raises_profile_error(tmp_path):
    config = tmp_path / "config"
    config.mkdir()
    (config / "workspace_profile.local.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(ProfileError, match="Invalid JSON"):
        load_workspace_profile(tmp_path)


def test_load_workspace_profile_cache_invalidates_on_file_change(tmp_path):
    write_local_profile(tmp_path, {"gpu": {"max_user_gpus": 3}})
    assert load_workspace_profile(tmp_path)["gpu"]["max_user_gpus"] == 3
    write_local_profile(tmp_path, {"gpu": {"max_user_gpus": 5}})
    assert load_workspace_profile(tmp_path)["gpu"]["max_user_gpus"] == 5


def test_load_workspace_profile_returns_isolated_copies(tmp_path):
    write_local_profile(tmp_path, {"gpu": {"max_user_gpus": 3}})
    first = load_workspace_profile(tmp_path)
    first["gpu"]["max_user_gpus"] = 99
    first["gpu"]["profiles"]["a100"]["mem"] = "tampered"
    second = load_workspace_profile(tmp_path)
    assert second["gpu"]["max_user_gpus"] == 3
    assert second["gpu"]["profiles"]["a100"]["mem"] != "tampered"


def test_load_workspace_profile_unreadable_local_raises_profile_error(tmp_path, monkeypatch):
    config = tmp_path / "config"
    config.mkdir()
    local = config / "workspace_profile.local.json"
    local.write_text(json.dumps({"gpu": {"max_user_gpus": 7}}), encoding="utf-8")
    original_read_bytes = Path.read_bytes

    def read_bytes(path):
        if path == local:
            raise PermissionError("access denied")
        return original_read_bytes(path)

    # chmod(000) is ineffective on Windows and under elevated POSIX users.
    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    with pytest.raises(ProfileError, match="Cannot read workspace profile"):
        load_workspace_profile(tmp_path)
