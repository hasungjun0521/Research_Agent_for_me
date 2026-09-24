#!/usr/bin/env python3
"""Compare cloned baseline source layouts and recommend project code structure."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from scripts.harness.state import (
    HarnessError,
    append_agent_event,
    project_root,
    update_agent_status,
)
from scripts.harness.workflow_hooks import refresh_report_index

IGNORED_DIRS = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", "node_modules", "wandb", "runs", "outputs", "checkpoints", "data", "datasets"}
ENTRYPOINTS = {"train.py", "main.py", "run.py", "eval.py", "evaluate.py", "test.py", "infer.py", "inference.py"}
CONFIG_SUFFIXES = {".yaml", ".yml", ".json", ".toml", ".ini", ".cfg"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare baseline repo structures under 08_baselines/source_snapshots/.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--agent", default="code_agent")
    parser.add_argument("--max-files", type=int, default=400)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def scan_snapshot(path: Path, max_files: int) -> dict[str, Any]:
    files: list[Path] = []
    for current, dirs, filenames in os.walk(path):
        dirs[:] = [name for name in dirs if name not in IGNORED_DIRS and not name.startswith(".")]
        for filename in filenames:
            files.append(Path(current) / filename)
            if len(files) >= max_files:
                break
        if len(files) >= max_files:
            break
    relative = [item.relative_to(path).as_posix() for item in files]
    entrypoints = [item for item in relative if Path(item).name in ENTRYPOINTS]
    config_files = [item for item in relative if Path(item).suffix.lower() in CONFIG_SUFFIXES]
    python_packages = sorted({Path(item).parts[0] for item in relative if item.endswith(".py") and len(Path(item).parts) > 1})[:20]
    categories = {
        "data": [item for item in relative if "data" in item.lower() or "dataset" in item.lower()],
        "model": [item for item in relative if "model" in item.lower() or "network" in item.lower()],
        "train": [item for item in relative if "train" in item.lower()],
        "eval": [item for item in relative if "eval" in item.lower() or "metric" in item.lower()],
        "config": config_files,
    }
    return {
        "baseline_id": path.name,
        "file_count_scanned": len(files),
        "truncated": len(files) >= max_files,
        "entrypoints": entrypoints[:20],
        "config_files": config_files[:20],
        "python_packages": python_packages,
        "categories": {key: values[:10] for key, values in categories.items()},
    }


def snapshots(root: Path) -> list[Path]:
    base = root / "08_baselines" / "source_snapshots"
    if not base.is_dir():
        return []
    return sorted(path for path in base.iterdir() if path.is_dir() and not path.name.startswith("."))


def build_report(root: Path, max_files: int) -> dict[str, Any]:
    rows = [scan_snapshot(path, max_files) for path in snapshots(root)]
    common_categories = {
        "configs": any(row["config_files"] for row in rows),
        "entrypoints": any(row["entrypoints"] for row in rows),
        "data_interfaces": any(row["categories"]["data"] for row in rows),
        "model_interfaces": any(row["categories"]["model"] for row in rows),
        "eval_interfaces": any(row["categories"]["eval"] for row in rows),
    }
    return {"schema_version": 1, "project": root.name, "baselines": rows, "common_categories": common_categories}


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Baseline Compare",
        "",
        f"- Project: `{report['project']}`",
        f"- Baselines scanned: {len(report['baselines'])}",
        "",
        "## Structure Summary",
        "",
        "| Baseline | Files Scanned | Entrypoints | Config Files | Python Packages |",
        "| --- | ---: | --- | --- | --- |",
    ]
    if not report["baselines"]:
        lines.append("| _none_ | 0 | missing | missing | missing |")
    for row in report["baselines"]:
        lines.append(
            "| `{baseline}` | {count}{truncated} | {entrypoints} | {configs} | {packages} |".format(
                baseline=row["baseline_id"],
                count=row["file_count_scanned"],
                truncated="+" if row["truncated"] else "",
                entrypoints=", ".join(row["entrypoints"][:5]) or "missing",
                configs=", ".join(row["config_files"][:5]) or "missing",
                packages=", ".join(row["python_packages"][:5]) or "missing",
            )
        )
    lines.extend([
        "",
        "## Recommended 04_code/src Shape",
        "",
        "```text",
        "04_code/src/",
        "  configs/        # normalized experiment config schema and loaders",
        "  data/           # dataset roots, split/version handling, preprocessing",
        "  models/         # project model definitions and architecture modules",
        "  training/       # train loops, checkpoints, seeds, optimizer setup",
        "  evaluation/     # metrics, evaluators, result serialization",
        "  experiments/    # wrappers binding config/data/model/eval for each run",
        "  utils/",
        "```",
        "",
        "Baseline wrappers/adapters do NOT live under `04_code/src/`. They live in",
        "`08_baselines/run_scripts/<baseline_id>/` (or `08_baselines/patches/`), keeping",
        "`04_code/src/` independent of external baseline code.",
        "",
        "## Rules",
        "",
        "- Do not edit cloned baseline snapshots directly.",
        "- Use this comparison before adding substantial project code under `04_code/src/`.",
        "- Keep adapters thin and document behavior changes in `08_baselines/code_adaptation_notes.md`.",
        "- Move cleaned release-facing code to `09_report/src/` only after the active implementation is stable.",
    ])
    return "\n".join(lines) + "\n"


def update_structure_plan(root: Path, content: str) -> None:
    path = root / "08_baselines" / "code_structure_plan.md"
    existing = path.read_text(encoding="utf-8", errors="replace") if path.exists() else "# Baseline Code Structure Plan\n"
    marker = "\n## Latest Baseline Compare Recommendation\n"
    if marker in existing:
        existing = existing.split(marker, 1)[0].rstrip() + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(existing.rstrip() + marker + "\n" + content + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    try:
        root = project_root(args.project)
        report = build_report(root, args.max_files)
        content = render_markdown(report)
        outputs: list[str] = []
        if args.write:
            path = root / "08_baselines" / "baseline_compare.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            update_structure_plan(root, content)
            outputs = ["08_baselines/baseline_compare.md", "08_baselines/code_structure_plan.md"]
            try:
                update_agent_status(root, args.agent, "done", task="Compare baseline source structures.", stage="baseline compare", outputs=outputs, notes=f"Compared {len(report['baselines'])} baseline snapshot(s).")
            except HarnessError:
                pass
            append_agent_event(root, "baseline_compare", args.agent, status="done", task="Compare baseline source structures.", stage="baseline compare", outputs=outputs, notes=f"Compared {len(report['baselines'])} baseline snapshot(s).")
            refresh_report_index(root)
        if args.json:
            import json
            print(json.dumps({"written": bool(args.write), "outputs": outputs, "report": report}, indent=2, ensure_ascii=False))
        else:
            print(content, end="")
        return 0
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
