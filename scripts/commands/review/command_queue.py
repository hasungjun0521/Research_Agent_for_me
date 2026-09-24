#!/usr/bin/env python3
"""Manage state/command_queue.json safely."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from scripts.harness.state import (
    QUEUE_PRIORITIES,
    QUEUE_STATUSES,
    HarnessError,
    append_agent_event,
    command_queue_path,
    default_command_queue,
    load_command_queue,
    mutate_command_queue,
    now_iso,
    project_root,
    split_values,
    write_command_queue,
)
from scripts.harness.workflow_hooks import refresh_report_index


def command_by_id(queue: dict) -> dict[str, dict]:
    return {
        str(command.get("id") or "").strip(): command
        for command in queue.get("commands", [])
        if isinstance(command, dict) and str(command.get("id") or "").strip()
    }


def unfinished_dependencies(command: dict, commands_by_id: dict[str, dict]) -> list[str]:
    return [
        dependency_id
        for dependency_id in command.get("depends_on") or []
        if str(commands_by_id.get(dependency_id, {}).get("status") or "").lower() != "done"
    ]


def command_with_readiness(command: dict, commands_by_id: dict[str, dict]) -> dict:
    unfinished = unfinished_dependencies(command, commands_by_id)
    enriched = dict(command)
    enriched["dependency_ready"] = not unfinished
    enriched["unfinished_dependencies"] = unfinished
    return enriched


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage the structured command queue.")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create command_queue.json if missing.")
    init.add_argument("--project", required=True)

    add = sub.add_parser("add", help="Add a command.")
    add.add_argument("--project", required=True)
    add.add_argument("--id", required=True)
    add.add_argument("--action", required=True)
    add.add_argument("--owner", required=True, dest="owner_agent")
    add.add_argument("--priority", choices=sorted(QUEUE_PRIORITIES), default="medium")
    add.add_argument("--status", choices=sorted(QUEUE_STATUSES), default="open")
    add.add_argument("--input", action="append", dest="inputs")
    add.add_argument("--output", action="append", dest="outputs")
    add.add_argument("--depends-on", action="append", dest="depends_on")
    add.add_argument("--parallel-group", default="")
    add.add_argument("--display-summary", default="")
    add.add_argument("--why-now", default="")
    add.add_argument("--done-when", default="")
    add.add_argument("--requires-vote", action="store_true")
    add.add_argument("--vote-id", default="")
    add.add_argument(
        "--risk-level", choices=["low", "medium", "high", "critical"], default="medium"
    )
    add.add_argument("--note", default="")

    update = sub.add_parser("update", help="Update a command.")
    update.add_argument("--project", required=True)
    update.add_argument("--id", required=True)
    update.add_argument("--action")
    update.add_argument("--owner", dest="owner_agent")
    update.add_argument("--priority", choices=sorted(QUEUE_PRIORITIES))
    update.add_argument("--status", choices=sorted(QUEUE_STATUSES))
    update.add_argument("--input", action="append", dest="inputs")
    update.add_argument("--output", action="append", dest="outputs")
    update.add_argument("--depends-on", action="append", dest="depends_on")
    update.add_argument("--parallel-group")
    update.add_argument("--display-summary")
    update.add_argument("--why-now")
    update.add_argument("--done-when")
    update.add_argument("--requires-vote", choices=["true", "false"])
    update.add_argument("--vote-id")
    update.add_argument("--risk-level", choices=["low", "medium", "high", "critical"])
    update.add_argument("--note")

    remove = sub.add_parser("remove", help="Remove a command by id.")
    remove.add_argument("--project", required=True)
    remove.add_argument("--id", required=True)

    list_cmd = sub.add_parser("list", help="List commands.")
    list_cmd.add_argument("--project", required=True)
    list_cmd.add_argument("--verbose", action="store_true")
    list_cmd.add_argument("--json", action="store_true")

    reap = sub.add_parser("reap", help="Reset stale 'in progress' commands to 'open'.")
    reap.add_argument("--project", required=True)
    reap.add_argument("--hours", type=int, default=12)
    reap.add_argument("--dry-run", action="store_true")

    return parser.parse_args()


def parse_time(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def is_stale(updated_at: str, threshold_hours: int) -> bool:
    parsed = parse_time(updated_at)
    if not parsed:
        return False
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    delta = datetime.now(timezone.utc) - parsed.astimezone(timezone.utc)
    return delta.total_seconds() > threshold_hours * 3600


def run_reap(root: Path, args: argparse.Namespace) -> int:
    reaped_ids: list[str] = []

    def mut(q):
        for c in q.get("commands", []):
            if str(c.get("status") or "").lower() == "in progress":
                if is_stale(str(c.get("updated_at") or ""), args.hours):
                    reaped_ids.append(str(c.get("id")))
                    if not args.dry_run:
                        c["status"] = "open"
                        c["updated_at"] = now_iso()
                        c["notes"] = (
                            str(c.get("notes", "")) + f"\n{now_iso()}: Reaped from stale state."
                        )

    if args.dry_run:
        mut(load_command_queue(root))
    else:
        mutate_command_queue(root, mut)
    if reaped_ids:
        print(
            f"{'Dry run: ' if args.dry_run else ''}Reaped {len(reaped_ids)}: {', '.join(reaped_ids)}"
        )
    else:
        print("No stale commands.")
    return 0


def find_command(queue: dict, command_id: str) -> dict:
    for command in queue["commands"]:
        if command.get("id") == command_id:
            return command
    raise HarnessError(f"Command not found: {command_id}")


def command_outputs(command: dict | None = None) -> list[str]:
    outputs = ["state/command_queue.json"]
    for output in (command or {}).get("expected_outputs") or []:
        if output and output not in outputs:
            outputs.append(output)
    return outputs


def event_status_for_command(command: dict | None = None) -> str:
    s = str((command or {}).get("status") or "").lower()
    return "running" if s == "in progress" else "blocked" if s == "blocked" else "waiting"


def record_command_queue_event(
    root, event_type: str, command: dict | None, task: str, notes: str = ""
) -> None:
    agent = str((command or {}).get("owner_agent") or "director")
    append_agent_event(
        root,
        event_type,
        agent,
        status=event_status_for_command(command),
        task=task,
        stage="command_queue",
        outputs=command_outputs(command),
        notes=notes,
    )


def main() -> int:
    args = parse_args()
    try:
        root = project_root(args.project)
        if args.command == "init":
            path = command_queue_path(root)
            queue = (
                load_command_queue(root) if path.exists() else default_command_queue(args.project)
            )
            if not path.exists():
                write_command_queue(root, queue)
            refresh_report_index(root)
            print(f"commands: {len(queue['commands'])}")
            return 0

        ts = now_iso()
        if args.command == "add":
            added = {
                "id": args.id,
                "action": args.action,
                "owner_agent": args.owner_agent,
                "priority": args.priority,
                "status": args.status,
                "required_inputs": split_values(args.inputs),
                "expected_outputs": split_values(args.outputs),
                "depends_on": split_values(args.depends_on),
                "parallel_group": args.parallel_group,
                "display_summary": args.display_summary,
                "why_now": args.why_now,
                "done_when": args.done_when,
                "requires_vote": args.requires_vote,
                "vote_id": args.vote_id,
                "risk_level": args.risk_level,
                "created_at": ts,
                "updated_at": ts,
                "notes": args.note,
            }
            mutate_command_queue(root, lambda q: q["commands"].append(added))
            record_command_queue_event(
                root, "command_queue_add", added, f"Added {args.id}.", args.note
            )
            refresh_report_index(root)
            print(f"added: {args.id}")
            return 0

        if args.command == "update":

            def mut(q):
                c = find_command(q, args.id)
                for f in (
                    "action",
                    "owner_agent",
                    "priority",
                    "status",
                    "display_summary",
                    "why_now",
                    "done_when",
                ):
                    v = getattr(args, f, None)
                    if v is not None:
                        c[f] = v
                if args.note is not None:
                    c["notes"] = args.note
                if args.requires_vote is not None:
                    c["requires_vote"] = args.requires_vote == "true"
                if args.vote_id is not None:
                    c["vote_id"] = args.vote_id
                if args.risk_level is not None:
                    c["risk_level"] = args.risk_level
                if args.inputs is not None:
                    c["required_inputs"] = split_values(args.inputs)
                if args.outputs is not None:
                    c["expected_outputs"] = split_values(args.outputs)
                if args.depends_on is not None:
                    c["depends_on"] = split_values(args.depends_on)
                if args.parallel_group is not None:
                    c["parallel_group"] = args.parallel_group
                c["updated_at"] = ts

            mutate_command_queue(root, mut)
            q = load_command_queue(root)
            c = find_command(q, args.id)
            record_command_queue_event(
                root, "command_queue_update", c, f"Updated {args.id}.", c.get("notes", "")
            )
            refresh_report_index(root)
            print(f"updated: {args.id}")
            return 0

        if args.command == "remove":

            def mut(q):
                before = len(q["commands"])
                q["commands"] = [c for c in q["commands"] if c.get("id") != args.id]
                if len(q["commands"]) == before:
                    raise HarnessError(f"Not found: {args.id}")

            mutate_command_queue(root, mut)
            record_command_queue_event(root, "command_queue_remove", None, f"Removed {args.id}.")
            refresh_report_index(root)
            print(f"removed: {args.id}")
            return 0

        if args.command == "list":
            q = load_command_queue(root)
            cmds = q["commands"]
            cb_id = command_by_id(q)
            if args.json:
                print(
                    json.dumps(
                        {
                            "project": args.project,
                            "commands": [command_with_readiness(c, cb_id) for c in cmds],
                        },
                        indent=2,
                        ensure_ascii=False,
                    )
                )
                return 0
            for c in cmds:
                line = f"{c['id']}\t{c['status']}\t{c['priority']}\t{c.get('owner_agent', '')}\t{c.get('action', '')}"
                if args.verbose:
                    dep = ", ".join(c.get("depends_on") or []) or "-"
                    unf = unfinished_dependencies(c, cb_id)
                    line = f"{line}\tdepends_on={dep}\tdependency_ready={'yes' if not unf else 'no'}\tunfinished={', '.join(unf) or '-'}\tparallel_group={c.get('parallel_group', '-')}\texpected_outputs={', '.join(c.get('expected_outputs', [])) or '-'}"
                print(line)
            return 0

        if args.command == "reap":
            return run_reap(root, args)
        raise HarnessError(f"Unknown command: {args.command}")
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
