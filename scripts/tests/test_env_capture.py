"""Tests for reproducibility environment auto-capture."""

from __future__ import annotations

import json
import platform
import subprocess
from pathlib import Path
from types import SimpleNamespace

from scripts.commands.experiments import env_capture
from scripts.commands.experiments.env_capture import main, run_env_capture

STARTER_MANIFEST = {
    "project": "unit_project",
    "exp_id": "exp_001",
    "hypothesis": {"file": "03_experiments/exp_001/hypothesis.md", "claim_id": ""},
    "dataset": {"name": "", "version": "", "path": "", "split": "",
                "checksum": "", "license_or_access_notes": ""},
    "code": {"working_dir": "04_code", "commit": "", "entrypoint": "",
             "config": "03_experiments/exp_001/config.yaml"},
    "environment": {"python": "", "dependencies": "", "container": "", "env_file": ""},
    "randomness": {"seeds": [], "determinism_notes": ""},
    "command": {"train_or_run": "", "analysis": "", "expected_runtime": ""},
    "hardware": {"gpu_type": "", "gpu_count": "", "node": "", "slurm_job": ""},
    "baselines": [],
}


def make_project(tmp_path: Path, exp_id: str = "exp_001",
                 manifest: dict | None = None) -> Path:
    root = tmp_path / "unit_project"
    exp_dir = root / "03_experiments" / exp_id
    exp_dir.mkdir(parents=True)
    if manifest is not None:
        path = exp_dir / "reproducibility_manifest.json"
        path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return root


def fake_subprocess_run(git_status: str = " M scripts/foo.py\n",
                        gpu_lines: str = "NVIDIA A100\nNVIDIA A100\n",
                        fail: frozenset[str] = frozenset()):
    """Hermetic stand-in for subprocess.run covering git/pip/nvidia-smi probes."""

    def run(cmd, **kwargs):  # noqa: ANN001 - mirrors subprocess.run
        tail = cmd[-2:]
        if cmd[:3] == ["git", "rev-parse", "HEAD"]:
            if "git" in fail:
                return subprocess.CompletedProcess(cmd, 128, stdout="", stderr="boom")
            return subprocess.CompletedProcess(cmd, 0, stdout="abc1234\n", stderr="")
        if cmd[:3] == ["git", "status", "--porcelain"]:
            return subprocess.CompletedProcess(cmd, 0, stdout=git_status, stderr="")
        if tail == ["pip", "freeze"]:
            if "pip" in fail:
                raise OSError("no pip")
            return subprocess.CompletedProcess(cmd, 0, stdout="numpy==2.0.0\ntorch==2.3.0\n",
                                               stderr="")
        if cmd[0] == "nvidia-smi":
            if "nvidia-smi" in fail:
                raise FileNotFoundError("nvidia-smi")
            return subprocess.CompletedProcess(cmd, 0, stdout=gpu_lines, stderr="")
        raise AssertionError(f"unexpected probe command: {cmd}")

    return run


def patch_capture_subprocess(monkeypatch, run):
    # Keep mocks local: platform.node() uses subprocess on native Windows.
    monkeypatch.setattr(env_capture, "subprocess", SimpleNamespace(
        run=run, SubprocessError=subprocess.SubprocessError,
    ))


def load_manifest(root: Path, exp_id: str = "exp_001") -> dict:
    path = root / "03_experiments" / exp_id / "reproducibility_manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_fills_empty_observable_fields(tmp_path, monkeypatch):
    root = make_project(tmp_path, manifest=STARTER_MANIFEST)
    patch_capture_subprocess(monkeypatch, fake_subprocess_run())

    report = run_env_capture(root, "exp_001")

    data = load_manifest(root)
    assert data["code"]["commit"] == "abc1234-dirty"
    assert data["environment"]["python"] == platform.python_version()
    assert data["environment"]["dependencies"] == "03_experiments/exp_001/environment_freeze.txt"
    assert data["hardware"]["node"] == platform.node()
    assert data["hardware"]["gpu_type"] == "NVIDIA A100"
    assert data["hardware"]["gpu_count"] == "2"
    freeze = root / "03_experiments" / "exp_001" / "environment_freeze.txt"
    assert freeze.read_text(encoding="utf-8") == "numpy==2.0.0\ntorch==2.3.0\n"
    assert sorted(report["filled"]) == sorted(env_capture.CAPTURED_FIELDS)
    # Untouched non-observable starter fields stay exactly as authored.
    assert data["randomness"] == STARTER_MANIFEST["randomness"]
    assert data["command"] == STARTER_MANIFEST["command"]


def test_clean_tree_commit_has_no_dirty_suffix(tmp_path, monkeypatch):
    root = make_project(tmp_path, manifest=STARTER_MANIFEST)
    patch_capture_subprocess(monkeypatch, fake_subprocess_run(git_status=""))
    run_env_capture(root, "exp_001")
    assert load_manifest(root)["code"]["commit"] == "abc1234"


