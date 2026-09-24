#!/usr/bin/env python3
"""Record durable mid-pass progress checkpoints."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from scripts.harness.agent_limits import (
    extract_limit_pct,
    run_status_command,
)
from scripts.harness.experiment_journal import (
    append_experiment_analysis_note,
    append_experiment_journal_row,
)
from scripts.harness.state import (
    AGENT_STATUSES,
    RUN_STATUSES,
    HarnessError,
    append_agent_event,
    append_run_history,
    find_agent,
    load_agent_status,
    load_command_queue,
    mutate_run_state,
    now_iso,
    owned_active_commands,
    owner_matches,
    project_root,
    split_values,
    update_agent_status,
    update_command_for_agent,
)
from scripts.harness.state_io import locked_state_file
from scripts.harness.workflow_hooks import refresh_report_index
from scripts.harness.workspace_profile import (
    ProfileError,
    workspace_agent_limit_enabled,
    workspace_agent_limit_json_paths,
    workspace_agent_limit_status_command,
    workspace_agent_limit_threshold,
    workspace_agent_limit_timeout,
)

KINDS = {
    "observation",
    "result",
    "experiment_result",
    "memory",
    "direction",
    "blocker",
    "handoff",
}

EXPERIMENT_RESULT_FIELDS = [
    "experiment_id",
    "claim_id",
    "dataset",
    "method",
    "baseline_id",
    "metric",
    "value",
    "delta",
    "status",
    "evidence",
    "caveat",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Persist a mid-pass progress checkpoint.")
    sub = parser.add_subparsers(dest="command", required=True)

    record = sub.add_parser("record", help="Record a durable progress checkpoint.")
    record.add_argument("--project", required=True)
    record.add_argument("--agent", required=True)
    record.add_argument("--summary", required=True)
    record.add_argument("--kind", choices=sorted(KINDS), default="observation")
    record.add_argument("--detail", action="append", dest="details")
    record.add_argument("--evidence", action="append", dest="evidence")
    record.add_argument("--output", action="append", dest="outputs")
    record.add_argument("--memory", action="append", dest="memory_notes", help="Durable memory note to append to state/agent_memory.md.")
    record.add_argument("--next-action", action="append", dest="next_actions")
    record.add_argument("--open-question", action="append", dest="open_questions")
    record.add_argument("--command-id", default="")
    record.add_argument("--exp-id", default="")
    record.add_argument("--stage", default="")
    record.add_argument("--status", choices=sorted(AGENT_STATUSES), default="running")
    record.add_argument("--run-status", choices=sorted(RUN_STATUSES), help="Optional experiment run_state status.")
    record.add_argument("--result-path", default="", help="Project-relative result path for run_state.")
    record.add_argument("--rationale", default="", help="Why this experiment/result checkpoint was recorded.")
    record.add_argument("--dataset", default="", help="Dataset label for experiment journal rows.")
    record.add_argument("--method", default="", help="Method label for experiment journal rows.")
    record.add_argument("--baseline-id", default="", help="Baseline label for experiment journal rows.")
    record.add_argument(
        "--result-analysis",
        "--analysis-note",
        default="",
        help="Why the result improved, regressed, or stayed flat.",
    )
    record.add_argument("--caveat", default="", help="Caveat for experiment journal rows.")
    record.add_argument("--session-id", default="", help="Optional session folder under state/sessions/.")
    record.add_argument("--append-to", action="append", dest="append_paths", help="Extra project-relative Markdown/text file to append this checkpoint to.")
    record.add_argument("--no-current-state", action="store_true", help="Do not append the checkpoint to state/current_state.md.")
    record.add_argument("--no-run-log", action="store_true", help="Do not append experiment checkpoints to 03_experiments/<exp_id>/run_log.md.")
    record.add_argument("--no-status", action="store_true", help="Do not update agent_status.json.")
    record.add_argument("--no-refresh", action="store_true", help="Do not refresh report index after recording.")
    record.add_argument(
        "--allow-open-commands",
        action="store_true",
        help="Allow --status done even when the agent owns open/in-progress commands.",
    )

    list_cmd = sub.add_parser("list", help="List recent progress checkpoints.")
    list_cmd.add_argument("--project", required=True)
    list_cmd.add_argument("--limit", type=int, default=20)
    list_cmd.add_argument("--json", action="store_true")

    validate = sub.add_parser("validate", help="Validate progress checkpoint log.")
    validate.add_argument("--project", required=True)

    limit = sub.add_parser("limit-handoff", help="Record a continuation handoff when agent usage limits are low.")
    limit.add_argument("--project", required=True)
    limit.add_argument("--agent", required=True)
    limit.add_argument("--summary", required=True, help="What this session accomplished.")
    limit.add_argument("--five-hour-remaining-pct", type=float)
    limit.add_argument("--weekly-remaining-pct", type=float)
    limit.add_argument("--threshold-pct", type=float, default=5.0)
    limit.add_argument("--in-progress", action="append", dest="in_progress")
    limit.add_argument("--next-action", action="append", dest="next_actions")
    limit.add_argument("--memory", action="append", dest="memory_notes")
    limit.add_argument("--open-question", action="append", dest="open_questions")
    limit.add_argument("--command-id", default="")
    limit.add_argument("--force", action="store_true", help="Write the handoff even when reported limits are above threshold.")
    limit.add_argument("--no-refresh", action="store_true", help="Do not refresh report index after recording.")

    check = sub.add_parser("check-limits", help="Run an opt-in non-interactive status command and record a handoff if limits are low.")
    check.add_argument("--project", required=True)
    check.add_argument("--agent", required=True)
    check.add_argument("--summary", required=True, help="What this session accomplished if a handoff is needed.")
    check.add_argument("--in-progress", action="append", dest="in_progress")
    check.add_argument("--next-action", action="append", dest="next_actions")
    check.add_argument("--memory", action="append", dest="memory_notes")
    check.add_argument("--open-question", action="append", dest="open_questions")
    check.add_argument("--command-id", default="")
    check.add_argument("--threshold-pct", type=float, help="Override the configured handoff threshold.")
    check.add_argument("--status-command-json", default="", help="Override status command as a JSON argv array. Intended for explicit local use or tests.")
    check.add_argument("--status-json-file", default="", help="Read status JSON from a project-relative file instead of running a command.")
    check.add_argument("--force", action="store_true", help="Write the handoff even when reported limits are above threshold.")
    check.add_argument("--no-refresh", action="store_true", help="Do not refresh report index after recording.")

    return parser.parse_args()


def progress_log_jsonl(root: Path) -> Path:
    return root / "state" / "progress_hooks.jsonl"


def progress_log_md(root: Path) -> Path:
    return root / "state" / "sessions" / "progress_log.md"


def limit_handoff_md(root: Path) -> Path:
    return root / "state" / "limit_handoff.md"


def safe_project_path(root: Path, value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise HarnessError(f"Path must be project-relative and must not contain '..': {value}")
    return root / candidate


def safe_single_name(value: str, label: str) -> str:
    candidate = Path(value)
    if not value or candidate.is_absolute() or len(candidate.parts) != 1 or ".." in candidate.parts:
        raise HarnessError(f"{label} must be a single folder/file-safe name.")
    return value


def validate_reference_values(root: Path, values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        # Allow free-form labels such as "User-provided idea", but validate path-like values.
        if "/" in value or "." in Path(value).name:
            safe_project_path(root, value)
        result.append(value)
    return result


def validate_project_paths(root: Path, values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if not value:
            continue
        safe_project_path(root, value)
        result.append(value)
    return result


def session_progress_log(root: Path, session_id: str) -> Path:
    safe_id = safe_single_name(session_id, "session id")
    session_dir = root / "state" / "sessions" / safe_id
    if not (session_dir / "session.json").is_file():
        raise HarnessError(f"Session not found: state/sessions/{safe_id}/session.json")
    return session_dir / "progress_log.md"


def append_text(path: Path, text: str) -> None:
    with locked_state_file(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        existing = path.read_text(encoding="utf-8") if path.exists() else ""
        separator = "\n" if existing and not existing.endswith("\n") else ""
        path.write_text(existing + separator + text, encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    with locked_state_file(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")


def markdown_block(record: dict[str, Any]) -> str:
    lines = [
        "",
        f"## {record['timestamp']} - {record['kind']}: {record['summary']}",
        "",
        f"- Agent: `{record['agent']}`",
    ]
    if record.get("status"):
        lines.append(f"- Status: `{record['status']}`")
    if record.get("stage"):
        lines.append(f"- Stage: {record['stage']}")
    if record.get("command_id"):
        lines.append(f"- Command: `{record['command_id']}`")
    if record.get("exp_id"):
        lines.append(f"- Experiment: `{record['exp_id']}`")
    if record.get("details"):
        lines.extend(["", "### Details", ""])
        lines.extend(f"- {item}" for item in record["details"])
    if record.get("evidence"):
        lines.extend(["", "### Evidence", ""])
        lines.extend(f"- `{item}`" if "/" in item else f"- {item}" for item in record["evidence"])
    if record.get("outputs"):
        lines.extend(["", "### Outputs", ""])
        lines.extend(f"- `{item}`" if "/" in item else f"- {item}" for item in record["outputs"])
    if record.get("memory_notes"):
        lines.extend(["", "### Memory Notes", ""])
        lines.extend(f"- {item}" for item in record["memory_notes"])
    if record.get("next_actions"):
        lines.extend(["", "### Next Actions", ""])
        lines.extend(f"- {item}" for item in record["next_actions"])
    if record.get("open_questions"):
        lines.extend(["", "### Open Questions", ""])
        lines.extend(f"- {item}" for item in record["open_questions"])
    return "\n".join(lines) + "\n"


def append_experiment_journal(root: Path, record: dict[str, Any]) -> None:
    if record.get("kind") != "experiment_result" or not record.get("exp_id"):
        return
    evidence_values = record.get("outputs") or record.get("evidence") or []
    evidence = "; ".join(str(value) for value in evidence_values) or record.get("result_path") or "-"
    append_experiment_result_row(root, record, evidence)
    append_experiment_journal_row(
        root,
        exp_id=record["exp_id"],
        rationale=record.get("rationale", ""),
        dataset=record.get("dataset", ""),
        method=record.get("method", ""),
        baseline_id=record.get("baseline_id", ""),
        result_summary=record["summary"],
        result_analysis=record.get("result_analysis", ""),
        evidence=evidence,
        caveat=record.get("caveat", ""),
        timestamp=record["timestamp"],
    )
    append_experiment_analysis_note(
        root,
        exp_id=record["exp_id"],
        rationale=record.get("rationale", ""),
        dataset=record.get("dataset", ""),
        method=record.get("method", ""),
        baseline_id=record.get("baseline_id", ""),
        result_summary=record["summary"],
        result_analysis=record.get("result_analysis", ""),
        evidence=evidence,
        caveat=record.get("caveat", ""),
        timestamp=record["timestamp"],
    )


def append_experiment_result_row(root: Path, record: dict[str, Any], evidence: str) -> None:
    path = root / "05_results" / "experiment_results.csv"
    with locked_state_file(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        needs_header = not path.exists() or not path.read_text(encoding="utf-8").strip()
        with path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=EXPERIMENT_RESULT_FIELDS)
            if needs_header:
                writer.writeheader()
            writer.writerow({
                "experiment_id": record["exp_id"],
                "claim_id": "",
                "dataset": record.get("dataset", ""),
                "method": record.get("method", ""),
                "baseline_id": record.get("baseline_id", ""),
                "metric": "checkpoint",
                "value": record["summary"],
                "delta": "",
                "status": record.get("run_status", "") or record.get("status", ""),
                "evidence": evidence,
                "caveat": record.get("caveat", ""),
            })


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    with locked_state_file(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def append_memory(root: Path, record: dict[str, Any]) -> None:
    if not record.get("memory_notes"):
        return
    lines = [
        "",
        f"## Memory Checkpoint: {record['timestamp']}",
        "",
        f"- Source: {record['kind']} by `{record['agent']}`",
        f"- Summary: {record['summary']}",
    ]
    lines.extend(f"- {note}" for note in record["memory_notes"])
    append_text(root / "state" / "agent_memory.md", "\n".join(lines) + "\n")


def append_next_actions(root: Path, record: dict[str, Any]) -> None:
    if not record.get("next_actions"):
        return
    lines = ["", f"## Hooked Next Actions: {record['timestamp']}", ""]
    lines.extend(f"- {action}" for action in record["next_actions"])
    append_text(root / "state" / "next_actions.md", "\n".join(lines) + "\n")


def append_open_questions(root: Path, record: dict[str, Any]) -> None:
    if not record.get("open_questions"):
        return
    lines = ["", f"## Hooked Open Questions: {record['timestamp']}", ""]
    lines.extend(f"- {question}" for question in record["open_questions"])
    append_text(root / "state" / "open_questions.md", "\n".join(lines) + "\n")


def update_run_state(root: Path, record: dict[str, Any], run_status: str | None, result_path: str) -> None:
    exp_id = str(record.get("exp_id") or "").strip()
    if not exp_id:
        return

    def mutate(data: dict[str, Any]) -> None:
        if run_status:
            data["status"] = run_status
        data["updated_at"] = record["timestamp"]
        data["current_step"] = record["summary"]
        data["judgement"] = record["summary"] if record["kind"] in {"result", "experiment_result"} else data.get("judgement", "")
        if record.get("next_actions"):
            data["next_action"] = "; ".join(record["next_actions"])
        if result_path:
            data["result_path"] = result_path
        for field in ("dataset", "method", "baseline_id"):
            if record.get(field):
                data[field] = record[field]
        data["notes"] = record["summary"]
        append_run_history(data, "progress_checkpoint", record["summary"])

    mutate_run_state(root, exp_id, mutate)


def command_status_for_agent_status(status: str) -> str:
    if status == "done":
        return "done"
    if status == "blocked":
        return "blocked"
    if status == "running":
        return "in progress"
    return "open"


def preflight_status_update(root: Path, agent: str, status: str, command_id: str, allow_open_commands: bool) -> None:
    status_data = load_agent_status(root)
    find_agent(status_data, agent)
    if status == "done" and not command_id and not allow_open_commands:
        active = owned_active_commands(root, agent)
        if active:
            ids = ", ".join(str(command.get("id")) for command in active)
            raise HarnessError(
                "Refusing to mark agent done while it owns open/in-progress commands: "
                f"{ids}. Pass --command-id to complete one command, record the checkpoint "
                "with a non-terminal status, or use --allow-open-commands explicitly."
            )
    if not command_id:
        return
    queue = load_command_queue(root)
    command = next((item for item in queue["commands"] if item.get("id") == command_id), None)
    if command is None:
        raise HarnessError(f"Command not found: {command_id}")
    owner = str(command.get("owner_agent") or "")
    if not owner_matches(owner, agent):
        raise HarnessError(f"Command {command_id} is owned by {owner!r}, not {agent!r}")


def load_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            raise HarnessError(f"Invalid JSONL in {path} line {line_number}: {exc.msg}.") from exc
        if not isinstance(record, dict):
            raise HarnessError(f"{path} line {line_number} must contain a JSON object.")
        records.append(record)
    return records


def format_pct(value: float | None) -> str:
    if value is None:
        return "not reported"
    return f"{value:.2f}%"


def limit_handoff_needed(args: argparse.Namespace) -> bool:
    reported = [
        value
        for value in (args.five_hour_remaining_pct, args.weekly_remaining_pct)
        if value is not None
    ]
    if not reported and not args.force:
        raise HarnessError("Report --five-hour-remaining-pct or --weekly-remaining-pct, or pass --force.")
    for value in reported:
        if value < 0 or value > 100:
            raise HarnessError("Reported remaining percentages must be between 0 and 100.")
    return args.force or any(value < args.threshold_pct for value in reported)


def decode_status_command(value: str) -> list[str]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as exc:
        raise HarnessError("--status-command-json must be a JSON array of strings.") from exc
    if not isinstance(parsed, list) or not all(isinstance(item, str) and item.strip() for item in parsed):
        raise HarnessError("--status-command-json must be a JSON array of non-empty strings.")
    return parsed


def read_status_payload(args: argparse.Namespace, root: Path) -> dict[str, Any]:
    if args.status_json_file:
        path = safe_project_path(root, args.status_json_file)
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise HarnessError(f"Invalid status JSON file: {args.status_json_file}") from exc
        if not isinstance(payload, dict):
            raise HarnessError("--status-json-file must contain a JSON object.")
        return payload

    if args.status_command_json:
        command = decode_status_command(args.status_command_json)
        timeout_seconds = workspace_agent_limit_timeout()
        return run_status_command(command, timeout_seconds)

    if not workspace_agent_limit_enabled():
        raise HarnessError("agent_limits.enabled is false; configure config/workspace_profile.local.json or pass --status-command-json.")
    command = workspace_agent_limit_status_command()
    timeout_seconds = workspace_agent_limit_timeout()
    return run_status_command(command, timeout_seconds)


def record_checked_limit_handoff(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    try:
        paths = workspace_agent_limit_json_paths()
        threshold = float(args.threshold_pct if args.threshold_pct is not None else workspace_agent_limit_threshold())
    except ProfileError as exc:
        raise HarnessError(str(exc)) from exc
    payload = read_status_payload(args, root)
    five_hour = extract_limit_pct(
        payload,
        paths.get("five_hour_remaining_pct", ""),
        [
            "five_hour_remaining_pct",
            "five_hour_remaining_percent",
            "five_hour.remaining_pct",
            "five_hour.remaining_percent",
            "limits.five_hour.remaining_pct",
            "limits.five_hour.remaining_percent",
        ],
    )
    weekly = extract_limit_pct(
        payload,
        paths.get("weekly_remaining_pct", ""),
        [
            "weekly_remaining_pct",
            "weekly_remaining_percent",
            "weekly.remaining_pct",
            "weekly.remaining_percent",
            "limits.weekly.remaining_pct",
            "limits.weekly.remaining_percent",
        ],
    )
    limit_args = argparse.Namespace(
        project=args.project,
        agent=args.agent,
        summary=args.summary,
        five_hour_remaining_pct=five_hour,
        weekly_remaining_pct=weekly,
        threshold_pct=threshold,
        in_progress=args.in_progress,
        next_actions=args.next_actions,
        memory_notes=args.memory_notes,
        open_questions=args.open_questions,
        command_id=args.command_id,
        force=args.force,
        no_refresh=args.no_refresh,
    )
    return record_limit_handoff(limit_args)


def recent_progress_lines(root: Path, limit: int = 5) -> list[str]:
    lines: list[str] = []
    for record in load_records(progress_log_jsonl(root))[-limit:]:
        summary = str(record.get("summary") or "").strip()
        if not summary:
            continue
        lines.append(
            f"- {record.get('timestamp', '')} `{record.get('kind', '')}` "
            f"{record.get('agent', '')}: {summary}"
        )
    return lines


def build_limit_handoff(root: Path, record: dict[str, Any], args: argparse.Namespace) -> str:
    active = owned_active_commands(root, record["agent"])
    active_lines = [
        f"- `{command.get('id')}`: {command.get('action') or command.get('display_summary') or 'open command'}"
        for command in active
    ]
    prompt_lines = [
        f"Continue project {record['project']} from file state.",
        "Read HANDOFF.md, state/current_state.md, state/agent_memory.md,",
        "state/next_actions.md, state/open_questions.md, state/command_queue.json,",
        "and state/limit_handoff.md.",
        "Before planning experiments or writing claims, also check",
        "03_experiments/data_roots.md, 05_results/experiment_results.csv,",
        "05_results/experiment_journal.md, 05_results/experiment_journal.csv,",
        "and 06_writing/terminology.md.",
        "Resume from the limit handoff. Use harness CLIs yourself. Save progress",
        "to files as you work, especially before the next final response.",
    ]
    lines = [
        "# Agent Limit Handoff",
        "",
        f"- Timestamp: {record['timestamp']}",
        f"- Project: `{record['project']}`",
        f"- Agent: `{record['agent']}`",
        f"- Five-hour remaining: {format_pct(args.five_hour_remaining_pct)}",
        f"- Weekly remaining: {format_pct(args.weekly_remaining_pct)}",
        f"- Threshold: {args.threshold_pct:.2f}%",
        "",
        "## Continue Prompt",
        "",
        "```text",
        *prompt_lines,
        "```",
        "",
        "## Current Session Summary",
        "",
        record["summary"],
        "",
        "## In Progress",
        "",
    ]
    in_progress = record.get("details") or []
    lines.extend(f"- {item}" for item in in_progress) if in_progress else lines.append("- Not specified.")
    lines.extend(["", "## Active Commands", ""])
    lines.extend(active_lines) if active_lines else lines.append("- No active owned commands found.")
    lines.extend(["", "## Next Actions", ""])
    next_actions = record.get("next_actions") or []
    lines.extend(f"- {item}" for item in next_actions) if next_actions else lines.append("- Re-run director triage and choose the next action from file state.")
    lines.extend(["", "## Memory Notes", ""])
    memory_notes = record.get("memory_notes") or []
    lines.extend(f"- {item}" for item in memory_notes) if memory_notes else lines.append("- No additional memory notes supplied.")
    lines.extend(["", "## Open Questions", ""])
    open_questions = record.get("open_questions") or []
    lines.extend(f"- {item}" for item in open_questions) if open_questions else lines.append("- No new open questions supplied.")
    lines.extend(["", "## Recent Progress", ""])
    recent_lines = recent_progress_lines(root)
    lines.extend(recent_lines) if recent_lines else lines.append("- No recent progress checkpoint records found.")
    return "\n".join(lines).rstrip() + "\n"


def record_limit_handoff(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    if not limit_handoff_needed(args):
        print("limit handoff not required")
        return 0
    timestamp = now_iso()
    agent = args.agent.strip()
    summary = args.summary.strip()
    command_id = args.command_id.strip()
    if not agent:
        raise HarnessError("--agent must not be empty.")
    if not summary:
        raise HarnessError("--summary must not be empty.")
    find_agent(load_agent_status(root), agent)
    record = {
        "timestamp": timestamp,
        "project": args.project,
        "agent": agent,
        "kind": "handoff",
        "summary": summary,
        "details": split_values(args.in_progress),
        "evidence": ["state/limit_handoff.md"],
        "outputs": ["state/limit_handoff.md", "state/agent_memory.md"],
        "memory_notes": split_values(args.memory_notes),
        "next_actions": split_values(args.next_actions),
        "open_questions": split_values(args.open_questions),
        "command_id": command_id,
        "exp_id": "",
        "stage": "limit_handoff",
        "status": "running",
        "session_id": "",
        "result_path": "",
    }
    handoff = build_limit_handoff(root, record, args)
    write_text(limit_handoff_md(root), handoff)
    append_jsonl(progress_log_jsonl(root), record)
    append_text(progress_log_md(root), handoff)
    append_text(root / "state" / "current_state.md", handoff)
    append_memory(root, record)
    append_next_actions(root, record)
    append_open_questions(root, record)
    append_agent_event(
        root,
        "limit_handoff",
        agent,
        status="running",
        command_id=command_id,
        task=summary,
        stage="limit_handoff",
        outputs=["state/limit_handoff.md", "state/agent_memory.md"],
        notes="usage limit handoff recorded",
    )
    update_agent_status(
        root,
        agent,
        "running",
        task="Limit handoff recorded; resume from state/limit_handoff.md.",
        stage="limit_handoff",
        outputs=["state/limit_handoff.md", "state/agent_memory.md"],
        notes=summary,
        append_note=True,
    )
    if not args.no_refresh:
        refresh_report_index(root)
    print("recorded limit handoff")
    print("state/limit_handoff.md")
    return 0


def record_checkpoint(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    timestamp = now_iso()
    agent = args.agent.strip()
    summary = args.summary.strip()
    command_id = args.command_id.strip()
    if not agent:
        raise HarnessError("--agent must not be empty.")
    if not summary:
        raise HarnessError("--summary must not be empty.")
    evidence = validate_reference_values(root, split_values(args.evidence))
    outputs = validate_reference_values(root, split_values(args.outputs))
    append_paths = validate_project_paths(root, split_values(args.append_paths))
    result_path = args.result_path.strip()
    if result_path:
        safe_project_path(root, result_path)
    exp_id = args.exp_id.strip()
    if exp_id:
        safe_single_name(exp_id, "exp_id")
    if args.kind == "experiment_result" and exp_id:
        analysis_output = f"03_experiments/{exp_id}/analysis.md"
        if analysis_output not in outputs:
            outputs.append(analysis_output)
        for journal_output in ("05_results/experiment_journal.md", "05_results/experiment_journal.csv"):
            if journal_output not in outputs:
                outputs.append(journal_output)
        if "05_results/experiment_results.csv" not in outputs:
            outputs.append("05_results/experiment_results.csv")
    session_id = args.session_id.strip()
    session_log = session_progress_log(root, session_id) if session_id else None
    if not args.no_status:
        preflight_status_update(root, agent, args.status, command_id, args.allow_open_commands)

    record = {
        "timestamp": timestamp,
        "project": args.project,
        "agent": agent,
        "kind": args.kind,
        "summary": summary,
        "details": split_values(args.details),
        "evidence": evidence,
        "outputs": outputs,
        "memory_notes": split_values(args.memory_notes),
        "next_actions": split_values(args.next_actions),
        "open_questions": split_values(args.open_questions),
        "command_id": command_id,
        "exp_id": exp_id,
        "stage": args.stage,
        "status": args.status,
        "session_id": session_id,
        "result_path": result_path,
        "rationale": args.rationale.strip(),
        "dataset": args.dataset.strip(),
        "method": args.method.strip(),
        "baseline_id": args.baseline_id.strip(),
        "result_analysis": args.result_analysis.strip(),
        "caveat": args.caveat.strip(),
        "run_status": args.run_status or "",
    }
    block = markdown_block(record)

    append_jsonl(progress_log_jsonl(root), record)
    append_text(progress_log_md(root), block)
    if not args.no_current_state:
        append_text(root / "state" / "current_state.md", block)
    append_memory(root, record)
    append_next_actions(root, record)
    append_open_questions(root, record)

    if session_log is not None:
        append_text(session_log, block)
    if exp_id and not args.no_run_log:
        append_text(root / "03_experiments" / exp_id / "run_log.md", block)
    append_experiment_journal(root, record)
    for rel_path in append_paths:
        append_text(safe_project_path(root, rel_path), block)

    if not args.no_status:
        if command_id:
            command_status = command_status_for_agent_status(args.status)
            update_command_for_agent(root, command_id, agent, command_status, summary)
        update_agent_status(
            root,
            agent,
            args.status,
            task=summary,
            stage=args.stage or None,
            outputs=outputs if outputs else None,
            notes=summary,
            append_note=True,
        )
    update_run_state(root, record, args.run_status, result_path)
    append_agent_event(
        root,
        "progress_checkpoint",
        agent,
        status=args.status,
        command_id=command_id,
        task=summary,
        stage=args.stage,
        inputs=evidence,
        outputs=outputs,
        notes=f"{args.kind}: {summary}",
    )
    if not args.no_refresh:
        refresh_report_index(root)
    print(f"recorded progress checkpoint: {args.project}:{args.agent} {timestamp}")
    return 0


def validate_log(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    records = load_records(progress_log_jsonl(root))
    required = {"timestamp", "project", "agent", "kind", "summary"}
    for index, record in enumerate(records, start=1):
        missing = [field for field in required if not str(record.get(field) or "").strip()]
        if missing:
            raise HarnessError(f"progress_hooks.jsonl row {index} missing: {', '.join(missing)}")
        if str(record.get("kind") or "") not in KINDS:
            raise HarnessError(f"progress_hooks.jsonl row {index} has invalid kind: {record.get('kind')!r}")
        for list_field in ("details", "evidence", "outputs", "memory_notes", "next_actions", "open_questions"):
            value = record.get(list_field, [])
            if value is not None and not isinstance(value, list):
                raise HarnessError(f"progress_hooks.jsonl row {index} field {list_field} must be a list.")
        for path_field in ("evidence", "outputs"):
            values = record.get(path_field, [])
            if not isinstance(values, list):
                continue
            for item in values:
                text = str(item or "")
                if "/" not in text and "." not in Path(text).name:
                    continue
                safe_project_path(root, text)
    print(f"valid progress checkpoints: {args.project} ({len(records)} records)")
    return 0


def list_records(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    records = load_records(progress_log_jsonl(root))
    selected = records[-max(args.limit, 0):] if args.limit else records
    if args.json:
        print(json.dumps({"project": args.project, "records": selected}, indent=2, ensure_ascii=False))
    else:
        for record in selected:
            print(
                f"{record.get('timestamp', '')}\t{record.get('kind', '')}\t"
                f"{record.get('agent', '')}\t{record.get('summary', '')}"
            )
    return 0


def main() -> int:
    args = parse_args()
    try:
        if args.command == "record":
            return record_checkpoint(args)
        if args.command == "limit-handoff":
            return record_limit_handoff(args)
        if args.command == "check-limits":
            return record_checked_limit_handoff(args)
        if args.command == "validate":
            return validate_log(args)
        if args.command == "list":
            return list_records(args)
        raise HarnessError(f"Unknown command: {args.command}")
    except (HarnessError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
