"""Unit tests for the project_resume workspace listing mode (--list)."""

from __future__ import annotations

import json
import os

import pytest

from scripts.commands.projects import project_resume

BASE_TIME = 1_700_000_000.0


def make_project(
    projects_dir,
    name,
    *,
    current_state=None,
    next_actions=None,
    mtime=None,
):
    root = projects_dir / name
    (root / "state").mkdir(parents=True)
    touched = []
    if current_state is not None:
        path = root / "state" / "current_state.md"
        path.write_text(current_state, encoding="utf-8")
        touched.append(path)
    if next_actions is not None:
        path = root / "state" / "next_actions.md"
        path.write_text(next_actions, encoding="utf-8")
        touched.append(path)
    if mtime is not None:
        for path in touched:
            os.utime(path, (mtime, mtime))
    return root


@pytest.fixture
def fake_workspace(tmp_path, monkeypatch):
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    monkeypatch.setattr(project_resume, "projects_root", lambda: projects_dir)
    return projects_dir


def row_by_name(rows, name):
    return next(row for row in rows if row["project"] == name)


def test_listing_sorted_by_last_touched_descending(fake_workspace):
    make_project(
        fake_workspace,
        "older",
        current_state="Old work.\n",
        next_actions="- old action\n",
        mtime=BASE_TIME + 100,
    )
    make_project(
        fake_workspace,
        "newest",
        current_state="Fresh work.\n",
        next_actions="- fresh action\n",
        mtime=BASE_TIME + 900,
    )
    make_project(
        fake_workspace,
        "middle",
        current_state="Middle work.\n",
        next_actions="- middle action\n",
        mtime=BASE_TIME + 500,
    )
    rows = project_resume.build_project_listing()
    assert [row["project"] for row in rows] == ["newest", "middle", "older"]


def test_last_touched_uses_max_mtime_across_touch_files(fake_workspace):
    root = make_project(
        fake_workspace,
        "journaled",
        current_state="Stale headline.\n",
        mtime=BASE_TIME + 10,
    )
    journal = root / "05_results" / "experiment_journal.csv"
    journal.parent.mkdir(parents=True)
    journal.write_text("experiment,result_summary\n", encoding="utf-8")
    os.utime(journal, (BASE_TIME + 800, BASE_TIME + 800))
    rows = project_resume.build_project_listing()
    assert row_by_name(rows, "journaled")["last_touched_epoch"] == BASE_TIME + 800


def test_headline_skips_headings_comments_and_blanks(fake_workspace):
    make_project(
        fake_workspace,
        "headline",
        current_state=(
            "# Current State\n"
            "\n"
            "<!-- starter comment -->\n"
            "## Current Stage\n"
            "\n"
            "Running ablation sweep on seed 1.\n"
        ),
    )
    rows = project_resume.build_project_listing()
    assert row_by_name(rows, "headline")["headline"] == "Running ablation sweep on seed 1."


def test_headline_is_truncated_with_explicit_marker(fake_workspace):
    long_line = "x" * 200
    make_project(fake_workspace, "longline", current_state=f"{long_line}\n")
    rows = project_resume.build_project_listing()
    headline = row_by_name(rows, "longline")["headline"]
    assert len(headline) <= 80
    assert headline.endswith("...")
    assert headline.startswith("xxx")


def test_next_action_skips_completed_items(fake_workspace):
    make_project(
        fake_workspace,
        "actions",
        next_actions=(
            "# Next Actions\n"
            "- [x] finished smoke run\n"
            "- launch main sweep\n"
            "- write journal entry\n"
        ),
    )
    rows = project_resume.build_project_listing()
    assert row_by_name(rows, "actions")["next_action"] == "launch main sweep"


def test_missing_files_yield_empty_fields_without_raising(fake_workspace):
    bare = fake_workspace / "bare"
    bare.mkdir()
    rows = project_resume.build_project_listing()
    row = row_by_name(rows, "bare")
    assert row["headline"] == ""
    assert row["next_action"] == ""
    assert row["last_touched"] == ""
    assert row["last_touched_epoch"] == 0.0


