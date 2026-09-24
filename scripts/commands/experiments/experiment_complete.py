#!/usr/bin/env python3
"""Complete an experiment and persist result, analysis, and registry state."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scripts.commands.experiments.result_ingest import (
    RESULT_HEADER,
    load_rows,
    project_relative,
)
from scripts.harness.experiment_journal import (
    append_experiment_analysis_note,
    append_experiment_journal_row,
)
from scripts.harness.experiment_registry import (
    append_data_root_rows,
    artifact_row,
    data_root_row,
    upsert_artifact_rows,
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

FINAL_STATUSES = {"succeeded", "failed", "blocked", "cancelled"}


def setup_subparsers(subparsers: argparse._SubParsersAction) -> None:
    complete = subparsers.add_parser("complete", help="Record a completed experiment in all working ledgers.")
    complete.add_argument("--project", required=True)
    complete.add_argument("--agent", default="data_analyst")
    complete.add_argument("--exp-id", required=True)
    complete.add_argument("--status", choices=sorted(FINAL_STATUSES), required=True)
    complete.add_argument("--summary", required=True, help="Observed result summary.")
    complete.add_argument("--result-analysis", default="", help="Why performance improved, regressed, or stayed flat.")
    complete.add_argument("--allow-pending-analysis", action="store_true")
    complete.add_argument("--input", help="Optional JSON/CSV metric file to ingest into 05_results/experiment_results.csv.")
    complete.add_argument("--metric", action="append", help="Metric value in metric=value form. May be repeated.")
    complete.add_argument("--claim-id", default="unassigned")
    complete.add_argument("--dataset", default="")
    complete.add_argument("--split", default="test", help="The dataset split (e.g. 'val', 'test'). Defaults to 'test'.")
    complete.add_argument("--method", default="")
    complete.add_argument("--baseline-id", default="")
    complete.add_argument("--rationale", default="")
    complete.add_argument("--evidence", default="")
    complete.add_argument("--caveat", default="")
    complete.add_argument("--result-path", default="")
    complete.add_argument("--expected-output", default="")
    complete.add_argument("--check-procedure", default="")
    complete.add_argument("--next-action", default="")
    complete.add_argument("--artifact", action="append", help="Artifact in artifact_id=path or artifact_id:kind=path form.")
    complete.add_argument("--data-root", action="append", help="Data root in data_id=root_or_uri form.")
    complete.add_argument("--data-split", default="")
    complete.add_argument("--data-status", default="observed")
    complete.add_argument("--final-export", action="store_true")
    complete.add_argument("--json", action="store_true")


def parse_metric_values(values: list[str] | None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for value in values or []:
        if "=" not in value:
            raise HarnessError("--metric must use metric=value.")
        metric, raw = value.split("=", 1)
        metric = metric.strip()
        raw = raw.strip()
        if not metric or not raw:
            raise HarnessError("--metric must include a non-empty metric and value.")
        rows.append({"metric": metric, "value": raw})
    return rows


def result_rows_from_args(root: Path, args: argparse.Namespace) -> list[dict[str, str]]:
    source_rows: list[dict[str, Any]] = []
    if args.input:
        source_rows.extend(load_rows(project_relative(root, args.input)))
    source_rows.extend(parse_metric_values(args.metric))
    if not source_rows:
        source_rows.append({"metric": "completion_summary", "value": args.summary})
    rows: list[dict[str, str]] = []
    for row in source_rows:
        metric = str(row.get("metric") or row.get("name") or "").strip()
        value = str(row.get("value") or row.get("score") or "").strip()
        if not metric or not value:
            continue
        rows.append({
            "experiment_id": args.exp_id,
            "claim_id": args.claim_id,
            "dataset": args.dataset or "not recorded",
            "split": str(row.get("split") or args.split).strip(),
            "method": args.method or "not recorded",
            "baseline_id": args.baseline_id,
            "metric": metric,
            "value": value,
            "delta": str(row.get("delta") or "").strip(),
            "status": args.status,
            "evidence": args.evidence or args.input or args.result_path,
            "caveat": args.caveat,
        })
    if not rows:
        raise HarnessError("No result rows could be built from --input, --metric, or --summary.")
    return rows


def write_result_rows(root: Path, args: argparse.Namespace, rows: list[dict[str, str]]) -> list[str]:
    working_output = root / "05_results" / "experiment_results.csv"
    merged = upsert_rows(
        read_csv(working_output, RESULT_HEADER),
        rows,
        ("experiment_id", "claim_id", "dataset", "split", "method", "baseline_id", "metric"),
    )
    write_csv(working_output, RESULT_HEADER, merged)
    outputs = ["05_results/experiment_results.csv"]
    if args.final_export:
        final_output = root / "09_report" / "results" / "experiment_results.csv"
        final_rows = upsert_rows(
            read_csv(final_output, RESULT_HEADER),
            rows,
            ("experiment_id", "claim_id", "dataset", "split", "method", "baseline_id", "metric"),
        )
        write_csv(final_output, RESULT_HEADER, final_rows)
        outputs.append("09_report/results/experiment_results.csv")
    return outputs


def parse_artifacts(args: argparse.Namespace) -> list[tuple[str, str, str]]:
    artifacts: list[tuple[str, str, str]] = []
    for value in args.artifact or []:
        if "=" not in value:
            raise HarnessError("--artifact must use artifact_id=path or artifact_id:kind=path.")
        left, path = value.split("=", 1)
        left = left.strip()
        path = path.strip()
        if not left or not path:
            raise HarnessError("--artifact must include artifact id and path.")
        if ":" in left:
            artifact_id, kind = [part.strip() for part in left.split(":", 1)]
        else:
            artifact_id = left
            kind = left
        artifacts.append((artifact_id, kind, path))
    if args.input:
        artifacts.append(("metric_input", "metrics", args.input))
    if args.result_path:
        artifacts.append(("result_path", "result", args.result_path))
    if args.evidence:
        artifacts.append(("evidence", "evidence", args.evidence))
    return artifacts


def parse_data_roots(args: argparse.Namespace) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for value in args.data_root or []:
        if "=" not in value:
            raise HarnessError("--data-root must use data_id=root_or_uri.")
        data_id, root_uri = value.split("=", 1)
        data_id = data_id.strip()
        root_uri = root_uri.strip()
        if not data_id or not root_uri:
            raise HarnessError("--data-root must include data id and root/URI.")
        rows.append((data_id, root_uri))
    return rows


def update_registries(root: Path, args: argparse.Namespace) -> list[str]:
    timestamp = now_iso()
    artifact_rows = [
        artifact_row(
            experiment_id=args.exp_id,
            artifact_id=artifact_id,
            kind=kind,
            path=path,
            produced_by=args.agent,
            status=args.status,
            notes=args.summary,
            timestamp=timestamp,
        )
        for artifact_id, kind, path in parse_artifacts(args)
    ]
    upsert_artifact_rows(root, artifact_rows)
    data_rows = [
        data_root_row(
            data_id=data_id,
            root_uri=root_uri,
            split_version=args.data_split or args.dataset or "not recorded",
            produced_by=args.agent,
            used_by_experiments=args.exp_id,
            status=args.data_status,
            notes=args.rationale or args.summary,
            timestamp=timestamp,
        )
        for data_id, root_uri in parse_data_roots(args)
    ]
    append_data_root_rows(root, data_rows)
    outputs: list[str] = []
    if artifact_rows:
        outputs.append("03_experiments/artifact_registry.csv")
    if data_rows:
        outputs.append("03_experiments/data_roots.md")
    return outputs


def summarize_result_rows(rows: list[dict[str, str]]) -> str:
    return "; ".join(
        f"{row['metric']}={row['value']}" + (f" delta={row['delta']}" if row.get("delta") else "")
        for row in rows
    )


def run_complete(args: argparse.Namespace) -> int:
    if args.status in {"succeeded", "failed"} and not args.result_analysis.strip() and not args.allow_pending_analysis:
        raise HarnessError("--result-analysis is required for succeeded/failed experiments unless --allow-pending-analysis is set.")
    root = project_root(args.project)
    rows = result_rows_from_args(root, args)
    result_outputs = write_result_rows(root, args, rows)
    registry_outputs = update_registries(root, args)
    result_summary = args.summary or summarize_result_rows(rows)
    evidence = args.evidence or args.input or args.result_path
    append_experiment_journal_row(
        root,
        exp_id=args.exp_id,
        rationale=args.rationale,
        dataset=args.dataset,
        method=args.method,
        baseline_id=args.baseline_id,
        result_summary=result_summary,
        result_analysis=args.result_analysis,
        evidence=evidence,
        caveat=args.caveat,
    )
    append_experiment_analysis_note(
        root,
        exp_id=args.exp_id,
        rationale=args.rationale,
        dataset=args.dataset,
        method=args.method,
        baseline_id=args.baseline_id,
        result_summary=result_summary,
        result_analysis=args.result_analysis,
        evidence=evidence,
        caveat=args.caveat,
    )
    timestamp = now_iso()
    analysis_next = (
        args.next_action
        or "Use this completed experiment to update claims, robustness checks, or the next experiment plan."
    )

    def update_run(data: dict[str, Any]) -> None:
        data["status"] = args.status
        data["owner_agent"] = args.agent
        data["current_step"] = f"Experiment {args.exp_id} completed with status {args.status}."
        data["display_summary"] = result_summary
        data["judgement"] = args.result_analysis or "analysis pending"
        data["next_action"] = analysis_next
        data["dataset"] = args.dataset
        data["method"] = args.method
        data["baseline_id"] = args.baseline_id
        data["claim_id"] = args.claim_id
        if args.result_path:
            data["result_path"] = args.result_path
        if args.expected_output:
            data["expected_output"] = args.expected_output
        if args.check_procedure:
            data["check_procedure"] = args.check_procedure
        data["updated_at"] = timestamp
        data["finished_at"] = timestamp
        append_run_history(data, f"experiment_complete:{args.status}", result_summary)

    mutate_run_state(root, args.exp_id, update_run)
    outputs = [
        *result_outputs,
        f"03_experiments/{args.exp_id}/analysis.md",
        f"03_experiments/{args.exp_id}/run_state.json",
        "05_results/experiment_journal.md",
        "05_results/experiment_journal.csv",
        *registry_outputs,
    ]
    agent_status = "blocked" if args.status in {"failed", "blocked"} else "waiting"
    update_agent_status(
        root,
        args.agent,
        agent_status,
        task=f"Recorded completion for {args.exp_id}: {args.status}.",
        stage="experiment_complete",
        outputs=outputs,
        notes=args.result_analysis or "analysis pending",
        append_note=True,
    )
    append_agent_event(
        root,
        "experiment_complete",
        args.agent,
        status=agent_status,
        task=f"Recorded completion for {args.exp_id}: {args.status}.",
        stage="experiment_complete",
        outputs=outputs,
        notes=args.result_analysis or "analysis pending",
    )
    refresh_report_index(root, include_report=args.final_export)
    payload = {"project": args.project, "exp_id": args.exp_id, "status": args.status, "outputs": outputs}
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print(f"completed experiment: {args.exp_id} -> {args.status}")
        for output in outputs:
            print(output)
    return 0


def main() -> int:
    from scripts.commands.experiments.experiments import main as experiments_main
    if len(sys.argv) < 2 or sys.argv[1] != "complete":
        sys.argv.insert(1, "complete")
    return experiments_main()


if __name__ == "__main__":
    raise SystemExit(main())
