"""Regression coverage for dispatch readiness and overlapping work paths."""

from argparse import Namespace
from unittest.mock import Mock

import pytest

from scripts.commands.agents import agent_orchestrator as orchestrator


def command(command_id, *, status="open", depends_on=None, outputs=None, inputs=None):
    return {
        "id": command_id,
        "status": status,
        "priority": "high",
        "depends_on": depends_on or [],
        "expected_outputs": outputs or [],
        "required_inputs": inputs or [],
    }


def test_next_skips_blocked_and_unfinished_dependencies():
    blocked = command("a_blocked", status="blocked")
    waiting = command("b_waiting", depends_on=["a_blocked"])
    missing = command("c_missing", depends_on=["unknown"])
    ready = command("z_ready")
    queue = {"commands": [blocked, waiting, missing, ready]}
    assert orchestrator.select_next_command(queue) is ready


def test_next_accepts_completed_dependencies():
    prerequisite = command("first", status="done")
    dependent = command("second", depends_on=["first"])
    assert orchestrator.select_next_command({"commands": [dependent, prerequisite]}) is dependent


@pytest.mark.parametrize("status", ["blocked", "in progress", "done", "deferred"])
def test_explicit_dispatch_rejects_non_open_before_prompt(monkeypatch, tmp_path, status):
    task = command("task", status=status)
    monkeypatch.setattr(orchestrator, "parse_args", lambda: Namespace(
        command="dispatch", project="example", command_id="task", execute=False,
    ))
    monkeypatch.setattr(orchestrator, "project_root", lambda _: tmp_path)
    monkeypatch.setattr(orchestrator, "find_command", lambda *_: task)
    monkeypatch.setattr(orchestrator, "load_command_queue", lambda _: {"commands": [task]})
    write_prompt = Mock()
    monkeypatch.setattr(orchestrator, "write_prompt", write_prompt)
    assert orchestrator.main() == 1
    write_prompt.assert_not_called()


def test_dispatch_rechecks_dependencies_inside_queue_mutation(monkeypatch, tmp_path):
    task = command("task", depends_on=["dependency"])
    queue = {"commands": [task, command("dependency", status="in progress")]}
    monkeypatch.setattr(orchestrator, "mutate_command_queue", lambda _, mutate: mutate(queue))
    with pytest.raises(orchestrator.HarnessError, match="unfinished_dependencies:dependency"):
        orchestrator.mark_dispatched(tmp_path, task, tmp_path / "prompt.md")
    assert task["status"] == "open"


@pytest.mark.parametrize("left_path,right_path", [
    ("04_code/src/", "04_code/src/model.py"),
    ("04_code/src/model.py", "04_code/src/"),
    ("./04_code/src/", "04_code/src/model.py"),
    ("04_code\\src\\", "04_code/src/model.py"),
    ("05_results/data.csv", "05_results/data.csv"),
])
def test_output_conflicts_include_directory_ancestors(left_path, right_path):
    assert orchestrator.has_path_conflict(
        command("left", outputs=[left_path]), command("right", outputs=[right_path]),
    )


def test_output_conflicts_with_nested_input_in_either_direction():
    writer = command("writer", outputs=["04_code/"])
    reader = command("reader", inputs=["04_code/src/model.py"], outputs=["05_results/check.md"])
    assert orchestrator.has_path_conflict(writer, reader)
    assert orchestrator.has_path_conflict(reader, writer)


def test_sibling_paths_and_shared_reads_do_not_conflict():
    assert not orchestrator.has_path_conflict(
        command("left", outputs=["04_code/src/"], inputs=["00_brief/"]),
        command("right", outputs=["04_code/src_extra/"], inputs=["00_brief/"]),
    )


def test_parallel_plan_excludes_nested_output_collision(tmp_path):
    left = command("a", outputs=["04_code/"])
    right = command("b", outputs=["04_code/src/model.py"])
    left["owner_agent"] = "code_agent"
    right["owner_agent"] = "critic"
    assert orchestrator.select_parallel_commands(tmp_path, {"commands": [left, right]}) == [left]
