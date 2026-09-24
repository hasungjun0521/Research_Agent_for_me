#!/usr/bin/env python3
"""Parse and validate research worker result blocks."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

START = "=== WORKER RESULT ==="
END = "=== END WORKER RESULT ==="
SUPPORTED_STATUSES = {"OK", "BLOCKED", "FAIL"}
SUPPORTED_CONFIDENCE = {"HIGH", "MEDIUM", "LOW"}
REQUIRED_FIELDS = (
    "status",
    "confidence",
    "summary",
    "files_read",
    "files_updated",
    "evidence",
    "blockers",
    "next",
)


BLOCK_RE = re.compile(
    rf"{re.escape(START)}\s*\n(?P<body>.*?)\n{re.escape(END)}",
    re.DOTALL,
)


def read_input(path: str | None) -> str:
    if not path or path == "-":
        return sys.stdin.read()
    return Path(path).read_text(encoding="utf-8", errors="replace")


def parse_scalar_fields(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    current_key = ""
    current_lines: list[str] = []

    def flush_current() -> None:
        if current_key:
            fields[current_key] = "\n".join(current_lines).strip()

    for line in body.splitlines():
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if match:
            flush_current()
            current_key = match.group(1)
            current_lines = [match.group(2).strip()]
            continue
        if current_key and line.strip():
            current_lines.append(line.strip())
    flush_current()
    return fields


def parse_worker_result_blocks(text: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for match in BLOCK_RE.finditer(text):
        body = match.group("body").strip()
        fields = parse_scalar_fields(body)
        blocks.append({
            "status": fields.get("status", ""),
            "confidence": fields.get("confidence", ""),
            "fields": fields,
            "body": body,
        })
    return blocks


def is_none_like(value: str) -> bool:
    return value.strip().lower() in {"", "none", "n/a", "na", "-"}


def validate_block(block: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    fields = block.get("fields") or {}

    for field in REQUIRED_FIELDS:
        if field not in fields or not str(fields.get(field) or "").strip():
            errors.append(f"missing {field}")

    status = str(fields.get("status") or "").strip().upper()
    if status and status not in SUPPORTED_STATUSES:
        errors.append(f"invalid status: {status}")

    confidence = str(fields.get("confidence") or "").strip().upper()
    if confidence and confidence not in SUPPORTED_CONFIDENCE:
        errors.append(f"invalid confidence: {confidence}")

    if status == "OK" and is_none_like(str(fields.get("evidence") or "")):
        errors.append("OK result must cite evidence")
    if status == "BLOCKED" and is_none_like(str(fields.get("blockers") or "")):
        errors.append("BLOCKED result must describe blockers")
    if status == "FAIL" and is_none_like(str(fields.get("evidence") or "")):
        errors.append("FAIL result must cite failure evidence")

    return errors


def validate_text(text: str, *, allow_empty: bool = False, allow_multiple: bool = False) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    blocks = parse_worker_result_blocks(text)
    starts = text.count(START)
    ends = text.count(END)

    if starts != ends:
        errors.append(f"worker result delimiter mismatch: {starts} start, {ends} end")
    if not blocks and not allow_empty:
        errors.append("no complete worker result block found")
    if len(blocks) > 1 and not allow_multiple:
        errors.append(f"expected one worker result block, found {len(blocks)}")
    for index, block in enumerate(blocks, start=1):
        for error in validate_block(block):
            errors.append(f"block {index}: {error}")
    return blocks, errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse and validate WORKER RESULT blocks.")
    sub = parser.add_subparsers(dest="command", required=True)

    parse = sub.add_parser("parse", help="Parse worker result blocks and print JSON.")
    parse.add_argument("--file", default="-", help="Input file, or '-' for stdin.")

    validate = sub.add_parser("validate", help="Validate worker result block structure.")
    validate.add_argument("--file", default="-", help="Input file, or '-' for stdin.")
    validate.add_argument("--allow-empty", action="store_true")
    validate.add_argument("--allow-multiple", action="store_true")
    validate.add_argument("--json", action="store_true")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    text = read_input(args.file)

    if args.command == "parse":
        print(json.dumps({"blocks": parse_worker_result_blocks(text)}, indent=2, ensure_ascii=False))
        return 0

    if args.command == "validate":
        blocks, errors = validate_text(
            text,
            allow_empty=args.allow_empty,
            allow_multiple=args.allow_multiple,
        )
        result = {"ok": not errors, "block_count": len(blocks), "errors": errors}
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        elif errors:
            for error in errors:
                print(f"error: {error}", file=sys.stderr)
        else:
            print(f"valid worker result: {len(blocks)} block(s)")
        return 0 if not errors else 1

    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
