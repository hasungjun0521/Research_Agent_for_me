#!/usr/bin/env python3
"""Summarize file-based project state for a fresh agent session."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.commands.agents.agent_orchestrator import (
    command_by_id,
    command_dependencies,
    command_owner,
    select_parallel_commands,
    unfinished_command_dependencies,
)
from scripts.commands.projects.validate_project import workflow_warnings
from scripts.harness.project_diagnostics import latest_activity_mtime, reconciliation_issues
from scripts.harness.state import (
    HarnessError,
    discover_run_states,
    load_agent_events,
    load_agent_messages,
    load_agent_status,
    load_command_queue,
    project_root,
    repo_root,
)

READ_FIRST = [
    "HANDOFF.md",
    "state/current_state.md",
    "state/project_health.md",
    "state/state_doctor.md",
    "state/agent_memory.md",
    "state/next_actions.md",
    "state/open_questions.md",
    "state/command_queue.json",
]
OPTIONAL_READ_FIRST = [
    "state/limit_handoff.md",
    "03_experiments/data_roots.md",
    "03_experiments/artifact_registry.csv",
    "03_experiments/experiment_dag.json",
    "05_results/experiment_results.csv",
    "05_results/experiment_journal.md",
    "05_results/experiment_journal.csv",
    "05_results/claim_graph.md",
    "06_writing/terminology.md",
    "07_reviews/agent_quality_audit.md",
    "08_baselines/baseline_compare.md",
]


LISTING_TOUCH_FILES = [
    "state/current_state.md",
    "state/next_actions.md",
    "HANDOFF.md",
    "05_results/experiment_journal.csv",
]
LISTING_FIELD_WIDTH = 80


def setup_subparsers(subparsers: argparse._SubParsersAction) -> None:
    resume = subparsers.add_parser("resume", help="Print a compact project resume summary.")
    resume.add_argument("--project", help="Project folder name under projects/. Required unless --list is given.")
    resume.add_argument("--list", action="store_true", help="List every project under projects/ with last-touched state, newest first.")
    resume.add_argument("--json", action="store_true")
    resume.add_argument("--max-items", type=int, default=5)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Print a compact project resume summary.")
    parser.add_argument("--project", help="Project folder name under projects/. Required unless --list is given.")
    parser.add_argument(
        "--list",
        action="store_true",
        help="List every project under projects/ with last-touched state, newest first (read-only).",
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--max-items", type=int, default=5)
    args = parser.parse_args(argv)
    if not args.list and not args.project:
        parser.error("--project is required unless --list is given")
    if args.list and args.project:
        print("note: --list ignores --project and scans every project.", file=sys.stderr)
    return args


def read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return [
                {str(key or "").strip(): str(value or "").strip() for key, value in row.items()}
                for row in csv.DictReader(handle)
                if any(str(value or "").strip() for value in row.values())
            ]
    except OSError:
        return []


def nonstarter_journal_rows(root: Path) -> int:
    count = 0
    for row in csv_rows(root / "05_results" / "experiment_journal.csv"):
        experiment = str(row.get("experiment") or "").strip()
        result_summary = str(row.get("result_summary") or "").strip().lower()
        updated_at = str(row.get("updated_at") or "").strip()
        if experiment == "exp_001" and result_summary == "planned" and not updated_at:
            continue
        count += 1
    return count


def working_artifact_summary(root: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    artifact_specs = [
        ("state/project_health.md", "dashboard-free status, blockers, and next best action"),
        ("state/state_doctor.md", "stale or contradictory state diagnostics"),
        ("03_experiments/data_roots.md", "dataset roots and split/version IDs"),
        ("03_experiments/artifact_registry.csv", "experiment output, metric, log, checkpoint, and evidence artifacts"),
        ("03_experiments/experiment_dag.json", "smoke-first experiment DAGs and parallel-run dependencies"),
        ("05_results/experiment_results.csv", "structured working result table"),
        ("05_results/experiment_journal.md", "human-readable experiment ledger"),
        ("05_results/experiment_journal.csv", "structured experiment ledger"),
        ("05_results/claim_graph.md", "working claim-to-evidence graph"),
        ("06_writing/terminology.md", "paper terminology glossary"),
        ("07_reviews/agent_quality_audit.md", "agent continuity quality audit"),
        ("08_baselines/baseline_compare.md", "baseline repository structure comparison"),
    ]
    for relative, purpose in artifact_specs:
        path = root / relative
        text = read_text(path)
        if not path.is_file():
            status = "missing"
            detail = f"Create {relative}; it should track {purpose}."
        elif not text.strip():
            status = "empty"
            detail = f"Populate {relative}; it should track {purpose}."
        elif relative == "03_experiments/artifact_registry.csv":
            real_rows = len(csv_rows(path))
            status = "current" if real_rows else "starter"
            detail = f"{real_rows} experiment artifact row(s)."
        elif relative == "05_results/experiment_results.csv":
            real_rows = len(csv_rows(path))
            status = "current" if real_rows else "starter"
            detail = f"{real_rows} working experiment result row(s)."
        elif relative == "05_results/experiment_journal.csv":
            real_rows = nonstarter_journal_rows(root)
            status = "current" if real_rows else "starter"
            detail = f"{real_rows} non-starter experiment result row(s)."
        elif relative == "03_experiments/experiment_dag.json":
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                data = {}
            plans = data.get("plans") if isinstance(data, dict) else []
            real_rows = len(plans) if isinstance(plans, list) else 0
            status = "current" if real_rows else "starter"
            detail = f"{real_rows} experiment plan(s)."
        elif "to_be_defined" in text:
            status = "starter"
            detail = f"Replace starter placeholders in {relative}; it should track {purpose}."
        else:
            status = "present"
            detail = purpose
        rows.append({"path": relative, "status": status, "detail": detail})
    return rows


def nonempty_lines(text: str, limit: int) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line in {"---"}:
            continue
        if line.startswith("- "):
            line = line[2:].strip()
        lowered = line.lower()
        if lowered.startswith("| ---") or "question | why it matters" in lowered:
            continue
        if line.startswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            cells = [cell for cell in cells if cell]
            if not cells or cells[0].lower() in {"action", "question"}:
                continue
            line = cells[0]
        lines.append(line)
        if len(lines) >= limit:
            break
    return lines


def table_rows(text: str, header: str, limit: int) -> list[str]:
    in_section = False
    rows: list[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("## "):
            in_section = stripped[3:].strip().lower() == header.strip().lower()
            continue
        if not in_section or not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if len(cells) < 2:
            continue
        first = cells[0].strip()
        if not first or first.lower() in {"action", "idea"} or set(first) <= {"-"}:
            continue
        rows.append(first)
        if len(rows) >= limit:
            break
    return rows


def section_lines(text: str, section: str, limit: int) -> list[str]:
    target = section.strip().lower()
    in_section = False
    lines: list[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("## "):
            in_section = stripped[3:].strip().lower() == target
            continue
        if in_section and stripped:
            if stripped.startswith("- "):
                stripped = stripped[2:].strip()
            lines.append(stripped)
            if len(lines) >= limit:
                break
    return lines


def section_items(text: str, section: str, limit: int) -> list[str]:
    target = section.strip().lower()
    in_section = False
    items: list[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped.startswith("## "):
            in_section = stripped[3:].strip().lower() == target
            continue
        if not in_section or not stripped or stripped in {"---"}:
            continue
        if stripped.startswith("|"):
            continue
        if stripped.startswith("- "):
            items.append(stripped[2:].strip())
        elif items:
            items[-1] = f"{items[-1]} {stripped}".strip()
        else:
            items.append(stripped)
    return items[:limit]


def command_summary(queue: dict[str, Any], limit: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for command in queue.get("commands", []):
        if not isinstance(command, dict):
            continue
        status = str(command.get("status") or "").strip().lower()
        if status not in {"open", "in progress", "blocked"}:
            continue
        rows.append({
            "id": str(command.get("id") or ""),
            "status": status,
            "priority": str(command.get("priority") or ""),
            "owner": str(command.get("owner_agent") or ""),
            "summary": str(command.get("display_summary") or command.get("action") or ""),
            "done_when": str(command.get("done_when") or ""),
        })
    return rows[:limit]


def parallel_command_summary(root: Path, queue: dict[str, Any], limit: int) -> list[dict[str, str]]:
    commands = select_parallel_commands(root, queue, max_agents=max(1, limit))
    if len(commands) < 2:
        return []
    rows: list[dict[str, str]] = []
    for command in commands:
        rows.append({
            "id": str(command.get("id") or ""),
            "priority": str(command.get("priority") or ""),
            "owner": command_owner(command),
            "parallel_group": str(command.get("parallel_group") or ""),
            "summary": str(command.get("display_summary") or command.get("action") or ""),
        })
    return rows


def prepared_parallel_prompt_summary(root: Path, queue: dict[str, Any], limit: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    commands_by_id = command_by_id(queue)
    for command in queue.get("commands", []):
        if not isinstance(command, dict):
            continue
        status = str(command.get("status") or "").strip().lower()
        prompt = str(command.get("orchestrator_prompt") or "").strip()
        parallel_group = str(command.get("parallel_group") or "").strip()
        if status != "in progress" or not prompt or not parallel_group:
            continue
        prompt_status = "present" if (root / prompt).is_file() else "missing"
        rows.append({
            "id": str(command.get("id") or ""),
            "owner": command_owner(command),
            "parallel_group": parallel_group,
            "prompt": prompt,
            "prompt_status": prompt_status,
            "depends_on": ", ".join(command_dependencies(command)),
            "unfinished_dependencies": ", ".join(unfinished_command_dependencies(command, commands_by_id)),
            "summary": str(command.get("display_summary") or command.get("action") or ""),
        })
        if len(rows) >= limit:
            break
    return rows


def parallel_batch_manifest_summary(root: Path, limit: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    manifest_dir = root / "state" / "orchestrator_prompts" / "parallel_batches"
    for path in sorted(manifest_dir.glob("*.json"), reverse=True):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        commands = data.get("commands") if isinstance(data, dict) else []
        prompts = data.get("prompts") if isinstance(data, dict) else []
        rows.append({
            "path": path.relative_to(root).as_posix(),
            "timestamp": str(data.get("timestamp") or "") if isinstance(data, dict) else "",
            "commands": str(len(commands) if isinstance(commands, list) else 0),
            "prompts": str(len(prompts) if isinstance(prompts, list) else 0),
        })
        if len(rows) >= limit:
            break
    return rows


def parallel_event_summary(root: Path, limit: int) -> list[dict[str, str]]:
    parallel_events = {
        "parallel_dispatch_plan",
        "parallel_prepared_run",
        "parallel_runner_result",
        "parallel_prepared_runner_result",
        "parallel_finish",
    }
    rows: list[dict[str, str]] = []
    for event in reversed(load_agent_events(root)):
        if str(event.get("event") or "") not in parallel_events:
            continue
        rows.append({
            "timestamp": str(event.get("timestamp") or ""),
            "event": str(event.get("event") or ""),
            "status": str(event.get("status") or ""),
            "stage": str(event.get("stage") or ""),
            "task": str(event.get("task") or ""),
            "notes": str(event.get("notes") or ""),
        })
        if len(rows) >= limit:
            break
    return rows


def message_summary(messages: dict[str, Any], limit: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for message in messages.get("messages", []):
        if not isinstance(message, dict):
            continue
        status = str(message.get("status") or "").strip().lower()
        if status not in {"open", "blocked"}:
            continue
        rows.append({
            "id": str(message.get("id") or ""),
            "status": status,
            "priority": str(message.get("priority") or ""),
            "from": str(message.get("from_agent") or ""),
            "to": str(message.get("to_agent") or ""),
            "summary": str(
                message.get("summary")
                or message.get("subject")
                or message.get("question")
                or message.get("message")
                or message.get("body")
                or ""
            ),
        })
    return rows[:limit]


def agent_summary(status: dict[str, Any], limit: int) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for agent in status.get("agents", []):
        if not isinstance(agent, dict):
            continue
        value = str(agent.get("status") or "").strip().lower()
        if value in {"", "idle", "done"}:
            continue
        rows.append({
            "agent": str(agent.get("agent") or agent.get("name") or ""),
            "status": value,
            "task": str(agent.get("task") or agent.get("current_task") or ""),
            "command_id": str(agent.get("command_id") or ""),
        })
    return rows[:limit]


def continuation_prompt(project: str) -> str:
    return (
        f"Continue project {project} from file state. "
        "Read HANDOFF.md, state/current_state.md, state/project_health.md, "
        "state/state_doctor.md, state/agent_memory.md, state/next_actions.md, "
        "state/open_questions.md, and state/command_queue.json. If present, "
        "also read state/limit_handoff.md. "
        "Check 03_experiments/data_roots.md, 03_experiments/artifact_registry.csv, "
        "03_experiments/experiment_dag.json, 05_results/experiment_results.csv, "
        "05_results/experiment_journal.md, 05_results/experiment_journal.csv, "
        "05_results/claim_graph.md, 06_writing/terminology.md, "
        "07_reviews/agent_quality_audit.md, and 08_baselines/baseline_compare.md "
        "before planning experiments, writing claims, or shaping project code. "
        "If project_health.md or state_doctor.md is missing, still starter-level, "
        "or older than recent project progress, refresh dashboard-free diagnostics "
        "before choosing the next action. Refresh state doctor first, then project "
        "health, so health routing uses the latest state diagnosis. "
        "Before choosing one serial action, inspect parallel work with "
        "scripts.commands.agents.agent_orchestrator status-parallel. If multiple "
        "independent open commands can be handled by different owner agents, use "
        "scripts.commands.agents.agent_orchestrator parallel. If prompts were "
        "already written and commands are in progress, use run-prepared. "
        "Otherwise pick the highest-value next action. Use harness CLIs yourself, "
        "and save meaningful progress with progress_checkpoint during the pass."
    )


def build_resume(root: Path, max_items: int) -> dict[str, Any]:
    current_state = read_text(root / "state" / "current_state.md")
    agent_memory = read_text(root / "state" / "agent_memory.md")
    next_actions = read_text(root / "state" / "next_actions.md")
    open_questions = read_text(root / "state" / "open_questions.md")
    handoff = read_text(root / "HANDOFF.md")
    limit_handoff = read_text(root / "state" / "limit_handoff.md")
    status = load_agent_status(root)
    queue = load_command_queue(root)
    messages = load_agent_messages(root)
    run_states = discover_run_states(root)
    warnings = workflow_warnings(status, queue, run_states)
    current_summary = (
        section_items(current_state, "Research Question", 1)
        + section_items(current_state, "Current Hypothesis", 1)
        + section_items(current_state, "Blockers", max_items)
    )
    return {
        "project": root.name,
        "read_first": READ_FIRST,
        "optional_read_first": [
            path
            for path in OPTIONAL_READ_FIRST
            if (root / path).is_file()
        ],
        "current_stage": section_lines(current_state, "Current Stage", 1),
        "current_state": current_summary[:max_items],
        "memory_notes": (
            section_items(agent_memory, "Stable Project Facts", max_items)
            + section_items(agent_memory, "Important Decisions", max_items)
        )[:max_items],
        "next_actions": table_rows(next_actions, "Immediate Next Actions", max_items)
        or section_lines(next_actions, "Suggested Prompt", max_items),
        "open_questions": nonempty_lines(open_questions, max_items),
        "handoff_next": section_lines(handoff, "Next Best Command", max_items),
        "limit_handoff": (
            section_items(limit_handoff, "Current Session Summary", 1)
            + section_items(limit_handoff, "In Progress", max_items)
            + section_items(limit_handoff, "Next Actions", max_items)
        )[:max_items],
        "working_artifacts": working_artifact_summary(root),
        "active_commands": command_summary(queue, max_items),
        "parallel_commands": parallel_command_summary(root, queue, max_items),
        "prepared_parallel_prompts": prepared_parallel_prompt_summary(root, queue, max_items),
        "parallel_batch_manifests": parallel_batch_manifest_summary(root, max_items),
        "parallel_events": parallel_event_summary(root, max_items),
        "active_agents": agent_summary(status, max_items),
        "open_messages": message_summary(messages, max_items),
        "workflow_warnings": warnings[:max_items],
        "reconciliation": reconciliation_issues(root, latest_activity_mtime(root)),
        "continuation_prompt": continuation_prompt(root.name),
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Project Resume",
        "",
        f"- Project: `{summary['project']}`",
        "",
        "## Read First",
        "",
    ]
    lines.extend(f"- `{path}`" for path in summary["read_first"])
    optional_read = summary.get("optional_read_first", [])
    if optional_read:
        lines.extend(["", "## Optional Read If Present", ""])
        lines.extend(f"- `{path}`" for path in optional_read)

    lines.extend(["", "## Current State", ""])
    current_stage = summary.get("current_stage") or []
    if current_stage:
        lines.append(f"- Stage: {current_stage[0]}")
    for line in summary.get("current_state", []):
        lines.append(f"- {line}")

    reconciliation = summary.get("reconciliation", [])
    if reconciliation:
        lines.extend(["", "## State Reconciliation", ""])
        lines.append("- ⚠️ Canonical state surfaces disagree with real progress. Fix these BEFORE trusting the rest of this resume:")
        for item in reconciliation:
            lines.append(f"  - [{item.get('severity')}] {item.get('summary')} → {item.get('next_action')}")

    lines.extend(["", "## Memory Highlights", ""])
    memory = summary.get("memory_notes", [])
    if memory:
        lines.extend(f"- {line}" for line in memory)
    else:
        lines.append("- No durable memory notes found.")

    lines.extend(["", "## Active Commands", ""])
    commands = summary.get("active_commands", [])
    if commands:
        for command in commands:
            lines.append(
                f"- `{command['id']}` [{command['status']}/{command['priority']}] "
                f"{command['owner']}: {command['summary']}"
            )
    else:
        lines.append("- No open, in-progress, or blocked commands found.")

    lines.extend(["", "## Parallel Agent Batch Candidates", ""])
    parallel_commands = summary.get("parallel_commands", [])
    if parallel_commands:
        max_agents = len(parallel_commands)
        lines.append(
            f"- Plan: `python -m scripts.commands.agents.agent_orchestrator parallel "
            f"--project {summary['project']} --max-agents {max_agents}`"
        )
        lines.append(
            f"- Write prompts and mark in progress: `python -m scripts.commands.agents.agent_orchestrator "
            f"parallel --project {summary['project']} --max-agents {max_agents} --write`"
        )
        for command in parallel_commands:
            group = f" group `{command['parallel_group']}`" if command.get("parallel_group") else ""
            lines.append(
                f"- `{command['id']}` [{command['priority']}] {command['owner']}{group}: "
                f"{command['summary']}"
            )
    else:
        lines.append("- No safe multi-agent batch found; fall back to the highest-value serial action.")

    lines.extend(["", "## Prepared Or In-Progress Parallel Prompts", ""])
    prepared_prompts = summary.get("prepared_parallel_prompts", [])
    if prepared_prompts:
        groups = sorted({str(item.get("parallel_group") or "") for item in prepared_prompts if item.get("parallel_group")})
        for group in groups:
            group_items = [item for item in prepared_prompts if str(item.get("parallel_group") or "") == group]
            waiting_items = [
                item for item in group_items
                if str(item.get("unfinished_dependencies") or "").strip()
            ]
            lines.append(
                f"- Inspect prepared group `{group}` with: `python -m scripts.commands.agents.agent_orchestrator "
                f"run-prepared --project {summary['project']} --group {group} --dry-run`"
            )
            if waiting_items:
                waiting_summary = "; ".join(
                    f"{item['id']} waits for {item['unfinished_dependencies']}"
                    for item in waiting_items
                )
                lines.append(
                    f"- Prepared group `{group}` is not ready to run: {waiting_summary}."
                )
            else:
                lines.append(
                    f"- Run prepared group `{group}` with: `python -m scripts.commands.agents.agent_orchestrator "
                    f"run-prepared --project {summary['project']} --group {group} --runner-command \"<agent-cli> --prompt-file {{prompt_file}}\"`"
                )
                lines.append(
                    f"- Inspect finish for group `{group}` with: `python -m scripts.commands.agents.agent_orchestrator "
                    f"finish-parallel --project {summary['project']} --group {group} --status done --dry-run`"
                )
                lines.append(
                    f"- Finish prepared group `{group}` with: `python -m scripts.commands.agents.agent_orchestrator "
                    f"finish-parallel --project {summary['project']} --group {group} --status done --note \"<verification>\"`"
                )
        for item in prepared_prompts:
            unfinished = str(item.get("unfinished_dependencies") or "").strip()
            readiness = f"waiting: {unfinished}" if unfinished else "ready"
            lines.append(
                f"- `{item['id']}` group `{item['parallel_group']}` {item['owner']} [{readiness}]: "
                f"`{item['prompt']}` [{item['prompt_status']}] - {item['summary']}"
            )
    else:
        lines.append("- No in-progress parallel prompts found.")

    lines.extend(["", "## Parallel Batch Manifests", ""])
    manifests = summary.get("parallel_batch_manifests", [])
    if manifests:
        for item in manifests:
            stamp = f" at {item['timestamp']}" if item.get("timestamp") else ""
            lines.append(
                f"- `{item['path']}`{stamp}: {item['commands']} command(s), {item['prompts']} prompt(s)"
            )
    else:
        lines.append("- No parallel batch manifests found.")

    lines.extend(["", "## Recent Parallel Lifecycle Events", ""])
    parallel_events = summary.get("parallel_events", [])
    if parallel_events:
        for event in parallel_events:
            stamp = f"{event['timestamp']} " if event.get("timestamp") else ""
            notes = f" ({event['notes']})" if event.get("notes") else ""
            lines.append(
                f"- {stamp}`{event['event']}` [{event['status']}] {event['task']}{notes}"
            )
    else:
        lines.append("- No recent parallel lifecycle events found.")

    lines.extend(["", "## Suggested Next Actions", ""])
    next_actions = summary.get("next_actions", [])
    if next_actions:
        lines.extend(f"- {line}" for line in next_actions)
    else:
        lines.append("- No human-readable next actions found.")

    lines.extend(["", "## Working Artifacts", ""])
    artifacts = summary.get("working_artifacts", [])
    if artifacts:
        for artifact in artifacts:
            lines.append(f"- `{artifact['path']}` [{artifact['status']}]: {artifact['detail']}")
    else:
        lines.append("- No working artifact summary available.")

    lines.extend(["", "## Active Agents", ""])
    agents = summary.get("active_agents", [])
    if agents:
        for agent in agents:
            command = f" command `{agent['command_id']}`" if agent.get("command_id") else ""
            task = f": {agent['task']}" if agent.get("task") else ""
            lines.append(f"- `{agent['agent']}` [{agent['status']}]{command}{task}")
    else:
        lines.append("- No active, waiting, or blocked agents found.")

    lines.extend(["", "## Open Messages", ""])
    messages = summary.get("open_messages", [])
    if messages:
        for message in messages:
            route = f"{message['from']} -> {message['to']}".strip()
            lines.append(f"- `{message['id']}` [{message['status']}/{message['priority']}] {route}: {message['summary']}")
    else:
        lines.append("- No open agent messages found.")

    lines.extend(["", "## Open Questions", ""])
    questions = summary.get("open_questions", [])
    if questions:
        lines.extend(f"- {line}" for line in questions)
    else:
        lines.append("- No open questions found in state/open_questions.md.")

    lines.extend(["", "## Workflow Warnings", ""])
    warnings = summary.get("workflow_warnings", [])
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- No workflow ownership warnings found.")

    lines.extend(["", "## Continuation Prompt", "", "```text", summary["continuation_prompt"], "```"])
    return "\n".join(lines) + "\n"


def run_resume(args: argparse.Namespace) -> int:
    try:
        if args.list:
            if args.project:
                print("note: --list ignores --project and scans every project.", file=sys.stderr)
            rows = build_project_listing()
            if args.json:
                print(json.dumps({"projects": rows}, indent=2, ensure_ascii=False))
            else:
                print(render_listing(rows))
            return 0
        root = project_root(args.project); summary = build_resume(root, args.max_items)
        if args.json: print(json.dumps(summary, indent=2, ensure_ascii=False))
        else: print(render_markdown(summary).rstrip())
        return 0
    except (HarnessError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr); return 1


def projects_root() -> Path:
    return repo_root() / "projects"


def shorten(text: str, width: int = LISTING_FIELD_WIDTH) -> str:
    text = " ".join(text.split())
    if len(text) <= width:
        return text
    return text[: max(1, width - 3)].rstrip() + "..."


def listing_last_touched(root: Path) -> float:
    stamps: list[float] = []
    for relative in LISTING_TOUCH_FILES:
        path = root / relative
        try:
            if path.is_file():
                stamps.append(path.stat().st_mtime)
        except OSError:
            continue
    return max(stamps, default=0.0)


def listing_headline(root: Path) -> str:
    for raw in read_text(root / "state" / "current_state.md").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith("<!--"):
            continue
        return shorten(line)
    return ""


_LIST_ITEM_RE = re.compile(r"^(?:-|\*|\d+[.)])\s+(.*)$")
_OPEN_STATUSES = {"open", "in progress", "in_progress"}


def listing_next_action(root: Path) -> str:
    table_fallback = ""
    for raw in read_text(root / "state" / "next_actions.md").splitlines():
        line = raw.strip()
        item = _LIST_ITEM_RE.match(line)
        if item:
            text = item.group(1).strip()
            if text.lower().startswith("[x]"):
                continue
            text = re.sub(r"^\[\s?\]\s*", "", text)
            if text:
                return shorten(text)
            continue
        # Generated command-queue mirror rows:
        # | cmd | action | owner | ... | priority | status | done-when |
        if not table_fallback and line.startswith("|"):
            cells = [cell.strip() for cell in line.strip("|").split("|")]
            if len(cells) >= 10 and cells[8].lower() in _OPEN_STATUSES and cells[0] != "Command":
                table_fallback = shorten(f"{cells[0]}: {cells[1]}")
    return table_fallback


def listing_row(entry: Path) -> dict[str, Any]:
    row: dict[str, Any] = {
        "project": entry.name,
        "template": entry.name == "template",
        "last_touched_epoch": 0.0,
        "last_touched": "",
        "headline": "",
        "next_action": "",
    }
    try:
        stamp = listing_last_touched(entry)
        row["last_touched_epoch"] = stamp
        if stamp:
            row["last_touched"] = datetime.fromtimestamp(stamp).isoformat(timespec="minutes")
        row["headline"] = listing_headline(entry)
        row["next_action"] = listing_next_action(entry)
    except Exception as exc:  # noqa: BLE001 - a malformed project must not break the listing
        print(f"note: projects/{entry.name} could not be fully read ({exc}).", file=sys.stderr)
    return row


def build_project_listing() -> list[dict[str, Any]]:
    base = projects_root()
    if not base.is_dir():
        return []
    rows = [
        listing_row(entry)
        for entry in sorted(base.iterdir(), key=lambda item: item.name)
        if entry.is_dir() and not entry.name.startswith(".")
    ]
    rows.sort(key=lambda row: (-float(row["last_touched_epoch"]), str(row["project"])))
    return rows


def render_listing(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "No projects found under projects/."
    lines = ["# Workspace Projects (newest first)", ""]
    for row in rows:
        name = f"{row['project']} (template)" if row["template"] else str(row["project"])
        touched = str(row["last_touched"]) or "never"
        headline = str(row["headline"]) or "(no current state headline)"
        next_action = str(row["next_action"]) or "(no open next action)"
        lines.append(f"- {name} | {touched} | {headline} | next: {next_action}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.list:
            rows = build_project_listing()
            if args.json:
                print(json.dumps({"projects": rows}, indent=2, ensure_ascii=False))
            else:
                print(render_listing(rows))
            return 0
        root = project_root(args.project)
        summary = build_resume(root, args.max_items)
        if args.json:
            print(json.dumps(summary, indent=2, ensure_ascii=False))
        else:
            print(render_markdown(summary).rstrip())
        return 0
    except (HarnessError, OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
