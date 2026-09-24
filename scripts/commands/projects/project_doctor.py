#!/usr/bin/env python3
"""Consolidated project diagnosis: state doctor -> project health -> project hygiene."""

from __future__ import annotations

import argparse
import sys

from scripts.commands.projects.project_health import run_audit as run_health_audit
from scripts.commands.projects.project_hygiene import run_hygiene
from scripts.commands.projects.state_doctor import run_audit as run_state_audit
from scripts.harness.state import HarnessError, project_root


def setup_subparsers(subparsers: argparse._SubParsersAction) -> None:
    doctor = subparsers.add_parser(
        "doctor",
        help="Run all project diagnostics in the correct order (state -> health -> hygiene).",
    )
    doctor.add_argument("--project", required=True)
    doctor.add_argument("--agent", default="director")
    doctor.add_argument("--no-state", action="store_true", help="Skip state_doctor.")
    doctor.add_argument("--no-health", action="store_true", help="Skip project_health.")
    doctor.add_argument("--no-hygiene", action="store_true", help="Skip project_hygiene.")
    doctor.add_argument("--repair", action="store_true", help="Apply state doctor repairs.")
    doctor.add_argument("--fix-hygiene", action="store_true", help="Apply hygiene fixes.")
    doctor.add_argument("--enqueue", action="store_true", help="Enqueue suggested actions.")
    doctor.add_argument(
        "--strict", action="store_true", help="Fail if any diagnostic finds critical issues."
    )


def run_doctor(args: argparse.Namespace) -> int:
    project = args.project
    exit_code = 0

    try:
        project_root(project)
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    # 1. State Doctor (file-state consistency). Mirrors state_doctor.parse_args defaults.
    if not args.no_state:
        print(f"--- state_doctor --project {project} ---")
        sa = argparse.Namespace(
            project=project,
            agent=args.agent,
            write_report=True,
            repair=args.repair,
            dry_run_repair=False,
            enqueue_suggestions=args.enqueue,
            dry_run_enqueue=False,
            json=False,
        )
        res = run_state_audit(sa)
        if res != 0:
            exit_code = res
            if args.strict:
                return exit_code
        print()

    # 2. Project Health (research-progress next action). Mirrors project_health.parse_args defaults.
    if not args.no_health:
        print(f"--- project_health --project {project} ---")
        ha = argparse.Namespace(
            project=project,
            agent=args.agent,
            write=True,
            enqueue_suggestions=args.enqueue,
            dry_run_enqueue=False,
            strict=args.strict,
            json=False,
        )
        res = run_health_audit(ha)
        if res != 0:
            exit_code = res
            if args.strict:
                return exit_code
        print()

    # 3. Project Hygiene (folder structure). Mirrors project_hygiene.parse_args defaults.
    if not args.no_hygiene:
        print(f"--- project_hygiene --project {project} ---")
        hya = argparse.Namespace(
            project=project,
            all=False,
            agent=args.agent,
            max_report_files=200,
            max_report_mb=200,
            lock_age_hours=24.0,
            stale_hours=72.0,
            clean_locks=args.fix_hygiene,
            write_report=True,
            strict=args.strict,
            json=False,
        )
        res = run_hygiene(hya)
        if res != 0:
            exit_code = res
        print()

    if exit_code == 0:
        print("project_doctor: All diagnostics passed.")
    else:
        print(f"project_doctor: Finished with issues (exit code {exit_code}).")
    return exit_code


def main() -> int:
    from scripts.commands.projects.projects import main as projects_main

    if len(sys.argv) < 2 or sys.argv[1] != "doctor":
        sys.argv.insert(1, "doctor")
    return projects_main()


if __name__ == "__main__":
    raise SystemExit(main())
