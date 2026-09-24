#!/usr/bin/env python3
"""Read-only diff of two experiment runs (inspired by Guild AI's `guild diff`).

Answers "what actually changed between these two runs" mechanically by
comparing, for `03_experiments/<exp-a>/` vs `03_experiments/<exp-b>/`:

1. `config.yaml` as a unified text diff (explicitly says identical when equal),
2. `reproducibility_manifest.json` as a flat dotted-key-path comparison that
   lists only keys whose values differ or exist on one side,
3. result rows in `05_results/experiment_results.csv` whose `experiment_id`
   equals or starts with each exp id (so `<exp_id>_seed_<n>` rows are
   included), with a per-metric value difference.

The command never writes into the project; `--out` only writes the rendered
markdown report to the given path.

Usage:
    python -m scripts.commands.experiments.run_diff --project <name> \
        --exp-a <id> --exp-b <id> [--out <path>]
"""
from __future__ import annotations

import argparse
import csv
import difflib
import json
from pathlib import Path

from scripts.harness.errors import HarnessError
from scripts.harness.paths import project_root

CONFIG_DIFF_LINE_CAP = 400
MANIFEST_KEY_CAP = 100
METRIC_ROW_CAP = 50


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only config/manifest/result diff of two experiment runs.")
    parser.add_argument("--project", required=True, help="Project folder name under projects/.")
    parser.add_argument("--exp-a", required=True, help="First experiment id under 03_experiments/.")
    parser.add_argument("--exp-b", required=True, help="Second experiment id under 03_experiments/.")
    parser.add_argument("--out", help="Write the markdown report here instead of stdout.")
    return parser.parse_args(argv)


def _validate_exp_id(exp_id: str) -> str:
    candidate = Path(exp_id)
    if not exp_id or candidate.is_absolute() or len(candidate.parts) != 1 or ".." in candidate.parts:
        raise HarnessError(
            f"Experiment id must be a single folder name under 03_experiments/: {exp_id!r}")
    return exp_id


def _cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def config_section(dir_a: Path, dir_b: Path, exp_a: str, exp_b: str) -> list[str]:
    path_a = dir_a / "config.yaml"
    path_b = dir_b / "config.yaml"
    lines = ["## config.yaml", ""]
    if not path_a.is_file() and not path_b.is_file():
        lines.append("config.yaml is missing on both sides; nothing to compare.")
        return lines
    if not path_a.is_file() or not path_b.is_file():
        missing, present = (exp_a, exp_b) if not path_a.is_file() else (exp_b, exp_a)
        lines.append(
            f"config.yaml is missing for `{missing}` (present for `{present}`); no text diff possible.")
        return lines
    text_a = path_a.read_text(encoding="utf-8")
    text_b = path_b.read_text(encoding="utf-8")
    if text_a == text_b:
        lines.append("config.yaml files are identical.")
        return lines
    diff = list(difflib.unified_diff(
        text_a.splitlines(),
        text_b.splitlines(),
        fromfile=f"{exp_a}/config.yaml",
        tofile=f"{exp_b}/config.yaml",
        lineterm="",
    ))
    lines += ["```diff", *diff[:CONFIG_DIFF_LINE_CAP], "```"]
    if len(diff) > CONFIG_DIFF_LINE_CAP:
        lines.append(
            f"Note: {len(diff) - CONFIG_DIFF_LINE_CAP} diff lines omitted "
            f"(showing first {CONFIG_DIFF_LINE_CAP} of {len(diff)}).")
    return lines


def flatten_manifest(value: object, prefix: str = "") -> dict[str, str]:
    """Flatten nested JSON into dotted key paths mapping to compact JSON scalars."""
    if isinstance(value, dict):
        if not value:
            return {prefix or "(root)": "{}"}
        flat: dict[str, str] = {}
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            flat.update(flatten_manifest(child, path))
        return flat
    if isinstance(value, list):
        if not value:
            return {prefix or "(root)": "[]"}
        flat = {}
        for index, child in enumerate(value):
            path = f"{prefix}.{index}" if prefix else str(index)
            flat.update(flatten_manifest(child, path))
        return flat
    return {prefix or "(root)": json.dumps(value, ensure_ascii=False)}


