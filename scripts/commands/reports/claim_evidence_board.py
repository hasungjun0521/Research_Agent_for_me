#!/usr/bin/env python3
"""Build a project-local claim/evidence board from working and final evidence."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from scripts.commands.reports.paper_claim_linter import lint_project
from scripts.harness.report_lifecycle import sync_report_lifecycle
from scripts.harness.state import HarnessError, project_root

STRONG_STATUSES = {"supported", "partial", "validated"}
WEAK_STATUSES = {"untested", "unsupported", "contradicted", "invalid", "rejected"}
BOARD_HEADER = [
    "claim_id",
    "claim",
    "status",
    "result_rows",
    "robustness_rows",
    "evidence",
    "caveat",
    "next_needed",
]


def project_display_name(root: Path) -> str:
    return "{{PROJECT_NAME}}" if root.name == "template" else root.name


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a claim-evidence board for a research project.")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build", help="Print or write the claim-evidence board.")
    build.add_argument("--project", required=True)
    build.add_argument("--agent", default="result_interpreter")
    build.add_argument("--write", action="store_true")
    build.add_argument(
        "--final-export",
        action="store_true",
        help="Also export the stable reader-facing board table to 09_report/results/.",
    )
    build.add_argument("--strict", action="store_true", help="Fail when board-level blockers are present.")
    build.add_argument("--json", action="store_true")
    return parser.parse_args()


def csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [
            {str(k or "").strip(): str(v or "").strip() for k, v in row.items()}
            for row in csv.DictReader(handle)
            if any(str(value or "").strip() for value in row.values())
        ]


def by_claim(rows: list[dict[str, str]]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        claim_id = row.get("claim_id", "")
        if claim_id:
            grouped.setdefault(claim_id, []).append(row)
    return grouped


def working_journal_rows(root: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in csv_rows(root / "05_results" / "experiment_journal.csv"):
        experiment = str(row.get("experiment") or "").strip()
        result_summary = str(row.get("result_summary") or "").strip()
        updated_at = str(row.get("updated_at") or "").strip()
        if experiment == "exp_001" and result_summary.lower() == "planned" and not updated_at:
            continue
        if not experiment and not result_summary:
            continue
        rows.append({
            "updated_at": updated_at,
            "experiment": experiment or "missing",
            "dataset": str(row.get("dataset") or "").strip(),
            "method": str(row.get("method") or "").strip(),
            "baseline": str(row.get("baseline") or "").strip(),
            "result_summary": result_summary,
            "result_analysis": str(row.get("result_analysis") or "").strip(),
            "evidence": str(row.get("evidence") or "").strip(),
        })
    return rows


def claim_board(root: Path) -> tuple[dict[str, Any], list[str]]:
    claim_rows = csv_rows(root / "09_report" / "results" / "claim_evidence.csv")
    result_rows = by_claim(csv_rows(root / "09_report" / "results" / "experiment_results.csv"))
    robustness_rows = by_claim(csv_rows(root / "09_report" / "results" / "statistical_robustness.csv"))
    working_rows = working_journal_rows(root)
    warnings = lint_project(root)
    board: dict[str, Any] = {
        "project": project_display_name(root),
        "claims": [],
        "blockers": [],
        "working_results": working_rows,
    }

    if not claim_rows:
        board["blockers"].append("No stable claim rows have been exported to 09_report/results/claim_evidence.csv.")
        board["blockers"].append(
            "Before final export, consolidate working evidence in 05_results/interpretation.md, "
            "05_results/experiment_journal.md, 05_results/experiment_journal.csv, and "
            "05_results/claim_evidence_board.md."
        )

    seen: set[str] = set()
    for row in claim_rows:
        claim_id = row.get("claim_id", "")
        status = row.get("status", "").lower()
        if not claim_id:
            board["blockers"].append("A claim row is missing claim_id.")
            continue
        if claim_id in seen:
            board["blockers"].append(f"Duplicate claim row: {claim_id}.")
        seen.add(claim_id)
        results = result_rows.get(claim_id, [])
        robustness = robustness_rows.get(claim_id, [])
        if status in STRONG_STATUSES and not results and not robustness:
            board["blockers"].append(f"Strong claim {claim_id} has no result or robustness row.")
        if status in WEAK_STATUSES and not row.get("next_needed", ""):
            board["blockers"].append(f"Weak claim {claim_id} does not state next_needed.")
        board["claims"].append({
            "claim_id": claim_id,
            "claim": row.get("claim", ""),
            "status": row.get("status", ""),
            "evidence": row.get("evidence", ""),
            "experiments": row.get("experiments", ""),
            "robustness": row.get("robustness", ""),
            "caveat": row.get("caveat", ""),
            "next_needed": row.get("next_needed", ""),
            "result_rows": len(results),
            "robustness_rows": len(robustness),
            "methods": sorted({item.get("method", "") for item in results if item.get("method", "")}),
            "metrics": sorted({item.get("metric", "") for item in results + robustness if item.get("metric", "")}),
        })
    board["paper_lint_warnings"] = warnings
    board["blockers"].extend(warnings)
    return board, board["blockers"]


def render_markdown(board: dict[str, Any]) -> str:
    lines = [
        "# Claim-Evidence Board",
        "",
        f"- Project: `{board['project']}`",
        f"- Claims tracked: {len(board['claims'])}",
        f"- Blockers: {len(board['blockers'])}",
        "",
        "## Claims",
        "",
        "| Claim ID | Status | Result Rows | Robustness Rows | Evidence | Next Needed |",
        "| --- | --- | ---: | ---: | --- | --- |",
    ]
    if board["claims"]:
        for claim in board["claims"]:
            lines.append(
                "| `{claim_id}` | {status} | {result_rows} | {robustness_rows} | {evidence} | {next_needed} |".format(
                    claim_id=claim["claim_id"],
                    status=claim["status"] or "missing",
                    result_rows=claim["result_rows"],
                    robustness_rows=claim["robustness_rows"],
                    evidence=(claim["evidence"] or "missing").replace("|", "\\|"),
                    next_needed=(claim["next_needed"] or "missing").replace("|", "\\|"),
                )
            )
    else:
        lines.append("| _none_ | missing | 0 | 0 | missing | define claim rows |")
    lines.extend(["", "## Blockers", ""])
    if board["blockers"]:
        lines.extend(f"- {item}" for item in board["blockers"])
    else:
        lines.append("- No board blockers.")
    lines.extend([
        "",
        "## Working Result Preview",
        "",
    ])
    working_results = board.get("working_results") or []
    if working_results:
        lines.extend([
            "| Experiment | Dataset | Method | Baseline | Result Summary | Result Analysis | Evidence |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ])
        for row in working_results:
            lines.append(
                "| {experiment} | {dataset} | {method} | {baseline} | {result_summary} | {result_analysis} | {evidence} |".format(
                    experiment=(row.get("experiment") or "missing").replace("|", "\\|"),
                    dataset=(row.get("dataset") or "missing").replace("|", "\\|"),
                    method=(row.get("method") or "missing").replace("|", "\\|"),
                    baseline=(row.get("baseline") or "none").replace("|", "\\|"),
                    result_summary=(row.get("result_summary") or "missing").replace("|", "\\|"),
                    result_analysis=(row.get("result_analysis") or "missing").replace("|", "\\|"),
                    evidence=(row.get("evidence") or "missing").replace("|", "\\|"),
                )
            )
    else:
        lines.append("- No non-starter rows found in `05_results/experiment_journal.csv`.")
    lines.extend([
        "",
        "## Working Evidence Before Export",
        "",
        "- Keep experiment movement analysis in `03_experiments/<exp_id>/analysis.md`.",
        "- Keep the running result ledger in `05_results/experiment_journal.md` and `05_results/experiment_journal.csv`.",
        "- Keep claim interpretation in `05_results/interpretation.md` before exporting stable rows to `09_report/results/`.",
    ])
    return "\n".join(lines) + "\n"


def write_report_table(root: Path, board: dict[str, Any]) -> Path:
    path = root / "09_report" / "results" / "claim_evidence_board.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=BOARD_HEADER, lineterminator="\n")
        writer.writeheader()
        for claim in board["claims"]:
            writer.writerow({
                "claim_id": claim["claim_id"],
                "claim": claim["claim"],
                "status": claim["status"],
                "result_rows": claim["result_rows"],
                "robustness_rows": claim["robustness_rows"],
                "evidence": claim["evidence"],
                "caveat": claim["caveat"],
                "next_needed": claim["next_needed"],
            })
    return path


def sync_claim_board_agent(root: Path, agent: str, board: dict[str, Any], *, final_export: bool) -> None:
    outputs = ["05_results/claim_evidence_board.md"]
    if final_export:
        outputs.append("09_report/results/claim_evidence_board.csv")
    blockers = len(board.get("blockers") or [])
    claims = len(board.get("claims") or [])
    status = "blocked" if blockers else "waiting"
    task = f"Built claim-evidence board with {claims} claim(s)."
    notes = f"Claim board has {blockers} blocker(s); working result preview rows: {len(board.get('working_results') or [])}."
    sync_report_lifecycle(
        root,
        agent=agent,
        event_type="claim_evidence_board",
        status=status,
        task=task,
        outputs=outputs,
        notes=notes,
        # sync_report_lifecycle calls refresh_report_index only for final exports.
        refresh_report=final_export,
    )


def build(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    board, blockers = claim_board(root)
    if args.json:
        print(json.dumps(board, indent=2, ensure_ascii=False))
    else:
        print(render_markdown(board).rstrip())
    if args.write or args.final_export:
        path = root / "05_results" / "claim_evidence_board.md"
        path.write_text(render_markdown(board), encoding="utf-8")
        print(path.relative_to(root).as_posix())
        if args.final_export:
            report_path = write_report_table(root, board)
            print(report_path.relative_to(root).as_posix())
        sync_claim_board_agent(root, args.agent, board, final_export=args.final_export)
    return 1 if blockers and args.strict else 0


def main() -> int:
    args = parse_args()
    try:
        if args.command == "build":
            return build(args)
        raise HarnessError(f"Unknown command: {args.command}")
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
