"""Exercise process transport and timeout handling with local fake agent CLIs."""

from __future__ import annotations

import json
import sys

import pytest

from scripts.commands.agents import agent_runner
from scripts.harness import HarnessError


@pytest.fixture
def fake_cli(tmp_path, monkeypatch):
    script = tmp_path / "fake_agent.py"
    script.write_text(
        "import json, os, sys\n"
        "payload = {'prompt': sys.stdin.buffer.read().decode('utf-8'), "
        "'argv': sys.argv[1:], 'child': os.environ.get('RESEARCH_AGENT_CHILD')}\n"
        "sys.stdout.buffer.write(json.dumps(payload, ensure_ascii=False).encode('utf-8'))\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(agent_runner, "cli_prefix", lambda provider: [sys.executable, str(script)])
    monkeypatch.setattr(agent_runner, "repo_root", lambda: tmp_path)
    return script


@pytest.mark.parametrize("provider", ["codex", "claude"])
def test_prompt_reaches_stdin_without_shell_interpolation(tmp_path, fake_cli, provider):
    content = "\ud55c\uae00 \uc5f0\uad6c \U0001f600\n$(echo injected); `whoami` & | > %PATH% \"quotes\" 'literal'\n"
    prompt = tmp_path / "prompt with spaces.md"
    prompt.write_text(content, encoding="utf-8")
    output = tmp_path / "logs/runner output.log"
    assert agent_runner.run_agent(provider, prompt, output=output, extra_args=["--model", "example"]) == 0
    result = json.loads(output.read_text(encoding="utf-8"))
    assert result["prompt"].replace("\r\n", "\n") == content
    assert content not in result["argv"]
    assert result["child"] == "1"
    assert result["argv"][-2:] == ["--model", "example"]
    if provider == "codex":
        assert result["argv"][:4] == ["exec", "--sandbox", "workspace-write", "-"]
    else:
        assert result["argv"][:3] == ["-p", "--permission-mode", "acceptEdits"]


def test_runner_propagates_failure_exit_and_retains_error_log(tmp_path, fake_cli):
    fake_cli.write_text("import sys\nsys.stderr.write('mock authentication failure\\n')\nsys.exit(7)\n", encoding="utf-8")
    prompt = tmp_path / "prompt.md"
    prompt.write_text("research task", encoding="utf-8")
    assert agent_runner.run_agent("codex", prompt) == 7
    assert "mock authentication failure" in prompt.with_suffix(".runner.log").read_text(encoding="utf-8")


def test_timeout_terminates_process_and_preserves_partial_output(tmp_path, fake_cli, capsys):
    fake_cli.write_text("import time\nprint('started', flush=True)\ntime.sleep(30)\nprint('finished', flush=True)\n", encoding="utf-8")
    prompt = tmp_path / "prompt.md"
    prompt.write_text("research task", encoding="utf-8")
    assert agent_runner.run_agent("claude", prompt, timeout=1) == 124
    log = prompt.with_suffix(".runner.log").read_text(encoding="utf-8")
    assert "started" in log
    assert "finished" not in log
    assert "timed out" in capsys.readouterr().err


@pytest.mark.parametrize("timeout", [0, -1])
def test_invalid_timeout_rejected_before_process_or_log_creation(tmp_path, monkeypatch, timeout):
    def unexpected_cli(provider):
        pytest.fail("Invalid timeouts must not start CLI lookup")
    monkeypatch.setattr(agent_runner, "cli_prefix", unexpected_cli)
    with pytest.raises(HarnessError, match="positive"):
        agent_runner.run_agent("codex", tmp_path / "missing.md", timeout=timeout)
    assert list(tmp_path.iterdir()) == []


def test_missing_agent_cli_has_actionable_error(monkeypatch):
    monkeypatch.setattr(agent_runner.shutil, "which", lambda provider: None)
    with pytest.raises(HarnessError, match="Install and authenticate the codex CLI"):
        agent_runner.cli_prefix("codex")
