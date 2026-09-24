#!/usr/bin/env python3
"""Unified experiment management."""

from __future__ import annotations

import argparse
import sys

from scripts.commands.experiments import (
    experiment_complete,
    experiment_diagnosis,
    experiment_planner,
    result_ingest,
    run_state,
)
from scripts.harness.state import HarnessError


def setup_subparsers(sub: argparse._SubParsersAction) -> None:
    # plan
    plan = sub.add_parser("plan", help="Plan experiments.")
    experiment_planner.setup_parser(plan)
    # diagnose
    experiment_diagnosis.setup_subparsers(sub)
    # complete
    experiment_complete.setup_subparsers(sub)
    # state
    run_state.setup_subparsers(sub)
    # ingest
    result_ingest.setup_subparsers(sub)


def main() -> int:
    parser = argparse.ArgumentParser(description="Unified experiment management.")
    sub = parser.add_subparsers(dest="command", required=True)
    setup_subparsers(sub)

    args = parser.parse_args()
    try:
        if args.command == "plan":
            return experiment_planner.run_plan(args)
        if args.command == "diagnose":
            return experiment_diagnosis.run_diagnose(args)
        if args.command == "complete":
            return experiment_complete.run_complete(args)
        if args.command == "state":
            return run_state.run_state(args)
        if args.command == "ingest":
            return result_ingest.ingest_results(args)
        if args.command == "robustness":
            return result_ingest.ingest_robustness(args)
        if args.command == "parse-log":
            return result_ingest.parse_log_command(args)
        raise HarnessError(f"Unknown command: {args.command}")
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
