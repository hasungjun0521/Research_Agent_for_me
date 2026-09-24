#!/usr/bin/env python3
"""Safely update a project's state/agent_status.json."""

from __future__ import annotations

import argparse
import sys

from scripts.harness.state import (
    AGENT_STATUSES,
    HarnessError,
    append_agent_event,
    owned_active_commands,
    project_root,
    split_values,
    update_agent_status,
    update_command_for_agent,
)
from scripts.harness.workflow_hooks import refresh_report_index


def setup_subparsers(subparsers: argparse._SubParsersAction) -> None:
    status = subparsers.add_parser("status", help="Update agent status without hand-editing JSON.")
    status_sub = status.add_subparsers(dest="status_command", required=True)

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--project", required=True, help="Project folder name under projects/.")
        p.add_argument("--agent", required=True, help="Agent name, e.g. code_agent.")
        p.add_argument("--task", help="Concrete current task.")
        p.add_argument("--stage", help="Workflow stage.")
        p.add_argument("--input", action="append", dest="inputs", help="Input file. Repeat or comma-separate.")
        p.add_argument("--output", action="append", dest="outputs", help="Output file. Repeat or comma-separate.")
        p.add_argument("--note", help="Status note.")
        p.add_argument("--append-note", action="store_true", help="Append note instead of replacing notes.")
        p.add_argument("--command-id", help="Structured command id this agent is executing.")

    start = status_sub.add_parser("start", help="Mark an agent as running.")
    add_common(start)

    heartbeat = status_sub.add_parser("heartbeat", help="Refresh updated_at and optional task/note.")
    add_common(heartbeat)

    finish = status_sub.add_parser("finish", help="Mark an agent pass as done, waiting, blocked, or idle.")
    add_common(finish)
    finish.add_argument("--status", required=True, choices=sorted(AGENT_STATUSES - {"running"}), help="Final status for the agent.")
    finish.add_argument("--allow-open-commands", action="store_true", help="Allow status=done even when this agent still owns open/in-progress commands.")

    set_status = status_sub.add_parser("set", help="Set an explicit agent status.")
    add_common(set_status)
    set_status.add_argument("--status", required=True, choices=sorted(AGENT_STATUSES))


def run_status(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    cmd = getattr(args, "status_command", "")

    # Handle legacy call mapping
    if not cmd:
        cmd = getattr(args, "command", "")

    status = {
        "start": "running",
        "heartbeat": "running",
        "finish": getattr(args, "status", None),
        "set": getattr(args, "status", None),
    }.get(cmd)

    if status is None:
        raise HarnessError(f"Could not determine status for command: {cmd}")

    if cmd == "finish" and status == "done" and not args.command_id and not args.allow_open_commands:
        active = owned_active_commands(root, args.agent)
        if active:
            ids = ", ".join(str(command.get("id")) for command in active)
            raise HarnessError(f"Refusing to mark agent done while it owns open/in-progress commands: {ids}.")

    if cmd == "start":
        update_command_for_agent(root, args.command_id, args.agent, "in progress", args.note)
    elif cmd == "finish" and args.command_id:
        command_status = "done" if status == "done" else "blocked" if status == "blocked" else "open"
        update_command_for_agent(root, args.command_id, args.agent, command_status, args.note)

    update_agent_status(
        root, args.agent, status, task=args.task, stage=args.stage,
        inputs=split_values(args.inputs) if args.inputs is not None else None,
        outputs=split_values(args.outputs) if args.outputs is not None else None,
        notes=args.note, append_note=args.append_note,
    )
    append_agent_event(
        root, cmd, args.agent, status=status, command_id=args.command_id or "",
        task=args.task or "", stage=args.stage or "",
        inputs=split_values(args.inputs) if args.inputs is not None else [],
        outputs=split_values(args.outputs) if args.outputs is not None else [],
        notes=args.note or "",
    )
    if args.command_id:
        refresh_report_index(root)
    print(f"{args.project}:{args.agent} -> {status}")
    return 0


def main() -> int:
    from scripts.commands.agents.agents import main as agents_main
    if len(sys.argv) > 1 and sys.argv[1] in {"start", "heartbeat", "finish", "set"}:
        sys.argv.insert(1, "status")
    elif len(sys.argv) < 2 or (len(sys.argv) >= 2 and sys.argv[1] != "status"):
        sys.argv.insert(1, "status")
    return agents_main()

if __name__ == "__main__":
    raise SystemExit(main())
