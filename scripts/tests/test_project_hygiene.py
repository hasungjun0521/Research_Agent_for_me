"""Unit tests for the project hygiene scanner."""

from __future__ import annotations

import argparse
import os
import time

from scripts.commands.projects.project_hygiene import (
    remove_stale_lock,
    scan_project,
)
from scripts.harness.state_io import locked_state_file


def hygiene_args(**overrides):
    values = {
        "project": None,
        "all": False,
        "agent": "director",
        "max_report_files": 200,
        "max_report_mb": 200,
        "lock_age_hours": 24.0,
        "stale_hours": 72.0,
        "clean_locks": False,
        "write_report": False,
        "strict": False,
        "json": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def make_project(tmp_path, name="unit_project"):
    root = tmp_path / name
    for relative in (
        "HANDOFF.md",
        "README.md",
        "state/current_state.md",
        "state/next_actions.md",
        "state/agent_memory.md",
        "state/state_doctor.md",
        "state/project_health.md",
    ):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("content\n", encoding="utf-8")
    (root / "09_report").mkdir()
    (root / "09_report" / "README.md").write_text("# Report\n", encoding="utf-8")
    return root


def finding_codes(report):
    return {finding["code"] for finding in report["findings"]}


def test_clean_project_has_no_findings(tmp_path):
    root = make_project(tmp_path)
    report = scan_project(root, hygiene_args())
    assert report["counts"] == {"high": 0, "medium": 0, "low": 0}


def test_missing_diagnostics_and_core_files_are_high(tmp_path):
    root = make_project(tmp_path)
    (root / "state" / "state_doctor.md").unlink()
    (root / "state" / "agent_memory.md").unlink()
    report = scan_project(root, hygiene_args())
    codes = finding_codes(report)
    assert "missing_diagnostic" in codes
    assert "missing_core_file" in codes
    assert report["counts"]["high"] >= 2


def test_report_bloat_and_junk_detection(tmp_path):
    root = make_project(tmp_path)
    cache = root / "09_report" / "src" / "__pycache__"
    cache.mkdir(parents=True)
    (cache / "mod.pyc").write_bytes(b"x")
    (root / "09_report" / "model.ckpt").write_bytes(b"x" * 10)
    (root / "09_report" / "run.log").write_text("log\n", encoding="utf-8")
    report = scan_project(root, hygiene_args(max_report_files=1))
    codes = finding_codes(report)
    assert "report_bloat" in codes
    assert "report_junk" in codes


def test_quarantined_state_files_are_reported(tmp_path):
    root = make_project(tmp_path)
    backup = root / "state" / "loop_summary.json.corrupt-20260610T120000-1"
    backup.write_text("{broken", encoding="utf-8")
    report = scan_project(root, hygiene_args())
    assert "quarantined_state_files" in finding_codes(report)


def test_unexpected_top_level_entries_are_flagged(tmp_path):
    root = make_project(tmp_path)
    (root / "projects").mkdir()
    report = scan_project(root, hygiene_args())
    assert "unexpected_top_level" in finding_codes(report)


def make_old_lock(root, name="state/command_queue.json.lock", age_hours=48.0):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    old = time.time() - age_hours * 3600
    os.utime(path, (old, old))
    return path


def test_permanent_lock_sidecars_are_not_debris_or_removed(tmp_path):
    root = make_project(tmp_path)
    lock = make_old_lock(root)
    report = scan_project(root, hygiene_args())
    assert "lock_debris" not in finding_codes(report)
    report = scan_project(root, hygiene_args(clean_locks=True))
    assert "lock_cleanup_skipped" in finding_codes(report)
    assert report["cleaned_locks"] == []
    assert lock.exists()


def test_clean_locks_never_touches_template(tmp_path):
    root = make_project(tmp_path, name="template")
    lock = make_old_lock(root)
    report = scan_project(root, hygiene_args(clean_locks=True))
    assert lock.exists(), "template must stay scan-only"
    assert "lock_debris" not in finding_codes(report)


def test_remove_stale_lock_skips_lock_held_by_live_process(tmp_path):
    path = tmp_path / "held.lock"
    path.touch()
    old = time.time() - 48 * 3600
    os.utime(path, (old, old))
    with locked_state_file(tmp_path / "held"):
        assert remove_stale_lock(path, cutoff_seconds=3600.0) is False
        assert path.exists()
    assert remove_stale_lock(path, cutoff_seconds=3600.0) is False
    assert path.exists()


def test_fresh_or_nonempty_locks_are_not_debris(tmp_path):
    fresh = tmp_path / "fresh.lock"
    fresh.touch()
    assert remove_stale_lock(fresh, cutoff_seconds=3600.0) is False
    nonempty = tmp_path / "data.lock"
    nonempty.write_text("pid", encoding="utf-8")
    old = time.time() - 48 * 3600
    os.utime(nonempty, (old, old))
    assert remove_stale_lock(nonempty, cutoff_seconds=3600.0) is False
