#!/usr/bin/env python3
"""Diagnose experiment run states and recommend repair actions."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scripts.harness.state import (
    append_agent_event,
    load_run_state,
    mutate_command_queue,
    now_iso,
    project_root,
    update_agent_status,
)
from scripts.harness.workflow_hooks import refresh_report_index

CSV_HEADER = ["exp_id", "status", "severity", "diagnosis", "next_action", "result_path"]


def markdown_cell(value: Any) -> str:
    return str(value).replace("|", "\\|")


def setup_subparsers(subparsers: argparse._SubParsersAction) -> None:
    diagnose = subparsers.add_parser("diagnose", help="Diagnose experiment failures, stale runs, and missing results.")
    diagnose.add_argument("--project", required=True)
    diagnose.add_argument("--exp-id", default="")
    diagnose.add_argument("--write-report", action="store_true")
    diagnose.add_argument("--strict", action="store_true")
    diagnose.add_argument("--json", action="store_true")


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def stale_running(updated_at: str, hours: int = 12) -> bool:
    parsed = parse_time(updated_at)
    if not parsed:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return (datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)).total_seconds() > hours * 3600


def result_exists(root: Path, state: dict[str, Any]) -> bool:
    result_path = str(state.get("result_path") or "").strip()
    if not result_path:
        return False
    path = root / result_path
    if path.is_file():
        return path.stat().st_size > 0
    if path.is_dir():
        return any(item.is_file() and item.stat().st_size > 0 for item in path.rglob("*"))
    return False


def likely_cause(log_text: str) -> str:
    lower = log_text.lower()
    patterns = [
        ("out of memory|oom|cuda out of memory", "Likely GPU memory exhaustion."),
        ("traceback|exception|runtimeerror|valueerror|keyerror", "Likely code exception; inspect traceback."),
        ("no such file|file not found|not found", "Likely missing file, dataset, or checkpoint path."),
        ("timeout|time limit|cancelled", "Likely timeout or external cancellation."),
        ("nan|inf|diverg", "Likely numerical instability."),
    ]
    for pattern, cause in patterns:
        if re.search(pattern, lower):
            return cause
    return "No obvious failure signature found."


def experiment_dirs(root: Path, exp_id: str = "") -> list[Path]:
    base = root / "03_experiments"
    if exp_id:
        return [base / exp_id] if (base / exp_id).is_dir() else []
    return sorted(path for path in base.glob("exp_*") if path.is_dir())


def diagnose_experiment(root: Path, exp_dir: Path) -> dict[str, str]:
    state = load_run_state(root, exp_dir.name)
    status = str(state.get("status") or "planned").lower()
    log_text = "\n".join([
        read_text(exp_dir / "run_log.md"),
        read_text(root / str(state.get("log_path") or "")),
        "\n".join(str(item.get("note") or "") for item in state.get("history", []) if isinstance(item, dict)),
    ])
    has_result = result_exists(root, state)
    severity = "info"
    diagnosis = "No repair needed."
    next_action = str(state.get("next_action") or "").strip() or "Continue with the planned experiment workflow."

    if status in {"failed", "blocked", "cancelled"}:
        severity = "blocker" if status in {"failed", "blocked"} else "warning"
        diagnosis = likely_cause(log_text)
        next_action = "Record the failure cause, run the smallest reproduction, then either repair and retry or explicitly abandon the run."
    elif status == "running" and stale_running(str(state.get("updated_at") or "")):
        severity = "warning"
        diagnosis = "Run is marked running but has a stale update timestamp."
        next_action = "Synchronize scheduler/run state, then mark the run succeeded, failed, blocked, or cancelled."
    elif status == "succeeded" and not has_result:
        severity = "warning"
        diagnosis = "Run is marked succeeded but no non-empty result artifact was found."
        next_action = "Attach or ingest the result artifact before using this run as evidence."
    elif status in {"planned", "queued"}:
        severity = "info"
        diagnosis = "Run has not produced evidence yet."
        next_action = "Keep preregistration and launch conditions current before execution."

    return {
        "exp_id": exp_dir.name,
        "status": status,
        "severity": severity,
        "diagnosis": diagnosis,
        "next_action": next_action,
        "result_path": str(state.get("result_path") or ""),
    }


def diagnose_project(root: Path, exp_id: str = "") -> dict[str, Any]:
    rows = [diagnose_experiment(root, exp_dir) for exp_dir in experiment_dirs(root, exp_id)]
    blockers = [row for row in rows if row["severity"] == "blocker"]
    warnings = [row for row in rows if row["severity"] == "warning"]
    return {
        "project": root.name,
        "status": "blocked" if blockers else "warning" if warnings else "ready",
        "blockers": [f"{row['exp_id']}: {row['diagnosis']}" for row in blockers],
        "warnings": [f"{row['exp_id']}: {row['diagnosis']}" for row in warnings],
        "experiments": rows,
    }


def owner_for_diagnosis(row: dict[str, str]) -> str:
    diagnosis = row.get("diagnosis", "").lower()
    next_action = row.get("next_action", "").lower()
    if "ingest" in next_action or "result artifact" in next_action:
        return "data_analyst"
    if "scheduler" in next_action or "failed" in next_action or "traceback" in diagnosis:
        return "code_agent"
    return "experiment_designer"


def upsert_repair_commands(root: Path, report: dict[str, Any]) -> list[str]:
    actionable = [
        row for row in report.get("experiments", [])
        if row.get("severity") in {"blocker", "warning"}
    ]
    if not actionable:
        return []
    timestamp = now_iso()
    command_ids: list[str] = []

    def mutate(queue: dict[str, Any]) -> None:
        existing = {str(command.get("id") or ""): command for command in queue.get("commands", [])}
        for row in actionable:
            exp_id = row["exp_id"]
            command_id = f"repair_{exp_id}"
            command_ids.append(command_id)
            command = existing.get(command_id)
            payload = {
                "id": command_id,
                "action": row["next_action"],
                "owner_agent": owner_for_diagnosis(row),
                "priority": "high" if row["severity"] == "blocker" else "medium",
                "status": "open",
                "required_inputs": [
                    f"03_experiments/{exp_id}/run_state.json",
                    f"03_experiments/{exp_id}/run_log.md",
                    "07_reviews/experiment_diagnosis.md",
                ],
                "expected_outputs": [
                    f"03_experiments/{exp_id}/run_state.json",
                    f"03_experiments/{exp_id}/run_log.md",
                    "05_results/experiment_journal.md",
                    "state/progress_hooks.jsonl",
                ],
                "depends_on": [],
                "parallel_group": f"experiment_repair_{exp_id}",
                "display_summary": f"Repair or resolve experiment diagnosis for {exp_id}.",
                "why_now": row["diagnosis"],
                "done_when": "The run state, run log, and experiment journal explain the outcome and next evidence step.",
                "requires_vote": False,
                "vote_id": "",
                "risk_level": "high" if row["severity"] == "blocker" else "medium",
                "updated_at": timestamp,
                "notes": f"Generated by experiment_diagnosis.py: {row['diagnosis']}",
            }
            if command is None:
                payload["created_at"] = timestamp
                queue.setdefault("commands", []).append(payload)
            else:
                command.update(payload)
                command.setdefault("created_at", timestamp)

    mutate_command_queue(root, mutate)
    return command_ids


def sync_diagnosis_lifecycle(root: Path, report: dict[str, Any], outputs: list[str], command_ids: list[str]) -> None:
    status = "blocked" if report.get("blockers") else "waiting"
    note = (
        f"Experiment diagnosis wrote {len(command_ids)} repair command(s)."
        if command_ids
        else "Experiment diagnosis found no repair commands to enqueue."
    )
    update_agent_status(
        root,
        "director",
        status,
        task="Review experiment diagnosis and route repair actions.",
        stage="experiment_diagnosis",
        outputs=outputs,
        notes=note,
        append_note=True,
    )
    append_agent_event(
        root,
        "experiment_diagnosis",
        "director",
        status=status,
        task="Review experiment diagnosis and route repair actions.",
        stage="experiment_diagnosis",
        outputs=outputs,
        notes=note,
    )


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Experiment Diagnosis",
        "",
        f"- Project: `{report['project']}`",
        f"- Status: `{report['status']}`",
        f"- Blockers: {len(report['blockers'])}",
        f"- Warnings: {len(report['warnings'])}",
        "",
        "| Experiment | Status | Severity | Diagnosis | Next Action |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in report["experiments"]:
        diagnosis = markdown_cell(row["diagnosis"])
        next_action = markdown_cell(row["next_action"])
        lines.append(
            f"| {row['exp_id']} | {row['status']} | {row['severity']} | "
            f"{diagnosis} | {next_action} |"
        )
    return "\n".join(lines) + "\n"


def write_csv(root: Path, report: dict[str, Any]) -> Path:
    path = root / "09_report" / "results" / "experiment_diagnosis.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_HEADER, lineterminator="\n")
        writer.writeheader()
        writer.writerows(report["experiments"])
    return path


def run_diagnose(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    report = diagnose_project(root, args.exp_id)
    if args.write_report:
        report_path = root / "07_reviews" / "experiment_diagnosis.md"
        report_path.write_text(render_markdown(report), encoding="utf-8")
        csv_path = write_csv(root, report)
        command_ids = upsert_repair_commands(root, report)
        sync_diagnosis_lifecycle(
            root,
            report,
            [report_path.relative_to(root).as_posix(), csv_path.relative_to(root).as_posix(), "state/command_queue.json"],
            command_ids,
        )
        refresh_report_index(root, include_report=True)
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print(render_markdown(report).rstrip())
        if args.write_report:
            print("07_reviews/experiment_diagnosis.md")
            print(csv_path.relative_to(root).as_posix())
    return 1 if args.strict and report["blockers"] else 0


def main() -> int:
    from scripts.commands.experiments.experiments import main as experiments_main
    if len(sys.argv) < 2 or sys.argv[1] != "diagnose":
        sys.argv.insert(1, "diagnose")
    return experiments_main()


if __name__ == "__main__":
    raise SystemExit(main())
