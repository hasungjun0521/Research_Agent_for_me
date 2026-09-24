#!/usr/bin/env python3
"""Manage reusable project-local workflow patterns."""

from __future__ import annotations

import argparse
import json
import sys

from scripts.harness.state import (
    HarnessError,
    append_agent_event,
    find_pattern,
    load_pattern_memory,
    mutate_pattern_memory,
    now_iso,
    project_root,
    split_values,
    validate_pattern_memory_doc,
    write_pattern_memory,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage state/pattern_memory.json.")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create pattern_memory.json if missing.")
    init.add_argument("--project", required=True)

    add = sub.add_parser("add", help="Add a reusable pattern.")
    add.add_argument("--project", required=True)
    add.add_argument("--id", required=True)
    add.add_argument("--title", required=True)
    add.add_argument("--summary", required=True)
    add.add_argument("--status", choices=["candidate", "active", "deprecated"], default="active")
    add.add_argument("--tag", action="append", dest="tags")
    add.add_argument("--trigger", action="append", dest="triggers")
    add.add_argument("--recommendation", default="")
    add.add_argument("--evidence", action="append", dest="evidence_files")
    add.add_argument("--note", default="")

    update = sub.add_parser("update", help="Update an existing pattern.")
    update.add_argument("--project", required=True)
    update.add_argument("--id", required=True, dest="pattern_id")
    update.add_argument("--title")
    update.add_argument("--summary")
    update.add_argument("--status", choices=["candidate", "active", "deprecated"])
    update.add_argument("--tag", action="append", dest="tags")
    update.add_argument("--trigger", action="append", dest="triggers")
    update.add_argument("--recommendation")
    update.add_argument("--evidence", action="append", dest="evidence_files")
    update.add_argument("--note")

    list_cmd = sub.add_parser("list", help="List patterns.")
    list_cmd.add_argument("--project", required=True)
    list_cmd.add_argument("--status", choices=["candidate", "active", "deprecated"])
    list_cmd.add_argument("--json", action="store_true")

    search = sub.add_parser("search", help="Search patterns by text.")
    search.add_argument("--project", required=True)
    search.add_argument("--query", required=True)
    search.add_argument("--status", choices=["candidate", "active", "deprecated"])
    search.add_argument("--limit", type=int, default=10)
    search.add_argument("--json", action="store_true")

    validate = sub.add_parser("validate", help="Validate pattern_memory.json.")
    validate.add_argument("--project", required=True)

    return parser.parse_args()


def unique_extend(existing: list, incoming: list[str]) -> list[str]:
    result = [str(item).strip() for item in existing if str(item).strip()]
    for item in incoming:
        stripped = str(item).strip()
        if stripped and stripped not in result:
            result.append(stripped)
    return result


def searchable(pattern: dict) -> str:
    fields = [
        pattern.get("id"),
        pattern.get("title"),
        pattern.get("summary"),
        pattern.get("recommendation"),
        pattern.get("notes"),
        " ".join(str(item) for item in pattern.get("tags", [])),
        " ".join(str(item) for item in pattern.get("triggers", [])),
        " ".join(str(item) for item in pattern.get("evidence_files", [])),
    ]
    return " ".join(str(field or "") for field in fields).lower()


def filter_patterns(patterns: list[dict], status: str | None = None) -> list[dict]:
    if not status:
        return patterns
    return [
        pattern for pattern in patterns
        if str(pattern.get("status") or "").lower() == status
    ]


def search_patterns(patterns: list[dict], query: str, status: str | None, limit: int) -> list[dict]:
    tokens = [token for token in query.lower().split() if token]
    candidates = filter_patterns(patterns, status)
    if not tokens:
        return candidates[:limit]
    matches = [
        pattern for pattern in candidates
        if all(token in searchable(pattern) for token in tokens)
    ]
    return matches[:limit]


def print_patterns(patterns: list[dict]) -> None:
    for pattern in patterns:
        tags = ",".join(str(tag) for tag in pattern.get("tags", []))
        print(f"{pattern.get('id')}\t{pattern.get('status')}\t{tags}\t{pattern.get('title')}")


