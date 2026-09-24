"""Tests for the cross-seed variance audit command."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.commands.experiments import seed_variance
from scripts.commands.experiments.seed_variance import main, run_audit, split_seed_suffix

HEADER = "experiment_id,claim_id,dataset,split,method,baseline_id,metric,value,delta,status,evidence,caveat"

DEFAULT_ROWS = [
    # Stable multi-seed family backing a claim (rel std ~0.001 < 0.05).
    "exp_a_seed_1,C1,ds,test,ours,,acc,0.800,,observed,,",
    "exp_a_seed_2,C1,ds,test,ours,,acc,0.802,,observed,,",
    "exp_a_seed_3,C1,ds,test,ours,,acc,0.801,,observed,,",
    # Unstable multi-seed family (rel std ~0.286 > 0.05).
    "exp_b_seed_1,C2,ds,test,ours,,acc,0.50,,observed,,",
    "exp_b_seed_2,C2,ds,test,ours,,acc,0.90,,observed,,",
    # Single-seed family backing a claim.
    "exp_c,C3,ds,test,ours,,acc,0.75,,observed,,",
    # Single-seed family with no claim (must not warn).
    "exp_d,,ds,test,ours,,acc,0.60,,observed,,",
    # Unparseable value (must be skipped, not crash).
    "exp_e_seed_1,C4,ds,test,ours,,acc,oops,,observed,,",
]


def make_project(tmp_path: Path, rows: list[str], name: str = "unit_project") -> Path:
    root = tmp_path / name
    results = root / "05_results" / "experiment_results.csv"
    results.parent.mkdir(parents=True)
    results.write_text("\n".join([HEADER, *rows]) + "\n", encoding="utf-8")
    return root


def family_by_id(audit: dict, family: str) -> dict:
    matches = [entry for entry in audit["families"] if entry["family"] == family]
    assert len(matches) == 1, f"expected exactly one family {family!r}"
    return matches[0]


def test_split_seed_suffix_strips_only_trailing_token():
    assert split_seed_suffix("exp_a_seed_1") == ("exp_a", "1")
    assert split_seed_suffix("exp_plain") == ("exp_plain", "")
    # Only the trailing suffix is stripped, never an interior one.
    assert split_seed_suffix("exp_seed_1_seed_42") == ("exp_seed_1", "42")


def test_stable_multi_seed_family_has_no_warning(tmp_path):
    root = make_project(tmp_path, DEFAULT_ROWS)
    audit = run_audit(root)
    stable = family_by_id(audit, "exp_a")
    assert stable["n_seeds"] == 3
    assert stable["values"] == [0.800, 0.802, 0.801]
    assert stable["seeds"] == ["1", "2", "3"]
    assert stable["claim_ids"] == ["C1"]
    assert stable["rel_std"] < 0.05
    assert not [f for f in audit["findings"] if f["family"] == "exp_a"]


def test_unstable_family_gets_rel_std_warning(tmp_path):
    root = make_project(tmp_path, DEFAULT_ROWS)
    audit = run_audit(root)
    unstable = family_by_id(audit, "exp_b")
    assert unstable["mean"] == 0.7
    assert unstable["std"] == 0.2  # population stddev of [0.5, 0.9]
    findings = [f for f in audit["findings"] if f["family"] == "exp_b"]
    assert [f["kind"] for f in findings] == ["unstable across seeds"]


def test_single_seed_claim_warns_but_unclaimed_single_seed_does_not(tmp_path):
    root = make_project(tmp_path, DEFAULT_ROWS)
    audit = run_audit(root)
    claimed = [f for f in audit["findings"] if f["family"] == "exp_c"]
    assert [f["kind"] for f in claimed] == ["single-seed claim"]
    assert "C3" in claimed[0]["message"]
    assert not [f for f in audit["findings"] if f["family"] == "exp_d"]


def test_unparseable_value_row_is_skipped_and_reported(tmp_path):
    root = make_project(tmp_path, DEFAULT_ROWS)
    audit = run_audit(root)
    assert audit["rows_skipped"] == 1
    assert audit["skipped_rows"][0]["experiment_id"] == "exp_e_seed_1"
    assert audit["skipped_rows"][0]["value"] == "oops"
    assert not [entry for entry in audit["families"] if entry["family"] == "exp_e"]
    assert audit["rows_total"] == len(DEFAULT_ROWS)
    assert audit["rows_audited"] == len(DEFAULT_ROWS)


def test_strict_exit_code_and_report_writing(tmp_path, monkeypatch, capsys):
    root = make_project(tmp_path, DEFAULT_ROWS)
    monkeypatch.setattr(seed_variance, "project_root", lambda name: root)
    assert main(["--project", "unit_project", "--strict", "--write-report"]) == 1
    out = capsys.readouterr().out
    assert "single-seed claim" in out and "unstable across seeds" in out
    report = root / "05_results" / "seed_variance.md"
    assert report.is_file()
    text = report.read_text(encoding="utf-8")
    assert "| exp_a | acc |" in text
    assert "is not a finite float" in text


def test_strict_returns_zero_when_clean(tmp_path, monkeypatch):
    root = make_project(tmp_path, DEFAULT_ROWS[:3])  # stable claimed family only
    monkeypatch.setattr(seed_variance, "project_root", lambda name: root)
    assert main(["--project", "unit_project", "--strict"]) == 0


def test_json_output_is_machine_readable(tmp_path, monkeypatch, capsys):
    root = make_project(tmp_path, DEFAULT_ROWS)
    monkeypatch.setattr(seed_variance, "project_root", lambda name: root)
    assert main(["--project", "unit_project", "--json"]) == 0
    audit = json.loads(capsys.readouterr().out)
    assert audit["rows_skipped"] == 1
    assert {f["kind"] for f in audit["findings"]} == {"single-seed claim", "unstable across seeds"}
    assert family_by_id(audit, "exp_b")["rel_std"] > 0.05


def test_metric_filter_limits_audited_rows(tmp_path):
    rows = DEFAULT_ROWS + [
        "exp_f_seed_1,C5,ds,test,ours,,f1,0.10,,observed,,",
        "exp_f_seed_2,C5,ds,test,ours,,f1,0.30,,observed,,",
    ]
    root = make_project(tmp_path, rows)
    audit = run_audit(root, metric="f1")
    assert audit["rows_total"] == len(rows)
    assert audit["rows_audited"] == 2
    assert [entry["family"] for entry in audit["families"]] == ["exp_f"]


def test_missing_results_file_is_clean_error(tmp_path, monkeypatch, capsys):
    root = tmp_path / "empty_project"
    root.mkdir()
    monkeypatch.setattr(seed_variance, "project_root", lambda name: root)
    assert main(["--project", "empty_project"]) == 1
    assert "error:" in capsys.readouterr().out


def test_duplicate_rows_warn_and_do_not_mask_single_seed_claims(tmp_path):
    """Append-style result CSVs can record the same run twice; the claim gate
    must count distinct seeds, not rows."""
    root = make_project(tmp_path, [
        "exp_c_seed_1,C3,ds,test,ours,,acc,0.75,,observed,,",
        "exp_c_seed_1,C3,ds,test,ours,,acc,0.75,,observed,,",
    ])
    audit = seed_variance.run_audit(root)
    family = family_by_id(audit, "exp_c")
    assert family["n_seeds"] == 1
    assert family["n_rows"] == 2
    kinds = {finding["kind"] for finding in audit["findings"]}
    assert "single-seed claim" in kinds
    assert "duplicate seed rows" in kinds
