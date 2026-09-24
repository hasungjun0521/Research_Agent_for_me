#!/usr/bin/env python3
"""Manage dataset and metric provenance registries."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from scripts.harness.data_roots import sync_dataset_to_data_roots
from scripts.harness.state import (
    HarnessError,
    append_agent_event,
    atomic_write_json,
    load_json,
    now_iso,
    project_root,
    split_values,
    update_agent_status,
)
from scripts.harness.workflow_hooks import refresh_report_index

DATASET_STATUSES = {"candidate", "available", "prepared", "validated", "rejected"}
METRIC_STATUSES = {"candidate", "implemented", "validated", "rejected"}
DIRECTIONS = {"higher", "lower", "target", "none"}


def is_local_absolute_reference(value: str) -> bool:
    stripped = str(value or "").strip()
    if not stripped:
        return False
    return stripped.startswith(("/", "~")) or (
        len(stripped) >= 3 and stripped[1] == ":" and stripped[2] in {"\\", "/"}
    )


def reject_local_absolute_reference(value: str, label: str) -> None:
    if is_local_absolute_reference(value):
        raise HarnessError(
            f"{label} must not be a local absolute path. Store private paths in "
            "config/workspace_profile.local.json and put a stable URI or project-relative path here."
        )


def registry_path(root: Path, kind: str) -> Path:
    return root / "03_experiments" / f"{kind}_registry.json"


def default_registry(project: str, kind: str) -> dict[str, Any]:
    key = "datasets" if kind == "dataset" else "metrics"
    return {
        "project": project,
        "schema_version": 1,
        "last_updated": now_iso(),
        key: [],
    }


def load_registry(root: Path, kind: str) -> dict[str, Any]:
    data = load_json(registry_path(root, kind), fallback=default_registry(root.name, kind))
    validate_registry(data, kind)
    return data


def write_registry(root: Path, kind: str, data: dict[str, Any]) -> None:
    data["last_updated"] = now_iso()
    validate_registry(data, kind)
    atomic_write_json(registry_path(root, kind), data)


def validate_registry(data: dict[str, Any], kind: str) -> list[str]:
    warnings: list[str] = []
    if not isinstance(data, dict):
        raise HarnessError(f"{kind}_registry.json must be a JSON object.")
    key = "datasets" if kind == "dataset" else "metrics"
    rows = data.get(key)
    if not isinstance(rows, list):
        raise HarnessError(f"{kind}_registry.json must contain a {key} array.")
    seen: set[str] = set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise HarnessError(f"{key}[{index}] must be an object.")
        item_id = str(row.get("id") or "").strip()
        if not item_id:
            raise HarnessError(f"{key}[{index}] is missing id.")
        if item_id in seen:
            raise HarnessError(f"Duplicate {kind} id: {item_id}")
        seen.add(item_id)
        if not str(row.get("name") or "").strip():
            warnings.append(f"{kind} {item_id} has no name.")
        status = str(row.get("status") or "candidate").strip().lower()
        allowed = DATASET_STATUSES if kind == "dataset" else METRIC_STATUSES
        if status not in allowed:
            raise HarnessError(f"{kind} {item_id} has invalid status: {status!r}")
        if kind == "metric":
            direction = str(row.get("direction") or "").strip().lower()
            if direction and direction not in DIRECTIONS:
                raise HarnessError(f"metric {item_id} has invalid direction: {direction!r}")
        for list_field in ("evidence_files", "aliases"):
            if list_field in row and not isinstance(row[list_field], list):
                raise HarnessError(f"{kind} {item_id} field {list_field} must be a list.")
    return warnings


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage dataset and metric registries.")
    sub = parser.add_subparsers(dest="command", required=True)

    for name in ("init-datasets", "init-metrics", "list-datasets", "list-metrics", "validate"):
        cmd = sub.add_parser(name)
        cmd.add_argument("--project", required=True)

    add_dataset = sub.add_parser("add-dataset")
    add_dataset.add_argument("--project", required=True)
    add_dataset.add_argument("--agent", default="experiment_designer")
    add_dataset.add_argument("--id", required=True)
    add_dataset.add_argument("--name", required=True)
    add_dataset.add_argument("--status", choices=sorted(DATASET_STATUSES), default="candidate")
    add_dataset.add_argument("--source", default="")
    add_dataset.add_argument("--license", default="")
    add_dataset.add_argument("--split", default="")
    add_dataset.add_argument("--preprocessing", default="")
    add_dataset.add_argument("--path", default="")
    add_dataset.add_argument("--checksum", default="")
    add_dataset.add_argument("--evidence", action="append", dest="evidence_files")
    add_dataset.add_argument("--alias", action="append", dest="aliases")
    add_dataset.add_argument("--used-by-exp", action="append", dest="used_by_experiments")
    add_dataset.add_argument(
        "--no-data-root-sync",
        action="store_true",
        help="Do not update 03_experiments/data_roots.md from this dataset row.",
    )

    add_metric = sub.add_parser("add-metric")
    add_metric.add_argument("--project", required=True)
    add_metric.add_argument("--agent", default="experiment_designer")
    add_metric.add_argument("--id", required=True)
    add_metric.add_argument("--name", required=True)
    add_metric.add_argument("--status", choices=sorted(METRIC_STATUSES), default="candidate")
    add_metric.add_argument("--direction", choices=sorted(DIRECTIONS), default="")
    add_metric.add_argument("--definition", default="")
    add_metric.add_argument("--implementation", default="")
    add_metric.add_argument("--evidence", action="append", dest="evidence_files")
    add_metric.add_argument("--alias", action="append", dest="aliases")

    return parser.parse_args()


def upsert(items: list[dict[str, Any]], item: dict[str, Any]) -> dict[str, Any]:
    for existing in items:
        if existing.get("id") == item["id"]:
            existing.update({key: value for key, value in item.items() if value not in ("", [], None)})
            existing["updated_at"] = now_iso()
            return existing
    timestamp = now_iso()
    item["created_at"] = timestamp
    item["updated_at"] = timestamp
    items.append(item)
    return item


def sync_data_roots(root: Path, item: dict[str, Any], used_by: list[str]) -> None:
    sync_dataset_to_data_roots(
        root,
        item,
        producer="research_registry",
        used_by=used_by,
        notes="synchronized from research_registry; keep machine-private paths out of tracked files",
        update_existing=True,
    )


def sync_registry_agent(root: Path, agent: str, kind: str, item_id: str, outputs: list[str]) -> None:
    task = f"Updated {kind} registry entry {item_id}."
    note = "Research provenance registry updated; keep data roots, metrics, and experiment configs aligned before execution."
    update_agent_status(
        root,
        agent,
        "waiting",
        task=task,
        stage="research_registry",
        outputs=outputs,
        notes=note,
        append_note=True,
    )
    append_agent_event(
        root,
        "research_registry",
        agent,
        status="waiting",
        task=task,
        stage="research_registry",
        outputs=outputs,
        notes=note,
    )
    append_agent_event(
        root,
        f"research_registry_{kind}",
        agent,
        status="waiting",
        task=task,
        stage="research_registry",
        outputs=outputs,
        notes=note,
    )


def main() -> int:
    args = parse_args()
    try:
        root = project_root(args.project)
        if args.command == "init-datasets":
            data = load_registry(root, "dataset")
            write_registry(root, "dataset", data)
            print(f"datasets: {len(data['datasets'])}")
            return 0
        if args.command == "init-metrics":
            data = load_registry(root, "metric")
            write_registry(root, "metric", data)
            print(f"metrics: {len(data['metrics'])}")
            return 0
        if args.command == "add-dataset":
            reject_local_absolute_reference(args.source, "--source")
            reject_local_absolute_reference(args.path, "--path")
            data = load_registry(root, "dataset")
            item = {
                "id": args.id,
                "name": args.name,
                "status": args.status,
                "source": args.source,
                "license": args.license,
                "split": args.split,
                "preprocessing": args.preprocessing,
                "path": args.path,
                "checksum": args.checksum,
                "evidence_files": split_values(args.evidence_files),
                "aliases": split_values(args.aliases),
            }
            stored_item = upsert(data["datasets"], item)
            write_registry(root, "dataset", data)
            outputs = ["03_experiments/dataset_registry.json"]
            if not args.no_data_root_sync:
                sync_data_roots(root, stored_item, split_values(args.used_by_experiments))
                outputs.append("03_experiments/data_roots.md")
            sync_registry_agent(root, args.agent, "dataset", args.id, outputs)
            refresh_report_index(root)
            print(f"dataset: {args.id}")
            return 0
        if args.command == "add-metric":
            data = load_registry(root, "metric")
            upsert(data["metrics"], {
                "id": args.id,
                "name": args.name,
                "status": args.status,
                "direction": args.direction,
                "definition": args.definition,
                "implementation": args.implementation,
                "evidence_files": split_values(args.evidence_files),
                "aliases": split_values(args.aliases),
            })
            write_registry(root, "metric", data)
            sync_registry_agent(root, args.agent, "metric", args.id, ["03_experiments/metric_registry.json"])
            refresh_report_index(root)
            print(f"metric: {args.id}")
            return 0
        if args.command in {"list-datasets", "list-metrics"}:
            kind = "dataset" if args.command == "list-datasets" else "metric"
            key = "datasets" if kind == "dataset" else "metrics"
            data = load_registry(root, kind)
            for item in data[key]:
                print(f"{item['id']}\t{item.get('status', '')}\t{item.get('name', '')}")
            return 0
        if args.command == "validate":
            warnings = []
            warnings.extend(validate_registry(load_registry(root, "dataset"), "dataset"))
            warnings.extend(validate_registry(load_registry(root, "metric"), "metric"))
            if warnings:
                print("warnings:")
                for warning in warnings:
                    print(f"- {warning}")
            print(f"valid research registries: {args.project}")
            return 0 if not warnings else 1
        raise HarnessError(f"Unknown command: {args.command}")
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
