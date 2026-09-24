#!/usr/bin/env python3
"""Auto-capture reproducibility environment metadata for an experiment.

Inspired by Sacred/MLflow run metadata: fill the observable fields of an
experiment's reproducibility manifest (git commit, Python version, pip freeze
snapshot, host node, GPU type/count) without ever overwriting values a human
or another command already recorded. Non-observable fields (dataset, seeds,
commands, ...) are left for the experiment owner.

Usage:
    python -m scripts.commands.experiments.env_capture \
        --project <name> --exp-id <id> [--dry-run] [--json]
"""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts.harness.errors import HarnessError
from scripts.harness.paths import project_root, repo_root
from scripts.harness.state_io import atomic_write_json_unlocked

SUBPROCESS_TIMEOUT_SECONDS = 20.0
DISPLAY_VALUE_LIMIT = 60

# Manifest fields this command is allowed to fill, in report order.
CAPTURED_FIELDS = (
    "code.commit",
    "environment.python",
    "environment.dependencies",
    "hardware.node",
    "hardware.gpu_type",
    "hardware.gpu_count",
)

PLANNER_HINT = (
    "Plan the experiment scaffold first with "
    "'python -m scripts.commands.experiments.experiment_planner "
    "--project {project} --experiment-id {exp_id} --write'."
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fill observable reproducibility-manifest fields (commit, python, "
        "pip freeze, node, GPUs) without overwriting existing values.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--exp-id", required=True,
                        help="Experiment folder name under 03_experiments/ (e.g. exp_001).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show the before/after plan without writing any file.")
    parser.add_argument("--json", action="store_true",
                        help="Emit the machine-readable capture report.")
    return parser.parse_args(argv)


def _run(cmd: list[str], cwd: Path | None = None,
         timeout: float = SUBPROCESS_TIMEOUT_SECONDS) -> str | None:
    """Run a capture probe; return stdout on success, None on any failure."""
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                              timeout=timeout, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout


def capture_git_commit(repo: Path) -> str:
    """Return HEAD commit (with '-dirty' suffix) or '' when not observable."""
    head = _run(["git", "rev-parse", "HEAD"], cwd=repo)
    if head is None or not head.strip():
        return ""
    commit = head.strip()
    status = _run(["git", "status", "--porcelain"], cwd=repo)
    if status is not None and status.strip():
        commit += "-dirty"
    return commit


def capture_pip_freeze() -> str | None:
    """Return the pip freeze snapshot text, or None when not observable."""
    return _run([sys.executable, "-m", "pip", "freeze"])


def capture_gpus() -> tuple[str, str] | None:
    """Return (gpu_type, gpu_count) from nvidia-smi, or None when unavailable."""
    output = _run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"])
    if output is None:
        return None
    names = [line.strip() for line in output.splitlines() if line.strip()]
    if not names:
        return None
    unique_names = list(dict.fromkeys(names))
    return ", ".join(unique_names), str(len(names))


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, dict)):
        return not value
    return False


def _plan_field(manifest: dict[str, Any], field: str, observed: str | None,
                observed_note: str = "") -> dict[str, Any]:
    """Plan one field update; mutates the manifest only for 'filled' fields."""
    section_name, key = field.split(".", 1)
    section = manifest.get(section_name)
    if section is not None and not isinstance(section, dict):
        return {"field": field, "action": "skipped", "before": section, "after": section,
                "note": f"manifest section '{section_name}' is not an object; left untouched"}
    if section is None:
        section = {}
        manifest[section_name] = section
    before = section.get(key, "")
    if observed is None or not observed.strip():
        return {"field": field, "action": "unavailable", "before": before, "after": before,
                "note": "not observable on this host (probe failed or missing)"}
    if not _is_empty(before):
        note = f"existing value kept; observed {observed!r}"
        if observed_note:
            note = f"existing value kept; {observed_note}"
        return {"field": field, "action": "preserved", "before": before, "after": before,
                "note": note}
    section[key] = observed
    return {"field": field, "action": "filled", "before": before, "after": observed,
            "note": observed_note}


