#!/usr/bin/env python3
"""Track and summarize research workflow resource usage."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from scripts.harness.state import (
    HarnessError,
    append_agent_event,
    atomic_write_json,
    load_json,
    now_iso,
    project_root,
    update_agent_status,
)
from scripts.harness.workflow_hooks import refresh_report_index

KIND_VALUES = {"tokens", "cost", "gpu_hours", "wall_time", "storage", "api_calls", "other"}
CSV_HEADER = ["kind", "unit", "amount", "entries", "detail"]


def ledger_path(root: Path) -> Path:
    return root / "state" / "resource_ledger.json"


def default_ledger(project_name: str) -> dict[str, Any]:
    return {
        "project": project_name,
        "schema_version": 1,
        "last_updated": now_iso(),
        "kind_values": sorted(KIND_VALUES),
        "entries": [],
    }


def load_ledger(root: Path) -> dict[str, Any]:
    data = load_json(ledger_path(root), fallback=default_ledger(root.name))
    validate_ledger(data)
    return data


def write_ledger(root: Path, data: dict[str, Any]) -> None:
    data["last_updated"] = now_iso()
    validate_ledger(data)
    atomic_write_json(ledger_path(root), data)


def validate_ledger(data: dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise HarnessError("resource_ledger.json must be a JSON object.")
    entries = data.get("entries")
    if not isinstance(entries, list):
        raise HarnessError("resource_ledger.json must contain an entries array.")
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise HarnessError(f"resource ledger entry {index} must be an object.")
        entry_id = str(entry.get("id") or "").strip()
        if not entry_id:
            raise HarnessError(f"resource ledger entry {index} is missing id.")
        if entry_id in seen:
            raise HarnessError(f"Duplicate resource ledger entry id: {entry_id}")
        seen.add(entry_id)
        kind = str(entry.get("kind") or "").strip()
        if kind not in KIND_VALUES:
            raise HarnessError(f"Resource ledger entry {entry_id} has invalid kind: {kind!r}")
        amount = entry.get("amount", 0)
        if not isinstance(amount, (int, float)):
            raise HarnessError(f"Resource ledger entry {entry_id} amount must be numeric.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Track research workflow resource usage.")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create state/resource_ledger.json if missing.")
    init.add_argument("--project", required=True)

    record = sub.add_parser("record", help="Record one resource usage entry.")
    record.add_argument("--project", required=True)
    record.add_argument("--id", required=True)
    record.add_argument("--kind", required=True, choices=sorted(KIND_VALUES))
    record.add_argument("--amount", required=True, type=float)
    record.add_argument("--unit", required=True)
    record.add_argument("--owner", default="")
    record.add_argument("--command-id", default="")
    record.add_argument("--exp-id", default="")
    record.add_argument("--note", default="")

    summary = sub.add_parser("summary", help="Summarize resource usage.")
    summary.add_argument("--project", required=True)
    summary.add_argument("--write-report", action="store_true")
    summary.add_argument("--json", action="store_true")

    audit = sub.add_parser("audit", help="Validate resource ledger structure.")
    audit.add_argument("--project", required=True)
    audit.add_argument("--strict", action="store_true")
    audit.add_argument("--json", action="store_true")
    return parser.parse_args()


def summarize(data: dict[str, Any]) -> dict[str, Any]:
    totals: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in data.get("entries", []):
        key = (str(entry.get("kind") or ""), str(entry.get("unit") or ""))
        bucket = totals.setdefault(key, {"kind": key[0], "unit": key[1], "amount": 0.0, "entries": 0, "detail": ""})
        bucket["amount"] += float(entry.get("amount") or 0)
        bucket["entries"] += 1
    rows = sorted(totals.values(), key=lambda row: (row["kind"], row["unit"]))
    return {
        "project": data.get("project"),
        "entries": len(data.get("entries", [])),
        "totals": rows,
        "warnings": [] if rows else ["No resource usage entries recorded."],
    }


def render_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# Resource Ledger Summary",
        "",
        f"- Project: `{summary['project']}`",
        f"- Entries: {summary['entries']}",
        "",
        "| Kind | Unit | Amount | Entries |",
        "| --- | --- | ---: | ---: |",
    ]
    for row in summary["totals"]:
        lines.append(f"| {row['kind']} | {row['unit']} | {row['amount']:.4g} | {row['entries']} |")
    if not summary["totals"]:
        lines.append("| none | none | 0 | 0 |")
    return "\n".join(lines) + "\n"


def write_summary(root: Path, summary: dict[str, Any]) -> Path:
    report = root / "07_reviews" / "resource_ledger.md"
    report.write_text(render_markdown(summary), encoding="utf-8")
    csv_path = root / "09_report" / "results" / "resource_ledger.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_HEADER, lineterminator="\n")
        writer.writeheader()
        writer.writerows(summary["totals"])
    refresh_report_index(root, include_report=True)
    return csv_path


def sync_resource_lifecycle(root: Path, summary: dict[str, Any], outputs: list[str]) -> None:
    note = f"Resource ledger summarized {summary.get('entries', 0)} entrie(s)."
    update_agent_status(
        root,
        "director",
        "waiting",
        task="Review resource ledger summary.",
        stage="resource_ledger",
        outputs=outputs,
        notes=note,
        append_note=True,
    )
    append_agent_event(
        root,
        "resource_ledger_summary",
        "director",
        status="waiting",
        task="Review resource ledger summary.",
        stage="resource_ledger",
        outputs=outputs,
        notes=note,
    )


def sync_resource_record_event(root: Path, entry: dict[str, Any]) -> None:
    owner = str(entry.get("owner") or "director")
    append_agent_event(
        root,
        "resource_ledger_record",
        owner,
        status="waiting",
        task=f"Recorded resource ledger entry {entry.get('id')}.",
        stage="resource_ledger",
        outputs=["state/resource_ledger.json"],
        notes=(
            f"{entry.get('kind')}={entry.get('amount')} {entry.get('unit')} "
            f"command={entry.get('command_id', '')} exp={entry.get('exp_id', '')}"
        ).strip(),
    )


def main() -> int:
    args = parse_args()
    try:
        root = project_root(args.project)
        if args.command == "init":
            path = ledger_path(root)
            if not path.exists():
                write_ledger(root, default_ledger(root.name))
            print(path.relative_to(root).as_posix())
            return 0

        data = load_ledger(root)
        if args.command == "record":
            entries = data.setdefault("entries", [])
            if any(entry.get("id") == args.id for entry in entries):
                raise HarnessError(f"Resource ledger entry already exists: {args.id}")
            entry = {
                "id": args.id,
                "kind": args.kind,
                "amount": args.amount,
                "unit": args.unit,
                "owner": args.owner,
                "command_id": args.command_id,
                "exp_id": args.exp_id,
                "note": args.note,
                "recorded_at": now_iso(),
            }
            entries.append(entry)
            write_ledger(root, data)
            sync_resource_record_event(root, entry)
            print(f"recorded resource entry: {args.id}")
            return 0

        summary = summarize(data)
        if args.command == "summary":
            if args.write_report:
                csv_path = write_summary(root, summary)
                summary["written"] = ["07_reviews/resource_ledger.md", csv_path.relative_to(root).as_posix()]
                sync_resource_lifecycle(root, summary, summary["written"])
            if args.json:
                print(json.dumps(summary, indent=2, ensure_ascii=False))
            else:
                print(render_markdown(summary).rstrip())
            return 0

        if args.command == "audit":
            if args.json:
                print(json.dumps({"project": root.name, "ok": not summary["warnings"], "warnings": summary["warnings"]}, indent=2))
            else:
                print("resource ledger OK")
                for warning in summary["warnings"]:
                    print(f"warning: {warning}", file=sys.stderr)
            return 1 if args.strict and summary["warnings"] else 0
        raise HarnessError(f"Unknown command: {args.command}")
    except (HarnessError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
