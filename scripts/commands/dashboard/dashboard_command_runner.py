#!/usr/bin/env python3
"""Allowlisted dashboard command runner for local server mode."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from collections.abc import Callable
from typing import Any

try:
    from scripts.harness.commands import python_module_command
    from scripts.harness.state import HarnessError, project_root, repo_root
except ModuleNotFoundError:
    from scripts.harness.commands import python_module_command
    from scripts.harness.state import HarnessError, project_root, repo_root


CommandFactory = Callable[[str], list[str]]


def project_command(script: str, *args: str) -> CommandFactory:
    def factory(project: str) -> list[str]:
        return python_module_command(script, *args, "--project", project)

    return factory


ALLOWED_COMMANDS: dict[str, dict[str, Any]] = {
    "dashboard_sources": {
        "title": "Dashboard Source Check",
        "description": "Print dashboard data-source coverage for the selected project.",
        "timeout_seconds": 30,
        "command": project_command("dashboard_sources.py"),
    },
    "dashboard_refresh": {
        "title": "Refresh Dashboard Inputs",
        "description": "Regenerate claim, audit, report-index, and source-coverage inputs used by the dashboard.",
        "timeout_seconds": 90,
        "command": project_command("dashboard_refresh.py"),
    },
    "project_closeout": {
        "title": "Project Closeout Audit",
        "description": "Write a project closeout audit and route blockers to the right project skills.",
        "timeout_seconds": 120,
        "command": project_command("project_closeout.py", "--refresh-dashboard", "--write-report"),
    },
    "source_credibility": {
        "title": "Source Credibility Audit",
        "description": "Check bibliography, citation integrity, paper notes, and claim-source links.",
        "timeout_seconds": 60,
        "command": project_command("source_credibility_audit.py", "--json"),
    },
    "experiment_diagnosis": {
        "title": "Experiment Diagnosis",
        "description": "Diagnose failed, stale, or result-missing experiment runs.",
        "timeout_seconds": 60,
        "command": project_command("experiment_diagnosis.py", "--json"),
    },
    "phase_gate_audit": {
        "title": "Phase Gate Audit",
        "description": "Audit phase-gate status against current project evidence.",
        "timeout_seconds": 60,
        "command": project_command("phase_gate.py", "audit", "--json"),
    },
    "resource_ledger": {
        "title": "Resource Ledger Summary",
        "description": "Summarize tracked token, cost, GPU, wall-time, and storage usage.",
        "timeout_seconds": 60,
        "command": project_command("resource_ledger.py", "summary", "--json"),
    },
    "run_checkpoints": {
        "title": "Run Checkpoints",
        "description": "List lightweight workflow checkpoints for replay/fork planning.",
        "timeout_seconds": 60,
        "command": project_command("run_checkpoint.py", "list", "--json"),
    },
    "workflow_audit": {
        "title": "Workflow Audit",
        "description": "Run static wiring checks for dashboard and harness contracts.",
        "timeout_seconds": 60,
        "command": lambda _project: python_module_command("workflow_audit.py"),
    },
    "validate_project": {
        "title": "Validate Project",
        "description": "Validate project state with strict template/research workflow checks.",
        "timeout_seconds": 90,
        "command": project_command("validate_project.py", "--strict"),
    },
    "report_refresh": {
        "title": "Refresh Report Index",
        "description": "Refresh the generated 09_report/README.md index.",
        "timeout_seconds": 60,
        "command": project_command("report_index.py", "refresh"),
    },
}


def command_catalog() -> list[dict[str, str]]:
    return [
        {
            "id": command_id,
            "title": spec["title"],
            "description": spec["description"],
        }
        for command_id, spec in ALLOWED_COMMANDS.items()
    ]


def run_dashboard_command(project: str, command_id: str) -> dict[str, Any]:
    project_root(project)
    command_key = str(command_id or "").strip()
    spec = ALLOWED_COMMANDS.get(command_key)
    if not spec:
        return {
            "ok": False,
            "id": command_key,
            "title": "",
            "returncode": 2,
            "stdout": "",
            "stderr": f"Unknown dashboard command: {command_key}",
            "duration_ms": 0,
            "args": [],
        }

    args = spec["command"](project)
    timeout = int(spec["timeout_seconds"])
    started = time.monotonic()
    try:
        completed = subprocess.run(
            args,
            cwd=repo_root(),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        duration_ms = int((time.monotonic() - started) * 1000)
        return {
            "ok": completed.returncode == 0,
            "id": command_key,
            "title": spec["title"],
            "returncode": completed.returncode,
            "stdout": completed.stdout[-20000:],
            "stderr": completed.stderr[-12000:],
            "duration_ms": duration_ms,
            "args": args,
        }
    except subprocess.TimeoutExpired as exc:
        duration_ms = int((time.monotonic() - started) * 1000)
        return {
            "ok": False,
            "id": command_key,
            "title": spec["title"],
            "returncode": 124,
            "stdout": (exc.stdout or "")[-20000:] if isinstance(exc.stdout, str) else "",
            "stderr": f"Command timed out after {timeout} seconds.",
            "duration_ms": duration_ms,
            "args": args,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run an allowlisted dashboard command.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--id", required=True, choices=sorted(ALLOWED_COMMANDS))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = run_dashboard_command(args.project, args.id)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else int(result["returncode"] or 1)


if __name__ == "__main__":
    raise SystemExit(main())
