#!/usr/bin/env python3
"""Unified project management."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from scripts.harness.state import HarnessError
# We import the modules, not the main functions, to avoid circularity if they need to import us (though they shouldn't)
from scripts.commands.projects import (
    create_project,
    project_doctor,
    project_resume,
    project_index,
)

def main() -> int:
    parser = argparse.ArgumentParser(description="Unified project management.")
    sub = parser.add_subparsers(dest="command", required=True)

    # create
    create_project.setup_subparsers(sub)

    # doctor
    project_doctor.setup_subparsers(sub)

    # resume
    project_resume.setup_subparsers(sub)

    # index
    project_index.setup_subparsers(sub)

    args = parser.parse_args()
    try:
        if args.command == "create":
            return create_project.run_create(args)
        if args.command == "doctor":
            return project_doctor.run_doctor(args)
        if args.command == "resume":
            return project_resume.run_resume(args)
        if args.command == "index":
            # For project_index, we check the subcommand
            cmd = getattr(args, "index_command", "")
            if cmd == "refresh":
                return project_index.run_refresh()
            if cmd == "check":
                return project_index.run_check()

        raise HarnessError(f"Unknown command: {args.command}")
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
