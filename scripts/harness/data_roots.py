"""Shared helpers for synchronizing experiment data-root provenance."""

from __future__ import annotations

from pathlib import Path
from typing import Any

DATA_ROOTS_RELATIVE_PATH = Path("03_experiments/data_roots.md")
DATA_ROOTS_HEADER = [
    "# Experiment Data Roots",
    "",
    "Use this file to keep dataset roots, derived-data locations, and split files auditable.",
    "",
    "| Data ID | Root / URI | Split / Version | Produced By | Used By Experiments | Status | Notes |",
    "| --- | --- | --- | --- | --- | --- | --- |",
]


def markdown_cell(value: object, *, fallback: str = "not specified") -> str:
    text = str(value or "").replace("\n", " ").strip()
    return text.replace("|", "\\|") or fallback


def dataset_used_by(dataset: dict[str, Any], used_by: list[str] | None = None) -> str:
    if used_by:
        return ", ".join(str(item).strip() for item in used_by if str(item).strip()) or "to be assigned"
    stored = dataset.get("used_by_experiments") or dataset.get("used_by") or []
    if isinstance(stored, list):
        return ", ".join(str(item).strip() for item in stored if str(item).strip()) or "to be assigned"
    return str(stored or "to be assigned").strip()


def data_root_row(
    dataset: dict[str, Any],
    *,
    producer: str,
    used_by: list[str] | None = None,
    notes: str,
) -> tuple[str, str]:
    dataset_id = str(dataset.get("id") or "").strip()
    root_uri = str(
        dataset.get("source")
        or dataset.get("path")
        or dataset.get("uri")
        or dataset.get("name")
        or dataset_id
    ).strip()
    split_version = str(dataset.get("split") or dataset.get("split_version") or "").strip()
    checksum = str(dataset.get("checksum") or dataset.get("sha256") or "").strip()
    if checksum and checksum not in split_version:
        split_version = f"{split_version} checksum={checksum}".strip()
    row = (
        f"| {markdown_cell(dataset_id)} | {markdown_cell(root_uri)} | "
        f"{markdown_cell(split_version)} | {markdown_cell(producer)} | "
        f"{markdown_cell(dataset_used_by(dataset, used_by))} | "
        f"{markdown_cell(str(dataset.get('status') or 'candidate'))} | "
        f"{markdown_cell(notes)} |"
    )
    return dataset_id, row


def _line_data_id(line: str) -> str:
    if not line.startswith("|"):
        return ""
    cells = [cell.strip().replace("\\|", "|") for cell in line.strip().strip("|").split("|")]
    return cells[0] if cells else ""


def _canonical_table_insert_index(lines: list[str]) -> int:
    """Index right after the canonical table's separator row, or -1 if absent."""
    header = DATA_ROOTS_HEADER[4]
    for index, line in enumerate(lines):
        if line.strip() == header and index + 1 < len(lines) and lines[index + 1].strip().startswith("| ---"):
            return index + 2
    return -1


def sync_data_root_rows(
    root: Path,
    rows: list[tuple[str, str]],
    *,
    dry_run: bool = False,
    update_existing: bool = False,
) -> bool:
    path = root / DATA_ROOTS_RELATIVE_PATH
    if not rows:
        return False

    if path.is_file() and path.read_text(encoding="utf-8", errors="replace").strip():
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    else:
        lines = [*DATA_ROOTS_HEADER]

    missing_rows: list[str] = []
    changed = False
    for data_id, row in rows:
        if not data_id:
            continue
        for index, line in enumerate(lines):
            if _line_data_id(line) == data_id:
                if update_existing and lines[index] != row:
                    lines[index] = row
                    changed = True
                break
        else:
            missing_rows.append(row)

    if missing_rows:
        changed = True
        for index, line in enumerate(lines):
            if _line_data_id(line) == "to_be_defined":
                lines[index : index + 1] = missing_rows
                break
        else:
            insert_at = _canonical_table_insert_index(lines)
            if insert_at >= 0:
                lines[insert_at:insert_at] = missing_rows
            else:
                # Never append rows under a non-canonical table header (for
                # example a legacy 8-column layout): start a fresh canonical
                # table instead so columns stay aligned with their header.
                lines.extend(["", *DATA_ROOTS_HEADER[4:], *missing_rows])

    if changed and not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return changed


def sync_dataset_to_data_roots(
    root: Path,
    dataset: dict[str, Any],
    *,
    producer: str,
    used_by: list[str] | None = None,
    notes: str,
    dry_run: bool = False,
    update_existing: bool = False,
) -> bool:
    dataset_id, row = data_root_row(dataset, producer=producer, used_by=used_by, notes=notes)
    return sync_data_root_rows(
        root,
        [(dataset_id, row)] if dataset_id else [],
        dry_run=dry_run,
        update_existing=update_existing,
    )


def sync_datasets_to_data_roots(
    root: Path,
    datasets: list[dict[str, Any]],
    *,
    producer: str,
    notes: str,
    dry_run: bool = False,
    update_existing: bool = False,
) -> bool:
    rows = [
        data_root_row(dataset, producer=producer, notes=notes)
        for dataset in datasets
        if isinstance(dataset, dict) and str(dataset.get("id") or "").strip()
    ]
    return sync_data_root_rows(root, rows, dry_run=dry_run, update_existing=update_existing)