def test_non_empty_fields_are_preserved_and_reported(tmp_path, monkeypatch):
    manifest = json.loads(json.dumps(STARTER_MANIFEST))
    manifest["code"]["commit"] = "deadbeef"
    manifest["hardware"]["gpu_type"] = "H100"
    root = make_project(tmp_path, manifest=manifest)
    patch_capture_subprocess(monkeypatch, fake_subprocess_run())

    report = run_env_capture(root, "exp_001")

    data = load_manifest(root)
    assert data["code"]["commit"] == "deadbeef"
    assert data["hardware"]["gpu_type"] == "H100"
    assert data["hardware"]["gpu_count"] == "2"  # still filled, was empty
    assert set(report["skipped"]) == {"code.commit", "hardware.gpu_type"}
    actions = {change["field"]: change["action"] for change in report["changes"]}
    assert actions["code.commit"] == "preserved"
    assert actions["hardware.gpu_type"] == "preserved"


def test_failed_probes_leave_fields_untouched(tmp_path, monkeypatch):
    root = make_project(tmp_path, manifest=STARTER_MANIFEST)
    monkeypatch.setattr(
        subprocess, "run",
        fake_subprocess_run(fail=frozenset({"git", "pip", "nvidia-smi"})))

    report = run_env_capture(root, "exp_001")

    data = load_manifest(root)
    assert data["code"]["commit"] == ""
    assert data["environment"]["dependencies"] == ""
    assert data["hardware"]["gpu_type"] == ""
    assert data["hardware"]["gpu_count"] == ""
    assert not (root / "03_experiments" / "exp_001" / "environment_freeze.txt").exists()
    actions = {change["field"]: change["action"] for change in report["changes"]}
    assert actions["code.commit"] == "unavailable"
    assert actions["hardware.gpu_count"] == "unavailable"
    # platform-derived fields still fill without subprocess probes
    assert data["environment"]["python"] == platform.python_version()


def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    root = make_project(tmp_path, manifest=STARTER_MANIFEST)
    manifest_path = root / "03_experiments" / "exp_001" / "reproducibility_manifest.json"
    before = manifest_path.read_bytes()
    patch_capture_subprocess(monkeypatch, fake_subprocess_run())

    report = run_env_capture(root, "exp_001", dry_run=True)

    assert manifest_path.read_bytes() == before
    assert not (root / "03_experiments" / "exp_001" / "environment_freeze.txt").exists()
    assert report["dry_run"] is True
    assert report["written"] == []
    assert "code.commit" in report["filled"]  # plan is still visible


def test_missing_manifest_exits_1_and_points_at_planner(tmp_path, monkeypatch, capsys):
    root = make_project(tmp_path, manifest=None)  # exp dir exists, manifest missing
    monkeypatch.setattr(env_capture, "project_root", lambda name: root)
    patch_capture_subprocess(monkeypatch, fake_subprocess_run())

    assert main(["--project", "unit_project", "--exp-id", "exp_001"]) == 1
    out = capsys.readouterr().out
    assert "error:" in out
    assert "experiment_planner" in out


def test_missing_exp_dir_exits_1(tmp_path, monkeypatch, capsys):
    root = tmp_path / "unit_project"
    (root / "03_experiments").mkdir(parents=True)
    monkeypatch.setattr(env_capture, "project_root", lambda name: root)

    assert main(["--project", "unit_project", "--exp-id", "exp_404"]) == 1
    out = capsys.readouterr().out
    assert "error:" in out
    assert "03_experiments/exp_404" in out


def test_main_json_output_is_machine_readable(tmp_path, monkeypatch, capsys):
    root = make_project(tmp_path, manifest=STARTER_MANIFEST)
    monkeypatch.setattr(env_capture, "project_root", lambda name: root)
    patch_capture_subprocess(monkeypatch, fake_subprocess_run())

    assert main(["--project", "unit_project", "--exp-id", "exp_001", "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["exp_id"] == "exp_001"
    assert report["manifest"] == "03_experiments/exp_001/reproducibility_manifest.json"
    assert "03_experiments/exp_001/environment_freeze.txt" in report["written"]


def test_invalid_exp_id_is_rejected(tmp_path, monkeypatch, capsys):
    root = make_project(tmp_path, manifest=STARTER_MANIFEST)
    monkeypatch.setattr(env_capture, "project_root", lambda name: root)

    assert main(["--project", "unit_project", "--exp-id", "../exp_001"]) == 1
    assert "file-safe" in capsys.readouterr().out


def test_existing_freeze_file_is_never_overwritten(tmp_path, monkeypatch):
    """A pre-existing freeze file is run-host evidence; only the manifest field
    may be pointed at it."""
    root = make_project(tmp_path, manifest=STARTER_MANIFEST)
    freeze = root / "03_experiments" / "exp_001" / "environment_freeze.txt"
    freeze.write_text("original-run-host-torch==2.1.0\n", encoding="utf-8")
    patch_capture_subprocess(monkeypatch, fake_subprocess_run())

    report = run_env_capture(root, "exp_001")

    assert freeze.read_text(encoding="utf-8") == "original-run-host-torch==2.1.0\n"
    data = load_manifest(root)
    assert data["environment"]["dependencies"] == "03_experiments/exp_001/environment_freeze.txt"
    dep_change = next(c for c in report["changes"] if c["field"] == "environment.dependencies")
    assert "preserved" in dep_change["note"]
