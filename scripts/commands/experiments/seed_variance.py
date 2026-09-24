#!/usr/bin/env python3
"""Audit cross-seed variance in working experiment results.

Inspired by CodeScientist's replication meta-analysis: a claim backed by a
single lucky seed, or by seeds that disagree wildly, should be flagged before
it is strengthened in the paper. This command groups rows of
05_results/experiment_results.csv into seed families (the experiment planner
names per-seed main runs '<exp_id>_seed_<n>'), computes per-family spread
statistics, and reports two kinds of warnings:

- single-seed claim: a family with fewer than --min-seeds runs backs a
  non-empty claim_id.
- unstable across seeds: a family's relative std (std / |mean|) exceeds
  --rel-std-warn.

Read-only by default; the only mutation is the explicit --write-report, which
writes the working diagnostic 05_results/seed_variance.md (never 09_report/).

Usage:
    python -m scripts.commands.experiments.seed_variance --project <name> \
        [--metric M] [--min-seeds 2] [--rel-std-warn 0.05] \
        [--write-report] [--strict] [--json]
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.harness.errors import HarnessError
from scripts.harness.paths import project_root

RESULTS_RELPATH = "05_results/experiment_results.csv"
REPORT_RELPATH = "05_results/seed_variance.md"
REQUIRED_COLUMNS = ("experiment_id", "metric", "value")
SEED_SUFFIX = re.compile(r"^(?P<family>.+)_seed_(?P<seed>[^_]+)$")

FAMILY_TABLE_HEADERS = [
    "family",
    "metric",
    "dataset",
    "method",
    "n_seeds",
    "mean",
    "std",
    "rel_std",
    "min",
    "max",
    "values",
    "claims",
]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Audit cross-seed variance of working experiment result rows.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--metric", default="",
                        help="Only audit rows whose metric equals this name (default: all metrics).")
    parser.add_argument("--min-seeds", type=int, default=2,
                        help="Families backing a claim with fewer runs than this are flagged.")
    parser.add_argument("--rel-std-warn", type=float, default=0.05,
                        help="Flag families whose std/|mean| exceeds this fraction.")
    parser.add_argument("--write-report", action="store_true",
                        help=f"Write the working diagnostic {REPORT_RELPATH}.")
    parser.add_argument("--strict", action="store_true",
                        help="Return exit code 1 when any warning exists.")
    parser.add_argument("--json", action="store_true",
                        help="Print machine-readable JSON instead of the summary table.")
    return parser.parse_args(argv)


def split_seed_suffix(experiment_id: str) -> tuple[str, str]:
    """Return (family_id, seed_token); seed_token is '' for single-run ids."""
    match = SEED_SUFFIX.match(experiment_id)
    if match:
        return match.group("family"), match.group("seed")
    return experiment_id, ""


def load_result_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise HarnessError(f"results file not found: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        missing = [column for column in REQUIRED_COLUMNS if column not in fields]
        if missing:
            raise HarnessError(f"{path} is missing required columns: {', '.join(missing)}")
        return [
            {str(key or ""): str(value or "").strip() for key, value in row.items()}
            for row in reader
            if any(str(value or "").strip() for value in row.values())
        ]


def run_audit(root: Path, *, metric: str = "", min_seeds: int = 2,
              rel_std_warn: float = 0.05) -> dict[str, Any]:
    """Group result rows into seed families and compute spread stats + findings."""
    all_rows = load_result_rows(root / RESULTS_RELPATH)
    rows = [row for row in all_rows if not metric or row.get("metric", "") == metric]

    groups: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    skipped: list[dict[str, str]] = []
    for row in rows:
        raw_value = row.get("value", "")
        try:
            value = float(raw_value)
            parseable = math.isfinite(value)
        except ValueError:
            parseable = False
        if not parseable:
            skipped.append({
                "experiment_id": row.get("experiment_id", ""),
                "metric": row.get("metric", ""),
                "dataset": row.get("dataset", ""),
                "method": row.get("method", ""),
                "value": raw_value,
            })
            continue
        family, seed = split_seed_suffix(row.get("experiment_id", ""))
        key = (family, row.get("metric", ""), row.get("dataset", ""), row.get("method", ""))
        group = groups.setdefault(key, {"seeds": [], "values": [], "claim_ids": []})
        group["seeds"].append(seed)
        group["values"].append(value)
        claim_id = row.get("claim_id", "")
        if claim_id and claim_id not in group["claim_ids"]:
            group["claim_ids"].append(claim_id)

    families: list[dict[str, Any]] = []
    findings: list[dict[str, str]] = []
    for (family, metric_name, dataset, method), group in sorted(groups.items()):
        values: list[float] = group["values"]
        mean = statistics.fmean(values)
        std = statistics.pstdev(values)
        rel_std = std / abs(mean) if mean != 0 else None
        # Result CSVs are append-style: the same run can be recorded twice, so
        # claims are gated on DISTINCT seed tokens, not row count.
        distinct_seeds = len(set(group["seeds"]))
        entry = {
            "family": family,
            "metric": metric_name,
            "dataset": dataset,
            "method": method,
            "n_seeds": distinct_seeds,
            "n_rows": len(values),
            "mean": mean,
            "std": std,
            "rel_std": rel_std,
            "min": min(values),
            "max": max(values),
            "seeds": list(group["seeds"]),
            "values": values,
            "claim_ids": list(group["claim_ids"]),
        }
        families.append(entry)
        where = {"family": family, "metric": metric_name, "dataset": dataset, "method": method}
        if entry["n_rows"] > distinct_seeds:
            findings.append({
                **where,
                "kind": "duplicate seed rows",
                "message": (
                    f"{entry['n_rows']} rows but only {distinct_seeds} distinct seed(s) "
                    f"({', '.join(group['seeds'])}); duplicated rows deflate the variance "
                    "estimate — deduplicate the result CSV."
                ),
            })
        if entry["claim_ids"] and distinct_seeds < min_seeds:
            findings.append({
                **where,
                "kind": "single-seed claim",
                "message": (
                    f"claim(s) {', '.join(entry['claim_ids'])} backed by only "
                    f"{distinct_seeds} distinct seed(s) (< {min_seeds}); rerun with more "
                    "seeds before strengthening the claim."
                ),
            })
        if std > 0 and (rel_std is None or rel_std > rel_std_warn):
            spread = (
                f"relative std {_format_float(rel_std)} exceeds {rel_std_warn:g}"
                if rel_std is not None
                else f"relative std undefined (mean=0, std={_format_float(std)})"
            )
            findings.append({
                **where,
                "kind": "unstable across seeds",
                "message": (
                    f"{spread} across {entry['n_rows']} row(s): "
                    f"values [{', '.join(_format_float(v) for v in values)}]."
                ),
            })

    return {
        "project": root.name,
        "results_csv": RESULTS_RELPATH,
        "metric_filter": metric,
        "min_seeds": min_seeds,
        "rel_std_warn": rel_std_warn,
        "rows_total": len(all_rows),
        "rows_audited": len(rows),
        "rows_skipped": len(skipped),
        "skipped_rows": skipped,
        "families": families,
        "findings": findings,
    }


def _format_float(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.6g}"


def _family_cells(entry: dict[str, Any]) -> list[str]:
    return [
        entry["family"],
        entry["metric"],
        entry["dataset"] or "-",
        entry["method"] or "-",
        str(entry["n_seeds"]),
        _format_float(entry["mean"]),
        _format_float(entry["std"]),
        _format_float(entry["rel_std"]),
        _format_float(entry["min"]),
        _format_float(entry["max"]),
        ", ".join(_format_float(value) for value in entry["values"]),
        ", ".join(entry["claim_ids"]) or "-",
    ]


def _render_text_table(headers: list[str], rows: list[list[str]]) -> list[str]:
    widths = [len(header) for header in headers]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))
    lines = [
        "  ".join(header.ljust(widths[index]) for index, header in enumerate(headers)).rstrip(),
        "  ".join("-" * width for width in widths),
    ]
    for row in rows:
        lines.append("  ".join(cell.ljust(widths[index]) for index, cell in enumerate(row)).rstrip())
    return lines


def _skipped_lines(audit: dict[str, Any]) -> list[str]:
    if not audit["skipped_rows"]:
        return ["No rows skipped."]
    return [
        (
            f"- experiment_id={row['experiment_id'] or '-'} metric={row['metric'] or '-'} "
            f"dataset={row['dataset'] or '-'}: value {row['value']!r} is not a finite float."
        )
        for row in audit["skipped_rows"]
    ]


def _finding_lines(audit: dict[str, Any]) -> list[str]:
    if not audit["findings"]:
        return ["No warnings: every audited family meets the seed-count and stability thresholds."]
    return [
        (
            f"- [{finding['kind']}] {finding['family']} / {finding['metric']} "
            f"(dataset={finding['dataset'] or '-'}, method={finding['method'] or '-'}): "
            f"{finding['message']}"
        )
        for finding in audit["findings"]
    ]


def _header_lines(audit: dict[str, Any]) -> list[str]:
    return [
        f"- source: {audit['results_csv']}",
        f"- metric filter: {audit['metric_filter'] or '(all metrics)'}",
        f"- thresholds: min_seeds={audit['min_seeds']}, rel_std_warn={audit['rel_std_warn']:g}",
        f"- rows: {audit['rows_total']} total, {audit['rows_audited']} audited, "
        f"{audit['rows_skipped']} skipped (unparseable value)",
        f"- seed families: {len(audit['families'])}",
        f"- warnings: {len(audit['findings'])}",
    ]


def render_summary(audit: dict[str, Any]) -> str:
    lines = [f"# Seed Variance Audit: {audit['project']}", "", *_header_lines(audit), ""]
    if audit["families"]:
        lines += _render_text_table(
            FAMILY_TABLE_HEADERS,
            [_family_cells(entry) for entry in audit["families"]],
        )
    else:
        lines.append("No seed families found (no parseable result rows matched the filter).")
    # Complete listings on purpose: warnings and skipped rows are never capped.
    lines += ["", f"## Skipped rows ({audit['rows_skipped']})", "", *_skipped_lines(audit)]
    lines += ["", f"## Findings ({len(audit['findings'])})", "", *_finding_lines(audit)]
    return "\n".join(lines)


def render_report(audit: dict[str, Any]) -> str:
    generated = datetime.now().astimezone().isoformat(timespec="seconds")
    lines = [
        "# Seed Variance Audit",
        "",
        f"- Generated: {generated}",
        f"- Project: {audit['project']}",
        *_header_lines(audit),
        "",
        "## Seed Families",
        "",
    ]
    if audit["families"]:
        lines.append("| " + " | ".join(FAMILY_TABLE_HEADERS) + " |")
        lines.append("| " + " | ".join("---" for _ in FAMILY_TABLE_HEADERS) + " |")
        for entry in audit["families"]:
            cells = [cell.replace("|", "\\|") for cell in _family_cells(entry)]
            lines.append("| " + " | ".join(cells) + " |")
    else:
        lines.append("No seed families found (no parseable result rows matched the filter).")
    lines += ["", f"## Skipped Rows ({audit['rows_skipped']})", "", *_skipped_lines(audit)]
    lines += ["", f"## Findings ({len(audit['findings'])})", "", *_finding_lines(audit), ""]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.min_seeds < 1:
            raise HarnessError("--min-seeds must be >= 1.")
        if args.rel_std_warn < 0:
            raise HarnessError("--rel-std-warn must be >= 0.")
        root = project_root(args.project)
        audit = run_audit(
            root,
            metric=args.metric,
            min_seeds=args.min_seeds,
            rel_std_warn=args.rel_std_warn,
        )
        if args.json:
            print(json.dumps(audit, indent=2))
        else:
            print(render_summary(audit))
        if args.write_report:
            report_path = root / REPORT_RELPATH
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(render_report(audit), encoding="utf-8")
            print(f"saved: {report_path}")
        if args.strict and audit["findings"]:
            return 1
        return 0
    except HarnessError as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
