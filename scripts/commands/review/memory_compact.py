#!/usr/bin/env python3
"""Compact the monotonically-growing agent memory file.

`state/agent_memory.md` accumulates one `## Memory Checkpoint: <timestamp>`
block per durable note. Because the file is read at every resume, the
checkpoints tax context indefinitely. This command archives old checkpoint
blocks verbatim to `state/sessions/memory_archive.md` and rewrites the live
file with the curated header sections plus the kept checkpoints (the recent
pinned ones, any not yet past the cutoff, and any undated ones), so the
always-loaded surface stays bounded without losing history.

Curated sections (anything that is not a ``## Memory Checkpoint:`` block, such
as ``## Stable Project Facts`` and ``## Operating Model``) are always kept.

Preview by default; pass ``--apply`` to write.

Usage:
    python -m scripts.commands.review.memory_compact --project <name> \
        [--older-than-days 30] [--keep-recent 5] [--apply] [--json]
"""
from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from scripts.harness.errors import HarnessError
from scripts.harness.paths import project_root

CHECKPOINT_RE = re.compile(r"^##\s+Memory Checkpoint:\s*(.+?)\s*$")
MEMORY_RELPATH = "state/agent_memory.md"
ARCHIVE_RELPATH = "state/sessions/memory_archive.md"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Archive old agent-memory checkpoints to keep the always-loaded file small.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--older-than-days", type=int, default=30,
                        help="Archive checkpoints older than this many days (default 30).")
    parser.add_argument("--keep-recent", type=int, default=5,
                        help="Always keep at least this many most-recent checkpoints (default 5).")
    parser.add_argument("--apply", action="store_true",
                        help="Write the changes. Without it, only a preview is printed.")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def _parse_ts(text: str) -> date | None:
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def split_segments(text: str) -> list[dict]:
    """Split memory text into ordered segments.

    Each segment is a dict with ``kind`` ('curated' or 'checkpoint'), the raw
    ``text``, and for checkpoints the heading ``stamp`` and parsed ``date``.
    A checkpoint segment runs from its ``## Memory Checkpoint:`` heading up to
    the next ``## Memory Checkpoint:`` heading (or end of file). Only those
    headings are boundaries, so a ``#``/``##`` line inside a checkpoint body
    does not fragment the block; this matches how ``progress_checkpoint``
    appends checkpoints after the curated header sections.
    """
    lines = text.splitlines(keepends=True)
    segments: list[dict] = []
    buffer: list[str] = []
    current: dict | None = None

    def flush() -> None:
        nonlocal buffer, current
        if not buffer:
            return
        body = "".join(buffer)
        if current is not None:
            current["text"] = body
            segments.append(current)
        else:
            segments.append({"kind": "curated", "text": body})
        buffer = []
        current = None

    for line in lines:
        match = CHECKPOINT_RE.match(line.rstrip("\n"))
        if match:
            flush()
            stamp = match.group(1).strip()
            current = {"kind": "checkpoint", "stamp": stamp, "date": _parse_ts(stamp)}
            buffer = [line]
        else:
            buffer.append(line)
    flush()
    return segments


def plan_compaction(text: str, *, older_than_days: int, keep_recent: int,
                    today: date) -> dict:
    segments = split_segments(text)
    checkpoints = [s for s in segments if s["kind"] == "checkpoint"]
    cutoff = today - timedelta(days=max(0, older_than_days))

    # Indices (into `checkpoints`) of the most-recent blocks that are pinned.
    dated = [(i, s["date"]) for i, s in enumerate(checkpoints) if s["date"] is not None]
    dated.sort(key=lambda pair: pair[1], reverse=True)
    pinned = {i for i, _ in dated[:max(0, keep_recent)]}

    archived: list[dict] = []
    kept_segments: list[dict] = []
    cp_index = 0
    for seg in segments:
        if seg["kind"] != "checkpoint":
            kept_segments.append(seg)
            continue
        idx = cp_index
        cp_index += 1
        d = seg["date"]
        # Archive only dated, old, non-pinned checkpoints. Undated blocks are
        # never archived (we cannot prove they are stale).
        if d is not None and d < cutoff and idx not in pinned:
            archived.append(seg)
        else:
            kept_segments.append(seg)

    return {
        "segments": segments,
        "checkpoints_total": len(checkpoints),
        "kept_segments": kept_segments,
        "archived": archived,
        "cutoff": cutoff,
    }


