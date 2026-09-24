"""Portable smoke fixtures and resolved scheduler executable coverage."""

from __future__ import annotations

import stat
import subprocess
from types import SimpleNamespace

import pytest

from scripts.commands.baselines import baseline_intake
from scripts.commands.experiments import gpu_scheduler
from scripts.commands.release import smoke_test


def test_fixture_cleanup_removes_readonly_git_objects(tmp_path, monkeypatch):
    monkeypatch.setattr(smoke_test, "repo_root", lambda: tmp_path)
    fixture = tmp_path / "projects" / "ci_smoke_unit"
    obj = fixture / ".git" / "objects" / "fixture"
    obj.parent.mkdir(parents=True)
    obj.write_text("fixture", encoding="utf-8")
    obj.chmod(stat.S_IREAD)
    smoke_test.remove_smoke_tree(fixture)
    assert not fixture.exists()


def test_fixture_cleanup_refuses_non_smoke_project(tmp_path, monkeypatch):
    monkeypatch.setattr(smoke_test, "repo_root", lambda: tmp_path)
    project = tmp_path / "projects" / "template"
    project.mkdir(parents=True)
    with pytest.raises(RuntimeError, match="Refusing cleanup"):
        smoke_test.remove_smoke_tree(project)
    assert project.exists()


def test_gpu_launch_uses_resolved_scheduler_executable(tmp_path, monkeypatch):
    executable = str(tmp_path / "mock tools" / "sbatch.cmd")
    monkeypatch.setattr(gpu_scheduler.shutil, "which", lambda name: executable)
    monkeypatch.setattr(gpu_scheduler, "sbatch_args", lambda root, job: ["sbatch", "--parsable"])
    launches = []
    monkeypatch.setattr(gpu_scheduler, "mark_launched", lambda root, job, ident: launches.append(ident))

    def run(argv, **kwargs):
        assert argv == [executable, "--parsable"]
        return subprocess.CompletedProcess(argv, 0, stdout="424242\n", stderr="")

    monkeypatch.setattr(gpu_scheduler, "subprocess", SimpleNamespace(run=run))
    gpu_scheduler.execute_launch(tmp_path, {"id": "test", "log_path": "logs/test.log"})
    assert launches == ["424242"]


def test_baseline_source_under_workspace_is_stored_as_relative_path(tmp_path, monkeypatch):
    monkeypatch.setattr(baseline_intake, "repo_root", lambda: tmp_path)
    source = tmp_path / "projects" / "fixture" / "source"
    spec = baseline_intake.normalize_spec({"repo_url": str(source)}, 1, "code_agent")
    assert spec.repo_url == "projects/fixture/source"
