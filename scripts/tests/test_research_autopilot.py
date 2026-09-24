"""Bounded autonomy tests use local fake agents and never launch paid runners."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from scripts.commands.agents import agent_orchestrator
from scripts.commands.research import research_autopilot as autopilot


def task(command_id="task", **overrides):
    result = {"id": command_id, "status": "open", "priority": "high",
              "owner_agent": "director", "expected_outputs": ["evidence.md"]}
    result.update(overrides)
    return result


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "research"
    root.mkdir()
    queue = {"commands": []}
    monkeypatch.setattr(autopilot, "load_command_queue", lambda _: queue)
    monkeypatch.setattr(autopilot, "render_prompt", lambda *_: "Test task")
    monkeypatch.setattr(autopilot, "refresh_context", Mock(), raising=False)
    def dispatch(_root, command, _prompt):
        command["status"] = "in progress"
    def finish(_root, command_id, status, _note, _outputs):
        next(c for c in queue["commands"] if c["id"] == command_id)["status"] = status
    monkeypatch.setattr(autopilot, "mark_dispatched", dispatch)
    monkeypatch.setattr(autopilot, "finish_command", finish)
    monkeypatch.setattr(autopilot, "run_agent", Mock(side_effect=AssertionError("No real runner allowed")))
    return root, queue


def run(root, **overrides):
    options = {"provider": "codex", "max_steps": 3, "timeout": 30, "max_seconds": 100}
    options.update(overrides)
    return autopilot.execute(root, **options)


def journal(root):
    paths = list((root / "state/sessions").glob("autopilot_*/run.json"))
    assert len(paths) == 1
    assert not (root / "state/sessions/autopilot.lock").exists()
    return json.loads(paths[0].read_text(encoding="utf-8"))


def test_plan_excludes_missing_vote_and_unfinished_dependencies(workspace, monkeypatch):
    root, queue = workspace
    queue["commands"] = [task("vote", requires_vote=True),
                         task("dependent", depends_on=["missing"]), task("ready")]
    monkeypatch.setattr(agent_orchestrator, "command_has_approved_vote", lambda *_: False)
    result = autopilot.plan(root)
    assert result["next"] == "ready"
    reasons = {item["id"]: " ".join(item["reasons"]) for item in result["excluded"]}
    assert "approved vote" in reasons["vote"]
    assert "unfinished_dependencies:missing" in reasons["dependent"]


def test_active_native_work_stops_competing_execution(workspace):
    root, queue = workspace
    queue["commands"] = [task("active", status="in progress"), task("ready")]
    result = run(root)
    assert result["status"] == "needs_attention"
    assert result["steps"] == []
    autopilot.run_agent.assert_not_called()
    assert journal(root)["readiness"]["active"] == ["active"]


@pytest.mark.parametrize("evidence", ["missing", "unchanged", "directory"])
def test_closeout_requires_changed_concrete_evidence(workspace, evidence):
    root, queue = workspace
    command = task(status="done")
    queue["commands"] = [command]
    if evidence == "unchanged":
        (root / "evidence.md").write_text("old", encoding="utf-8")
    elif evidence == "directory":
        (root / "evidence.md").mkdir()
    before = autopilot.outputs_snapshot(root, command)
    assert autopilot.closeout_error(root, command, before)


def test_closeout_accepts_changed_evidence_only_after_explicit_finish(workspace):
    root, queue = workspace
    command = task()
    queue["commands"] = [command]
    before = autopilot.outputs_snapshot(root, command)
    (root / "evidence.md").write_text("verified", encoding="utf-8")
    assert "explicitly settle" in autopilot.closeout_error(root, command, before)
    command["status"] = "done"
    assert autopilot.closeout_error(root, command, before) == ""


def test_output_snapshot_rejects_project_escape(workspace):
    root, _queue = workspace
    with pytest.raises(autopilot.HarnessError, match="escapes project"):
        autopilot.outputs_snapshot(root, task(expected_outputs=["../outside.md"]))


def test_step_limit_bounds_agent_and_persists_journal(workspace, monkeypatch):
    root, queue = workspace
    queue["commands"] = [task("first")]
    calls = []
    def agent(_provider, _prompt, *, timeout):
        calls.append(timeout)
        current = next(c for c in queue["commands"] if c["status"] == "in progress")
        (root / "evidence.md").write_text(current["id"], encoding="utf-8")
        current["status"] = "done"
        queue["commands"].append(task("next_" + str(len(calls))))
        return 0
    monkeypatch.setattr(autopilot, "run_agent", agent)
    result = run(root, max_steps=2)
    assert result["status"] == "step_limit"
    assert len(calls) == 2
    saved = journal(root)
    assert saved["status"] == "step_limit"
    assert [step["status"] for step in saved["steps"]] == ["done", "done"]
    assert saved["finished_at"]


def test_timeout_exit_blocks_command_and_releases_lock(workspace, monkeypatch):
    root, queue = workspace
    queue["commands"] = [task()]
    agent = Mock(return_value=124)
    monkeypatch.setattr(autopilot, "run_agent", agent)
    result = run(root)
    assert result["status"] == "needs_attention"
    assert result["steps"][0]["exit_code"] == 124
    assert queue["commands"][0]["status"] == "blocked"
    assert journal(root)["steps"][0]["note"] == "Runner exited 124."


def test_elapsed_limit_prevents_agent_launch(workspace, monkeypatch):
    root, queue = workspace
    queue["commands"] = [task()]
    ticks = iter([0.0, 5.0])
    monkeypatch.setattr(autopilot.time, "monotonic", lambda: next(ticks, 5.0))
    assert run(root, max_seconds=1)["status"] == "time_limit"
    autopilot.run_agent.assert_not_called()
    assert journal(root)["status"] == "time_limit"


def test_runner_exception_records_interruption_and_releases_lock(workspace, monkeypatch):
    root, queue = workspace
    queue["commands"] = [task()]
    monkeypatch.setattr(autopilot, "run_agent", Mock(side_effect=OSError("runner missing")))
    with pytest.raises(OSError, match="runner missing"):
        run(root)
    assert journal(root)["status"] == "interrupted"


def test_existing_autopilot_lock_is_preserved(workspace):
    root, _queue = workspace
    session = root / "state/sessions"
    session.mkdir(parents=True)
    lock = session / "autopilot.lock"
    lock.write_text("12345", encoding="utf-8")
    with pytest.raises(autopilot.HarnessError, match="already owns"):
        run(root)
    assert lock.read_text(encoding="utf-8") == "12345"
    autopilot.run_agent.assert_not_called()


def test_journal_failure_still_releases_owned_lock(workspace, monkeypatch):
    root, _queue = workspace
    monkeypatch.setattr(autopilot, "atomic_write_json", Mock(side_effect=OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        run(root)
    assert not (root / "state/sessions/autopilot.lock").exists()


@pytest.mark.parametrize("coordination_path", [
    "state/command_queue.json", "state/current_state.md", "HANDOFF.md", "README.md",
    "./state/command_queue.json",
])
def test_coordination_only_change_does_not_count_as_research_evidence(workspace, coordination_path):
    root, queue = workspace
    command = task(status="done", expected_outputs=[coordination_path, "evidence.md"])
    queue["commands"] = [command]
    (root / "evidence.md").write_text("unchanged substantive evidence", encoding="utf-8")
    coordination = root / coordination_path
    coordination.parent.mkdir(parents=True, exist_ok=True)
    coordination.write_text("before", encoding="utf-8")
    before = autopilot.outputs_snapshot(root, command)
    coordination.write_text("after", encoding="utf-8")
    assert autopilot.closeout_error(root, command, before)


def test_execute_refreshes_context_once_before_agent(workspace, monkeypatch):
    root, queue = workspace
    queue["commands"] = [task()]
    events = []
    def refresh(project, session, timeout):
        assert project == root
        assert session.is_dir()
        assert 0 < timeout <= 100
        events.append("refresh")
    def agent(*_args, **_kwargs):
        events.append("agent")
        return 124
    monkeypatch.setattr(autopilot, "refresh_context", refresh)
    monkeypatch.setattr(autopilot, "run_agent", agent)
    run(root)
    assert events == ["refresh", "agent"]


def test_refresh_context_runs_resume_doctor_health_in_order_with_logs(tmp_path, monkeypatch):
    root = tmp_path / "project"
    session = root / "state/sessions/check"
    session.mkdir(parents=True)
    calls = []
    def subprocess_run(argv, **kwargs):
        calls.append(argv)
        assert 0 < kwargs["timeout"] <= 17
        kwargs["stdout"].write("durable preflight output\n")
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(autopilot.subprocess, "run", subprocess_run)
    autopilot.refresh_context(root, session, timeout=17)
    assert [argv[2] for argv in calls] == [
        "scripts.commands.projects.project_resume",
        "scripts.commands.projects.state_doctor",
        "scripts.commands.projects.project_health",
    ]
    assert all(argv[3:5] == ["--project", "project"] for argv in calls)
    assert "--write-report" in calls[1]
    assert "--write" in calls[2]
    logs = list(session.rglob("*.log"))
    assert logs
    assert "".join(path.read_text(encoding="utf-8") for path in logs).count("durable preflight output") == 3


def test_refresh_context_failure_stops_next_checks_and_keeps_log(tmp_path, monkeypatch):
    root = tmp_path / "project"
    session = root / "state/sessions/check"
    session.mkdir(parents=True)
    calls = []
    def subprocess_run(argv, **kwargs):
        calls.append(argv)
        kwargs["stdout"].write("preflight failed\n")
        return SimpleNamespace(returncode=9)
    monkeypatch.setattr(autopilot.subprocess, "run", subprocess_run)
    with pytest.raises(autopilot.HarnessError):
        autopilot.refresh_context(root, session, timeout=17)
    assert len(calls) == 1
    assert any("preflight failed" in p.read_text(encoding="utf-8") for p in session.rglob("*.log"))


def test_refresh_context_timeout_preserves_diagnostic_log(tmp_path, monkeypatch):
    root = tmp_path / "project"
    session = root / "state/sessions/check"
    session.mkdir(parents=True)
    def subprocess_run(argv, **kwargs):
        kwargs["stdout"].write("partial diagnostic output\n")
        raise autopilot.subprocess.TimeoutExpired(argv, kwargs["timeout"])
    monkeypatch.setattr(autopilot.subprocess, "run", subprocess_run)
    with pytest.raises(autopilot.HarnessError, match="timed out"):
        autopilot.refresh_context(root, session, timeout=17)
    assert any("partial diagnostic output" in p.read_text(encoding="utf-8") for p in session.rglob("*.log"))
