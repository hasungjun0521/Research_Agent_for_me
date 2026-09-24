#!/usr/bin/env python3
"""Generate a researcher-facing readiness audit for a project."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from scripts.commands.experiments.preregistration_helper import audit_preregistration
from scripts.commands.reports.claim_evidence_board import claim_board, project_display_name
from scripts.commands.reports.data_metric_audit import audit as data_metric_audit
from scripts.commands.reports.paper_claim_linter import lint_project
from scripts.harness.report_lifecycle import sync_report_lifecycle
from scripts.harness.state import HarnessError, project_root

AUDIT_HEADER = ["kind", "check", "status", "detail"]


def markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit project readiness for real research use.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--agent", default="director")
    parser.add_argument("--write-report", action="store_true")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [
            {str(k or "").strip(): str(v or "").strip() for k, v in row.items()}
            for row in csv.DictReader(handle)
            if any(str(value or "").strip() for value in row.values())
        ]


def meaningful_brief(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < 80:
        return False
    weak_markers = ("Not yet finalized", "Describe the question", "Use this file", "{{PROJECT_NAME}}")
    return not any(marker in stripped for marker in weak_markers)


def nonstarter_journal_rows(root: Path) -> int:
    rows = csv_rows(root / "05_results" / "experiment_journal.csv")
    count = 0
    for row in rows:
        experiment = str(row.get("experiment") or "").strip()
        result_summary = str(row.get("result_summary") or "").strip().lower()
        updated_at = str(row.get("updated_at") or "").strip()
        if experiment == "exp_001" and result_summary == "planned" and not updated_at:
            continue
        count += 1
    return count


def working_artifact_warnings(root: Path) -> tuple[list[str], list[dict[str, str]]]:
    if root.name == "template":
        return [], []
    warnings: list[str] = []
    checks: list[dict[str, str]] = []
    required_files = [
        ("data_roots", root / "03_experiments" / "data_roots.md", "Register dataset roots, split/version IDs, and derived-data locations."),
        ("experiment_results_csv", root / "05_results" / "experiment_results.csv", "Keep structured working experiment result rows before final export."),
        ("experiment_journal_md", root / "05_results" / "experiment_journal.md", "Keep the human-readable experiment result ledger current."),
        ("experiment_journal_csv", root / "05_results" / "experiment_journal.csv", "Keep the structured experiment result ledger current."),
        ("terminology", root / "06_writing" / "terminology.md", "Normalize paper terms, abbreviations, dataset names, method names, and metric labels."),
    ]
    for check_name, path, detail in required_files:
        relative = path.relative_to(root).as_posix()
        text = read_text(path)
        if not path.is_file():
            warnings.append(f"Missing working artifact: {relative}. {detail}")
            checks.append({"check": check_name, "status": "warning", "detail": f"Missing {relative}. {detail}"})
            continue
        if not text.strip():
            warnings.append(f"Working artifact is empty: {relative}. {detail}")
            checks.append({"check": check_name, "status": "warning", "detail": f"Empty {relative}. {detail}"})
            continue
        if check_name in {"data_roots", "terminology"} and "to_be_defined" in text:
            warnings.append(f"Working artifact still contains starter placeholder: {relative}.")
            checks.append({"check": check_name, "status": "warning", "detail": f"Replace starter placeholders in {relative}."})
            continue
        if check_name == "experiment_results_csv" and not csv_rows(path):
            warnings.append("Structured working experiment results table has no result rows.")
            checks.append({
                "check": check_name,
                "status": "warning",
                "detail": "Append working result rows to 05_results/experiment_results.csv before final export.",
            })
            continue
        if check_name == "experiment_journal_csv" and nonstarter_journal_rows(root) == 0:
            warnings.append("Structured experiment journal has no non-starter result rows.")
            checks.append({
                "check": check_name,
                "status": "warning",
                "detail": "Append real experiment result rows to 05_results/experiment_journal.csv.",
            })
            continue
        checks.append({"check": check_name, "status": "pass", "detail": f"{relative} exists and is not empty."})
    return warnings, checks


def audit_project(root: Path) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    checks: list[dict[str, str]] = []

    question_text = read_text(root / "00_brief" / "research_question.md")
    if meaningful_brief(question_text):
        checks.append({"check": "research_question", "status": "pass", "detail": "Research question is populated."})
    else:
        blockers.append("Research question is missing or still a starter placeholder.")
        checks.append({"check": "research_question", "status": "blocker", "detail": "Fill 00_brief/research_question.md."})

    claim_rows = csv_rows(root / "09_report" / "results" / "claim_evidence.csv")
    if claim_rows:
        checks.append({"check": "claim_table", "status": "pass", "detail": f"{len(claim_rows)} claim row(s) found."})
    else:
        blockers.append("No stable claim rows have been exported to 09_report/results/claim_evidence.csv.")
        checks.append({
            "check": "claim_table",
            "status": "blocker",
            "detail": (
                "First consolidate working evidence in 05_results/interpretation.md, "
                "05_results/experiment_journal.md, 05_results/experiment_journal.csv, "
                "and 05_results/claim_evidence_board.md; then export stable rows to "
                "09_report/results/claim_evidence.csv."
            ),
        })

    board, board_blockers = claim_board(root)
    board_warnings = [warning for warning in board_blockers if warning not in blockers]
    if board_warnings:
        warnings.extend(board_warnings)
        checks.append({"check": "claim_evidence_board", "status": "warning", "detail": f"{len(board_warnings)} board warning(s)."})
    else:
        checks.append({"check": "claim_evidence_board", "status": "pass", "detail": "Claim-evidence board has no blockers."})

    prereg_warnings: list[str] = []
    exp_dirs = sorted(path for path in (root / "03_experiments").glob("exp_*") if path.is_dir())
    for exp_dir in exp_dirs:
        prereg_warnings.extend(audit_preregistration(root, exp_dir.name))
    if prereg_warnings:
        blockers.extend(prereg_warnings)
        checks.append({"check": "preregistration", "status": "blocker", "detail": f"{len(prereg_warnings)} preregistration issue(s)."})
    else:
        checks.append({"check": "preregistration", "status": "pass", "detail": f"{len(exp_dirs)} experiment preregistration(s) audited."})

    data_warnings, data_manifest = data_metric_audit(root)
    if data_warnings:
        warnings.extend(data_warnings)
        checks.append({"check": "data_metric_provenance", "status": "warning", "detail": f"{len(data_warnings)} provenance warning(s)."})
    else:
        checks.append({"check": "data_metric_provenance", "status": "pass", "detail": "Dataset/metric provenance audit has no warnings."})

    artifact_warnings, artifact_checks = working_artifact_warnings(root)
    warnings.extend(artifact_warnings)
    checks.extend(artifact_checks)

    paper_warnings = lint_project(root)
    if paper_warnings:
        warnings.extend(paper_warnings)
        checks.append({"check": "paper_claim_lint", "status": "warning", "detail": f"{len(paper_warnings)} paper claim warning(s)."})
    else:
        checks.append({"check": "paper_claim_lint", "status": "pass", "detail": "Paper claim lint has no warnings."})

    reviewer_matrix = read_text(root / "07_reviews" / "reviewer_attack_matrix.md")
    if "likely reviewer objections" in reviewer_matrix.lower() or "| attack" in reviewer_matrix.lower():
        checks.append({"check": "reviewer_attack_matrix", "status": "pass", "detail": "Reviewer-risk file exists."})
    else:
        warnings.append("Reviewer attack matrix is missing concrete reviewer risks.")
        checks.append({"check": "reviewer_attack_matrix", "status": "warning", "detail": "Add reviewer risks before submission-style writing."})

    readiness = "blocked" if blockers else "warning" if warnings else "ready"
    return {
        "project": project_display_name(root),
        "readiness": readiness,
        "blockers": blockers,
        "warnings": warnings,
        "checks": checks,
        "data_metric_manifest": data_manifest,
        "claim_board": board,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Research Readiness Audit",
        "",
        f"- Project: `{report['project']}`",
        f"- Readiness: `{report['readiness']}`",
        f"- Blockers: {len(report['blockers'])}",
        f"- Warnings: {len(report['warnings'])}",
        "",
        "## Checks",
        "",
        "| Check | Status | Detail |",
        "| --- | --- | --- |",
    ]
    for check in report["checks"]:
        detail = markdown_cell(check["detail"])
        lines.append(f"| {check['check']} | {check['status']} | {detail} |")
    lines.extend(["", "## Blockers", ""])
    lines.extend(f"- {item}" for item in report["blockers"]) if report["blockers"] else lines.append("- None.")
    lines.extend(["", "## Warnings", ""])
    lines.extend(f"- {item}" for item in report["warnings"]) if report["warnings"] else lines.append("- None.")
    return "\n".join(lines) + "\n"


def write_report_table(root: Path, report: dict[str, Any]) -> Path:
    path = root / "09_report" / "results" / "research_audit.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=AUDIT_HEADER, lineterminator="\n")
        writer.writeheader()
        writer.writerow({
            "kind": "summary",
            "check": "readiness",
            "status": report["readiness"],
            "detail": f"{len(report['blockers'])} blocker(s), {len(report['warnings'])} warning(s)",
        })
        for check in report["checks"]:
            writer.writerow({
                "kind": "check",
                "check": check["check"],
                "status": check["status"],
                "detail": check["detail"],
            })
        for item in report["blockers"]:
            writer.writerow({"kind": "blocker", "check": "", "status": "blocker", "detail": item})
        for item in report["warnings"]:
            writer.writerow({"kind": "warning", "check": "", "status": "warning", "detail": item})
    return path


def sync_research_audit_agent(root: Path, agent: str, report: dict[str, Any]) -> None:
    outputs = [
        "07_reviews/research_audit.md",
        "09_report/results/research_audit.csv",
    ]
    readiness = str(report.get("readiness") or "warning")
    blockers = len(report.get("blockers") or [])
    warnings = len(report.get("warnings") or [])
    status = "blocked" if readiness == "blocked" else "waiting"
    task = f"Generated research readiness audit: {readiness}."
    notes = f"Research audit found {blockers} blocker(s) and {warnings} warning(s)."
    sync_report_lifecycle(
        root,
        agent=agent,
        event_type="research_audit",
        status=status,
        task=task,
        outputs=outputs,
        notes=notes,
        # sync_report_lifecycle calls refresh_report_index for this report-facing audit.
        refresh_report=True,
    )


def main() -> int:
    args = parse_args()
    try:
        root = project_root(args.project)
        report = audit_project(root)
        if args.write_report:
            path = root / "07_reviews" / "research_audit.md"
            path.write_text(render_markdown(report), encoding="utf-8")
            report_path = write_report_table(root, report)
            sync_research_audit_agent(root, args.agent, report)
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(render_markdown(report).rstrip())
            if args.write_report:
                print("07_reviews/research_audit.md")
                print(report_path.relative_to(root).as_posix())
        return 1 if args.strict and report["blockers"] else 0
    except (HarnessError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
