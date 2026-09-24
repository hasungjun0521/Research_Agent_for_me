"""Tests for the read-only run diff command."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.commands.experiments import run_diff

RESULT_HEADER = "experiment_id,claim_id,dataset,split,method,baseline_id,metric,value,delta,status,evidence,caveat"
CONFIG_A = "experiment:\n  lr: 0.001\n  batch: 8\n"
CONFIG_B = "experiment:\n  lr: 0.0001\n  batch: 8\n"


def make_project(tmp_path: Path, config_a: str = CONFIG_A, config_b: str = CONFIG_B) -> Path:
    root = tmp_path / "unit_project"
    for exp_id, config_text, commit in (("exp_001", config_a, "abc123"), ("exp_002", config_b, "def456")):
        exp_dir = root / "03_experiments" / exp_id
        exp_dir.mkdir(parents=True)
        (exp_dir / "config.yaml").write_text(config_text, encoding="utf-8")
        manifest = {"code": {"commit": commit}, "randomness": {"seeds": [0, 1]}}
        if exp_id == "exp_002":
            manifest["hardware"] = {"gpu_type": "a100"}
        (exp_dir / "reproducibility_manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8")
    results = root / "05_results"
    results.mkdir(parents=True)
    rows = [
        RESULT_HEADER,
        "exp_001,c1,ds,test,ours,base,accuracy,0.80,,observed,ev,",
        "exp_001_seed_1,c1,ds,test,ours,base,accuracy,0.82,,observed,ev,",
        "exp_002,c1,ds,test,ours,base,accuracy,0.90,,observed,ev,",
        "exp_002_seed_1,c1,ds,test,ours,base,accuracy,0.92,,observed,ev,",
        "exp_999,c1,ds,test,other,base,accuracy,0.50,,observed,ev,",
    ]
    (results / "experiment_results.csv").write_text("\n".join(rows) + "\n", encoding="utf-8")
    return root


def _patch_root(monkeypatch, root: Path) -> None:
    monkeypatch.setattr(run_diff, "project_root", lambda name: root)


def _run(monkeypatch, capsys, root: Path, *extra: str) -> tuple[int, str]:
    _patch_root(monkeypatch, root)
    argv = ["--project", "unit_project", "--exp-a", "exp_001", "--exp-b", "exp_002", *extra]
    code = run_diff.main(argv)
    return code, capsys.readouterr().out


def test_diff_reports_config_manifest_and_metric_changes(tmp_path, monkeypatch, capsys):
    root = make_project(tmp_path)
    code, out = _run(monkeypatch, capsys, root)
    assert code == 0
    # 1. config.yaml unified diff hunk.
    assert "-  lr: 0.001" in out
    assert "+  lr: 0.0001" in out
    # 2. nested manifest key shown as a dotted path, including one-sided keys.
    assert "code.commit" in out
    assert "hardware.gpu_type" in out
    assert "randomness.seeds" not in out  # equal nested values are not listed
    # 3. metric means include seed-suffixed rows; value diff is computed.
    assert "0.81 (mean of 2 rows)" in out
    assert "0.91 (mean of 2 rows)" in out
    assert "+0.1" in out
    assert "Matched rows" in out


def test_identical_configs_and_manifests_say_identical(tmp_path, monkeypatch, capsys):
    root = make_project(tmp_path, config_a=CONFIG_A, config_b=CONFIG_A)
    manifest = json.dumps({"code": {"commit": "same"}})
    for exp_id in ("exp_001", "exp_002"):
        (root / "03_experiments" / exp_id / "reproducibility_manifest.json").write_text(
            manifest, encoding="utf-8")
    code, out = _run(monkeypatch, capsys, root)
    assert code == 0
    assert "config.yaml files are identical." in out
    assert "reproducibility_manifest.json values are identical" in out


def test_missing_config_on_one_side_is_noted(tmp_path, monkeypatch, capsys):
    root = make_project(tmp_path)
    (root / "03_experiments" / "exp_002" / "config.yaml").unlink()
    code, out = _run(monkeypatch, capsys, root)
    assert code == 0
    assert "config.yaml is missing for `exp_002`" in out


def test_missing_exp_dir_exits_1(tmp_path, monkeypatch, capsys):
    root = make_project(tmp_path)
    _patch_root(monkeypatch, root)
    code = run_diff.main(
        ["--project", "unit_project", "--exp-a", "exp_001", "--exp-b", "exp_404"])
    out = capsys.readouterr().out
    assert code == 1
    assert "error:" in out
    assert "exp_404" in out


def test_missing_project_exits_1(capsys):
    code = run_diff.main(
        ["--project", "definitely_missing_project", "--exp-a", "a", "--exp-b", "b"])
    assert code == 1
    assert "error:" in capsys.readouterr().out


def test_out_writes_markdown_file_with_parent_mkdir(tmp_path, monkeypatch, capsys):
    root = make_project(tmp_path)
    out_path = tmp_path / "diag" / "nested" / "run_diff.md"
    code, out = _run(monkeypatch, capsys, root, "--out", str(out_path))
    assert code == 0
    assert "saved:" in out
    text = out_path.read_text(encoding="utf-8")
    assert "# Run Diff: exp_001 vs exp_002" in text
    assert "code.commit" in text


def test_manifest_key_cap_is_explicit(tmp_path, monkeypatch, capsys):
    root = make_project(tmp_path)
    big_a = {f"k{i:03d}": i for i in range(120)}
    big_b = {f"k{i:03d}": i + 1 for i in range(120)}
    (root / "03_experiments" / "exp_001" / "reproducibility_manifest.json").write_text(
        json.dumps(big_a), encoding="utf-8")
    (root / "03_experiments" / "exp_002" / "reproducibility_manifest.json").write_text(
        json.dumps(big_b), encoding="utf-8")
    code, out = _run(monkeypatch, capsys, root)
    assert code == 0
    assert "20 more differing keys omitted (showing first 100)" in out


def test_prefix_ids_do_not_collide(tmp_path, monkeypatch, capsys):
    """exp_1 must not absorb exp_10 / exp_100 result rows."""
    root = make_project(tmp_path)
    rows = [
        RESULT_HEADER,
        "exp_1,c1,ds,test,ours,base,accuracy,0.10,,observed,ev,",
        "exp_10,c1,ds,test,ours,base,accuracy,0.99,,observed,ev,",
        "exp_10_seed_1,c1,ds,test,ours,base,accuracy,0.99,,observed,ev,",
    ]
    (root / "05_results" / "experiment_results.csv").write_text(
        "\n".join(rows) + "\n", encoding="utf-8")
    for exp_id in ("exp_1", "exp_10"):
        (root / "03_experiments" / exp_id).mkdir(parents=True)
    _patch_root(monkeypatch, root)
    code = run_diff.main(["--project", "unit_project", "--exp-a", "exp_1", "--exp-b", "exp_10"])
    out = capsys.readouterr().out
    assert code == 0
    assert "`exp_1` -> 1, `exp_10` -> 2" in out


def test_relative_out_resolves_under_project_root(tmp_path, monkeypatch, capsys):
    root = make_project(tmp_path)
    code, _ = _run(monkeypatch, capsys, root, "--out", "05_results/diff.md")
    assert code == 0
    assert (root / "05_results" / "diff.md").is_file()
