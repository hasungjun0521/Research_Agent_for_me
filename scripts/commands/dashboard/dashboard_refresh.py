#!/usr/bin/env python3
"""Refresh all derived project surfaces used by the dashboard."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scripts.commands.dashboard.dashboard_sources import build_dashboard_sources
from scripts.commands.experiments.experiment_diagnosis import diagnose_project
from scripts.commands.experiments.experiment_diagnosis import (
    render_markdown as render_experiment_diagnosis,
)
from scripts.commands.experiments.experiment_diagnosis import (
    write_csv as write_experiment_diagnosis_csv,
)
from scripts.commands.reports.claim_evidence_board import claim_board
from scripts.commands.reports.claim_evidence_board import render_markdown as render_claim_board
from scripts.commands.reports.claim_evidence_board import (
    write_report_table as write_claim_board_table,
)
from scripts.commands.reports.report_index import build_block, refresh_project_index
from scripts.commands.reports.resource_ledger import load_ledger
from scripts.commands.reports.resource_ledger import render_markdown as render_resource_summary
from scripts.commands.reports.resource_ledger import summarize as summarize_resource_ledger
from scripts.commands.reports.resource_ledger import write_summary as write_resource_summary
from scripts.commands.reports.source_credibility_audit import (
    audit_project as audit_source_credibility,
)
from scripts.commands.reports.source_credibility_audit import (
    render_markdown as render_source_credibility,
)
from scripts.commands.reports.source_credibility_audit import (
    write_csv as write_source_credibility_csv,
)
from scripts.commands.research.phase_gate import audit_gates, load_gates
from scripts.commands.research.phase_gate import render_markdown as render_phase_gate_audit
from scripts.commands.research.phase_gate import write_report as write_phase_gate_report
from scripts.commands.research.research_audit import audit_project
from scripts.commands.research.research_audit import render_markdown as render_research_audit
from scripts.commands.research.research_audit import (
    write_report_table as write_research_audit_table,
)
from scripts.harness.state import HarnessError, project_root


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Refresh dashboard-visible claim, audit, report, and source-manifest inputs."
    )
    parser.add_argument("--project", required=True)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Build the dashboard summary in memory without writing generated files.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit nonzero when research blockers or required dashboard sources are present.",
    )
    parser.add_argument(
        "--final-export",
        action="store_true",
        help="Also refresh final 09_report CSVs and 09_report/README.md.",
    )
    parser.add_argument("--max-results", type=int, default=8)
    parser.add_argument("--max-actions", type=int, default=5)
    return parser.parse_args()


def relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def write_claim_board(root: Path, board: dict[str, Any], *, final_export: bool) -> list[str]:
    board_path = root / "05_results" / "claim_evidence_board.md"
    board_path.parent.mkdir(parents=True, exist_ok=True)
    board_path.write_text(render_claim_board(board), encoding="utf-8")
    paths = [relative(root, board_path)]
    if final_export:
        table_path = write_claim_board_table(root, board)
        paths.append(relative(root, table_path))
    return paths


def write_audit(root: Path, report: dict[str, Any], *, final_export: bool) -> list[str]:
    audit_path = root / "07_reviews" / "research_audit.md"
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(render_research_audit(report), encoding="utf-8")
    paths = [relative(root, audit_path)]
    if final_export:
        table_path = write_research_audit_table(root, report)
        paths.append(relative(root, table_path))
    return paths


def write_source_audit(root: Path, report: dict[str, Any], *, final_export: bool) -> list[str]:
    path = root / "07_reviews" / "source_credibility_audit.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_source_credibility(report), encoding="utf-8")
    paths = [relative(root, path)]
    if final_export:
        table_path = write_source_credibility_csv(root, report)
        paths.append(relative(root, table_path))
    return paths


def write_experiment_diagnosis(root: Path, report: dict[str, Any], *, final_export: bool) -> list[str]:
    path = root / "07_reviews" / "experiment_diagnosis.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_experiment_diagnosis(report), encoding="utf-8")
    paths = [relative(root, path)]
    if final_export:
        table_path = write_experiment_diagnosis_csv(root, report)
        paths.append(relative(root, table_path))
    return paths


def write_phase_gate_summary(root: Path, report: dict[str, Any], *, final_export: bool) -> list[str]:
    path = root / "07_reviews" / "phase_gate_audit.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_phase_gate_audit(report), encoding="utf-8")
    paths = [relative(root, path)]
    if final_export:
        table_path = write_phase_gate_report(root, report)
        paths.append(relative(root, table_path))
    return paths


def write_resource_ledger_summary(root: Path, summary: dict[str, Any], *, final_export: bool) -> list[str]:
    path = root / "07_reviews" / "resource_ledger.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_resource_summary(summary), encoding="utf-8")
    paths = [relative(root, path)]
    if final_export:
        table_path = write_resource_summary(root, summary)
        paths.append(relative(root, table_path))
    return paths


def refresh_dashboard_inputs(
    root: Path,
    *,
    write: bool,
    final_export: bool = False,
    max_results: int = 8,
    max_actions: int = 5,
) -> dict[str, Any]:
    claim_report, claim_blockers = claim_board(root)
    audit_report = audit_project(root)
    source_report = audit_source_credibility(root)
    experiment_report = diagnose_project(root)
    phase_report = audit_gates(root, load_gates(root))
    resource_summary = summarize_resource_ledger(load_ledger(root))
    written_files: list[str] = []

    if write:
        written_files.extend(write_claim_board(root, claim_report, final_export=final_export))
        written_files.extend(write_audit(root, audit_report, final_export=final_export))
        written_files.extend(write_source_audit(root, source_report, final_export=final_export))
        written_files.extend(write_experiment_diagnosis(root, experiment_report, final_export=final_export))
        written_files.extend(write_phase_gate_summary(root, phase_report, final_export=final_export))
        written_files.extend(write_resource_ledger_summary(root, resource_summary, final_export=final_export))
        if final_export:
            report_readme, report_changed = refresh_project_index(
                root,
                max_results=max_results,
                max_actions=max_actions,
            )
            report_index = {
                "path": relative(root, report_readme),
                "changed": report_changed,
                "mode": "write",
            }
            written_files.append(relative(root, report_readme))
        else:
            report_index = {
                "path": "09_report/README.md",
                "changed": None,
                "mode": "skipped_final_export",
            }
    else:
        report_block = build_block(root, max_results=max_results, max_actions=max_actions)
        report_index = {
            "path": "09_report/README.md",
            "changed": None,
            "mode": "check",
            "generated_chars": len(report_block),
        }

    sources = build_dashboard_sources(root)
    coverage = sources.get("coverage", {})
    required_missing = coverage.get("required_missing", [])

    return {
        "ok": True,
        "project": root.name,
        "mode": "write" if write else "check",
        "research_status": {
            "readiness": audit_report.get("readiness"),
            "claims": len(claim_report.get("claims", [])),
            "claim_blockers": len(claim_blockers),
            "audit_blockers": len(audit_report.get("blockers", [])),
            "audit_warnings": len(audit_report.get("warnings", [])),
        },
        "refreshed": {
            "claim_evidence_board": {
                "claims": len(claim_report.get("claims", [])),
                "blockers": len(claim_blockers),
                "paths": [
                    "05_results/claim_evidence_board.md",
                    *(["09_report/results/claim_evidence_board.csv"] if final_export else []),
                ],
            },
            "research_audit": {
                "readiness": audit_report.get("readiness"),
                "blockers": len(audit_report.get("blockers", [])),
                "warnings": len(audit_report.get("warnings", [])),
                "paths": [
                    "07_reviews/research_audit.md",
                    *(["09_report/results/research_audit.csv"] if final_export else []),
                ],
            },
            "source_credibility": {
                "status": source_report.get("status"),
                "blockers": len(source_report.get("blockers", [])),
                "warnings": len(source_report.get("warnings", [])),
                "paths": [
                    "07_reviews/source_credibility_audit.md",
                    *(["09_report/results/source_credibility_audit.csv"] if final_export else []),
                ],
            },
            "experiment_diagnosis": {
                "status": experiment_report.get("status"),
                "blockers": len(experiment_report.get("blockers", [])),
                "warnings": len(experiment_report.get("warnings", [])),
                "paths": [
                    "07_reviews/experiment_diagnosis.md",
                    *(["09_report/results/experiment_diagnosis.csv"] if final_export else []),
                ],
            },
            "phase_gates": {
                "status": phase_report.get("status"),
                "blockers": len(phase_report.get("blockers", [])),
                "warnings": len(phase_report.get("warnings", [])),
                "paths": [
                    "07_reviews/phase_gate_audit.md",
                    *(["09_report/results/phase_gate_audit.csv"] if final_export else []),
                ],
            },
            "resource_ledger": {
                "entries": resource_summary.get("entries"),
                "warnings": len(resource_summary.get("warnings", [])),
                "paths": [
                    "07_reviews/resource_ledger.md",
                    *(["09_report/results/resource_ledger.csv"] if final_export else []),
                ],
            },
            "report_index": report_index,
            "data_sources": {
                "required_missing": required_missing,
                "available": coverage.get("available"),
                "total": coverage.get("total"),
            },
        },
        "written_files": sorted(set(written_files)),
    }


def strict_blockers(summary: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    status = summary.get("research_status", {})
    if int(status.get("audit_blockers") or 0):
        blockers.append(f"research audit has {status['audit_blockers']} blocker(s)")
    if int(status.get("claim_blockers") or 0):
        blockers.append(f"claim board has {status['claim_blockers']} blocker(s)")
    missing = summary.get("refreshed", {}).get("data_sources", {}).get("required_missing", [])
    if missing:
        blockers.append(f"dashboard required sources missing: {', '.join(map(str, missing))}")
    return blockers


def main() -> int:
    args = parse_args()
    try:
        root = project_root(args.project)
        summary = refresh_dashboard_inputs(
            root,
            write=not args.check,
            final_export=args.final_export,
            max_results=args.max_results,
            max_actions=args.max_actions,
        )
        blockers = strict_blockers(summary) if args.strict else []
        if blockers:
            summary["ok"] = False
            summary["strict_blockers"] = blockers
        print(json.dumps(summary, indent=2, ensure_ascii=False))
        return 0 if summary["ok"] else 1
    except (HarnessError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
