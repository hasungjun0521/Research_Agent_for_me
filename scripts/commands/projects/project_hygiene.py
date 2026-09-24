#!/usr/bin/env python3
"""Report project folder hygiene: 09_report bloat and missing diagnostics.

Read-only by default. The only mutations are explicit: --write-report writes
state/project_hygiene.md. Legacy --clean-locks is retained as a safe no-op.
This command never moves or deletes research artifacts; it reports where they
should live and which harness command handles the move.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from pathlib import Path

from scripts.harness.state import (
    HarnessError,
    append_agent_event,
    now_iso,
    project_root,
    repo_root,
)

EXPECTED_TOP_LEVEL = {
    "00_brief",
    "01_literature",
    "02_planning",
    "03_experiments",
    "04_code",
    "05_results",
    "06_writing",
    "07_reviews",
    "08_baselines",
    "09_report",
    "state",
    "HANDOFF.md",
    "README.md",
    ".gitignore",
    ".gitattributes",
}

REQUIRED_CORE_FILES = (
    "HANDOFF.md",
    "README.md",
    "state/current_state.md",
    "state/next_actions.md",
    "state/agent_memory.md",
)

DIAGNOSTIC_FILES = (
    ("state/state_doctor.md", "python -m scripts.commands.projects.state_doctor --project {project} --write-report"),
    ("state/project_health.md", "python -m scripts.commands.projects.project_health --project {project} --write"),
)

FRESHNESS_REFERENCE_FILES = (
    "state/current_state.md",
    "state/next_actions.md",
    "state/command_queue.json",
    "state/agent_events.jsonl",
    "05_results/experiment_results.csv",
)

JUNK_DIR_NAMES = {"__pycache__", ".pytest_cache", ".ipynb_checkpoints", ".mypy_cache", ".ruff_cache"}
WEIGHT_SUFFIXES = {".pt", ".pth", ".ckpt", ".safetensors"}
RAW_LOG_SUFFIXES = {".log", ".out"}
SKIPPED_WALK_DIRS = {".git"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Diagnose project folder hygiene: 09_report bloat, junk artifacts, "
            "unexpected top-level entries, and missing or stale diagnostics."
        )
    )
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument("--project", help="Project folder name under projects/.")
    target.add_argument("--all", action="store_true", help="Scan every project under projects/.")
    parser.add_argument("--agent", default="director")
    parser.add_argument("--max-report-files", type=int, default=200, help="09_report file-count ceiling.")
    parser.add_argument("--max-report-mb", type=int, default=200, help="09_report total-size ceiling in MB.")
    parser.add_argument("--lock-age-hours", type=float, default=24.0, help="Legacy compatibility option; permanent lock sidecars are retained.")
    parser.add_argument("--stale-hours", type=float, default=72.0, help="Allowed diagnostic lag behind newest state change.")
    parser.add_argument(
        "--clean-locks",
        action="store_true",
        help="Deprecated no-op: lock sidecars must remain in place to protect concurrent writers.",
    )
    parser.add_argument("--write-report", action="store_true", help="Write state/project_hygiene.md.")
    parser.add_argument("--strict", action="store_true", help="Exit non-zero when high-severity findings exist.")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def safe_mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def format_size(num_bytes: int) -> str:
    value = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{int(num_bytes)} B"


def result_csv_data_rows(root: Path) -> int:
    path = root / "05_results" / "experiment_results.csv"
    if not path.is_file():
        return 0
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return sum(
                1
                for row in csv.DictReader(handle)
                if any(str(value or "").strip() for value in row.values())
            )
    except (OSError, csv.Error):
        return 0


def remove_stale_lock(path: Path, cutoff_seconds: float) -> bool:
    """Compatibility no-op: age and an unlocked probe cannot prove safe removal.

    Another process can already have the sidecar open while waiting for its
    lock. Unlinking would let later writers lock a different file concurrently.
    """
    return False


def walk_project(root: Path) -> dict[str, object]:
    """Single tolerant walk collecting lock debris and 09_report statistics."""
    report_root = root / "09_report"
    locks: list[dict[str, object]] = []
    quarantined: list[str] = []
    report_files = 0
    report_bytes = 0
    report_entries: dict[str, dict[str, int]] = {}
    junk_dirs: list[str] = []
    weight_files: list[str] = []
    raw_log_files: list[str] = []
    pyc_files = 0
    for current, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in SKIPPED_WALK_DIRS]
        current_path = Path(current)
        in_report = current_path == report_root or report_root in current_path.parents
        if in_report:
            for name in list(dirnames):
                if name in JUNK_DIR_NAMES:
                    junk_dirs.append((current_path / name).relative_to(root).as_posix())
        for name in filenames:
            path = current_path / name
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if name.endswith(".lock"):
                locks.append(
                    {
                        "path": path.relative_to(root).as_posix(),
                        "size": size,
                        "mtime": safe_mtime(path),
                    }
                )
            if ".corrupt-" in name:
                quarantined.append(path.relative_to(root).as_posix())
            if not in_report:
                continue
            report_files += 1
            report_bytes += size
            relative = path.relative_to(report_root)
            top_entry = relative.parts[0] if relative.parts else name
            bucket = report_entries.setdefault(top_entry, {"files": 0, "bytes": 0})
            bucket["files"] += 1
            bucket["bytes"] += size
            suffix = path.suffix.lower()
            if suffix in WEIGHT_SUFFIXES:
                weight_files.append(relative.as_posix())
            elif suffix in RAW_LOG_SUFFIXES:
                raw_log_files.append(relative.as_posix())
            elif suffix == ".pyc":
                pyc_files += 1
    return {
        "locks": locks,
        "quarantined": quarantined,
        "report_files": report_files,
        "report_bytes": report_bytes,
        "report_entries": report_entries,
        "junk_dirs": junk_dirs,
        "weight_files": weight_files,
        "raw_log_files": raw_log_files,
        "pyc_files": pyc_files,
    }


def scan_project(root: Path, args: argparse.Namespace) -> dict[str, object]:
    project = root.name
    findings: list[dict[str, str]] = []
    suggestions: list[str] = []

    def add(severity: str, code: str, message: str, suggestion: str = "") -> None:
        findings.append({"severity": severity, "code": code, "message": message})
        if suggestion and suggestion not in suggestions:
            suggestions.append(suggestion)

    walk = walk_project(root)

    for relative in REQUIRED_CORE_FILES:
        if not (root / relative).is_file():
            add(
                "high",
                "missing_core_file",
                f"{relative} is missing; a fresh session cannot resume from file state.",
                f"python -m scripts.commands.projects.validate_project --project {project} --strict",
            )

    reference_mtime = max(
        (safe_mtime(root / relative) for relative in FRESHNESS_REFERENCE_FILES),
        default=0.0,
    )
    stale_cutoff = args.stale_hours * 3600.0
    for relative, command in DIAGNOSTIC_FILES:
        path = root / relative
        rendered = command.format(project=project)
        if not path.is_file():
            add(
                "high",
                "missing_diagnostic",
                f"{relative} has never been generated; triage cannot follow the documented resume path.",
                rendered,
            )
        elif reference_mtime and safe_mtime(path) < reference_mtime - stale_cutoff:
            lag_hours = (reference_mtime - safe_mtime(path)) / 3600.0
            add(
                "medium",
                "stale_diagnostic",
                f"{relative} lags the newest state change by {lag_hours:.0f}h (allowed {args.stale_hours:.0f}h).",
                rendered,
            )

    report_files = int(walk["report_files"])
    report_bytes = int(walk["report_bytes"])
    max_bytes = args.max_report_mb * 1024 * 1024
    if report_files > args.max_report_files or report_bytes > max_bytes:
        heaviest = sorted(
            walk["report_entries"].items(),
            key=lambda item: item[1]["bytes"],
            reverse=True,
        )[:5]
        breakdown = ", ".join(
            f"{name} ({stats['files']} files, {format_size(stats['bytes'])})" for name, stats in heaviest
        )
        add(
            "high",
            "report_bloat",
            (
                f"09_report/ holds {report_files} files / {format_size(report_bytes)} "
                f"(ceiling {args.max_report_files} files / {args.max_report_mb} MB). "
                f"Heaviest entries: {breakdown}. 09_report/ is reader-facing only: active code belongs in "
                "04_code/, raw eval output in 05_results/ or 03_experiments/, snapshots in 08_baselines/."
            ),
            f"Follow prompts/skills/report_hygiene.md, then python -m scripts.commands.projects.project_closeout --project {project} --write-report",
        )

    junk_parts: list[str] = []
    if walk["junk_dirs"]:
        junk_parts.append(f"{len(walk['junk_dirs'])} cache dirs (e.g. {walk['junk_dirs'][0]})")
    if int(walk["pyc_files"]):
        junk_parts.append(f"{walk['pyc_files']} .pyc files")
    if walk["weight_files"]:
        junk_parts.append(f"{len(walk['weight_files'])} weight/checkpoint files (e.g. {walk['weight_files'][0]})")
    if walk["raw_log_files"]:
        junk_parts.append(f"{len(walk['raw_log_files'])} raw log files (e.g. {walk['raw_log_files'][0]})")
    if junk_parts:
        add(
            "medium",
            "report_junk",
            "09_report/ contains non-final artifacts: " + "; ".join(junk_parts) + ".",
            "Follow prompts/skills/report_hygiene.md to relocate or delete non-final artifacts.",
        )

    if walk["quarantined"]:
        add(
            "medium",
            "quarantined_state_files",
            (
                f"{len(walk['quarantined'])} quarantined .corrupt-* state files present "
                f"(e.g. {walk['quarantined'][0]}). Inspect them for unrecovered state, merge what "
                "matters back through harness CLIs, then delete the backups."
            ),
            f"python -m scripts.commands.projects.state_doctor --project {project} --write-report",
        )

    cleaned_locks: list[str] = []
    if args.clean_locks and walk["locks"]:
        add(
            "low",
            "lock_cleanup_skipped",
            "Lock sidecars are permanent synchronization files. --clean-locks is a no-op "
            "because deleting a sidecar can break exclusion for waiting writers.",
        )

    try:
        top_entries = sorted(entry.name for entry in root.iterdir())
    except OSError:
        top_entries = []
    unexpected = [
        name
        for name in top_entries
        if name not in EXPECTED_TOP_LEVEL and not name.endswith(".lock") and not name.startswith(".")
    ]
    if unexpected:
        add(
            "medium",
            "unexpected_top_level",
            "Unexpected top-level entries: "
            + ", ".join(unexpected)
            + ". Project content belongs in the numbered folders or state/.",
            "Move stray entries into 00_brief/..09_report/ or state/sessions/; nested projects/ dirs are accidental.",
        )

    result_rows = result_csv_data_rows(root)
    has_claim_graph = (root / "05_results" / "claim_graph.json").is_file() or (
        root / "05_results" / "claim_graph.md"
    ).is_file()
    if result_rows > 0 and not has_claim_graph:
        add(
            "medium",
            "missing_claim_graph",
            f"05_results/experiment_results.csv has {result_rows} result rows but no claim graph exists.",
            f"python -m scripts.commands.reports.claim_graph --project {project} --write",
        )

    counts = {"high": 0, "medium": 0, "low": 0}
    for finding in findings:
        counts[finding["severity"]] = counts.get(finding["severity"], 0) + 1
    return {
        "project": project,
        "generated_at": now_iso(),
        "thresholds": {
            "max_report_files": args.max_report_files,
            "max_report_mb": args.max_report_mb,
            "lock_age_hours": args.lock_age_hours,
            "stale_hours": args.stale_hours,
        },
        "report_usage": {"files": report_files, "bytes": report_bytes},
        "findings": findings,
        "counts": counts,
        "suggested_commands": suggestions,
        "cleaned_locks": cleaned_locks,
    }


def render_markdown(report: dict[str, object]) -> str:
    counts = report["counts"]
    lines = [
        "# Project Hygiene Report",
        "",
        f"- Project: `{report['project']}`",
        f"- Generated: {report['generated_at']}",
        f"- Findings: {counts['high']} high / {counts['medium']} medium / {counts['low']} low",
        f"- 09_report usage: {report['report_usage']['files']} files, {format_size(int(report['report_usage']['bytes']))}",
        "",
        "This is a working-state diagnostic, not a final report artifact. Do not export it to 09_report/.",
        "",
        "## Findings",
        "",
    ]
    findings = list(report["findings"])
    if not findings:
        lines.append("- No hygiene issues found.")
    for finding in findings:
        lines.append(f"- [{finding['severity']}] `{finding['code']}`: {finding['message']}")
    suggestions = list(report["suggested_commands"])
    if suggestions:
        lines += ["", "## Suggested Commands", ""]
        lines += [f"- `{command}`" for command in suggestions]
    return "\n".join(lines) + "\n"


def render_console(report: dict[str, object]) -> str:
    counts = report["counts"]
    lines = [
        f"project {report['project']}: {counts['high']} high / {counts['medium']} medium / {counts['low']} low "
        f"(09_report: {report['report_usage']['files']} files, {format_size(int(report['report_usage']['bytes']))})"
    ]
    for finding in report["findings"]:
        lines.append(f"  [{finding['severity']}] {finding['code']}: {finding['message']}")
    for command in report["suggested_commands"]:
        lines.append(f"  next: {command}")
    return "\n".join(lines)


def looks_like_project(entry: Path) -> bool:
    return (entry / "state").is_dir() or (entry / "HANDOFF.md").is_file()


def target_roots(args: argparse.Namespace) -> list[Path]:
    if args.project:
        return [project_root(args.project)]
    projects_dir = repo_root() / "projects"
    roots: list[Path] = []
    for entry in sorted(projects_dir.iterdir(), key=lambda item: item.name):
        if not entry.is_dir() or entry.name.startswith("."):
            continue
        if not looks_like_project(entry):
            print(
                f"note: skipping projects/{entry.name} (no state/ or HANDOFF.md; not a project folder)",
                file=sys.stderr,
            )
            continue
        roots.append(entry)
    return roots


def run_hygiene(args: argparse.Namespace) -> int:
    reports = [scan_project(root, args) for root in target_roots(args)]
    for report in reports:
        project = str(report["project"])
        if project == "template":
            if args.write_report or args.clean_locks:
                print(
                    "note: template is scan-only; --write-report/--clean-locks were not applied to it.",
                    file=sys.stderr,
                )
            continue
        root = repo_root() / "projects" / project
        if args.write_report:
            report_path = root / "state" / "project_hygiene.md"
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(render_markdown(report), encoding="utf-8")
        if args.write_report or report["cleaned_locks"]:
            counts = report["counts"]
            try:
                append_agent_event(
                    root,
                    "project_hygiene",
                    args.agent,
                    outputs=(["state/project_hygiene.md"] if args.write_report else []),
                    notes=(
                        f"hygiene findings high={counts['high']} medium={counts['medium']} "
                        f"low={counts['low']}; cleaned_locks={len(report['cleaned_locks'])}"
                    ),
                )
            except HarnessError:
                pass
    if args.json:
        print(json.dumps({"generated_at": now_iso(), "projects": reports}, indent=2, ensure_ascii=False))
    else:
        print("\n".join(render_console(report) for report in reports))
    if args.strict and any(report["counts"]["high"] for report in reports):
        return 1
    return 0


def main() -> int:
    from scripts.commands.projects.projects import main as projects_main
    return run_hygiene(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
