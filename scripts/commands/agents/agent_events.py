#!/usr/bin/env python3
"""Inspect, record, and validate append-only agent lifecycle events."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter

from scripts.harness.state import (
    AGENT_STATUSES,
    HarnessError,
    agent_events_path,
    append_agent_event,
    load_agent_events,
    locked_state_file,
    owned_active_commands,
    project_root,
    split_values,
    update_agent_status,
    update_command_for_agent,
    validate_agent_events,
)
from scripts.harness.workflow_hooks import refresh_report_index


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect state/agent_events.jsonl.")
    sub = parser.add_subparsers(dest="command", required=True)

    validate = sub.add_parser("validate", help="Validate the event log.")
    validate.add_argument("--project", required=True)

    record = sub.add_parser("record", help="Append a hook-visible activity event.")
    record.add_argument("--project", required=True)
    record.add_argument("--agent", required=True)
    record.add_argument("--event", default="activity")
    record.add_argument("--status", default="")
    record.add_argument("--command-id", default="")
    record.add_argument("--task", default="")
    record.add_argument("--stage", default="")
    record.add_argument("--input", action="append", dest="inputs")
    record.add_argument("--output", action="append", dest="outputs")
    record.add_argument("--note", default="")
    record.add_argument(
        "--sync-status",
        action="store_true",
        help="Also update state/agent_status.json. Defaults the synced status to running.",
    )
    record.add_argument(
        "--allow-open-commands",
        action="store_true",
        help="Allow --sync-status --status done even when the agent owns open/in-progress commands.",
    )

    list_cmd = sub.add_parser("list", help="List recent agent events.")
    list_cmd.add_argument("--project", required=True)
    list_cmd.add_argument("--limit", type=int, default=20)
    list_cmd.add_argument("--json", action="store_true")

    summary = sub.add_parser("summary", help="Summarize event counts by agent and event type.")
    summary.add_argument("--project", required=True)
    summary.add_argument("--json", action="store_true")

    reset = sub.add_parser("reset", help="Clear the append-only event log for template or explicit operator cleanup.")
    reset.add_argument("--project", required=True)

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        root = project_root(args.project)
        if args.command == "validate":
            warnings = validate_agent_events(root)
            if warnings:
                for warning in warnings:
                    print(f"warning: {warning}", file=sys.stderr)
                return 1
            print(f"valid agent event log: {args.project}")
            return 0

        if args.command == "record":
            agent_name = str(args.agent or "").strip()
            event_name = str(args.event or "").strip()
            if not agent_name:
                raise HarnessError("--agent is required.")
            if not event_name:
                raise HarnessError("--event must not be empty.")
            event_status = str(args.status or "").strip().lower()
            inputs = split_values(args.inputs)
            outputs = split_values(args.outputs)
            if args.sync_status:
                synced_status = event_status or "running"
                if synced_status not in AGENT_STATUSES:
                    raise HarnessError(f"--sync-status requires a valid agent status, got: {synced_status!r}")
                if synced_status == "done" and not args.command_id and not args.allow_open_commands:
                    active = owned_active_commands(root, agent_name)
                    if active:
                        ids = ", ".join(str(command.get("id")) for command in active)
                        raise HarnessError(
                            "Refusing to mark agent done while it owns open/in-progress commands: "
                            f"{ids}. Pass --command-id to complete one command, record the event without "
                            "--sync-status, or use --allow-open-commands explicitly."
                        )
                if args.command_id:
                    command_status = (
                        "done"
                        if synced_status == "done"
                        else "blocked"
                        if synced_status == "blocked"
                        else "in progress"
                        if synced_status == "running"
                        else "open"
                    )
                    update_command_for_agent(root, args.command_id, agent_name, command_status, args.note or None)
                update_agent_status(
                    root,
                    agent_name,
                    synced_status,
                    task=args.task or None,
                    stage=args.stage or None,
                    inputs=inputs if args.inputs is not None else None,
                    outputs=outputs if args.outputs is not None else None,
                    notes=args.note or None,
                )
                event_status = synced_status
            event = append_agent_event(
                root,
                event_name,
                agent_name,
                status=event_status,
                command_id=args.command_id,
                task=args.task,
                stage=args.stage,
                inputs=inputs,
                outputs=outputs,
                notes=args.note,
            )
            if args.sync_status and args.command_id:
                refresh_report_index(root)
            print(f"recorded: {args.project}:{agent_name} {event['event']} {event['timestamp']}")
            return 0

        if args.command == "reset":
            path = agent_events_path(root)
            with locked_state_file(path):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("", encoding="utf-8")
            print(f"reset agent event log: {args.project}")
            return 0

        events = load_agent_events(root)
        if args.command == "list":
            selected = events[-max(args.limit, 0):] if args.limit else events
            if args.json:
                print(json.dumps({"project": args.project, "events": selected}, indent=2, ensure_ascii=False))
            else:
                for event in selected:
                    print(
                        f"{event.get('timestamp', '')}\t{event.get('event', '')}\t"
                        f"{event.get('agent', '')}\t{event.get('status', '')}\t{event.get('command_id', '')}"
                    )
            return 0

        if args.command == "summary":
            by_agent = Counter(str(event.get("agent") or "") for event in events)
            by_event = Counter(str(event.get("event") or "") for event in events)
            payload = {
                "project": args.project,
                "total_events": len(events),
                "by_agent": dict(sorted(by_agent.items())),
                "by_event": dict(sorted(by_event.items())),
            }
            if args.json:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                print(f"events: {payload['total_events']}")
                for agent, count in payload["by_agent"].items():
                    print(f"agent\t{agent}\t{count}")
                for event, count in payload["by_event"].items():
                    print(f"event\t{event}\t{count}")
            return 0

        raise HarnessError(f"Unknown command: {args.command}")
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
