#!/usr/bin/env python3
"""Unified agent management entrypoint.

`status` is parsed inline (agent_status owns setup_subparsers/run_status and
delegates its standalone main here). Every other group delegates to the
standalone command module that owns the full subcommand tree, so
`agents orchestrate parallel ...` behaves exactly like
`agent_orchestrator parallel ...`. This avoids argparse subcommand-name
collisions (e.g. `list`/`validate` appear in several agent modules) while
keeping one discoverable entrypoint.
"""

from __future__ import annotations

import argparse
import importlib
import sys

from scripts.commands.agents import agent_status
from scripts.harness.state import HarnessError

# group token -> standalone module whose main() owns that group's subcommands
_DELEGATED = {
    "messages": "scripts.commands.agents.agent_messages",
    "orchestrate": "scripts.commands.agents.agent_orchestrator",
    "events": "scripts.commands.agents.agent_events",
    "vote": "scripts.commands.agents.agent_vote",
    "dashboard": "scripts.commands.agents.agent_dashboard",
}


def main() -> int:
    argv = sys.argv[1:]
    if argv and argv[0] in _DELEGATED:
        module = importlib.import_module(_DELEGATED[argv[0]])
        sys.argv = [f"agents {argv[0]}", *argv[1:]]
        return module.main()

    parser = argparse.ArgumentParser(description="Unified agent management.")
    sub = parser.add_subparsers(dest="command", required=True)
    agent_status.setup_subparsers(sub)
    for group in _DELEGATED:
        sub.add_parser(
            group,
            help=f"Delegates to the {group} command (run `agents {group} --help`).",
            add_help=False,
        )

    args = parser.parse_args()
    try:
        if args.command == "status":
            return agent_status.run_status(args)
        raise HarnessError(f"Unknown command: {args.command}")
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
