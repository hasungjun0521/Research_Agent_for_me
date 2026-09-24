#!/usr/bin/env python3
"""Condense a large training/SLURM log into a bounded, agent-readable digest.

Agents should not read multi-MB logs end to end. This command extracts the
head, the tail, and every line matching failure/metric patterns (bounded, with
explicit truncation notes), so sessions and dispatched workers can diagnose a
run from a small, deterministic artifact.

Usage:
    python -m scripts.commands.experiments.log_digest --log <path> \
        [--out <path>] [--head-bytes 8192] [--tail-bytes 8192] \
        [--max-matches 200] [--pattern REGEX ...] [--no-default-patterns]
"""
from __future__ import annotations

import argparse
import re
from collections import deque
from datetime import datetime
from pathlib import Path

from scripts.harness.errors import HarnessError

DEFAULT_PATTERNS = (
    r"error",
    r"exception",
    r"traceback",
    r"\bfail(ed|ure)?\b",
    r"\bnan\b|\binf\b",
    r"out of memory|\boom\b",
    r"cuda",
    r"slurmstepd",
    r"\bkilled\b",
    r"assert",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Condense a large log file into a bounded digest.")
    parser.add_argument("--log", required=True, help="Path to the log file.")
    parser.add_argument("--out", help="Write the digest here instead of stdout.")
    parser.add_argument("--head-bytes", type=int, default=8192)
    parser.add_argument("--tail-bytes", type=int, default=8192)
    parser.add_argument("--max-matches", type=int, default=200,
                        help="Keep at most this many matched lines (first and last halves).")
    parser.add_argument("--pattern", action="append", default=[],
                        help="Extra case-insensitive regex to match (repeatable).")
    parser.add_argument("--no-default-patterns", action="store_true",
                        help="Use only --pattern regexes, not the built-in failure patterns.")
    return parser.parse_args(argv)


def _read_span(path: Path, start: int, length: int) -> str:
    with path.open("rb") as handle:
        handle.seek(start)
        return handle.read(length).decode("utf-8", errors="replace")


def collect_matches(path: Path, patterns: list[str], max_matches: int) -> tuple[list[str], list[str], int]:
    """Scan the log line by line; keep the first and last halves of matches.

    Returns (first_half, last_half, total_match_count).
    """
    compiled = [re.compile(p, re.IGNORECASE) for p in patterns]
    keep_first = max(1, max_matches // 2)
    keep_last = max(1, max_matches - keep_first)
    first: list[str] = []
    last: deque[str] = deque(maxlen=keep_last)
    total = 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for lineno, line in enumerate(handle, start=1):
            if not any(rx.search(line) for rx in compiled):
                continue
            total += 1
            entry = f"[L{lineno}] {line.rstrip()}"
            if len(first) < keep_first:
                first.append(entry)
            else:
                last.append(entry)
    return first, list(last), total


def build_digest(path: Path, head_bytes: int, tail_bytes: int,
                 patterns: list[str], max_matches: int) -> str:
    size = path.stat().st_size
    mtime = datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")
    head = _read_span(path, 0, min(head_bytes, size))
    # Never re-emit bytes the head already covered.
    tail_start = max(min(head_bytes, size), size - tail_bytes)
    tail = _read_span(path, tail_start, size - tail_start) if tail_start < size else ""
    first, last, total = collect_matches(path, patterns, max_matches)

    lines = [
        f"# Log Digest: {path}",
        "",
        f"- size_bytes: {size}",
        f"- modified: {mtime}",
        f"- patterns: {', '.join(patterns)}",
        f"- pattern_matches_total: {total}",
        "",
        f"## Head (first {min(head_bytes, size)} bytes)",
        "",
        "```text",
        head.rstrip("\n"),
        "```",
        "",
    ]
    lines += ["## Pattern Matches", ""]
    if not total:
        lines.append("No pattern matches found.")
    else:
        lines += ["```text", *first]
        dropped = total - len(first) - len(last)
        if dropped > 0:
            lines.append(f"... ({dropped} matched lines omitted; rerun with --max-matches {total} for all) ...")
        lines += [*last, "```"]
    if tail:
        lines += [
            "",
            f"## Tail (last {size - tail_start} bytes)",
            "",
            "```text",
            tail.rstrip("\n"),
            "```",
        ]
    lines.append("")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        path = Path(args.log)
        if not path.is_file():
            raise HarnessError(f"Log file not found: {path}")
        patterns = list(args.pattern)
        if not args.no_default_patterns:
            patterns = list(DEFAULT_PATTERNS) + patterns
        if not patterns:
            raise HarnessError("No patterns to match: pass --pattern or drop --no-default-patterns.")
        try:
            for candidate in patterns:
                re.compile(candidate, re.IGNORECASE)
        except re.error as exc:
            raise HarnessError(f"Invalid --pattern regex {candidate!r}: {exc}") from exc
        digest = build_digest(path, max(0, args.head_bytes), max(0, args.tail_bytes),
                              patterns, max(2, args.max_matches))
        if args.out:
            out = Path(args.out)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(digest, encoding="utf-8")
            print(f"saved: {out}")
        else:
            print(digest)
        return 0
    except HarnessError as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
