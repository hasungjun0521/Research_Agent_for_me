"""Tests for preregistration drift verification."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.commands.experiments import preregistration_helper as ph
from scripts.commands.experiments.preregistration_helper import audit_drift

RESULT_HEADER = "experiment_id,claim_id,dataset,split,method,baseline_id,metric,value,delta,status,evidence,caveat"


class _ns:
    def __init__(self, **kw):
        self.__dict__.update(kw)


def _prereg(dataset="cnn_dm", split="test", metric="rougeL", claim="claim_001") -> str:
    return (
        "# Experiment Preregistration\n\n"
        "## Hypothesis\n\n"
        f"- Claim ID: {claim}\n"
        "- Claim tested: X improves Y\n\n"
        "## Metrics\n\n"
        "| Metric | Primary? | Direction | Rationale |\n"
        "| --- | --- | --- | --- |\n"
        f"| {metric} | yes | higher | primary signal |\n\n"
        "## Dataset And Split\n\n"
        f"- Dataset: {dataset}\n"
        f"- Split: {split}\n"
    )


def _make(tmp_path: Path, *, prereg: str | None, rows: list[str] | None,
          status: str | None, exp_id: str = "exp_001") -> Path:
    root = tmp_path / "proj"
    exp = root / "03_experiments" / exp_id
    exp.mkdir(parents=True)
    if prereg is not None:
        (exp / "preregistration.md").write_text(prereg, encoding="utf-8")
    if status is not None:
        (exp / "run_state.json").write_text(json.dumps({"status": status}), encoding="utf-8")
    if rows is not None:
        results = root / "05_results"
        results.mkdir(parents=True)
        (results / "experiment_results.csv").write_text(
            "\n".join([RESULT_HEADER, *rows]) + "\n", encoding="utf-8")
    return root


def test_no_drift_when_results_match_prereg(tmp_path):
    root = _make(tmp_path, prereg=_prereg(), status="succeeded",
                 rows=["exp_001,claim_001,cnn_dm,test,ours,base,rougeL,41.2,1.0,done,ev,"])
    assert audit_drift(root, "exp_001") == []


def test_dataset_drift_detected(tmp_path):
    root = _make(tmp_path, prereg=_prereg(dataset="cnn_dm"), status="succeeded",
                 rows=["exp_001,claim_001,xsum,test,ours,base,rougeL,41.2,1.0,done,ev,"])
    warnings = audit_drift(root, "exp_001")
    assert any("dataset drift" in w for w in warnings)


def test_metric_drift_detected(tmp_path):
    root = _make(tmp_path, prereg=_prereg(metric="rougeL"), status="succeeded",
                 rows=["exp_001,claim_001,cnn_dm,test,ours,base,bleu,41.2,1.0,done,ev,"])
    warnings = audit_drift(root, "exp_001")
    assert any("metric drift" in w for w in warnings)


def test_claim_drift_detected(tmp_path):
    root = _make(tmp_path, prereg=_prereg(claim="claim_001"), status="succeeded",
                 rows=["exp_001,claim_999,cnn_dm,test,ours,base,rougeL,41.2,1.0,done,ev,"])
    warnings = audit_drift(root, "exp_001")
    assert any("claim drift" in w for w in warnings)


def test_succeeded_without_results_flags_missing_evidence(tmp_path):
    root = _make(tmp_path, prereg=_prereg(), status="succeeded", rows=None)
    warnings = audit_drift(root, "exp_001")
    assert any("no rows" in w for w in warnings)


def test_seed_child_rows_count_as_the_experiment(tmp_path):
    root = _make(tmp_path, prereg=_prereg(), status="succeeded", rows=[
        "exp_001_seed_1,claim_001,cnn_dm,test,ours,base,rougeL,41.0,1.0,done,ev,",
        "exp_001_seed_2,claim_001,cnn_dm,test,ours,base,rougeL,41.4,1.0,done,ev,",
    ])
    assert audit_drift(root, "exp_001") == []


def test_planned_run_without_results_is_not_drift(tmp_path):
    root = _make(tmp_path, prereg=_prereg(), status="planned", rows=None)
    assert audit_drift(root, "exp_001") == []


def test_placeholder_metric_does_not_false_positive(tmp_path):
    root = _make(tmp_path, prereg=_prereg(metric="to_be_defined"), status="succeeded",
                 rows=["exp_001,claim_001,cnn_dm,test,ours,base,rougeL,41.2,1.0,done,ev,"])
    warnings = audit_drift(root, "exp_001")
    assert not any("metric drift" in w for w in warnings)


def test_non_dict_run_state_does_not_raise(tmp_path):
    root = _make(tmp_path, prereg=_prereg(), status=None,
                 rows=["exp_001,claim_001,cnn_dm,test,ours,base,rougeL,41.2,1.0,done,ev,"])
    # A valid-JSON-but-non-dict run_state.json must not crash the audit.
    (root / "03_experiments" / "exp_001" / "run_state.json").write_text("[1, 2, 3]", encoding="utf-8")
    assert audit_drift(root, "exp_001") == []


def test_missing_prereg_is_reported(tmp_path):
    root = _make(tmp_path, prereg=None, status="succeeded", rows=None)
    warnings = audit_drift(root, "exp_001")
    assert any("Missing preregistration" in w for w in warnings)


def test_drift_cli_strict_exit_code(tmp_path, monkeypatch, capsys):
    root = _make(tmp_path, prereg=_prereg(dataset="cnn_dm"), status="succeeded",
                 rows=["exp_001,claim_001,xsum,test,ours,base,rougeL,41.2,1.0,done,ev,"])
    monkeypatch.setattr(ph, "project_root", lambda name: root)
    code = ph.drift(_ns(project="proj", exp_id="exp_001", strict=True, json=False))
    assert code == 1
    out = capsys.readouterr().out
    assert "dataset drift" in out
