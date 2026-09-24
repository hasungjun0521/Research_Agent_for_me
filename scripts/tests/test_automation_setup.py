"""Portable setup preserves local choices and session hooks stay bounded."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.commands.release.automation_setup import setup as configure_workspace
from scripts.harness import HarnessError
from tools.research_session_hook import response


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def snapshot(root: Path) -> dict[str, bytes | None]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes() if path.is_file() else None
        for path in root.rglob("*")
    }


@pytest.fixture
def workspace(tmp_path):
    write_json(tmp_path / "config/workspace_profile.example.json", {
        "agent_runners": {
            "default_profile": "",
            "profiles": {"codex": {"command": []}, "claude": {"command": []}},
        },
        "gpu": {"enabled": False},
    })
    skill = tmp_path / ".claude/skills/project-resume/SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("---\nname: project-resume\n---\nResume from durable evidence.\n", encoding="utf-8")
    return tmp_path


def test_dry_run_does_not_create_files_or_directories(workspace):
    before = snapshot(workspace)
    changes = configure_workspace(workspace, dry_run=True)
    assert changes
    assert snapshot(workspace) == before


def test_setup_is_idempotent_and_installs_discoverable_skill(workspace):
    configure_workspace(workspace, provider="claude")
    first = snapshot(workspace)
    configure_workspace(workspace, provider="claude")
    assert snapshot(workspace) == first
    canonical = workspace / ".claude/skills/project-resume/SKILL.md"
    installed = workspace / ".agents/skills/project-resume/SKILL.md"
    assert installed.read_bytes() == canonical.read_bytes()
    profile = json.loads((workspace / "config/workspace_profile.local.json").read_text())
    assert profile["agent_runners"]["default_profile"] == "claude"
    for provider in ("codex", "claude"):
        command = profile["agent_runners"]["profiles"][provider]["command"]
        assert "scripts.commands.agents.agent_runner" in command
        assert command[command.index("--provider") + 1] == provider
        assert command[-1] == "{prompt_file}"


def test_setup_preserves_custom_runners_settings_and_hooks(workspace):
    profile_path = workspace / "config/workspace_profile.local.json"
    original_runner = {"command": ["custom-agent", "{prompt_file}"], "description": "My runner"}
    write_json(profile_path, {
        "agent_runners": {"default_profile": "private", "profiles": {
            "private": {"command": ["private-agent"]}, "codex": original_runner,
        }},
        "gpu": {"enabled": True, "max_user_gpus": 3},
        "agent_output": {"preferred_language": "ko"},
    })
    settings_path = workspace / ".claude/settings.local.json"
    original_hook = {"matcher": "startup", "hooks": [{"type": "command", "command": "custom-hook"}]}
    write_json(settings_path, {
        "permissions": {"allow": ["Read"]},
        "hooks": {"SessionStart": [original_hook], "PostToolUse": [{"hooks": []}]},
    })
    configure_workspace(workspace)
    profile = json.loads(profile_path.read_text())
    assert profile["agent_runners"]["default_profile"] == "private"
    assert profile["agent_runners"]["profiles"]["codex"] == original_runner
    assert profile["agent_runners"]["profiles"]["private"]["command"] == ["private-agent"]
    assert profile["gpu"] == {"enabled": True, "max_user_gpus": 3}
    assert profile["agent_output"]["preferred_language"] == "ko"
    settings = json.loads(settings_path.read_text())
    assert settings["permissions"] == {"allow": ["Read"]}
    assert settings["hooks"]["SessionStart"][0] == original_hook
    assert settings["hooks"]["PostToolUse"] == [{"hooks": []}]
    assert len(settings["hooks"]["SessionStart"]) == 2
    assert len(settings["hooks"]["Stop"]) == 1
    before = snapshot(workspace)
    configure_workspace(workspace, dry_run=True)
    assert snapshot(workspace) == before


@pytest.mark.parametrize("dry_run", [False, True])
def test_conflicting_skill_is_rejected_before_any_write(workspace, dry_run):
    target = workspace / ".agents/skills/project-resume/SKILL.md"
    target.parent.mkdir(parents=True)
    target.write_text("Locally customized skill", encoding="utf-8")
    before = snapshot(workspace)
    with pytest.raises(HarnessError, match="differs from canonical"):
        configure_workspace(workspace, dry_run=dry_run)
    assert snapshot(workspace) == before


def test_skill_symlink_is_rejected_without_overwriting_target(workspace, tmp_path):
    external = tmp_path / "external-skill.md"
    external.write_text("Keep this file", encoding="utf-8")
    target = workspace / ".agents/skills/project-resume/SKILL.md"
    target.parent.mkdir(parents=True)
    try:
        target.symlink_to(external)
    except (OSError, NotImplementedError):
        pytest.skip("Creating symlinks requires platform support or permission")
    with pytest.raises(HarnessError, match="symlink"):
        configure_workspace(workspace)
    assert external.read_text(encoding="utf-8") == "Keep this file"
    assert target.is_symlink()


def test_session_context_lists_projects_without_writing(tmp_path, monkeypatch):
    monkeypatch.delenv("RESEARCH_AGENT_CHILD", raising=False)
    for name in ("template", "zebra", "alpha"):
        (tmp_path / "projects" / name).mkdir(parents=True)
    (tmp_path / "projects/not_a_project.txt").write_text("ignore", encoding="utf-8")
    before = snapshot(tmp_path)
    result = response({"hook_event_name": "SessionStart"}, tmp_path)
    context = result["hookSpecificOutput"]["additionalContext"]
    assert "Projects: alpha, zebra" in context
    assert "not_a_project" not in context
    assert "project_resume" in context
    assert snapshot(tmp_path) == before


def test_stop_hook_has_one_reminder_and_recursion_guard(tmp_path, monkeypatch):
    monkeypatch.delenv("RESEARCH_AGENT_CHILD", raising=False)
    assert response({"hook_event_name": "Stop"}, tmp_path)["decision"] == "block"
    assert response({"hook_event_name": "Stop", "stop_hook_active": True}, tmp_path) == {}
    assert response({"hook_event_name": "Unknown"}, tmp_path) == {}
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("event", ["SessionStart", "Stop"])
def test_child_runner_suppresses_all_session_hooks(tmp_path, monkeypatch, event):
    monkeypatch.setenv("RESEARCH_AGENT_CHILD", "1")
    assert response({"hook_event_name": event}, tmp_path) == {}
    assert list(tmp_path.iterdir()) == []
