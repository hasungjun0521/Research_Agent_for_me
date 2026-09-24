#!/usr/bin/env python3
"""Generate a dashboard-free project health report."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scripts.harness.project_diagnostics import build_diagnostics, render_project_health
from scripts.harness.state import (
    HarnessError,
    append_agent_event,
    load_command_queue,
    now_iso,
    project_root,
    update_agent_status,
    write_command_queue,
)
from scripts.harness.workflow_hooks import refresh_report_index


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate state/project_health.md as a plain Markdown research-progress "
            "health report, not a final paper report or browser dashboard."
        )
    )
    parser.add_argument("--project", required=True)
    parser.add_argument("--agent", default="director")
    parser.add_argument("--write", action="store_true", help="Write state/project_health.md.")
    parser.add_argument(
        "--enqueue-suggestions",
        action="store_true",
        help="Add suggested health-report actions to state/command_queue.json when not already present.",
    )
    parser.add_argument(
        "--dry-run-enqueue",
        action="store_true",
        help="Preview suggested command_queue entries without writing them.",
    )
    parser.add_argument("--strict", action="store_true", help="Fail when critical or high-priority issues exist.")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def split_outputs(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip().strip("`") for item in value if str(item).strip()]
    return [item.strip().strip("`") for item in str(value or "").split(",") if item.strip()]


def unique_command_id(existing_ids: set[str], base: str) -> str:
    candidate = base
    index = 2
    while candidate in existing_ids:
        candidate = f"{base}_{index}"
        index += 1
    existing_ids.add(candidate)
    return candidate


def enqueue_suggestions(
    root: Path,
    diagnostics: dict,
    *,
    dry_run: bool = False,
    id_prefix: str = "health",
    source_label: str = "project health",
) -> tuple[list[str], list[dict[str, Any]]]:
    queue = load_command_queue(root)
    commands = queue.setdefault("commands", [])
    existing_actions = {str(command.get("action") or "").strip() for command in commands if isinstance(command, dict)}
    existing_ids = {str(command.get("id") or "").strip() for command in commands if isinstance(command, dict)}
    timestamp = now_iso()
    added: list[str] = []
    planned: list[dict[str, Any]] = []
    for index, suggestion in enumerate(diagnostics.get("suggested_commands", []), start=1):
        action = str(suggestion.get("action") or "").strip()
        owner = str(suggestion.get("owner_agent") or "director").strip()
        if not action or action in existing_actions:
            continue
        command_id = unique_command_id(existing_ids, f"{id_prefix}_{index:03d}")
        outputs = split_outputs(str(suggestion.get("expected_outputs") or ""))
        required_inputs = split_outputs(str(suggestion.get("required_inputs") or ""))
        command = {
            "id": command_id,
            "action": action,
            "display_summary": action,
            "owner_agent": owner,
            "status": "open",
            "priority": str(suggestion.get("priority") or "medium"),
            "depends_on": [],
            "parallel_group": "",
            "required_inputs": required_inputs or ["state/project_health.md", "state/state_doctor.md"],
            "expected_outputs": outputs,
            "done_when": f"The recommended {source_label} repair is reflected in project files and project health has been refreshed.",
            "created_at": timestamp,
            "updated_at": timestamp,
            "notes": f"Created from {source_label} suggested command queue entries.",
        }
        if not dry_run:
            commands.append(command)
        planned.append(command)
        existing_actions.add(action)
        added.append(command_id)
    if added and not dry_run:
        queue["last_updated"] = timestamp
        write_command_queue(root, queue)
    return added, planned


def run_audit(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    diagnostics = build_diagnostics(root, caller="project_health")
    enqueued: list[str] = []
    planned_enqueue: list[dict[str, Any]] = []
    if args.enqueue_suggestions or args.dry_run_enqueue:
        enqueued, planned_enqueue = enqueue_suggestions(root, diagnostics, dry_run=args.dry_run_enqueue)
        diagnostics["planned_enqueue_commands"] = planned_enqueue
        if not args.dry_run_enqueue:
            diagnostics["enqueued_commands"] = enqueued
    content = render_project_health(diagnostics)
    outputs: list[str] = []
    if args.write:
        write_text(root / "state" / "project_health.md", content)
        outputs.append("state/project_health.md")
    if enqueued and not args.dry_run_enqueue:
        outputs.extend(["state/command_queue.json", "state/next_actions.md"])
    if args.write or (enqueued and not args.dry_run_enqueue):
        try:
            update_agent_status(
                root,
                args.agent,
                "done",
                task="Generate project health report.",
                stage="project health",
                outputs=outputs,
                notes=(
                    f"Project health overall={diagnostics['overall']} score={diagnostics['score']}; "
                    f"enqueued {len(enqueued)} suggestion(s)."
                ),
            )
        except HarnessError:
            pass
        append_agent_event(
            root,
            "project_health",
            args.agent,
            status="done",
            task="Generate project health report.",
            stage="project health",
            outputs=outputs,
            notes=(
                f"Project health found {diagnostics['counts']['issues']} issue(s); "
                f"enqueued {len(enqueued)} suggestion(s)."
            ),
        )
        refresh_report_index(root)
    if args.json:
        print(json.dumps(diagnostics, indent=2, ensure_ascii=False))
    else:
        print(content, end="")
    if args.strict and diagnostics["counts"]["critical"] + diagnostics["counts"]["high"] > 0:
        return 2
    return 0


def main() -> int:
    from scripts.commands.projects.projects import main as projects_main
    return run_audit(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
