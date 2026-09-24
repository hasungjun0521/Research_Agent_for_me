#!/usr/bin/env python3
"""Manage state/loop_summary.json for dashboard loop summaries."""

from __future__ import annotations

import argparse
import sys

from scripts.harness.state import (
    LOOP_STATUSES,
    HarnessError,
    append_agent_event,
    default_loop_summary,
    load_loop_summary,
    loop_summary_path,
    mutate_loop_summary,
    now_iso,
    project_root,
    split_values,
    validate_loop_summary_doc,
    write_loop_summary,
)
from scripts.harness.workflow_hooks import refresh_report_index


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage the current research loop summary.")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create loop_summary.json if missing.")
    init.add_argument("--project", required=True)

    reset = sub.add_parser("reset", help="Reset loop_summary.json to the default planned state.")
    reset.add_argument("--project", required=True)

    start = sub.add_parser("start", help="Start or reset the current loop.")
    start.add_argument("--project", required=True)
    start.add_argument("--loop-id", required=True)
    start.add_argument("--goal", required=True)
    start.add_argument("--note", default="")

    update = sub.add_parser("update", help="Update the current loop without resetting recorded work.")
    update.add_argument("--project", required=True)
    update.add_argument("--status", choices=sorted(LOOP_STATUSES))
    update.add_argument("--goal")
    update.add_argument("--summary")
    update.add_argument("--outcome")
    update.add_argument("--note")

    finish = sub.add_parser("finish", help="Finish the current loop.")
    finish.add_argument("--project", required=True)
    finish.add_argument("--status", choices=sorted(LOOP_STATUSES - {"planned", "running"}), default="done")
    finish.add_argument("--summary", required=True)
    finish.add_argument("--outcome", default="")
    finish.add_argument("--note", default="")

    add_work = sub.add_parser("add-work", help="Record completed work or command.")
    add_work.add_argument("--project", required=True)
    add_work.add_argument("--id", default="")
    add_work.add_argument("--action", required=True)
    add_work.add_argument("--owner", dest="owner_agent", default="")
    add_work.add_argument("--result", default="")
    add_work.add_argument("--output", action="append", dest="outputs")
    add_work.add_argument("--status", default="done")

    add_result = sub.add_parser("add-result", help="Record an observed result.")
    add_result.add_argument("--project", required=True)
    add_result.add_argument("--title", required=True)
    add_result.add_argument("--status", default="")
    add_result.add_argument("--summary", default="")
    add_result.add_argument("--evidence", action="append", dest="evidence")

    add_next = sub.add_parser("add-next", help="Record a next action.")
    add_next.add_argument("--project", required=True)
    add_next.add_argument("--action", required=True)
    add_next.add_argument("--owner", dest="owner_agent", default="")
    add_next.add_argument("--priority", choices=["high", "medium", "low"], default="medium")
    add_next.add_argument("--output", action="append", dest="outputs")
    add_next.add_argument("--display-summary", default="", help="Human-readable summary for dashboard cards.")
    add_next.add_argument("--why-now", default="", help="Why this should happen next.")
    add_next.add_argument("--done-when", default="", help="Plain-language done condition.")
    add_next.add_argument("--note", default="")

    validate = sub.add_parser("validate", help="Validate loop_summary.json.")
    validate.add_argument("--project", required=True)
    validate.add_argument("--strict", action="store_true", help="Fail when validation warnings are present.")

    show = sub.add_parser("show", help="Print a compact loop summary.")
    show.add_argument("--project", required=True)

    return parser.parse_args()


def append_unique(items: list, item: dict) -> None:
    item_id = str(item.get("id") or "").strip()
    if item_id:
        for index, existing in enumerate(items):
            if isinstance(existing, dict) and existing.get("id") == item_id:
                items[index] = item
                return
    items.append(item)


def record_loop_event(root, event_type: str, agent: str, task: str, outputs: list[str] | None = None, notes: str = "") -> None:
    all_outputs = ["state/loop_summary.json"]
    for output in outputs or []:
        if output and output not in all_outputs:
            all_outputs.append(output)
    append_agent_event(
        root,
        event_type,
        agent or "director",
        status="waiting",
        task=task,
        stage="loop_summary",
        outputs=all_outputs,
        notes=notes,
    )


