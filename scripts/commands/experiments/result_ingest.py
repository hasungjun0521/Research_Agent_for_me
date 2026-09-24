#!/usr/bin/env python3
"""Ingest experiment result files into working results, with optional final export."""

from __future__ import annotations

import argparse
import collections
import csv
import json
import re
from pathlib import Path
from typing import Any

from scripts.harness.experiment_journal import (
    append_experiment_analysis_note,
    append_experiment_journal_row,
    experiment_analysis_path,
)
from scripts.harness.state import (
    HarnessError,
    append_agent_event,
    append_run_history,
    mutate_run_state,
    now_iso,
    project_root,
    update_agent_status,
)
from scripts.harness.state_io import read_csv, upsert_rows, write_csv
from scripts.harness.workflow_hooks import refresh_report_index

RESULT_HEADER = [
    "experiment_id",
    "claim_id",
    "dataset",
    "split",
    "method",
    "baseline_id",
    "metric",
    "value",
    "delta",
    "status",
    "evidence",
    "caveat",
]

ROBUSTNESS_HEADER = [
    "experiment_id",
    "claim_id",
    "check",
    "metric",
    "value",
    "status",
    "evidence",
    "caveat",
    "next_needed",
]


def setup_subparsers(subparsers: argparse._SubParsersAction) -> None:
    ingest = subparsers.add_parser("ingest", help="Append or update experiment result rows.")
    ingest.add_argument("--project", required=True)
    ingest.add_argument("--agent", default="data_analyst")
    ingest.add_argument("--exp-id", required=True)
    ingest.add_argument("--input", required=True)
    ingest.add_argument("--claim-id", required=True)
    ingest.add_argument("--dataset", required=True)
    ingest.add_argument("--split", default="test")
    ingest.add_argument("--method", required=True)
    ingest.add_argument("--baseline-id", default="")
    ingest.add_argument("--status", default="observed")
    ingest.add_argument("--evidence", default="")
    ingest.add_argument("--caveat", default="")
    ingest.add_argument("--rationale", default="")
    ingest.add_argument("--final-export", action="store_true")
    ingest.add_argument("--result-analysis", default="")

    robust = subparsers.add_parser("robustness", help="Append or update robustness check rows.")
    robust.add_argument("--project", required=True)
    robust.add_argument("--agent", default="data_analyst")
    robust.add_argument("--exp-id", required=True)
    robust.add_argument("--input", required=True)
    robust.add_argument("--claim-id", required=True)
    robust.add_argument("--evidence", default="")
    robust.add_argument("--caveat", default="")
    robust.add_argument("--next-needed", default="")
    robust.add_argument("--final-export", action="store_true")

    parse = subparsers.add_parser("parse-log", help="Extract metric from a log file.")
    parse.add_argument("--project", required=True)
    parse.add_argument("--exp-id", required=True)
    parse.add_argument("--log", required=True)
    parse.add_argument("--output")
    parse.add_argument("--metric-regex", default="")
    parse.add_argument("--metric-name", default="")
    parse.add_argument("--tail-lines", type=int, default=500)


def project_relative(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return root / value


def load_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        raise HarnessError(f"Input file not found: {path}")
    if path.suffix.lower() == ".json":
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict):
            rows = data.get("results", data)
            if isinstance(rows, dict):
                if "metric" in rows and "value" in rows:
                    rows = [rows]
                else:
                    rows = [{"metric": k, "value": v} for k, v in rows.items()]
        else:
            raise HarnessError("JSON metric file must contain a list or an object.")
        if not isinstance(rows, list):
            raise HarnessError("JSON metric file could not be parsed into a list of results.")
        return [row for row in rows if isinstance(row, dict)]
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [
            {str(k or ""): str(v or "") for k, v in row.items()} for row in csv.DictReader(handle)
        ]