def render_live(kept_segments: list[dict]) -> str:
    body = "".join(seg["text"] for seg in kept_segments)
    if body and not body.endswith("\n"):
        body += "\n"
    return body


def render_archive_addition(archived: list[dict], stamp: str) -> str:
    lines = [f"\n<!-- Archived by memory_compact at {stamp} -->\n"]
    for seg in archived:
        chunk = seg["text"]
        if not chunk.endswith("\n"):
            chunk += "\n"
        lines.append(chunk)
    return "".join(lines)


def run_compact(root: Path, *, older_than_days: int, keep_recent: int,
                apply: bool, today: date, stamp: str) -> dict:
    memory_path = root / "state" / "agent_memory.md"
    if not memory_path.is_file():
        raise HarnessError(
            f"Memory file not found: {MEMORY_RELPATH}. Nothing to compact.")
    text = memory_path.read_text(encoding="utf-8")
    plan = plan_compaction(text, older_than_days=older_than_days,
                           keep_recent=keep_recent, today=today)

    archived = plan["archived"]
    result = {
        "project": root.name,
        "memory_file": MEMORY_RELPATH,
        "archive_file": ARCHIVE_RELPATH,
        "checkpoints_total": plan["checkpoints_total"],
        "archived_count": len(archived),
        "kept_count": plan["checkpoints_total"] - len(archived),
        "cutoff": plan["cutoff"].isoformat(),
        "archived_stamps": [seg["stamp"] for seg in archived],
        "applied": False,
        "bytes_before": len(text.encode("utf-8")),
        "bytes_after": len(render_live(plan["kept_segments"]).encode("utf-8")),
    }
    if apply and archived:
        archive_path = root / "state" / "sessions" / "memory_archive.md"
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        if not archive_path.is_file():
            archive_path.write_text("# Memory Archive\n\n"
                                    "Checkpoints retired from `state/agent_memory.md` by "
                                    "`memory_compact`, preserved verbatim.\n", encoding="utf-8")
        with archive_path.open("a", encoding="utf-8") as handle:
            handle.write(render_archive_addition(archived, stamp))
        memory_path.write_text(render_live(plan["kept_segments"]), encoding="utf-8")
        result["applied"] = True
    return result


def _print_summary(result: dict, apply: bool) -> None:
    print(f"project          : {result['project']}")
    print(f"memory file      : {result['memory_file']}")
    print(f"checkpoints       : {result['checkpoints_total']} total")
    print(f"cutoff date       : {result['cutoff']} (older-than)")
    print(f"to archive        : {result['archived_count']} "
          f"-> {result['archive_file']}")
    print(f"to keep           : {result['kept_count']}")
    print(f"size              : {result['bytes_before']} -> {result['bytes_after']} bytes")
    if result["archived_stamps"]:
        print("archived stamps  :")
        for s in result["archived_stamps"]:
            print(f"  - {s}")
    if result["applied"]:
        print("status            : applied")
    elif apply:
        print("status            : nothing to archive")
    else:
        print("status            : preview only (pass --apply to write)")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = project_root(args.project)
        if not root.is_dir():
            raise HarnessError(f"Project not found: {root}")
        now = datetime.now().astimezone()
        result = run_compact(
            root,
            older_than_days=args.older_than_days,
            keep_recent=args.keep_recent,
            apply=args.apply,
            today=now.date(),
            stamp=now.isoformat(timespec="seconds"),
        )
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            _print_summary(result, args.apply)
        return 0
    except HarnessError as exc:
        print(f"error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
