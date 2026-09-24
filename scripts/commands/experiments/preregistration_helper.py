#!/usr/bin/env python3
"""Write and audit experiment preregistrations before execution."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from scripts.harness.state import (
    HarnessError,
    append_agent_event,
    project_root,
    update_agent_status,
)
from scripts.harness.workflow_hooks import refresh_report_index

REQUIRED_MARKERS = {
    "Claim ID": "- Claim ID:",
    "Claim tested": "- Claim tested:",
    "Directional expectation": "- Directional expectation:",
    "Support rule": "- What would count as support:",
    "Falsification rule": "- What would weaken or falsify the claim:",
    "Success criteria": "| Criterion | Required Signal | Evidence File | Status |",
    "Failure criteria": "| Failure Mode | Falsifying Signal | Evidence File | Mitigation |",
    "Metrics": "| Metric | Primary? | Direction | Rationale |",
    "Dataset": "- Dataset:",
    "Split": "- Split:",
    "Smoke command": "- Smoke command:",
    "Smoke expected output": "- Smoke expected output:",
    "Smoke check procedure": "- Smoke check procedure:",
    "Planned analysis": "- Primary comparison:",
    "Decision rule": "## Decision Rule",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or audit an experiment preregistration.")
    sub = parser.add_subparsers(dest="command", required=True)

    write = sub.add_parser("write", help="Write a completed preregistration skeleton.")
    write.add_argument("--project", required=True)
    write.add_argument("--agent", default="experiment_designer")
    write.add_argument("--exp-id", required=True)
    write.add_argument("--claim-id", required=True)
    write.add_argument("--claim", required=True)
    write.add_argument("--expectation", required=True)
    write.add_argument("--support", required=True)
    write.add_argument("--falsify", required=True)
    write.add_argument("--success", required=True, help="Criterion text for the primary success row.")
    write.add_argument("--failure", required=True, help="Failure mode text for the primary failure row.")
    write.add_argument("--baseline", default="not required for first diagnostic")
    write.add_argument("--metric", required=True)
    write.add_argument("--metric-direction", default="higher")
    write.add_argument("--dataset", required=True)
    write.add_argument("--split", required=True)
    write.add_argument("--smoke-command", default="to_be_defined")
    write.add_argument("--smoke-expected-output", default="to_be_defined")
    write.add_argument("--smoke-check-procedure", default="to_be_defined")
    write.add_argument("--analysis", required=True)
    write.add_argument("--confounder", default="Dataset leakage or baseline mismatch.")
    write.add_argument("--decision-rule", required=True)

    audit = sub.add_parser("audit", help="Check that preregistration has the required content.")
    audit.add_argument("--project", required=True)
    audit.add_argument("--exp-id", required=True)
    audit.add_argument("--strict", action="store_true")
    audit.add_argument("--json", action="store_true")

    drift = sub.add_parser(
        "drift",
        help="Check that the executed experiment matches its preregistration (dataset, metric, claim, status).")
    drift.add_argument("--project", required=True)
    drift.add_argument("--exp-id", required=True)
    drift.add_argument("--strict", action="store_true")
    drift.add_argument("--json", action="store_true")

    return parser.parse_args()


def prereg_path(root: Path, exp_id: str) -> Path:
    return root / "03_experiments" / exp_id / "preregistration.md"


def sync_preregistration_agent(root: Path, args: argparse.Namespace) -> None:
    output = prereg_path(root, args.exp_id).relative_to(root).as_posix()
    task = f"Preregistered experiment {args.exp_id} for claim {args.claim_id}."
    notes = (
        "Experiment hypothesis, success/failure criteria, metric, dataset, smoke test, "
        "planned analysis, confounder, and decision rule were recorded before execution."
    )
    update_agent_status(
        root,
        args.agent,
        "waiting",
        task=task,
        stage="preregistration_helper",
        outputs=[output],
        notes=notes,
        append_note=True,
    )
    append_agent_event(
        root,
        "preregistration_helper",
        args.agent,
        status="waiting",
        task=task,
        stage="preregistration_helper",
        outputs=[output],
        notes=notes,
    )


def write_preregistration(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    path = prereg_path(root, args.exp_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = f"""# Experiment Preregistration

Use this file before running the experiment. Do not rewrite success criteria after seeing results; append an amendment with date and reason if the plan changes.

## Hypothesis