def ingest_results(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    input_path = project_relative(root, args.input)
    source_rows = load_rows(input_path)
    new_rows: list[dict[str, str]] = []
    for row in source_rows:
        metric = str(row.get("metric") or row.get("name") or "").strip()
        value = str(row.get("value") or row.get("score") or "").strip()
        if not metric or not value:
            continue
        new_rows.append(
            {
                "experiment_id": args.exp_id,
                "claim_id": args.claim_id,
                "dataset": args.dataset,
                "split": str(row.get("split") or args.split).strip(),
                "method": args.method,
                "baseline_id": args.baseline_id,
                "metric": metric,
                "value": value,
                "delta": str(row.get("delta") or "").strip(),
                "status": str(row.get("status") or args.status).strip(),
                "evidence": args.evidence or args.input,
                "caveat": args.caveat,
            }
        )
    if not new_rows:
        raise HarnessError("No metric/value rows found in input.")

    working_output = root / "05_results" / "experiment_results.csv"
    rows = upsert_rows(
        read_csv(working_output, RESULT_HEADER),
        new_rows,
        ("experiment_id", "claim_id", "dataset", "split", "method", "baseline_id", "metric"),
    )
    write_csv(working_output, RESULT_HEADER, rows)

    final_output = root / "09_report" / "results" / "experiment_results.csv"
    if args.final_export:
        final_rows = upsert_rows(
            read_csv(final_output, RESULT_HEADER),
            new_rows,
            ("experiment_id", "claim_id", "dataset", "split", "method", "baseline_id", "metric"),
        )
        write_csv(final_output, RESULT_HEADER, final_rows)

    append_experiment_journal_row(
        root,
        exp_id=args.exp_id,
        rationale=args.rationale,
        dataset=args.dataset,
        method=args.method,
        baseline_id=args.baseline_id,
        result_summary="; ".join(f"{r['metric']}={r['value']}" for r in new_rows),
        result_analysis=args.result_analysis,
        evidence=args.evidence or args.input,
        caveat=args.caveat,
    )
    append_experiment_analysis_note(
        root,
        exp_id=args.exp_id,
        rationale=args.rationale,
        dataset=args.dataset,
        method=args.method,
        baseline_id=args.baseline_id,
        result_summary="; ".join(f"{r['metric']}={r['value']}" for r in new_rows),
        result_analysis=args.result_analysis,
        evidence=args.evidence or args.input,
        caveat=args.caveat,
    )

    timestamp = now_iso()
    analysis_next = (
        "Analyze why performance improved, regressed, or stayed flat before strengthening paper claims."
        if not args.result_analysis.strip()
        else "Use this result to update the claim graph and reader-facing evidence tables."
    )

    def update_run(data: dict[str, Any]) -> None:
        data["owner_agent"] = args.agent
        data["current_step"] = f"Ingested {len(new_rows)} result(s)."
        data["display_summary"] = "; ".join(f"{r['metric']}={r['value']}" for r in new_rows)
        data["judgement"] = args.result_analysis or "analysis pending"
        data["next_action"] = analysis_next
        data["updated_at"] = timestamp
        append_run_history(data, "result_ingest", data["display_summary"])

    mutate_run_state(root, args.exp_id, update_run)

    outputs = [working_output.relative_to(root).as_posix()]
    if args.final_export:
        outputs.append(final_output.relative_to(root).as_posix())

    update_agent_status(
        root,
        args.agent,
        "waiting",
        task=f"Ingested {len(new_rows)} result rows for {args.exp_id}.",
        stage="result_ingest",
        outputs=outputs,
    )
    append_agent_event(
        root,
        "result_ingest",
        args.agent,
        status="waiting",
        task=f"Ingested {len(new_rows)} result rows for {args.exp_id}.",
        stage="result_ingest",
        outputs=outputs,
    )
    refresh_report_index(root, include_report=args.final_export)
    return 0


def append_robustness_markdown(
    root: Path, exp_id: str, claim_id: str, new_rows: list[dict[str, str]]
) -> None:
    timestamp = now_iso()
    summary = "; ".join(f"{r['metric']}={r['value']}" for r in new_rows)
    md_path = root / "05_results" / "statistical_robustness.md"
    if not md_path.exists():
        md_path.write_text("# Statistical Robustness Ledger\n\n", encoding="utf-8")
    with md_path.open("a", encoding="utf-8") as handle:
        handle.write(f"\n## {exp_id} - {timestamp}\n\n- Claim: {claim_id}\n- Result: {summary}\n")
        for row in new_rows:
            if row.get("next_needed"):
                handle.write(f"- Next needed: {row['next_needed']}\n")
    analysis_path = experiment_analysis_path(root, exp_id)
    if not analysis_path.exists():
        analysis_path.parent.mkdir(parents=True, exist_ok=True)
        analysis_path.write_text(f"# Experiment {exp_id} Analysis\n\n", encoding="utf-8")
    with analysis_path.open("a", encoding="utf-8") as handle:
        handle.write(
            f"\n### Robustness checks - {timestamp}\n\n- Claim: {claim_id}\n- Summary: {summary}\n"
        )


def ingest_robustness(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    input_path = project_relative(root, args.input)
    source_rows = load_rows(input_path)
    new_rows: list[dict[str, str]] = []
    for row in source_rows:
        metric = str(row.get("metric") or row.get("name") or "").strip()
        value = str(row.get("value") or row.get("score") or "").strip()
        if not metric or not value:
            continue
        new_rows.append(
            {
                "experiment_id": args.exp_id,
                "claim_id": args.claim_id,
                "check": str(row.get("check") or "").strip(),
                "metric": metric,
                "value": value,
                "status": str(row.get("status") or "observed").strip(),
                "evidence": args.evidence or args.input,
                "caveat": args.caveat,
                "next_needed": args.next_needed,
            }
        )
    if not new_rows:
        raise HarnessError("No robustness metric rows found.")
    working_output = root / "05_results" / "statistical_robustness.csv"
    rows = upsert_rows(
        read_csv(working_output, ROBUSTNESS_HEADER),
        new_rows,
        ("experiment_id", "claim_id", "metric"),
    )
    write_csv(working_output, ROBUSTNESS_HEADER, rows)
    if args.final_export:
        final_output = root / "09_report" / "results" / "statistical_robustness.csv"
        # Final report refresh gating: 09_report/results/statistical_robustness.csv
        final_rows = upsert_rows(
            read_csv(final_output, ROBUSTNESS_HEADER),
            new_rows,
            ("experiment_id", "claim_id", "metric"),
        )
        write_csv(final_output, ROBUSTNESS_HEADER, final_rows)
    append_robustness_markdown(root, args.exp_id, args.claim_id, new_rows)
    outputs = [working_output.relative_to(root).as_posix()]
    if args.final_export:
        outputs.append(final_output.relative_to(root).as_posix())

    update_agent_status(
        root,
        args.agent,
        "waiting",
        task=f"Ingested {len(new_rows)} robustness rows for {args.exp_id}.",
        stage="result_ingest_robustness",
        outputs=outputs,
    )
    append_agent_event(
        root,
        "result_ingest_robustness",
        args.agent,
        status="waiting",
        task=f"Ingested {len(new_rows)} robustness rows for {args.exp_id}.",
        stage="result_ingest_robustness",
        outputs=outputs,
    )
    refresh_report_index(root, include_report=args.final_export)
    return 0


def get_experiment_plan_details(root: Path, exp_id: str) -> tuple[str, str]:
    dag_path = root / "03_experiments" / "experiment_dag.json"
    if not dag_path.is_file():
        return "", ""
    try:
        data = json.loads(dag_path.read_text(encoding="utf-8"))
        for plan in data.get("plans", []):
            if plan.get("experiment_id") == exp_id:
                return plan.get("metric", ""), plan.get("metric_regex", "")
    except json.JSONDecodeError:
        pass
    return "", ""


def parse_log_command(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    log_path = project_relative(root, args.log)
    if not log_path.is_file():
        raise HarnessError(f"Log file not found: {log_path}")
    plan_metric, plan_regex = get_experiment_plan_details(root, args.exp_id)
    m_name = args.metric_name or plan_metric
    m_regex = args.metric_regex or plan_regex
    if not m_name or not m_regex:
        raise HarnessError("Metric name/regex required.")
    pattern = re.compile(m_regex)
    with log_path.open("r", encoding="utf-8", errors="replace") as handle:
        lines = (
            collections.deque(handle, maxlen=args.tail_lines)
            if args.tail_lines > 0
            else list(handle)
        )
    last_match = None
    for line in lines:
        match = pattern.search(line)
        if match:
            last_match = "-".join(match.groups()) if match.groups() else match.group(0)
    if last_match is None:
        raise HarnessError(f"No match for {m_regex}.")
    output_data = {"results": [{"metric": m_name, "value": last_match}]}
    if args.output:
        out_path = project_relative(root, args.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(output_data, indent=2) + "\n")
    else:
        print(json.dumps(output_data, indent=2))
    return 0


def main() -> int:
    from scripts.commands.experiments.experiments import main as experiments_main

    return experiments_main()


if __name__ == "__main__":
    raise SystemExit(main())
