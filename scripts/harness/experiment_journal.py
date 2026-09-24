#!/usr/bin/env python3
"""Shared writer for the working experiment journal."""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from scripts.harness import now_iso

DEFAULT_ANALYSIS = (
    "analysis pending; explain why performance improved, regressed, or stayed flat before strengthening claims"
)

JOURNAL_INTRO = (
    "Append one row whenever experiment results are recorded. Keep this as "
    "the single running ledger for why each experiment was run, what "
    "happened, and why the result likely moved."
)

JOURNAL_HEADER = (
    "| Updated At | Experiment | Rationale | Dataset | Method | Baseline | "
    "Result Summary | Result Analysis | Evidence | Caveat |"
)
JOURNAL_CSV_HEADER = [
    "updated_at",
    "experiment",
    "rationale",
    "dataset",
    "method",
    "baseline",
    "result_summary",
    "result_analysis",
    "evidence",
    "caveat",
]


def markdown_cell(value: Any) -> str:
    text = str(value or "").replace("\n", " ").strip()
    return text.replace("|", "\\|") or "-"


def experiment_journal_path(root: Path) -> Path:
    return root / "05_results" / "experiment_journal.md"


def experiment_journal_csv_path(root: Path) -> Path:
    return root / "05_results" / "experiment_journal.csv"


def experiment_analysis_path(root: Path, exp_id: str) -> Path:
    candidate = Path(exp_id)
    if not exp_id or candidate.is_absolute() or len(candidate.parts) != 1 or ".." in candidate.parts:
        raise ValueError("exp_id must be a single project-local experiment folder name")
    return root / "03_experiments" / exp_id / "analysis.md"


def ensure_experiment_journal(root: Path) -> Path:
    path = experiment_journal_path(root)
    if path.is_file() and path.read_text(encoding="utf-8", errors="replace").strip():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join([
            "# Experiment Journal",
            "",
            JOURNAL_INTRO,
            "",
            JOURNAL_HEADER,
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]) + "\n",
        encoding="utf-8",
    )
    return path


def ensure_experiment_journal_csv(root: Path) -> Path:
    path = experiment_journal_csv_path(root)
    if path.is_file() and path.read_text(encoding="utf-8", errors="replace").strip():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=JOURNAL_CSV_HEADER)
        writer.writeheader()
    return path


def ensure_experiment_analysis(root: Path, exp_id: str) -> Path:
    path = experiment_analysis_path(root, exp_id)
    if path.is_file() and path.read_text(encoding="utf-8", errors="replace").strip():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join([
            f"# Experiment {exp_id} Analysis",
            "",
            "## Result Summary",
            "",
            "State what was observed after running the experiment.",
            "",
            "## Performance Movement Analysis",
            "",
            "- Improved/regressed/flat:",
            "- Most likely cause:",
            "- Evidence supporting that cause:",
            "- Alternative explanations:",
            "- What would falsify this explanation:",
        ]) + "\n",
        encoding="utf-8",
    )
    return path


def append_experiment_journal_row(
    root: Path,
    *,
    exp_id: str,
    result_summary: str,
    rationale: str = "",
    dataset: str = "",
    method: str = "",
    baseline_id: str = "",
    result_analysis: str = "",
    evidence: str = "",
    caveat: str = "",
    timestamp: str | None = None,
) -> None:
    updated_at = timestamp or now_iso()
    path = ensure_experiment_journal(root)
    analysis = result_analysis or DEFAULT_ANALYSIS
    line = (
        f"| {markdown_cell(updated_at)} | {markdown_cell(exp_id)} | "
        f"{markdown_cell(rationale or 'not recorded')} | "
        f"{markdown_cell(dataset or 'not recorded')} | "
        f"{markdown_cell(method or 'not recorded')} | "
        f"{markdown_cell(baseline_id or 'none')} | "
        f"{markdown_cell(result_summary)} | {markdown_cell(analysis)} | "
        f"{markdown_cell(evidence)} | {markdown_cell(caveat)} |"
    )
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    csv_path = ensure_experiment_journal_csv(root)
    with csv_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=JOURNAL_CSV_HEADER)
        writer.writerow({
            "updated_at": updated_at,
            "experiment": exp_id,
            "rationale": rationale or "not recorded",
            "dataset": dataset or "not recorded",
            "method": method or "not recorded",
            "baseline": baseline_id or "none",
            "result_summary": result_summary,
            "result_analysis": analysis,
            "evidence": evidence,
            "caveat": caveat,
        })


def append_experiment_analysis_note(
    root: Path,
    *,
    exp_id: str,
    result_summary: str,
    result_analysis: str = "",
    rationale: str = "",
    dataset: str = "",
    method: str = "",
    baseline_id: str = "",
    evidence: str = "",
    caveat: str = "",
    timestamp: str | None = None,
) -> None:
    updated_at = timestamp or now_iso()
    analysis = result_analysis or DEFAULT_ANALYSIS
    path = ensure_experiment_analysis(root, exp_id)
    lines = [
        "",
        f"## Result Analysis Checkpoint - {updated_at}",
        "",
        f"- Result summary: {result_summary or 'not recorded'}",
        f"- Result analysis: {analysis}",
        f"- Rationale: {rationale or 'not recorded'}",
        f"- Dataset: {dataset or 'not recorded'}",
        f"- Method: {method or 'not recorded'}",
        f"- Baseline: {baseline_id or 'none'}",
        f"- Evidence: {evidence or 'not recorded'}",
        f"- Caveat: {caveat or 'none'}",
    ]
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")