- Claim ID: {args.claim_id}
- Claim tested: {args.claim}
- Directional expectation: {args.expectation}
- What would count as support: {args.support}
- What would weaken or falsify the claim: {args.falsify}

## Success Criteria

| Criterion | Required Signal | Evidence File | Status |
| --- | --- | --- | --- |
| {args.success} | Matches directional expectation for `{args.metric}` | 05_results/experiment_results.csv | planned |

## Failure Criteria

| Failure Mode | Falsifying Signal | Evidence File | Mitigation |
| --- | --- | --- | --- |
| {args.failure} | Result contradicts success criterion or fails reproducibility checks | 03_experiments/{args.exp_id}/run_log.md | Record as failed evidence and update caveats |

## Baselines

| Baseline | Registry ID | Why Required | Reproducibility Status |
| --- | --- | --- | --- |
| {args.baseline} | to_be_registered | Needed for reviewer-facing comparison if claim is comparative | candidate |

## Metrics

| Metric | Primary? | Direction | Rationale |
| --- | --- | --- | --- |
| {args.metric} | yes | {args.metric_direction} | Primary signal for `{args.claim_id}` |

## Dataset And Split

- Dataset: {args.dataset}
- Split: {args.split}
- Sample exclusions: Record before execution if any examples are excluded.
- Leakage checks: Check overlap between train/evaluation splits before strengthening claims.

## Smoke Test Plan

- Smoke command: {args.smoke_command}
- Smoke expected output: {args.smoke_expected_output}
- Smoke check procedure: {args.smoke_check_procedure}
- Smoke status: planned

## Planned Analysis

- Primary comparison: {args.analysis}
- Ablations: Record ablations only if they map to the claim.
- Robustness checks: Run uncertainty, seed, or data-quality checks before claim strengthening.
- Failure-case analysis: Summarize representative failures in `05_results/failure_cases.md`.
- Statistical test or uncertainty estimate: Report confidence interval, seed variance, or an explicit reason it is not applicable.

## Confounders

| Confounder | Risk | Planned Control |
| --- | --- | --- |
| {args.confounder} | Could make the result non-causal or non-reproducible | Audit data, metric, and baseline provenance before interpreting |

## Decision Rule

{args.decision_rule}

## Amendments

