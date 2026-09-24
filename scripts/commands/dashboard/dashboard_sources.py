#!/usr/bin/env python3
"""Build a dashboard source manifest without mutating project state."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from scripts.commands.reports.report_snapshot import report_artifact_files, report_tables
    from scripts.harness.state import project_root
except ModuleNotFoundError:
    from scripts.commands.reports.report_snapshot import report_artifact_files, report_tables
    from scripts.harness.state import project_root


SOURCE_SPECS = (
    ("agent_status", "Agent Status", "state/agent_status.json", True, "agents"),
    ("command_queue", "Command Queue", "state/command_queue.json", True, "commands"),
    ("loop_summary", "Loop Summary", "state/loop_summary.json", True, None),
    ("agent_events", "Agent Events", "state/agent_events.jsonl", True, None),
    ("agent_messages", "Agent Messages", "state/agent_messages.json", False, "messages"),
    ("agent_votes", "Vote Gates", "state/agent_votes.json", False, "votes"),
    ("pattern_memory", "Pattern Memory", "state/pattern_memory.json", False, "patterns"),
    ("ralph_loop", "Ralph Loops", "state/ralph_loop.json", False, "runs"),
    ("gpu_queue", "GPU Queue", "state/gpu_experiment_queue.json", False, "jobs"),
    ("resource_ledger", "Resource Ledger", "state/resource_ledger.json", False, "entries"),
    ("phase_gates", "Phase Gates", "state/phase_gates.json", False, "phases"),
    ("current_state", "Current State", "state/current_state.md", True, None),
    ("next_actions", "Next Actions", "state/next_actions.md", True, None),
    ("report_readme", "Report README", "09_report/README.md", True, None),
)


def safe_mtime(path: Path) -> float:
    if not path.exists():
        return 0.0
    return path.stat().st_mtime


def iso_from_timestamp(timestamp: float) -> str:
    if timestamp <= 0:
        return ""
    return datetime.fromtimestamp(timestamp, timezone.utc).astimezone().isoformat(timespec="seconds")


def json_record_count(path: Path, field: str | None) -> int:
    if not path.is_file():
        return 0
    if field is None:
        return 1
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 0
    value = data.get(field) if isinstance(data, dict) else None
    return len(value) if isinstance(value, list) else 0


def jsonl_record_count(path: Path) -> int:
    if not path.is_file():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip())


def file_entry(root: Path, key: str, label: str, relative_path: str, required: bool, field: str | None) -> dict[str, Any]:
    path = root / relative_path
    records = jsonl_record_count(path) if relative_path.endswith(".jsonl") else json_record_count(path, field)
    if relative_path.endswith(".md") and path.is_file():
        records = 1
    return {
        "key": key,
        "label": label,
        "path": relative_path,
        "required": required,
        "status": "available" if path.exists() else "missing",
        "records": records,
        "updated_at": iso_from_timestamp(safe_mtime(path)),
    }


def aggregate_entry(root: Path, key: str, label: str, relative_path: str, required: bool, paths: list[Path]) -> dict[str, Any]:
    mtimes = [safe_mtime(path) for path in paths]
    return {
        "key": key,
        "label": label,
        "path": relative_path,
        "required": required,
        "status": "available" if paths else ("missing" if required else "empty"),
        "records": len(paths),
        "updated_at": iso_from_timestamp(max(mtimes, default=0)),
    }


def build_dashboard_sources(root: Path) -> dict[str, Any]:
    """Return source coverage for every dashboard data lane."""
    sources = [
        file_entry(root, key, label, relative_path, required, field)
        for key, label, relative_path, required, field in SOURCE_SPECS
    ]

    session_paths = sorted((root / "state" / "sessions").glob("*/session.json"))
    checkpoint_paths = sorted((root / "state" / "checkpoints").glob("*.json"))
    run_state_paths = sorted((root / "03_experiments").glob("exp_*/run_state.json"))
    table_paths = [root / table["path"] for table in report_tables(root)]
    artifact_paths = report_artifact_files(root, limit=50)
    sources.extend([
        aggregate_entry(root, "sessions", "Session Workspaces", "state/sessions/*/session.json", False, session_paths),
        aggregate_entry(root, "checkpoints", "Run Checkpoints", "state/checkpoints/*.json", False, checkpoint_paths),
        aggregate_entry(root, "experiment_runs", "Experiment Runs", "03_experiments/exp_*/run_state.json", False, run_state_paths),
        aggregate_entry(root, "report_tables", "Report Tables", "09_report/results/*.csv", False, table_paths),
        aggregate_entry(root, "report_artifacts", "Report Artifacts", "09_report/{results,analysis,figures}", False, artifact_paths),
    ])

    available = sum(1 for source in sources if source["status"] == "available")
    required_missing = [
        source["path"]
        for source in sources
        if source["required"] and source["status"] != "available"
    ]
    last_update = max((safe_mtime(root / source["path"]) for source in sources if "*" not in source["path"] and "{" not in source["path"]), default=0)
    return {
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "last_source_update": iso_from_timestamp(last_update),
        "coverage": {
            "available": available,
            "total": len(sources),
            "required_missing": required_missing,
        },
        "sources": sources,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Print dashboard data source coverage.")
    parser.add_argument("--project", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(json.dumps(build_dashboard_sources(project_root(args.project)), indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
