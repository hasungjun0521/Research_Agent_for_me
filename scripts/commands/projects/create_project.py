#!/usr/bin/env python3
"""Create a new research project from the template."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

from scripts.harness import repo_root as harness_repo_root
from scripts.commands.research.phase_gate import default_gates, gate_path, write_gates
from scripts.commands.reports.resource_ledger import default_ledger, ledger_path, write_ledger
from scripts.harness.state import append_agent_event, update_agent_status
from scripts.harness.workflow_hooks import refresh_report_index

TEXT_SUFFIXES = {
    ".bib", ".cfg", ".csv", ".json", ".md", ".tex", ".toml", ".txt", ".yaml", ".yml",
}

def validate_project_name(project_name: str) -> Path:
    candidate = Path(project_name)
    if candidate.is_absolute(): raise ValueError("Project name must be a relative folder name.")
    if len(candidate.parts) != 1: raise ValueError("Project name must be a single folder name, not a path.")
    return candidate

def replace_project_name(destination: Path, project_name: str) -> None:
    for path in destination.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES: continue
        try: text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError: continue
        updated = text.replace("{{PROJECT_NAME}}", project_name)
        if updated != text: path.write_text(updated, encoding="utf-8")

def sync_project_created(destination: Path, project_name: str) -> None:
    outputs = ["README.md", "HANDOFF.md", "state/current_state.md", "state/agent_memory.md", "state/next_actions.md", "state/command_queue.json", "09_report/README.md"]
    task = f"Project {project_name} initialized from template."
    notes = "New project created from projects/template."
    update_agent_status(destination, "director", "waiting", task=task, stage="project_created", outputs=outputs, notes=notes, append_note=True)
    append_agent_event(destination, "project_created", "director", status="waiting", task=task, stage="project_created", outputs=outputs, notes=notes)

def run_create(args: argparse.Namespace) -> int:
    try: project_relpath = validate_project_name(args.project_name)
    except ValueError as exc: print(f"error: {exc}", file=sys.stderr); return 2
    repo_root = harness_repo_root(); template = repo_root / "projects" / "template"; destination = repo_root / "projects" / project_relpath
    if not template.is_dir(): print(f"error: template directory not found: {template}", file=sys.stderr); return 1
    if destination.exists():
        if not args.force: print(f"error: project already exists: {destination}\nUse --force to overwrite it.", file=sys.stderr); return 1
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True); shutil.copytree(template, destination)
    replace_project_name(destination, project_relpath.as_posix())
    if not gate_path(destination).exists(): write_gates(destination, default_gates(project_relpath.as_posix()))
    if not ledger_path(destination).exists(): write_ledger(destination, default_ledger(project_relpath.as_posix()))
    (destination / "state" / "checkpoints").mkdir(parents=True, exist_ok=True)
    sync_project_created(destination, project_relpath.as_posix()); refresh_report_index(destination, include_report=True)
    print(f"created project: {destination}"); return 0

def setup_subparsers(subparsers: argparse._SubParsersAction) -> None:
    create = subparsers.add_parser("create", help="Copy projects/template to projects/<project_name>.")
    create.add_argument("project_name", help="Name of the project folder to create.")
    create.add_argument("--force", action="store_true", help="Overwrite the destination project if it already exists.")

def main() -> int:
    # Use direct call to avoid circular main import if possible, but projects.py depends on us
    # This structure allows smoke_test to import run_create and replace_project_name
    parser = argparse.ArgumentParser(); setup_subparsers(parser.add_subparsers(dest="command")); args = parser.parse_args()
    if args.command == "create": return run_create(args)
    return 1

if __name__ == "__main__":
    raise SystemExit(main())
