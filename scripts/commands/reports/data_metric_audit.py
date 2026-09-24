#!/usr/bin/env python3
"""Audit dataset/metric registry provenance for reported results."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from scripts.harness.report_lifecycle import sync_report_lifecycle
from scripts.harness.state import HarnessError, project_root


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit dataset and metric provenance before paper claims strengthen.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--agent", default="data_analyst")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--write-report", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def load_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    if not path.is_file():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [
            {str(k or "").strip(): str(v or "").strip() for k, v in row.items()}
            for row in csv.DictReader(handle)
            if any(str(value or "").strip() for value in row.values())
        ]


def working_journal_rows(root: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in csv_rows(root / "05_results" / "experiment_journal.csv"):
        experiment = str(row.get("experiment") or "").strip()
        result_summary = str(row.get("result_summary") or "").strip()
        updated_at = str(row.get("updated_at") or "").strip()
        if experiment == "exp_001" and result_summary.lower() == "planned" and not updated_at:
            continue
        if not experiment and not result_summary:
            continue
        rows.append(row)
    return rows


def markdown_table_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    rows: list[dict[str, str]] = []
    header: list[str] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [cell.strip().replace("\\|", "|") for cell in stripped.strip("|").split("|")]
        if cells and all(set(cell) <= {"-", ":", " "} for cell in cells):
            continue
        if not header:
            header = cells
            continue
        if len(cells) < len(header):
            cells.extend([""] * (len(header) - len(cells)))
        row = {header[index]: cells[index] for index in range(len(header))}
        if any(value.strip() for value in row.values()):
            rows.append(row)
    return rows


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def resolve_project_path(root: Path, value: str) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        return None
    return root / path


def is_local_absolute_reference(value: str) -> bool:
    stripped = str(value or "").strip()
    if not stripped:
        return False
    return stripped.startswith(("/", "~")) or (
        len(stripped) >= 3 and stripped[1] == ":" and stripped[2] in {"\\", "/"}
    )


def audit(root: Path) -> tuple[list[str], dict[str, Any]]:
    dataset_doc = load_json(root / "03_experiments" / "dataset_registry.json", {"datasets": []})
    metric_doc = load_json(root / "03_experiments" / "metric_registry.json", {"metrics": []})
    datasets = {str(row.get("id") or ""): row for row in dataset_doc.get("datasets", []) if isinstance(row, dict)}
    metrics = {str(row.get("id") or ""): row for row in metric_doc.get("metrics", []) if isinstance(row, dict)}
    result_rows = csv_rows(root / "09_report" / "results" / "experiment_results.csv")
    working_result_rows = csv_rows(root / "05_results" / "experiment_results.csv")
    working_rows = working_journal_rows(root)
    data_root_rows = markdown_table_rows(root / "03_experiments" / "data_roots.md")
    data_roots = {
        str(row.get("Data ID") or "").strip(): row
        for row in data_root_rows
        if str(row.get("Data ID") or "").strip()
    }
    warnings: list[str] = []
    manifest: dict[str, Any] = {
        "project": root.name,
        "datasets": {},
        "data_roots": {},
        "metrics": {},
        "result_rows": len(result_rows),
        "working_result_rows": len(working_result_rows),
        "working_journal_rows": len(working_rows),
    }

    for row in result_rows:
        dataset_id = row.get("dataset", "")
        metric_id = row.get("metric", "")
        if dataset_id and dataset_id not in datasets:
            warnings.append(f"Result references dataset not in registry: {dataset_id}.")
        if metric_id and metric_id not in metrics:
            warnings.append(f"Result references metric not in registry: {metric_id}.")
    for row in working_result_rows:
        dataset_id = row.get("dataset", "")
        metric_id = row.get("metric", "")
        if dataset_id and dataset_id not in datasets:
            warnings.append(f"Working result references dataset not in registry: {dataset_id}.")
        if metric_id and metric_id not in metrics:
            warnings.append(f"Working result references metric not in registry: {metric_id}.")

    for row in working_rows:
        dataset_id = str(row.get("dataset") or "").strip()
        if not dataset_id or dataset_id.lower() in {"not recorded", "missing", "-", "none"}:
            warnings.append(
                f"Working journal row for experiment {row.get('experiment', 'unknown')} has no dataset id."
            )
            continue
        if dataset_id not in datasets:
            warnings.append(f"Working journal references dataset not in registry: {dataset_id}.")
        if dataset_id not in data_roots:
            warnings.append(f"Working journal references dataset missing from data_roots.md: {dataset_id}.")

    dataset_ids_to_audit = {
        row.get("dataset", "")
        for row in result_rows + working_result_rows
        if row.get("dataset", "")
    }
    dataset_ids_to_audit.update(
        row.get("dataset", "")
        for row in working_rows
        if row.get("dataset", "") and row.get("dataset", "").lower() not in {"not recorded", "missing", "-", "none"}
    )
    for dataset_id in sorted(dataset_ids_to_audit):
        dataset = datasets.get(dataset_id)
        if not dataset:
            continue
        data_root = data_roots.get(dataset_id)
        if not data_root:
            warnings.append(f"Dataset {dataset_id} is used in results but is missing from 03_experiments/data_roots.md.")
        else:
            root_value = str(data_root.get("Root / URI") or "").strip()
            split_value = str(data_root.get("Split / Version") or "").strip()
            if not root_value or root_value == "-":
                warnings.append(f"Dataset {dataset_id} has no Root / URI in data_roots.md.")
            if is_local_absolute_reference(root_value):
                warnings.append(f"Dataset {dataset_id} uses a local absolute Root / URI in data_roots.md.")
            if not split_value or split_value == "-":
                warnings.append(f"Dataset {dataset_id} has no Split / Version in data_roots.md.")
            if "to_be_defined" in {root_value, split_value}:
                warnings.append(f"Dataset {dataset_id} still has starter data root values.")
            manifest["data_roots"][dataset_id] = {
                "root_uri": root_value,
                "split_version": split_value,
                "status": data_root.get("Status", ""),
            }
        if str(dataset.get("status") or "").lower() not in {"prepared", "validated"}:
            warnings.append(f"Dataset {dataset_id} is used in results but status is {dataset.get('status', 'candidate')}.")
        for field in ("source", "split"):
            if not str(dataset.get(field) or "").strip():
                warnings.append(f"Dataset {dataset_id} is missing {field}.")
        if not str(dataset.get("preprocessing") or "").strip():
            warnings.append(f"Dataset {dataset_id} has no preprocessing description.")
        path_value = str(dataset.get("path") or dataset.get("local_path") or "").strip()
        checksum = str(dataset.get("checksum") or dataset.get("sha256") or "").strip()
        resolved = resolve_project_path(root, path_value)
        computed = ""
        if resolved and resolved.is_file():
            computed = file_sha256(resolved)
            if checksum and checksum != computed:
                warnings.append(f"Dataset {dataset_id} checksum does not match local file.")
        elif path_value:
            warnings.append(f"Dataset {dataset_id} path is missing or unsafe: {path_value}.")
        elif not checksum and not (str(dataset.get("source") or "").strip() and str(dataset.get("split") or "").strip()):
            warnings.append(f"Dataset {dataset_id} has no checksum, local path, or source+split provenance.")
        manifest["datasets"][dataset_id] = {
            "status": dataset.get("status", ""),
            "source": dataset.get("source", ""),
            "split": dataset.get("split", ""),
            "preprocessing": dataset.get("preprocessing", ""),
            "checksum": checksum,
            "computed_sha256": computed,
        }

    metric_ids_to_audit = {
        row.get("metric", "")
        for row in result_rows + working_result_rows
        if row.get("metric", "")
    }
    for metric_id in sorted(metric_ids_to_audit):
        metric = metrics.get(metric_id)
        if not metric:
            continue
        if str(metric.get("status") or "").lower() not in {"implemented", "validated"}:
            warnings.append(f"Metric {metric_id} is used in results but status is {metric.get('status', 'candidate')}.")
        for field in ("definition", "implementation"):
            if not str(metric.get(field) or "").strip():
                warnings.append(f"Metric {metric_id} is missing {field}.")
        manifest["metrics"][metric_id] = {
            "status": metric.get("status", ""),
            "direction": metric.get("direction", ""),
            "definition": metric.get("definition", ""),
            "implementation": metric.get("implementation", ""),
        }

    return warnings, manifest


def write_report(root: Path, warnings: list[str], manifest: dict[str, Any]) -> Path:
    path = root / "05_results" / "data_metric_audit.md"
    lines = [
        "# Data And Metric Audit",
        "",
        f"- Result rows: {manifest['result_rows']}",
        f"- Working result rows: {manifest.get('working_result_rows', 0)}",
        f"- Working journal rows: {manifest.get('working_journal_rows', 0)}",
        f"- Dataset IDs: {', '.join(manifest['datasets']) or 'none'}",
        f"- Metric IDs: {', '.join(manifest['metrics']) or 'none'}",
        "",
        "## Findings",
        "",
    ]
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings)
    else:
        lines.append("- No audit warnings.")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    manifest_path = root / "05_results" / "data_metric_audit.json"
    manifest_path.write_text(json.dumps({"warnings": warnings, **manifest}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def sync_data_metric_agent(root: Path, agent: str, warnings: list[str]) -> None:
    outputs = [
        "05_results/data_metric_audit.md",
        "05_results/data_metric_audit.json",
    ]
    status = "blocked" if warnings else "waiting"
    task = "Wrote data/metric provenance audit."
    notes = f"Data/metric audit found {len(warnings)} warning(s)."
    sync_report_lifecycle(
        root,
        agent=agent,
        event_type="data_metric_audit",
        status=status,
        task=task,
        outputs=outputs,
        notes=notes,
        refresh_report=False,
    )


def main() -> int:
    args = parse_args()
    try:
        root = project_root(args.project)
        warnings, manifest = audit(root)
        report_path = write_report(root, warnings, manifest) if args.write_report else None
        if args.write_report:
            sync_data_metric_agent(root, args.agent, warnings)
        if args.json:
            print(json.dumps({"project": args.project, "warnings": warnings, "manifest": manifest}, indent=2, ensure_ascii=False))
        else:
            if warnings:
                print("data/metric audit warnings:")
                for warning in warnings:
                    print(f"- {warning}")
            else:
                print(f"data/metric audit OK: {args.project}")
            if report_path:
                print(report_path.relative_to(root).as_posix())
        return 1 if warnings and args.strict else 0
    except (HarnessError, json.JSONDecodeError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
