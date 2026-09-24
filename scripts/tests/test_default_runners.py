"""Public defaults must not invent vendor runner or account-status commands."""

from scripts.harness.workspace_profile import DEFAULT_PROFILE, validate_profile


def test_runner_defaults_require_explicit_local_configuration():
    runners = DEFAULT_PROFILE["agent_runners"]
    assert runners["default_profile"] == ""
    assert runners["profiles"]
    for spec in runners["profiles"].values():
        assert spec["command"] == []
        assert spec.get("status_command", []) == []
        assert spec.get("json_paths", {}) == {}
    assert validate_profile(DEFAULT_PROFILE) == []