| Date | Change | Reason | Approved By |
| --- | --- | --- | --- |
"""
    path.write_text(content, encoding="utf-8")
    sync_preregistration_agent(root, args)
    refresh_report_index(root)
    print(path.relative_to(root).as_posix())
    return 0


def placeholder_after(text: str, marker: str) -> bool:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(marker):
            value = stripped.removeprefix(marker).strip()
            return value in {"", "to_be_defined", "not yet defined"}
    return True


def audit_preregistration(root: Path, exp_id: str) -> list[str]:
    path = prereg_path(root, exp_id)
    if not path.is_file():
        return [f"Missing preregistration: {path.relative_to(root)}."]
    text = path.read_text(encoding="utf-8", errors="replace")
    warnings: list[str] = []
    for label, marker in REQUIRED_MARKERS.items():
        if marker not in text:
            warnings.append(f"{exp_id} preregistration is missing {label}.")
    for label, marker in (
        ("Claim ID", "- Claim ID:"),
        ("Claim tested", "- Claim tested:"),
        ("Directional expectation", "- Directional expectation:"),
        ("Dataset", "- Dataset:"),
        ("Split", "- Split:"),
        ("Smoke command", "- Smoke command:"),
        ("Smoke expected output", "- Smoke expected output:"),
        ("Smoke check procedure", "- Smoke check procedure:"),
        ("Primary comparison", "- Primary comparison:"),
    ):
        if placeholder_after(text, marker):
            warnings.append(f"{exp_id} preregistration has empty {label}.")
    if "|  |" in text:
        warnings.append(f"{exp_id} preregistration still contains empty table cells.")
    return warnings


def _line_value(text: str, marker: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith(marker):
            return stripped.removeprefix(marker).strip()
    return ""


def _is_placeholder(value: str) -> bool:
    return value.strip().lower() in {"", "to_be_defined", "not yet defined"}


def _primary_metric(text: str) -> str:
    """Extract the Metric cell from the Metrics table row marked Primary? = yes."""
    in_table = False
    for line in text.splitlines():
        if line.strip().startswith("| Metric | Primary? | Direction |"):
            in_table = True
            continue
        if in_table:
            if not line.strip():
                continue
            if not line.strip().startswith("|"):
                break
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) >= 2 and cells[0] in {"---", "Metric"}:
                continue
            if len(cells) >= 2 and cells[1].lower() in {"yes", "y", "true", "primary"}:
                return cells[0].strip("`")
    return ""


def _result_rows_for(root: Path, exp_id: str) -> list[dict[str, str]]:
    path = root / "05_results" / "experiment_results.csv"
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = [dict(r) for r in csv.DictReader(handle)]
    return [
        r for r in rows
        if (rid := (r.get("experiment_id") or "").strip()) == exp_id
        or rid.startswith(f"{exp_id}_seed_")
    ]


def _run_state_status(root: Path, exp_id: str) -> str:
    path = root / "03_experiments" / exp_id / "run_state.json"
    if not path.is_file():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return ""
    if not isinstance(data, dict):
        return ""
    return str(data.get("status") or "").strip()


def audit_drift(root: Path, exp_id: str) -> list[str]:
    """Compare the executed experiment against its preregistration.

    Catches silent drift between what was registered and what the result rows /
    run state actually contain. Split drift requires the result CSV split column
    (see survey backlog #4); until then drift covers dataset, primary metric,
    claim id, and status-vs-evidence consistency.
    """
    path = prereg_path(root, exp_id)
    if not path.is_file():
        return [f"Missing preregistration: {path.relative_to(root)}."]
    text = path.read_text(encoding="utf-8", errors="replace")
    rows = _result_rows_for(root, exp_id)
    status = _run_state_status(root, exp_id)
    warnings: list[str] = []

    declared_dataset = _line_value(text, "- Dataset:")
    declared_claim = _line_value(text, "- Claim ID:")
    declared_metric = _primary_metric(text)

    if status == "succeeded" and not rows:
        warnings.append(
            f"{exp_id} run_state is 'succeeded' but no rows in experiment_results.csv match it.")

    if rows:
        observed_datasets = {(r.get("dataset") or "").strip() for r in rows if (r.get("dataset") or "").strip()}
        observed_metrics = {(r.get("metric") or "").strip() for r in rows if (r.get("metric") or "").strip()}
        observed_claims = {(r.get("claim_id") or "").strip() for r in rows if (r.get("claim_id") or "").strip()}
        if declared_dataset and not _is_placeholder(declared_dataset) and observed_datasets \
                and declared_dataset not in observed_datasets:
            warnings.append(
                f"{exp_id} dataset drift: preregistered '{declared_dataset}' but results used "
                f"{sorted(observed_datasets)}.")
        if declared_metric and not _is_placeholder(declared_metric) and observed_metrics \
                and declared_metric not in observed_metrics:
            warnings.append(
                f"{exp_id} metric drift: preregistered primary metric '{declared_metric}' but results "
                f"reported {sorted(observed_metrics)}.")
        if declared_claim and not _is_placeholder(declared_claim) and observed_claims \
                and declared_claim not in observed_claims:
            warnings.append(
                f"{exp_id} claim drift: preregistered claim '{declared_claim}' but results are keyed to "
                f"{sorted(observed_claims)}.")
    return warnings


def drift(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    warnings = audit_drift(root, args.exp_id)
    if args.json:
        print(json.dumps({"project": args.project, "exp_id": args.exp_id,
                          "drift_warnings": warnings}, indent=2, ensure_ascii=False))
    elif warnings:
        print("preregistration drift warnings:")
        for warning in warnings:
            print(f"- {warning}")
    else:
        print(f"no preregistration drift: {args.exp_id}")
    return 1 if warnings and args.strict else 0


def audit(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    warnings = audit_preregistration(root, args.exp_id)
    if args.json:
        print(json.dumps({"project": args.project, "exp_id": args.exp_id, "warnings": warnings}, indent=2, ensure_ascii=False))
    elif warnings:
        print("preregistration warnings:")
        for warning in warnings:
            print(f"- {warning}")
    else:
        print(f"preregistration OK: {args.exp_id}")
    return 1 if warnings and args.strict else 0


def main() -> int:
    args = parse_args()
    try:
        if args.command == "write":
            return write_preregistration(args)
        if args.command == "audit":
            return audit(args)
        if args.command == "drift":
            return drift(args)
        raise HarnessError(f"Unknown command: {args.command}")
    except (HarnessError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
