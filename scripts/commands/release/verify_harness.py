#!/usr/bin/env python3
"""Run the full harness verification suite."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from scripts.harness import repo_root as harness_repo_root
    from scripts.harness.commands import python_module_command
except ModuleNotFoundError:
    from scripts.harness import repo_root as harness_repo_root
    from scripts.harness.commands import python_module_command


def repo_root() -> Path:
    return harness_repo_root()


def git_command(*args: str) -> list[str]:
    return ["git", "-c", f"safe.directory={repo_root()}", *args]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run all harness verification checks.")
    parser.add_argument("--project", default="template", help="Project to validate. Default: template.")
    parser.add_argument(
        "--skip-paper-build",
        action="store_true",
        help="Skip LaTeX build validation.",
    )
    parser.add_argument(
        "--include-dashboard",
        action="store_true",
        help="Include optional dashboard JavaScript syntax checks.",
    )
    return parser.parse_args()


def run_step(name: str, cmd: list[str]) -> bool:
    print(f"== {name}")
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(cmd, cwd=repo_root(), text=True, capture_output=True, env=env)
    if result.stdout:
        print(result.stdout.rstrip())
    if result.returncode != 0:
        if result.stderr:
            print(result.stderr.rstrip(), file=sys.stderr)
        print(f"FAILED: {name}", file=sys.stderr)
        return False
    return True


def main() -> int:
    args = parse_args()
    script_files = sorted(str(path.relative_to(repo_root())) for path in (repo_root() / "scripts").rglob("*.py"))
    checks: list[tuple[str, list[str]]] = [
        ("python syntax", [sys.executable, "-m", "py_compile", *script_files]),
        ("project index check", python_module_command("project_index.py", "check")),
        ("project validation", python_module_command("validate_project.py", "--project", args.project, "--strict")),
        ("agent event log validation", python_module_command("agent_events.py", "validate", "--project", args.project)),
        ("progress checkpoint validation", python_module_command("progress_checkpoint.py", "validate", "--project", args.project)),
        ("agent vote validation", python_module_command("agent_vote.py", "validate", "--project", args.project)),
        ("pattern memory validation", python_module_command("pattern_memory.py", "validate", "--project", args.project)),
        ("ralph loop validation", python_module_command("ralph_loop.py", "validate", "--project", args.project)),
        ("session workspace validation", python_module_command("session_state.py", "validate", "--project", args.project)),
        ("state doctor dry run", python_module_command("state_doctor.py", "--project", args.project, "--dry-run-enqueue", "--json")),
        ("state doctor repair preview", python_module_command("state_doctor.py", "--project", args.project, "--dry-run-repair", "--json")),
        ("project health dry run", python_module_command("project_health.py", "--project", args.project, "--dry-run-enqueue", "--json")),
        ("project hygiene audit", python_module_command("project_hygiene.py", "--project", args.project, "--strict", "--json")),
        ("brief intake draft", python_module_command("brief_intake.py", "draft", "--project", args.project)),
        ("experiment planner dry run", python_module_command("experiment_planner.py", "--project", args.project, "--json")),
        ("claim graph dry run", python_module_command("claim_graph.py", "--project", args.project, "--json")),
        ("baseline compare dry run", python_module_command("baseline_compare.py", "--project", args.project, "--json")),
        ("agent quality audit dry run", python_module_command("agent_quality_audit.py", "--project", args.project, "--json")),
        ("review form validation", python_module_command("review_forms.py", "validate", "--strict")),
        ("research registry validation", python_module_command("research_registry.py", "validate", "--project", args.project)),
        ("data and metric audit", python_module_command("data_metric_audit.py", "--project", args.project, "--strict")),
        ("paper claim lint", python_module_command("paper_claim_linter.py", "--project", args.project, "--strict")),
        ("research readiness audit", python_module_command("research_audit.py", "--project", args.project, "--json")),
        ("source credibility audit", python_module_command("source_credibility_audit.py", "--project", args.project, "--json")),
        ("experiment diagnosis", python_module_command("experiment_diagnosis.py", "--project", args.project, "--json")),
        ("resource ledger audit", python_module_command("resource_ledger.py", "audit", "--project", args.project)),
        ("phase gate audit", python_module_command("phase_gate.py", "audit", "--project", args.project, "--json")),
        ("run checkpoint audit", python_module_command("run_checkpoint.py", "audit", "--project", args.project, "--json")),
        ("workflow wiring audit", python_module_command("workflow_audit.py", *(["--include-dashboard"] if args.include_dashboard else []))),
        ("release check metadata", python_module_command("release_check.py", "--project", args.project, "--skip-verify-harness", "--skip-paper-build", *(["--include-dashboard"] if args.include_dashboard else []))),
        ("baseline sandbox audit", python_module_command("baseline_sandbox.py", "--project", args.project, "--strict")),
        ("agent orchestrator planning", python_module_command("agent_orchestrator.py", "next", "--project", args.project)),
        ("research loop planning", python_module_command("research_loop.py", "plan", "--project", args.project)),
        ("gpu monitor check", python_module_command("gpu_monitor.py", "--project", args.project, "--squeue-output", os.devnull)),
        ("artifact manifest dry run", python_module_command("artifact_packager.py", "--project", args.project, "--dry-run")),
        ("smoke test", python_module_command("smoke_test.py", *(["--include-dashboard"] if args.include_dashboard else []))),
        ("privacy audit", python_module_command("privacy_audit.py")),
        ("publishable file check", python_module_command("check_publishable.py")),
        ("diff whitespace check", git_command("diff", "--check")),
    ]
    if not args.skip_paper_build:
        checks.insert(
            1,
            (
                "paper build validation",
                [
                    sys.executable,
                    "-m",
                    "scripts.commands.projects.validate_project",
                    "--project",
                    args.project,
                    "--check-paper-build",
                    "--strict",
                ],
            ),
        )
    dashboard_core = repo_root() / "dashboard" / "core.js"
    dashboard_app = repo_root() / "dashboard" / "app.js"
    if args.include_dashboard and shutil.which("node") and dashboard_core.is_file() and dashboard_app.is_file():
        checks.append(("dashboard core JavaScript syntax", ["node", "--check", "dashboard/core.js"]))
        checks.append(("dashboard app JavaScript syntax", ["node", "--check", "dashboard/app.js"]))
    else:
        print("== dashboard JavaScript syntax")
        print("skipped: pass --include-dashboard to enforce optional dashboard assets")

    ok = True
    for name, cmd in checks:
        ok = run_step(name, cmd) and ok
    if ok:
        print("full harness verification OK")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