def run_env_capture(root: Path, exp_id: str, dry_run: bool = False) -> dict[str, Any]:
    if not exp_id or "/" in exp_id or "\\" in exp_id or ".." in exp_id:
        raise HarnessError("--exp-id must be a single file-safe folder name (e.g. exp_001).")
    hint = PLANNER_HINT.format(project=root.name, exp_id=exp_id)
    exp_rel = f"03_experiments/{exp_id}"
    exp_dir = root / "03_experiments" / exp_id
    if not exp_dir.is_dir():
        raise HarnessError(f"Experiment folder not found: {exp_rel}. {hint}")
    manifest_rel = f"{exp_rel}/reproducibility_manifest.json"
    manifest_path = exp_dir / "reproducibility_manifest.json"
    if not manifest_path.is_file():
        raise HarnessError(f"Reproducibility manifest not found: {manifest_rel}. {hint}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HarnessError(
            f"Invalid JSON in {manifest_rel}: {exc}. Fix it by hand or regenerate the "
            f"scaffold. {hint}") from exc
    if not isinstance(manifest, dict):
        raise HarnessError(f"Manifest must be a JSON object: {manifest_rel}. {hint}")

    freeze_rel = f"{exp_rel}/environment_freeze.txt"
    freeze_path = exp_dir / "environment_freeze.txt"
    # A pre-existing freeze file is evidence from the actual run host — never
    # overwrite it with this host's snapshot; just point the manifest at it.
    freeze_exists = freeze_path.is_file()
    freeze_text = None if freeze_exists else capture_pip_freeze()
    gpus = capture_gpus()
    observed: dict[str, tuple[str | None, str]] = {
        "code.commit": (capture_git_commit(repo_root()), ""),
        "environment.python": (platform.python_version(), ""),
        "environment.dependencies": (
            freeze_rel if freeze_exists or freeze_text is not None else None,
            "existing freeze file preserved (not overwritten)" if freeze_exists
            else f"pip freeze snapshot ({len(freeze_text.splitlines())} lines)"
            if freeze_text is not None else "",
        ),
        "hardware.node": (platform.node(), ""),
        "hardware.gpu_type": (gpus[0] if gpus else None, ""),
        "hardware.gpu_count": (gpus[1] if gpus else None, ""),
    }
    changes = [_plan_field(manifest, field, value, note)
               for field, (value, note) in observed.items()]
    by_field = {change["field"]: change for change in changes}

    written: list[str] = []
    if (by_field["environment.dependencies"]["action"] == "filled"
            and not freeze_exists and not dry_run):
        assert freeze_text is not None
        payload = freeze_text if freeze_text.endswith("\n") or not freeze_text else freeze_text + "\n"
        freeze_path.write_text(payload, encoding="utf-8")
        written.append(freeze_rel)
    filled = [change["field"] for change in changes if change["action"] == "filled"]
    if filled and not dry_run:
        atomic_write_json_unlocked(manifest_path, manifest)
        written.append(manifest_rel)

    counts: dict[str, int] = {}
    for change in changes:
        counts[change["action"]] = counts.get(change["action"], 0) + 1
    return {
        "project": root.name,
        "exp_id": exp_id,
        "manifest": manifest_rel,
        "dry_run": dry_run,
        "changes": changes,
        "counts": counts,
        "filled": filled,
        "skipped": [change["field"] for change in changes
                    if change["action"] in ("preserved", "skipped")],
        "written": written,
    }


def _display(value: Any, limit: int = DISPLAY_VALUE_LIMIT) -> str:
    text = "" if value is None else str(value)
    if len(text) > limit:
        return f"'{text[:limit]}' (+{len(text) - limit} more chars truncated for display)"
    return f"'{text}'"


def render_report(report: dict[str, Any]) -> str:
    lines = [
        f"Reproducibility env capture: {report['project']} / {report['exp_id']}",
        f"- manifest: {report['manifest']}",
    ]
    if report["dry_run"]:
        lines.append("- dry run: nothing written")
    lines.append("")
    width = max(len(change["field"]) for change in report["changes"])
    for change in report["changes"]:
        arrow = f"{_display(change['before'])} -> {_display(change['after'])}"
        if change["action"] in ("preserved", "unavailable", "skipped"):
            arrow = f"{_display(change['before'])} (unchanged)"
        line = f"{change['action']:<11} {change['field']:<{width}}  {arrow}"
        if change["note"]:
            line += f"  [{change['note']}]"
        lines.append(line)
    lines.append("")
    counts = report["counts"]
    parts = [f"{counts[action]} {action}"
             for action in ("filled", "preserved", "unavailable", "skipped")
             if counts.get(action)]
    lines.append("summary: " + (", ".join(parts) if parts else "no fields examined"))
    if report["dry_run"] and report["filled"]:
        lines.append(f"dry run: would fill {len(report['filled'])} field(s); "
                     "rerun without --dry-run to write.")
    for rel in report["written"]:
        lines.append(f"wrote: {rel}")
    if not report["filled"] and not report["dry_run"]:
        lines.append("no empty observable fields to fill; manifest left unchanged.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = project_root(args.project)
        report = run_env_capture(root, args.exp_id, dry_run=args.dry_run)
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(render_report(report))
        return 0
    except HarnessError as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
