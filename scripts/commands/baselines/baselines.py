#!/usr/bin/env python3
"""Unified baseline management entrypoint.

`lib` and `intake` are parsed inline (their modules own setup_subparsers/run_*
and delegate their standalone main here). `compare`, `sandbox`, and `discover`
delegate to the standalone command module that owns each, so
`baselines compare --project X` behaves like `baseline_compare --project X`.
"""

from __future__ import annotations

import argparse
import importlib
import sys

from scripts.commands.baselines import baseline_intake, baseline_library
from scripts.harness.state import HarnessError

# group token -> standalone module whose main() owns that group
_DELEGATED = {
    "compare": "scripts.commands.baselines.baseline_compare",
    "sandbox": "scripts.commands.baselines.baseline_sandbox",
    "discover": "scripts.commands.baselines.repo_discovery",
}


def main() -> int:
    argv = sys.argv[1:]
    if argv and argv[0] in _DELEGATED:
        module = importlib.import_module(_DELEGATED[argv[0]])
        sys.argv = [f"baselines {argv[0]}", *argv[1:]]
        return module.main()

    parser = argparse.ArgumentParser(description="Unified baseline management.")
    sub = parser.add_subparsers(dest="command", required=True)
    baseline_library.setup_subparsers(sub)
    baseline_intake.setup_subparsers(sub)
    for group in _DELEGATED:
        sub.add_parser(
            group,
            help=f"Delegates to the {group} command (run `baselines {group} --help`).",
            add_help=False,
        )

    args = parser.parse_args()
    try:
        if args.command == "lib":
            return baseline_library.run_lib(args)
        if args.command == "intake":
            if args.intake_command == "ingest":
                return baseline_intake.run_ingest(args)
            if args.intake_command == "discover":
                return baseline_intake.run_discover(args)
            if args.intake_command == "inspect":
                return baseline_intake.run_inspect(args)
        raise HarnessError(f"Unknown command: {args.command}")
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