def _load_flat_manifest(path: Path, exp_id: str) -> tuple[dict[str, str], str]:
    if not path.is_file():
        return {}, f"`{exp_id}` has no reproducibility_manifest.json; treating its side as empty."
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {}, (
            f"`{exp_id}` reproducibility_manifest.json is not valid JSON ({exc}); "
            "treating its side as empty.")
    return flatten_manifest(data), ""


def manifest_section(dir_a: Path, dir_b: Path, exp_a: str, exp_b: str) -> list[str]:
    lines = ["## reproducibility_manifest.json", ""]
    flat_a, note_a = _load_flat_manifest(dir_a / "reproducibility_manifest.json", exp_a)
    flat_b, note_b = _load_flat_manifest(dir_b / "reproducibility_manifest.json", exp_b)
    for note in (note_a, note_b):
        if note:
            lines.append(f"- {note}")
    if note_a and note_b:
        lines.append("- nothing to compare on either side.")
        return lines
    if note_a or note_b:
        lines.append("")
    all_keys = sorted(set(flat_a) | set(flat_b))
    differing = [key for key in all_keys if flat_a.get(key) != flat_b.get(key)]
    if not differing:
        lines.append(
            f"reproducibility_manifest.json values are identical "
            f"({len(all_keys)} flattened keys compared).")
        return lines
    lines.append(
        f"Differing keys ({len(differing)} of {len(all_keys)} flattened keys), "
        f"`{exp_a}` -> `{exp_b}`:")
    lines.append("")
    for key in differing[:MANIFEST_KEY_CAP]:
        left = flat_a.get(key, "(absent)")
        right = flat_b.get(key, "(absent)")
        lines.append(f"- `{key}`: {left} -> {right}")
    if len(differing) > MANIFEST_KEY_CAP:
        lines.append(
            f"- note: {len(differing) - MANIFEST_KEY_CAP} more differing keys omitted "
            f"(showing first {MANIFEST_KEY_CAP}).")
    return lines


