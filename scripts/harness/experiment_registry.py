#!/usr/bin/env python3
"""Shared writers for experiment data-root and artifact registries.

Data-root rows are written through scripts/harness/data_roots.py so the whole
harness shares one canonical 03_experiments/data_roots.md table schema.
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from scripts.harness import now_iso
from scripts.harness.data_roots import (
    DATA_ROOTS_HEADER,
    DATA_ROOTS_RELATIVE_PATH,
    sync_data_root_rows,
)

ARTIFACT_HEADER = [
    "updated_at",
    "experiment_id",
    "artifact_id",
    "kind",
    "path",
    "produced_by",
    "status",
    "notes",
]


def markdown_cell(value: Any) -> str:
    text = str(value or "").replace("\n", " ").strip()
    return text.replace("|", "\\|") or "-"


def artifact_registry_path(root: Path) -> Path:
    return root / "03_experiments" / "artifact_registry.csv"


def data_roots_path(root: Path) -> Path:
    return root / DATA_ROOTS_RELATIVE_PATH


def read_artifact_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ARTIFACT_HEADER:
            return []
        return [
            {field: str(row.get(field) or "") for field in ARTIFACT_HEADER}
            for row in reader
            if any(str(value or "").strip() for value in row.values())
        ]


def write_artifact_rows(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=ARTIFACT_HEADER)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in ARTIFACT_HEADER})


def upsert_artifact_rows(root: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        return
    path = artifact_registry_path(root)
    existing = read_artifact_rows(path)
    index = {
        (row.get("experiment_id", ""), row.get("artifact_id", ""), row.get("path", "")): row
        for row in existing
    }
    ordered = [(row.get("experiment_id", ""), row.get("artifact_id", ""), row.get("path", "")) for row in existing]
    for row in rows:
        key = (row.get("experiment_id", ""), row.get("artifact_id", ""), row.get("path", ""))
        if key not in index:
            ordered.append(key)
        index[key] = row
    write_artifact_rows(path, [index[key] for key in ordered])


def ensure_data_roots(root: Path) -> Path:
    path = data_roots_path(root)
    if path.is_file() and path.read_text(encoding="utf-8", errors="replace").strip():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(DATA_ROOTS_HEADER) + "\n", encoding="utf-8")
    return path


def append_data_root_rows(root: Path, rows: list[dict[str, str]]) -> None:
    """Upsert data-root rows into the canonical 7-column data_roots.md table.

    The updated-at timestamp is folded into the Notes cell so this writer and
    scripts/harness/data_roots.py share one table schema instead of racing
    over two incompatible header layouts.
    """
    if not rows:
        return
    ensure_data_roots(root)
    converted: list[tuple[str, str]] = []
    for row in rows:
        data_id = str(row.get("data_id") or "").strip()
        if not data_id:
            continue
        notes = str(row.get("notes") or "").strip()
        updated_at = str(row.get("updated_at") or "").strip()
        if updated_at:
            notes = f"{notes} (updated {updated_at})".strip()
        converted.append(
            (
                data_id,
                "| {data_id} | {root_uri} | {split_version} | {produced_by} | "
                "{used_by_experiments} | {status} | {notes} |".format(
                    data_id=markdown_cell(data_id),
                    root_uri=markdown_cell(row.get("root_uri")),
                    split_version=markdown_cell(row.get("split_version")),
                    produced_by=markdown_cell(row.get("produced_by")),
                    used_by_experiments=markdown_cell(row.get("used_by_experiments")),
                    status=markdown_cell(row.get("status")),
                    notes=markdown_cell(notes),
                ),
            )
        )
    sync_data_root_rows(root, converted, update_existing=True)


def artifact_row(
    *,
    experiment_id: str,
    artifact_id: str,
    kind: str,
    path: str,
    produced_by: str,
    status: str,
    notes: str = "",
    timestamp: str | None = None,
) -> dict[str, str]:
    return {
        "updated_at": timestamp or now_iso(),
        "experiment_id": experiment_id,
        "artifact_id": artifact_id,
        "kind": kind,
        "path": path,
        "produced_by": produced_by,
        "status": status,
        "notes": notes,
    }


def data_root_row(
    *,
    data_id: str,
    root_uri: str,
    split_version: str,
    produced_by: str,
    used_by_experiments: str,
    status: str,
    notes: str = "",
    timestamp: str | None = None,
) -> dict[str, str]:
    return {
        "updated_at": timestamp or now_iso(),
        "data_id": data_id,
        "root_uri": root_uri,
        "split_version": split_version,
        "produced_by": produced_by,
        "used_by_experiments": used_by_experiments,
        "status": status,
        "notes": notes,
    }