def test_malformed_project_never_raises(fake_workspace):
    root = fake_workspace / "broken"
    (root / "state" / "current_state.md").mkdir(parents=True)
    rows = project_resume.build_project_listing()
    row = row_by_name(rows, "broken")
    assert row["headline"] == ""
    assert row["next_action"] == ""


def test_non_directories_and_hidden_entries_are_skipped(fake_workspace):
    make_project(fake_workspace, "real", current_state="Work.\n")
    (fake_workspace / "notes.md").write_text("not a project\n", encoding="utf-8")
    (fake_workspace / ".hidden").mkdir()
    rows = project_resume.build_project_listing()
    assert [row["project"] for row in rows] == ["real"]


def test_template_is_listed_and_marked(fake_workspace, capsys):
    make_project(fake_workspace, "template", current_state="Starter state.\n")
    make_project(fake_workspace, "active", current_state="Active state.\n")
    assert project_resume.main(["--list"]) == 0
    out = capsys.readouterr().out
    assert "template (template)" in out
    assert "active |" in out
    rows = project_resume.build_project_listing()
    assert row_by_name(rows, "template")["template"] is True
    assert row_by_name(rows, "active")["template"] is False


def test_list_json_emits_machine_readable_rows(fake_workspace, capsys):
    make_project(
        fake_workspace,
        "jsonproj",
        current_state="JSON headline.\n",
        next_actions="- json action\n",
        mtime=BASE_TIME + 50,
    )
    assert project_resume.main(["--list", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    row = row_by_name(payload["projects"], "jsonproj")
    assert row["headline"] == "JSON headline."
    assert row["next_action"] == "json action"
    assert row["last_touched_epoch"] == BASE_TIME + 50
    assert row["template"] is False


def test_empty_projects_dir_prints_note(fake_workspace, capsys):
    assert project_resume.main(["--list"]) == 0
    assert "No projects found under projects/." in capsys.readouterr().out


def test_project_still_required_without_list():
    with pytest.raises(SystemExit) as excinfo:
        project_resume.parse_args([])
    assert excinfo.value.code == 2


def test_list_ignores_project_argument(fake_workspace, capsys):
    make_project(fake_workspace, "solo", current_state="Solo state.\n")
    assert project_resume.main(["--list", "--project", "does-not-exist"]) == 0
    captured = capsys.readouterr()
    assert "solo" in captured.out
    assert "ignores --project" in captured.err


MIRROR_TABLE = """<!-- BEGIN GENERATED COMMAND QUEUE MIRROR -->
# Next Actions

## Immediate Next Actions

| Command | Action | Owner Agent | Depends On | Parallel Group | Required Inputs | Expected Outputs | Priority | Status | Done When |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cmd_007 | Run the smoke experiment. | code_agent | - | - | a | b | high | open | Smoke metrics exist. |
| cmd_008 | Analyze results. | data_analyst | cmd_007 | - | a | b | high | open | Analysis written. |
"""


def test_next_action_falls_back_to_generated_mirror_table(fake_workspace):
    make_project(fake_workspace, "mirrored", current_state="Working.\n",
                 next_actions=MIRROR_TABLE)
    rows = project_resume.build_project_listing()
    row = row_by_name(rows, "mirrored")
    assert "cmd_007" in row["next_action"]
    assert "smoke experiment" in row["next_action"]


def test_next_action_supports_numbered_lists_and_strips_checkboxes(fake_workspace):
    make_project(fake_workspace, "numbered", current_state="Working.\n",
                 next_actions="# Next\n1. first numbered action\n2. second\n")
    make_project(fake_workspace, "boxed", current_state="Working.\n",
                 next_actions="# Next\n- [x] done item\n- [ ] open boxed item\n")
    rows = project_resume.build_project_listing()
    assert row_by_name(rows, "numbered")["next_action"] == "first numbered action"
    assert row_by_name(rows, "boxed")["next_action"] == "open boxed item"
