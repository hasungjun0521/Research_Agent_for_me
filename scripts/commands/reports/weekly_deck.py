#!/usr/bin/env python3
"""Build an image-first weekly development deck for a project.

Collects the last ~7 days of progress (progress log, experiment results, next
actions, git commits, harvested figures) and renders a PowerPoint deck on top of
the lab template. Data collection uses only the standard library; rendering
requires the optional ``deck`` extra (python-pptx + matplotlib).

Usage:
    python -m scripts.commands.reports.weekly_deck build --project <name> \
        [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--weeks 1] [--metric COL] \
        [--template PATH] [--out PATH] [--max-figures 4] \
        [--cover-date week|today] [--title TEXT] [--dry-run]
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path

from scripts.harness.errors import HarnessError
from scripts.harness.paths import project_root, repo_root

IMAGE_EXTS = {".png", ".jpg", ".jpeg"}
HIGHLIGHT_KINDS = {"result", "experiment_result", "direction"}


# --- CLI -------------------------------------------------------------------

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an image-first weekly development deck for a project.")
    sub = parser.add_subparsers(dest="action", required=True)
    build = sub.add_parser("build", help="Build (or preview) the weekly deck.")
    build.add_argument("--project", required=True)
    build.add_argument("--since", help="Window start (YYYY-MM-DD).")
    build.add_argument("--until", help="Window end (YYYY-MM-DD); defaults to today.")
    build.add_argument("--weeks", type=int, default=1, help="Window width in weeks (default 1).")
    build.add_argument("--metric", help="Metric column for the trend chart; auto-detected if omitted.")
    build.add_argument("--template", help="Override the base .pptx template path.")
    build.add_argument("--out", help="Output .pptx path.")
    build.add_argument("--max-figures", type=int, default=4)
    build.add_argument("--cover-date", choices=("week", "today"), default="week")
    build.add_argument("--title", help="Cover title; defaults to the project name.")
    build.add_argument("--dry-run", action="store_true",
                       help="Print collected data + output path without writing.")
    return parser.parse_args(argv)


def _parse_date(value: str | None, default: date) -> date:
    if not value:
        return default
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise HarnessError(f"Invalid date (expected YYYY-MM-DD): {value}") from exc


# --- data collection (stdlib only) ----------------------------------------

def _read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def _record_date(record: dict) -> date | None:
    ts = record.get("timestamp")
    if not ts:
        return None
    try:
        return datetime.fromisoformat(str(ts).replace("Z", "+00:00")).date()
    except ValueError:
        return None


def _in_window(d: date | None, since: date, until: date) -> bool:
    return d is not None and since <= d <= until


def _git_commit_count(repo: Path, project: str, since: date, until: date) -> int:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), "log", f"--since={since}", f"--until={until} 23:59:59",
             "--oneline", "--", f"projects/{project}/"],
            capture_output=True, text=True, timeout=20, check=False)
    except (OSError, subprocess.SubprocessError):
        return 0
    if out.returncode != 0:
        return 0
    return sum(1 for line in out.stdout.splitlines() if line.strip())


def _float(value: str) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _read_results(path: Path, metric: str | None) -> tuple[list[dict], str | None]:
    if not path.is_file():
        return [], metric
    with path.open(newline="", encoding="utf-8") as handle:
        rows = [r for r in csv.DictReader(handle)]
    rows = [r for r in rows if _float(r.get("value")) is not None or _float(r.get("delta")) is not None]
    if metric is None and rows:
        counts = Counter(r.get("metric", "") for r in rows if r.get("metric"))
        metric = counts.most_common(1)[0][0] if counts else None
    return rows, metric


def _next_actions(path: Path) -> list[str]:
    if not path.is_file():
        return []
    actions = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("<!--") or line.startswith("#"):
            continue
        for marker in ("- [ ] ", "- [x] ", "- ", "* ", "1. ", "2. ", "3. "):
            if line.startswith(marker):
                text = line[len(marker):].strip()
                if text and not text.lower().startswith("this file"):
                    actions.append(text)
                break
    return actions


def _harvest_figures(root: Path, since: date, until: date, limit: int) -> list[dict]:
    candidates: list[tuple[float, Path]] = []
    search_dirs = [root / "05_results" / "figures"]
    search_dirs += sorted((root / "03_experiments").glob("*/results"))
    for d in search_dirs:
        if not d.is_dir():
            continue
        for f in d.rglob("*"):
            if f.suffix.lower() not in IMAGE_EXTS or not f.is_file():
                continue
            mtime = f.stat().st_mtime
            if since <= datetime.fromtimestamp(mtime).date() <= until:
                candidates.append((mtime, f))
    candidates.sort(reverse=True)
    return [{"path": p, "caption": p.stem} for _, p in candidates[:limit]]


def _journal_dates(path: Path) -> dict[str, date]:
    """Map experiment id -> latest journal updated_at date (for window filtering)."""
    if not path.is_file():
        return {}
    with path.open(newline="", encoding="utf-8") as handle:
        rows = [r for r in csv.DictReader(handle)]
    dates: dict[str, date] = {}
    for row in rows:
        exp = str(row.get("experiment") or "").strip()
        raw = str(row.get("updated_at") or "").strip()
        if not exp or not raw:
            continue
        try:
            dates[exp] = datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
        except ValueError:
            continue
    return dates


def collect_week_data(root: Path, repo: Path, project: str, since: date, until: date,
                      metric: str | None, max_figures: int, cover_date: str,
                      title: str | None) -> dict:
    # Structured progress records are appended by progress_checkpoint to
    # state/progress_hooks.jsonl (see progress_checkpoint.progress_log_jsonl).
    log_rows = _read_jsonl(root / "state" / "progress_hooks.jsonl")
    window = [r for r in log_rows if _in_window(_record_date(r), since, until)]
    highlights = [str(r.get("summary", "")).strip() for r in window
                  if r.get("kind") in HIGHLIGHT_KINDS and r.get("summary")]
    n_exp = sum(1 for r in window if r.get("kind") == "experiment_result" or r.get("exp_id"))
    n_blockers = sum(1 for r in window if "blocker" in str(r.get("kind", "")))
    commits = _git_commit_count(repo, project, since, until)

    results, metric = _read_results(root / "05_results" / "experiment_results.csv", metric)
    metric_rows = [r for r in results if (metric is None or r.get("metric") == metric)]
    # Keep only this window's experiments when the journal carries timestamps;
    # without journal dates, degrade to all rows rather than an empty deck.
    journal_dates = _journal_dates(root / "05_results" / "experiment_journal.csv")
    if journal_dates:
        metric_rows = [r for r in metric_rows
                       if _in_window(journal_dates.get(str(r.get("experiment_id") or "")), since, until)]
    deltas = [{"name": (r.get("experiment_id") or "exp")[:18], "delta": _float(r.get("delta")) or 0.0}
              for r in metric_rows if _float(r.get("delta")) is not None]
    best_delta = max((d["delta"] for d in deltas), default=None)

    trend = None
    pts = [r for r in metric_rows if _float(r.get("value")) is not None]
    if len(pts) >= 2:
        ours = [_float(r.get("value")) for r in pts]
        base = [(_float(r.get("value")) - (_float(r.get("delta")) or 0.0)) for r in pts]
        trend = {"labels": [(r.get("experiment_id") or f"e{i}")[:10] for i, r in enumerate(pts)],
                 "ours": ours, "baseline": base}

    figures = _harvest_figures(root, since, until, max_figures)

    kpis = [
        {"label": "실험", "value": n_exp, "unit": "건", "color": "accent"},
        {"label": "최고 Δ", "value": (f"{best_delta:+.2f}" if best_delta is not None else "—"),
         "unit": "", "color": "good" if (best_delta or 0) >= 0 else "bad"},
        {"label": "커밋", "value": commits, "unit": "개", "color": "accent2"},
        {"label": "블로커 기록", "value": n_blockers, "unit": "건", "color": "accent"},
    ]

    if best_delta is not None and best_delta > 0:
        takeaway = f"이번 주 최고 Δ +{best_delta:.2f} · 실험 {n_exp}건 · 커밋 {commits}개"
    else:
        takeaway = f"이번 주 실험 {n_exp}건 · 커밋 {commits}개"

    cover = f"{since.isoformat()} ~ {until.isoformat()}" if cover_date == "week" else until.isoformat()
    return {
        "title": title or project,
        "project": project,
        "since": since, "until": until,
        "cover_date": cover,
        "metric": metric or "metric",
        "takeaway": takeaway,
        "kpis": kpis,
        "highlights": highlights,
        "trend": trend,
        "deltas": deltas,
        "next_actions": _next_actions(root / "state" / "next_actions.md"),
        "figures": figures,
    }


# --- template resolution & deps -------------------------------------------

def resolve_template(repo: Path, cli_template: str | None) -> Path | None:
    if cli_template:
        p = Path(cli_template)
        return p if p.is_absolute() else (repo / p)
    local = repo / "config" / "workspace_profile.local.json"
    if local.is_file():
        try:
            data = json.loads(local.read_text(encoding="utf-8"))
            configured = (data.get("weekly_deck") or {}).get("template")
        except (json.JSONDecodeError, OSError):
            configured = None
        if configured:
            p = Path(configured)
            return p if p.is_absolute() else (repo / p)
    default = repo / "config" / "ppt_template_local.pptx"
    return default if default.is_file() else None


def _require_deps() -> None:
    missing = []
    for mod in ("pptx", "matplotlib"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        raise HarnessError(
            "Weekly deck needs the optional 'deck' extra. Install with: "
            "pip install python-pptx matplotlib  (or: pip install -e .[deck])")


# --- actions ---------------------------------------------------------------

def _print_summary(week: dict, template: Path | None, out_path: Path) -> None:
    print(f"project        : {week['project']}")
    print(f"window         : {week['since']} ~ {week['until']}")
    print(f"template       : {template if template else '(built-in fallback theme)'}")
    print(f"metric         : {week['metric']}")
    print("kpis           : " + ", ".join(f"{k['label']}={k['value']}{k['unit']}" for k in week["kpis"]))
    print(f"highlights     : {len(week['highlights'])}")
    print(f"trend points   : {len(week['trend']['ours']) if week['trend'] else 0}")
    print(f"delta rows     : {len(week['deltas'])}")
    print(f"figures        : {len(week['figures'])}")
    print(f"next actions   : {len(week['next_actions'])}")
    print(f"output         : {out_path}")


def build(args: argparse.Namespace) -> int:
    repo = repo_root()
    root = project_root(args.project)
    if not root.is_dir():
        raise HarnessError(f"Project not found: {root}")
    until = _parse_date(args.until, date.today())
    since = _parse_date(args.since, until - timedelta(days=7 * max(1, args.weeks)))
    if since > until:
        raise HarnessError(f"--since ({since}) is after --until ({until}).")

    week = collect_week_data(root, repo, args.project, since, until, args.metric,
                             args.max_figures, args.cover_date, args.title)
    decks_dir = root / "05_results" / "weekly_decks"
    out_path = Path(args.out) if args.out else decks_dir / f"weekly_{until.strftime('%Y%m%d')}.pptx"
    template = resolve_template(repo, args.template)

    if args.dry_run:
        _print_summary(week, template, out_path)
        return 0

    _require_deps()
    from . import weekly_deck_builder as builder
    build_dir = decks_dir / "_build"
    builder.build_deck(week, template, out_path, build_dir)
    rel = out_path.relative_to(repo) if out_path.is_relative_to(repo) else out_path
    print(f"saved: {rel}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        if args.action == "build":
            return build(args)
        raise HarnessError(f"Unknown action: {args.action}")
    except HarnessError as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