def main() -> int:
    args = parse_args()
    try:
        root = project_root(args.project)
        if args.command == "init":
            path = loop_summary_path(root)
            if path.exists():
                summary = load_loop_summary(root)
            else:
                summary = default_loop_summary(args.project)
                write_loop_summary(root, summary)
            refresh_report_index(root)
            print(f"loop summary: {summary.get('loop_id', '')}")
            return 0

        if args.command == "reset":
            project_name = "{{PROJECT_NAME}}" if args.project == "template" else args.project
            write_loop_summary(root, default_loop_summary(project_name))
            refresh_report_index(root)
            print("reset loop summary")
            return 0

        if args.command == "start":
            timestamp = now_iso()

            def start_loop(summary: dict) -> None:
                summary.update({
                    "project": args.project,
                    "loop_id": args.loop_id,
                    "status": "running",
                    "goal": args.goal,
                    "summary": "Loop is in progress.",
                    "outcome": "",
                    "started_at": timestamp,
                    "finished_at": "",
                    "completed_commands": [],
                    "results": [],
                    "next_actions": [],
                    "notes": args.note,
                })

            mutate_loop_summary(root, start_loop)
            record_loop_event(
                root,
                "loop_summary_start",
                "director",
                f"Started loop {args.loop_id}.",
                notes=args.note,
            )
            refresh_report_index(root)
            print(f"started loop: {args.loop_id}")
            return 0

        if args.command == "update":

            def update_loop(summary: dict) -> None:
                if args.status is not None:
                    summary["status"] = args.status
                if args.goal is not None:
                    summary["goal"] = args.goal
                if args.summary is not None:
                    summary["summary"] = args.summary
                if args.outcome is not None:
                    summary["outcome"] = args.outcome
                if args.note is not None:
                    summary["notes"] = args.note

            updated = mutate_loop_summary(root, update_loop)
            record_loop_event(
                root,
                "loop_summary_update",
                "director",
                f"Updated loop {updated.get('loop_id', '')}.",
                notes=args.note or args.summary or args.outcome or "",
            )
            refresh_report_index(root)
            print(f"updated loop: {updated.get('loop_id', '')}")
            return 0

        if args.command == "finish":
            timestamp = now_iso()

            def finish_loop(summary: dict) -> None:
                summary["status"] = args.status
                summary["summary"] = args.summary
                summary["outcome"] = args.outcome
                summary["finished_at"] = timestamp
                if args.note:
                    summary["notes"] = args.note

            mutate_loop_summary(root, finish_loop)
            record_loop_event(
                root,
                "loop_summary_finish",
                "director",
                f"Finished loop with status {args.status}.",
                notes=args.outcome or args.note,
            )
            refresh_report_index(root)
            print(f"finished loop: {args.status}")
            return 0

        if args.command == "add-work":
            item = {
                "id": args.id,
                "action": args.action,
                "owner_agent": args.owner_agent,
                "status": args.status,
                "result": args.result,
                "output_files": split_values(args.outputs),
                "updated_at": now_iso(),
            }

            def add_work_item(summary: dict) -> None:
                append_unique(summary.setdefault("completed_commands", []), item)

            mutate_loop_summary(root, add_work_item)
            record_loop_event(
                root,
                "loop_summary_add_work",
                args.owner_agent or "director",
                f"Recorded loop work: {args.action}.",
                outputs=item["output_files"],
                notes=args.result,
            )
            refresh_report_index(root)
            print(f"recorded work: {args.action}")
            return 0

        if args.command == "add-result":
            item = {
                "title": args.title,
                "status": args.status,
                "summary": args.summary,
                "evidence_files": split_values(args.evidence),
                "updated_at": now_iso(),
            }

            def add_result_item(summary: dict) -> None:
                summary.setdefault("results", []).append(item)

            mutate_loop_summary(root, add_result_item)
            record_loop_event(
                root,
                "loop_summary_add_result",
                "director",
                f"Recorded loop result: {args.title}.",
                outputs=item["evidence_files"],
                notes=args.summary,
            )
            refresh_report_index(root)
            print(f"recorded result: {args.title}")
            return 0

        if args.command == "add-next":
            item = {
                "action": args.action,
                "owner_agent": args.owner_agent,
                "priority": args.priority,
                "expected_outputs": split_values(args.outputs),
                "display_summary": args.display_summary,
                "why_now": args.why_now,
                "done_when": args.done_when,
                "notes": args.note,
                "created_at": now_iso(),
            }

            def add_next_item(summary: dict) -> None:
                summary.setdefault("next_actions", []).append(item)

            mutate_loop_summary(root, add_next_item)
            record_loop_event(
                root,
                "loop_summary_add_next",
                args.owner_agent or "director",
                f"Recorded loop next action: {args.action}.",
                outputs=item["expected_outputs"],
                notes=args.note or args.why_now,
            )
            refresh_report_index(root)
            print(f"recorded next action: {args.action}")
            return 0

        if args.command == "validate":
            summary = load_loop_summary(root)
            warnings = validate_loop_summary_doc(summary)
            if warnings:
                print("warnings:")
                for warning in warnings:
                    print(f"- {warning}")
                if args.strict:
                    return 1
            print(f"valid loop summary: {args.project}")
            return 0

        if args.command == "show":
            summary = load_loop_summary(root)
            print(f"{summary.get('loop_id')}\t{summary.get('status')}\t{summary.get('goal')}")
            print(summary.get("summary") or "")
            if summary.get("outcome"):
                print(f"outcome: {summary['outcome']}")
            return 0

        raise HarnessError(f"Unknown command: {args.command}")
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