def _summarize_metrics(rows: list[dict[str, str]]) -> dict[str, dict[str, object]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        metric = (row.get("metric") or "").strip()
        if metric:
            grouped.setdefault(metric, []).append(row)
    summary: dict[str, dict[str, object]] = {}
    for metric, items in grouped.items():
        values = [(row.get("value") or "").strip() for row in items]
        numeric: list[float] = []
        for value in values:
            try:
                numeric.append(float(value))
            except ValueError:
                continue
        mean = sum(numeric) / len(numeric) if numeric else None
        if len(values) == 1:
            display = values[0] or "(empty)"
        elif mean is not None and len(numeric) == len(values):
            display = f"{mean:.6g} (mean of {len(values)} rows)"
        elif mean is not None:
            display = f"{mean:.6g} (mean of {len(numeric)} numeric of {len(values)} rows)"
        else:
            display = "; ".join(dict.fromkeys(values)) or "(empty)"
        deltas = [d for d in dict.fromkeys((row.get("delta") or "").strip() for row in items) if d]
        statuses = [s for s in dict.fromkeys((row.get("status") or "").strip() for row in items) if s]
        summary[metric] = {
            "display": display,
            "mean": mean,
            "delta": " / ".join(deltas),
            "status": " / ".join(statuses),
        }
    return summary


def results_section(root: Path, exp_a: str, exp_b: str) -> list[str]:
    lines = ["## Result rows (05_results/experiment_results.csv)", ""]
    csv_path = root / "05_results" / "experiment_results.csv"
    if not csv_path.is_file():
        lines.append("05_results/experiment_results.csv not found; skipping result comparison.")
        return lines
    with csv_path.open("r", encoding="utf-8", newline="") as handle:
        rows = [dict(row) for row in csv.DictReader(handle)]

    def matched(exp_id: str) -> list[dict[str, str]]:
        # Exact id or the planner's seed children only — a bare prefix match
        # would wrongly fold exp_10 into exp_1.
        return [
            row for row in rows
            if (rid := (row.get("experiment_id") or "").strip()) == exp_id
            or rid.startswith(f"{exp_id}_seed_")
        ]

    rows_a = matched(exp_a)
    rows_b = matched(exp_b)
    lines.append(
        f"Matched rows (experiment_id equal to each id or its `_seed_<n>` children): "
        f"`{exp_a}` -> {len(rows_a)}, `{exp_b}` -> {len(rows_b)}.")
    if not rows_a and not rows_b:
        lines.append("No result rows matched either experiment id.")
        return lines
    summary_a = _summarize_metrics(rows_a)
    summary_b = _summarize_metrics(rows_b)
    metrics = sorted(set(summary_a) | set(summary_b))
    header = [
        "metric",
        f"{exp_a} value", f"{exp_a} delta", f"{exp_a} status",
        f"{exp_b} value", f"{exp_b} delta", f"{exp_b} status",
        "value diff (b-a)",
    ]
    lines.append("")
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + " --- |" * len(header))
    for metric in metrics[:METRIC_ROW_CAP]:
        side_a = summary_a.get(metric)
        side_b = summary_b.get(metric)
        diff_cell = "n/a"
        if (
            side_a is not None and side_b is not None
            and side_a["mean"] is not None and side_b["mean"] is not None
        ):
            diff_cell = f"{float(side_b['mean']) - float(side_a['mean']):+.6g}"
        cells = [f"`{_cell(metric)}`"]
        for side in (side_a, side_b):
            if side is None:
                cells += ["—", "—", "—"]
            else:
                cells += [
                    _cell(str(side["display"])),
                    _cell(str(side["delta"])) or "—",
                    _cell(str(side["status"])) or "—",
                ]
        cells.append(diff_cell)
        lines.append("| " + " | ".join(cells) + " |")
    if len(metrics) > METRIC_ROW_CAP:
        lines.append("")
        lines.append(
            f"Note: {len(metrics) - METRIC_ROW_CAP} more metrics omitted "
            f"(showing first {METRIC_ROW_CAP} of {len(metrics)}).")
    return lines


def build_diff(root: Path, exp_a: str, exp_b: str) -> str:
    dir_a = root / "03_experiments" / exp_a
    dir_b = root / "03_experiments" / exp_b
    lines = [
        f"# Run Diff: {exp_a} vs {exp_b}",
        "",
        f"- project: {root.name}",
        f"- exp_a: 03_experiments/{exp_a}",
        f"- exp_b: 03_experiments/{exp_b}",
        "- read-only comparison; no project files were modified",
        "",
        *config_section(dir_a, dir_b, exp_a, exp_b),
        "",
        *manifest_section(dir_a, dir_b, exp_a, exp_b),
        "",
        *results_section(root, exp_a, exp_b),
        "",
    ]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = project_root(args.project)
        exp_a = _validate_exp_id(args.exp_a)
        exp_b = _validate_exp_id(args.exp_b)
        missing = [
            exp_id for exp_id in (exp_a, exp_b)
            if not (root / "03_experiments" / exp_id).is_dir()
        ]
        if missing:
            raise HarnessError(
                "Experiment folder(s) not found under 03_experiments/: " + ", ".join(missing))
        report = build_diff(root, exp_a, exp_b)
        if args.out:
            out = Path(args.out)
            if not out.is_absolute():
                out = root / out
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(report, encoding="utf-8")
            print(f"saved: {out}")
        else:
            print(report)
        return 0
    except HarnessError as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
