#!/usr/bin/env python3
"""Unified claims management dispatcher: board, graph, and lint.

This is a thin wrapper that routes each subcommand to the canonical
standalone module so there is a single implementation of every surface:
- board/build -> claim_evidence_board
- graph       -> claim_graph
- lint        -> paper_claim_linter
"""

from __future__ import annotations

import argparse
import sys

from scripts.commands.reports import claim_evidence_board, claim_graph, paper_claim_linter
from scripts.harness.state import HarnessError


def setup_subparsers(subparsers: argparse._SubParsersAction) -> None:
    for name in ("board", "build"):
        board = subparsers.add_parser(name, help="Build the claim-evidence board.")
        board.add_argument("--project", required=True)
        board.add_argument("--agent", default="result_interpreter")
        board.add_argument("--write", action="store_true")
        board.add_argument("--final-export", action="store_true")
        board.add_argument("--strict", action="store_true")
        board.add_argument("--json", action="store_true")
    graph = subparsers.add_parser("graph", help="Build the working claim-to-evidence graph.")
    graph.add_argument("--project", required=True)
    graph.add_argument("--agent", default="result_interpreter")
    graph.add_argument("--write", action="store_true")
    graph.add_argument("--json", action="store_true")
    lint = subparsers.add_parser("lint", help="Lint paper claims against 09_report/results.")
    lint.add_argument("--project", required=True)
    lint.add_argument("--strict", action="store_true")
    lint.add_argument("--json", action="store_true")


def run_board(args: argparse.Namespace) -> int:
    return claim_evidence_board.build(args)


def run_graph(args: argparse.Namespace) -> int:
    return claim_graph.run_graph(args)


def run_lint(args: argparse.Namespace) -> int:
    return paper_claim_linter.run_lint(args)


def main() -> int:
    parser = argparse.ArgumentParser(description="Unified claims management: board, graph, and lint.")
    sub = parser.add_subparsers(dest="command", required=True)
    setup_subparsers(sub)
    args = parser.parse_args()
    try:
        if args.command in {"board", "build"}:
            return run_board(args)
        if args.command == "graph":
            return run_graph(args)
        if args.command == "lint":
            return run_lint(args)
        raise HarnessError(f"Unknown command: {args.command}")
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
