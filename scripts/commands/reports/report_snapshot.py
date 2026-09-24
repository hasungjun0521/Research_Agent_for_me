#!/usr/bin/env python3
"""Shared 09_report snapshot helpers for README and dashboard surfaces."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RESULT_TABLES = (
    "experiment_results.csv",
    "statistical_robustness.csv",
    "claim_evidence.csv",
    "claim_evidence_board.csv",
    "research_audit.csv",
)
REPORT_ARTIFACT_GLOBS = ("*.csv", "*.md", "*.json", "*.txt")


def safe_mtime(path: Path) -> float:
    if not path.exists():
        return 0.0
    return path.stat().st_mtime


def iso_from_timestamp(timestamp: float) -> str:
    if timestamp <= 0:
        return ""
    return datetime.fromtimestamp(timestamp, timezone.utc).astimezone().isoformat(timespec="seconds")


def project_relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def read_text(path: Path, max_chars: int) -> str:
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n[truncated]"


def csv_row_count(path: Path) -> int | None:
    if not path.is_file():
        return None
    with path.open(newline="", encoding="utf-8") as handle:
        return max(0, sum(1 for _ in csv.reader(handle)) - 1)


def csv_table_info(path: Path, limit: int = 5) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.reader(handle)
        try:
            columns = next(reader)
        except StopIteration:
            columns = []
            row_count = 0
            preview_rows: list[list[str]] = []
        else:
            row_count = 0
            preview_rows = []
            for row in reader:
                row_count += 1
                if len(preview_rows) < limit:
                    preview_rows.append(row)
    if not columns:
        return {
            "rows": 0,
            "columns": [],
            "preview_rows": [],
            "preview_limit": limit,
            "preview_truncated": False,
        }
    return {
        "rows": row_count,
        "columns": columns,
        "preview_rows": preview_rows,
        "preview_limit": limit,
        "preview_truncated": row_count > limit,
    }


def report_table_path(root: Path, filename: str) -> Path:
    report = root / "09_report"
    preferred = report / "results" / filename
    fallback = report / "src" / "results" / filename
    return preferred if preferred.exists() or not fallback.exists() else fallback


def report_tables(root: Path) -> list[dict[str, Any]]:
    tables: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for filename in RESULT_TABLES:
        path = report_table_path(root, filename)
        table_info = csv_table_info(path)
        if table_info is None:
            continue
        seen.add(path.resolve())
        tables.append({
            "path": project_relative(root, path),
            "name": path.name,
            "updated_at": iso_from_timestamp(safe_mtime(path)),
            **table_info,
        })

    results_dir = root / "09_report" / "results"
    if results_dir.is_dir():
        for path in sorted(results_dir.rglob("*.csv")):
            if path.resolve() in seen:
                continue
            table_info = csv_table_info(path)
            if table_info is None:
                continue
            tables.append({
                "path": project_relative(root, path),
                "name": path.name,
                "updated_at": iso_from_timestamp(safe_mtime(path)),
                **table_info,
            })
    return tables


def latest_result_entries(root: Path, limit: int) -> list[Path]:
    results_dir = root / "09_report" / "results"
    if not results_dir.is_dir():
        return []
    children = [path for path in results_dir.iterdir() if not path.name.startswith(".")]
    children.sort(key=safe_mtime, reverse=True)
    return children[:limit]


def report_artifact_files(root: Path, limit: int = 12) -> list[Path]:
    report = root / "09_report"
    candidates: list[Path] = []
    for folder in (report / "results", report / "analysis", report / "figures"):
        if not folder.is_dir():
            continue
        for pattern in REPORT_ARTIFACT_GLOBS:
            candidates.extend(path for path in folder.rglob(pattern) if path.is_file())
    candidates.sort(key=safe_mtime, reverse=True)
    return candidates[:limit]


def build_report_snapshot(root: Path, *, max_files: int = 12, readme_chars: int = 12000) -> dict[str, Any]:
    report = root / "09_report"
    readme = report / "README.md"
    tables = report_tables(root)
    files = [
        {
            "path": project_relative(root, path),
            "name": path.name,
            "kind": path.suffix.lstrip(".") or "file",
            "updated_at": iso_from_timestamp(safe_mtime(path)),
        }
        for path in report_artifact_files(root, max_files)
    ]
    snapshot_mtimes = [
        safe_mtime(readme),
        *(safe_mtime(root / item["path"]) for item in tables),
        *(safe_mtime(root / item["path"]) for item in files),
    ]
    return {
        "readme_path": project_relative(root, readme) if readme.is_file() else "",
        "readme_excerpt": read_text(readme, max_chars=readme_chars),
        "tables": tables,
        "latest_files": files,
        "updated_at": iso_from_timestamp(max(snapshot_mtimes, default=0)),
    }