def pattern_outputs(pattern: dict) -> list[str]:
    outputs = ["state/pattern_memory.json"]
    for output in pattern.get("evidence_files") or []:
        if output and output not in outputs:
            outputs.append(output)
    return outputs


def record_pattern_event(root, event_type: str, pattern: dict, task: str) -> None:
    append_agent_event(
        root,
        event_type,
        "director",
        status="waiting",
        task=task,
        stage="pattern_memory",
        outputs=pattern_outputs(pattern),
        notes=f"Pattern {pattern.get('id')}: {pattern.get('title', '')}",
    )


def main() -> int:
    args = parse_args()
    try:
        root = project_root(args.project)

        if args.command == "init":
            memory = load_pattern_memory(root)
            write_pattern_memory(root, memory)
            print(f"patterns: {len(memory.get('patterns', []))}")
            return 0

        if args.command == "add":
            tags = split_values(args.tags)
            triggers = split_values(args.triggers)
            evidence_files = split_values(args.evidence_files)
            added_pattern: dict = {}

            def mutate(data: dict) -> None:
                nonlocal added_pattern
                if find_pattern(data, args.id):
                    raise HarnessError(f"Pattern already exists: {args.id}")
                timestamp = now_iso()
                added_pattern = {
                    "id": args.id,
                    "title": args.title,
                    "summary": args.summary,
                    "status": args.status,
                    "tags": tags,
                    "triggers": triggers,
                    "recommendation": args.recommendation,
                    "evidence_files": evidence_files,
                    "created_at": timestamp,
                    "updated_at": timestamp,
                    "notes": args.note,
                }
                data["patterns"].append(added_pattern)

            mutate_pattern_memory(root, mutate)
            record_pattern_event(root, "pattern_memory_add", added_pattern, f"Added pattern {args.id}.")
            print(f"added pattern: {args.id}")
            return 0

        if args.command == "update":
            tags = split_values(args.tags)
            triggers = split_values(args.triggers)
            evidence_files = split_values(args.evidence_files)
            updated_pattern: dict = {}

            def mutate(data: dict) -> None:
                nonlocal updated_pattern
                pattern = find_pattern(data, args.pattern_id)
                if pattern is None:
                    raise HarnessError(f"Pattern not found: {args.pattern_id}")
                for field in ("title", "summary", "status", "recommendation"):
                    value = getattr(args, field)
                    if value is not None:
                        pattern[field] = value
                if args.note is not None:
                    pattern["notes"] = args.note
                if tags:
                    pattern["tags"] = unique_extend(pattern.get("tags", []), tags)
                if triggers:
                    pattern["triggers"] = unique_extend(pattern.get("triggers", []), triggers)
                if evidence_files:
                    pattern["evidence_files"] = unique_extend(pattern.get("evidence_files", []), evidence_files)
                pattern["updated_at"] = now_iso()
                updated_pattern = dict(pattern)

            mutate_pattern_memory(root, mutate)
            record_pattern_event(root, "pattern_memory_update", updated_pattern, f"Updated pattern {args.pattern_id}.")
            print(f"updated pattern: {args.pattern_id}")
            return 0

        if args.command == "list":
            data = load_pattern_memory(root)
            rows = filter_patterns(data.get("patterns", []), args.status)
            if args.json:
                print(json.dumps({"project": args.project, "patterns": rows}, indent=2, ensure_ascii=False))
            else:
                print_patterns(rows)
            return 0

        if args.command == "search":
            if args.limit < 1:
                raise HarnessError("--limit must be at least 1.")
            data = load_pattern_memory(root)
            rows = search_patterns(data.get("patterns", []), args.query, args.status, args.limit)
            if args.json:
                print(json.dumps({"project": args.project, "patterns": rows}, indent=2, ensure_ascii=False))
            else:
                print_patterns(rows)
            return 0

        if args.command == "validate":
            data = load_pattern_memory(root)
            warnings = validate_pattern_memory_doc(data)
            if warnings:
                for warning in warnings:
                    print(f"warning: {warning}", file=sys.stderr)
                return 1
            print(f"valid pattern memory: {args.project}")
            return 0

        raise HarnessError(f"Unknown command: {args.command}")
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
