#!/usr/bin/env python3
"""Summarize project handoff blockers and route them to concrete skills."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from scripts.harness.state import (
    HarnessError,
    append_agent_event,
    discover_run_states,
    load_agent_status,
    load_agent_votes,
    load_command_queue,
    project_root,
    update_agent_status,
)
from scripts.commands.research.research_audit import audit_project
from scripts.commands.projects.validate_project import report_freshness_warnings, voting_warnings, workflow_warnings
from scripts.harness.workflow_hooks import refresh_report_index


SKILL_BY_KIND = {
    "project_health": "prompts/skills/project_health.md",
    "state_doctor": "prompts/skills/state_doctor.md",
    "claim_evidence": "prompts/skills/claim_table_backfill.md",
    "claim_graph": "prompts/skills/claim_graph.md",
    "artifact_registry": "prompts/skills/project_closeout.md",
    "data_roots": "prompts/skills/project_closeout.md",
    "experiment_dag": "prompts/skills/experiment_planning.md",
    "experiment_journal": "prompts/skills/project_closeout.md",
    "agent_quality": "prompts/skills/agent_quality_audit.md",
    "baseline_compare": "prompts/skills/baseline_compare.md",
    "reviewer_risk": "prompts/skills/reviewer_risk_matrix.md",
    "workflow_state": "prompts/skills/workflow_state_reconcile.md",
    "vote_gate": "prompts/skills/workflow_state_reconcile.md",
    "report_hygiene": "prompts/skills/report_hygiene.md",
    "dashboard_sources": "prompts/skills/dashboard_refresh.md",
    "research_readiness": "prompts/skills/project_closeout.md",
    "terminology": "prompts/skills/project_closeout.md",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit project closeout blockers and next skills.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write-report", action="store_true")
    parser.add_argument(
        "--refresh-dashboard",
        action="store_true",
        help="Run dashboard_refresh write mode before building the closeout audit.",
    )
    parser.add_argument("--strict", action="store_true", help="Exit nonzero when closeout is blocked.")
    return parser.parse_args()


def csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [
            {str(key or "").strip(): str(value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle)
            if any(str(value or "").strip() for value in row.values())
        ]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def read_json(path: Path, fallback: Any) -> Any:
    if not path.is_file():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return fallback


def nonstarter_experiment_journal_rows(root: Path) -> int:
    count = 0
    for row in csv_rows(root / "05_results" / "experiment_journal.csv"):
        experiment = str(row.get("experiment") or "").strip()
        result_summary = str(row.get("result_summary") or "").strip().lower()
        updated_at = str(row.get("updated_at") or "").strip()
        if experiment == "exp_001" and result_summary == "planned" and not updated_at:
            continue
        count += 1
    return count


def issue(kind: str, severity: str, detail: str, next_step: str = "") -> dict[str, str]:
    return {
        "kind": kind,
        "severity": severity,
        "detail": detail,
        "skill": SKILL_BY_KIND.get(kind, "prompts/skills/project_closeout.md"),
        "next_step": next_step,
    }


def closeout_status(issues: list[dict[str, str]]) -> str:
    if any(item["severity"] == "blocker" for item in issues):
        return "blocked"
    if any(item["severity"] == "warning" for item in issues):
        return "warning"
    return "ready"


def build_project_closeout(root: Path, *, refresh_dashboard: bool = False) -> dict[str, Any]:
    dashboard_summary: dict[str, Any] = {"enabled": False}
    if refresh_dashboard:
        from scripts.commands.dashboard.dashboard_refresh import refresh_dashboard_inputs

        dashboard_summary = refresh_dashboard_inputs(root, write=True)
        dashboard_summary["enabled"] = True
    research = audit_project(root)
    status = load_agent_status(root)
    queue = load_command_queue(root)
    votes = load_agent_votes(root)
    run_states = discover_run_states(root)
    issues: list[dict[str, str]] = []

    project_health = root / "state" / "project_health.md"
    project_health_text = read_text(project_health)
    if not project_health.is_file() or not project_health_text.strip() or "not generated yet" in project_health_text.lower():
        issues.append(issue(
            "project_health",
            "warning",
            "Dashboard-free project health report is missing or still a starter file.",
            "Refresh state/project_health.md so the next agent sees blockers and recommended requests without dashboard state.",
        ))

    state_doctor = root / "state" / "state_doctor.md"
    state_doctor_text = read_text(state_doctor)
    if not state_doctor.is_file() or not state_doctor_text.strip() or "not generated yet" in state_doctor_text.lower():
        issues.append(issue(
            "state_doctor",
            "warning",
            "State doctor report is missing or still a starter file.",
            "Refresh state/state_doctor.md if command/status/result/GPU/baseline state may be stale.",
        ))

    claim_rows = csv_rows(root / "09_report" / "results" / "claim_evidence.csv")
    if not claim_rows:
        issues.append(issue(
            "claim_evidence",
            "blocker",
            "No stable claim rows have been exported to 09_report/results/claim_evidence.csv.",
            (
                "Use working claim IDs in 05_results first, then export stable rows after each claim "
                "is connected to evidence, experiments, caveats, and next_needed."
            ),
        ))
    data_roots = root / "03_experiments" / "data_roots.md"
    data_roots_text = read_text(data_roots)
    if not data_roots.is_file() or not data_roots_text.strip() or "to_be_defined" in data_roots_text:
        issues.append(issue(
            "data_roots",
            "blocker",
            "Experiment data roots are missing or still contain starter placeholders.",
            "Document dataset roots, split/version identifiers, checksums, and local-path handling in 03_experiments/data_roots.md.",
        ))

    working_result_rows = csv_rows(root / "05_results" / "experiment_results.csv")
    artifact_rows = csv_rows(root / "03_experiments" / "artifact_registry.csv")
    if working_result_rows and not artifact_rows:
        issues.append(issue(
            "artifact_registry",
            "blocker",
            "Working result rows exist but 03_experiments/artifact_registry.csv has no artifact rows.",
            (
                "Record metric files, logs, checkpoints, result directories, or evidence paths "
                "through experiment_complete before closeout."
            ),
        ))
    if working_result_rows and nonstarter_experiment_journal_rows(root) == 0:
        issues.append(issue(
            "experiment_journal",
            "blocker",
            "Working result rows exist but the experiment journal has no non-starter explanation rows.",
            (
                "Update 05_results/experiment_journal.md and 05_results/experiment_journal.csv "
                "with why each experiment was run, what happened, and why performance changed."
            ),
        ))

    experiment_dag = root / "03_experiments" / "experiment_dag.json"
    if working_result_rows and not experiment_dag.is_file():
        issues.append(issue(
            "experiment_dag",
            "warning",
            "Working result rows exist but no experiment DAG file is present.",
            "Record the smoke-first plan and parallel-run dependencies in 03_experiments/experiment_dag.json for reproducibility.",
        ))
    elif working_result_rows:
        dag = read_json(experiment_dag, {})
        plans = dag.get("plans") if isinstance(dag, dict) else []
        if not plans:
            issues.append(issue(
                "experiment_dag",
                "warning",
                "Working result rows exist but experiment_dag.json has no plans.",
                "Record the smoke-first plan and parallel-run dependencies in 03_experiments/experiment_dag.json for reproducibility.",
            ))

    claim_graph = root / "05_results" / "claim_graph.json"
    if working_result_rows and not claim_graph.is_file():
        issues.append(issue(
            "claim_graph",
            "warning",
            "Working result rows exist but no claim graph has been generated.",
            "Refresh 05_results/claim_graph.md/json before strengthening or exporting claims.",
        ))
    elif working_result_rows:
        graph = read_json(claim_graph, {})
        nodes = graph.get("nodes") if isinstance(graph, dict) else []
        edges = graph.get("edges") if isinstance(graph, dict) else []
        if not nodes or not edges:
            issues.append(issue(
                "claim_graph",
                "warning",
                "Working result rows exist but claim_graph.json has no useful nodes or edges.",
                "Refresh 05_results/claim_graph.md/json before strengthening or exporting claims.",
            ))

    terminology = root / "06_writing" / "terminology.md"
    terminology_text = read_text(terminology)
    if not terminology.is_file() or not terminology_text.strip() or "to_be_defined" in terminology_text:
        issues.append(issue(
            "terminology",
            "warning",
            "The paper terminology glossary is missing or still contains starter placeholders.",
            "Normalize method, dataset, metric, baseline, and abbreviation names in 06_writing/terminology.md before final writing/export.",
        ))

    source_snapshots = root / "08_baselines" / "source_snapshots"
    baseline_compare = root / "08_baselines" / "baseline_compare.md"
    has_snapshots = source_snapshots.is_dir() and any(
        path.is_dir() and not path.name.startswith(".")
        for path in source_snapshots.iterdir()
    )
    if has_snapshots and (
        not baseline_compare.is_file()
        or "no baseline source comparison" in read_text(baseline_compare).lower()
    ):
        issues.append(issue(
            "baseline_compare",
            "warning",
            "Baseline source snapshots exist but baseline comparison is missing or still a starter file.",
            "Compare cloned baseline structures and update 08_baselines/code_structure_plan.md before finalizing project code structure.",
        ))

    agent_quality = root / "07_reviews" / "agent_quality_audit.md"
    if not agent_quality.is_file() or "no agent continuity audit" in read_text(agent_quality).lower():
        issues.append(issue(
            "agent_quality",
            "warning",
            "Agent quality audit is missing or still a starter file.",
            "Audit whether previous agent passes left output-file evidence and checkpoints that make the project resumable.",
        ))

    for blocker in research.get("blockers", []):
        if "claim-evidence" in blocker.lower() or "claim rows" in blocker.lower():
            continue
        issues.append(issue("research_readiness", "blocker", str(blocker), "Resolve the research audit blocker."))

    for warning in research.get("warnings", []):
        lower = str(warning).lower()
        if "claim rows" in lower:
            continue
        if "reviewer attack matrix" in lower:
            issues.append(issue(
                "reviewer_risk",
                "warning",
                str(warning),
                "Add concrete reviewer objections, current weakness, evidence, and response plan.",
            ))
        else:
            issues.append(issue("research_readiness", "warning", str(warning), "Resolve or explicitly caveat the audit warning."))

    for warning in workflow_warnings(status, queue, run_states):
        issues.append(issue(
            "workflow_state",
            "warning",
            warning,
            "Start, finish, block, or reassign the owner through agent_status.py or command_queue.py.",
        ))

    for warning in voting_warnings(status, queue, votes, root):
        issues.append(issue(
            "vote_gate",
            "blocker" if "without approved vote" in warning else "warning",
            warning,
            "Open/approve/cancel the vote through agent_vote.py before treating the command as valid.",
        ))

    for warning in report_freshness_warnings(root):
        if "09_report should not contain Markdown scratch files" in warning or "Legacy 09_report markdown file" in warning:
            issues.append(issue(
                "report_hygiene",
                "warning",
                warning,
                "Move scratch Markdown to 05_results, 07_reviews, 08_baselines, or another working folder.",
            ))

    if refresh_dashboard:
        missing_sources = dashboard_summary.get("refreshed", {}).get("data_sources", {}).get("required_missing", [])
        for source in missing_sources:
            issues.append(issue(
                "dashboard_sources",
                "blocker",
                f"Dashboard required source is missing: {source}.",
                "Restore the missing source file or migrate the project before refreshing the dashboard.",
            ))

    skill_order = [
        "prompts/skills/project_health.md",
        "prompts/skills/state_doctor.md",
        "prompts/skills/claim_table_backfill.md",
        "prompts/skills/claim_graph.md",
        "prompts/skills/experiment_planning.md",
        "prompts/skills/baseline_compare.md",
        "prompts/skills/agent_quality_audit.md",
        "prompts/skills/reviewer_risk_matrix.md",
        "prompts/skills/workflow_state_reconcile.md",
        "prompts/skills/report_hygiene.md",
        "prompts/skills/dashboard_refresh.md",
        "prompts/skills/project_closeout.md",
    ]
    recommended_skills = [
        skill for skill in skill_order if any(item["skill"] == skill for item in issues)
    ]

    return {
        "project": root.name,
        "status": closeout_status(issues),
        "issue_count": len(issues),
        "issues": issues,
        "recommended_skills": recommended_skills,
        "dashboard_refresh": dashboard_summary,
        "research_readiness": {
            "readiness": research.get("readiness"),
            "blockers": len(research.get("blockers", [])),
            "warnings": len(research.get("warnings", [])),
        },
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Project Closeout Audit",
        "",
        f"- Project: `{report['project']}`",
        f"- Status: `{report['status']}`",
        f"- Issues: {report['issue_count']}",
        "",
        "## Recommended Skills",
        "",
    ]
    if report["recommended_skills"]:
        lines.extend(f"- `{skill}`" for skill in report["recommended_skills"])
    else:
        lines.append("- No closeout skills required.")

    lines.extend(["", "## Issues", ""])
    if report["issues"]:
        lines.extend([
            "| Kind | Severity | Detail | Skill | Next Step |",
            "| --- | --- | --- | --- | --- |",
        ])
        for item in report["issues"]:
            lines.append(
                "| {kind} | {severity} | {detail} | `{skill}` | {next_step} |".format(
                    kind=item["kind"],
                    severity=item["severity"],
                    detail=item["detail"].replace("|", "\\|"),
                    skill=item["skill"],
                    next_step=item["next_step"].replace("|", "\\|"),
                )
            )
    else:
        lines.append("- No closeout issues found.")

    lines.extend(["", "## Next Commands", ""])
    lines.append(f"- `python -m scripts.commands.projects.validate_project --project {report['project']} --strict`")
    if report.get("dashboard_refresh", {}).get("enabled"):
        lines.append(f"- `python -m scripts.commands.dashboard.dashboard_refresh --project {report['project']}`")
    return "\n".join(lines) + "\n"


def write_report(root: Path, report: dict[str, Any]) -> Path:
    path = root / "07_reviews" / "project_closeout_audit.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_markdown(report), encoding="utf-8")
    return path


def sync_closeout_lifecycle(root: Path, report: dict[str, Any], outputs: list[str]) -> None:
    status = "blocked" if report.get("status") == "blocked" else "waiting"
    note = f"Project closeout status is {report.get('status')} with {report.get('issue_count')} issue(s)."
    update_agent_status(
        root,
        "director",
        status,
        task="Review project closeout audit.",
        stage="project_closeout",
        outputs=outputs,
        notes=note,
        append_note=True,
    )
    append_agent_event(
        root,
        "project_closeout",
        "director",
        status=status,
        task="Review project closeout audit.",
        stage="project_closeout",
        outputs=outputs,
        notes=note,
    )


def main() -> int:
    args = parse_args()
    try:
        root = project_root(args.project)
        report = build_project_closeout(root, refresh_dashboard=args.refresh_dashboard)
        if args.write_report:
            path = write_report(root, report)
            report["written_report"] = path.relative_to(root).as_posix()
            sync_closeout_lifecycle(root, report, [report["written_report"]])
            refresh_report_index(root, include_report=True)
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(render_markdown(report).rstrip())
            if args.write_report:
                print(report["written_report"])
        return 1 if args.strict and report["status"] == "blocked" else 0
    except (HarnessError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
