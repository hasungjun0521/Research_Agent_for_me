#!/usr/bin/env python3
"""Parse and validate research leader dispatch blocks."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from scripts.commands.agents.agent_orchestrator import (
    mark_dispatched,
    record_parallel_dispatch_plan,
    select_parallel_commands,
    write_prompt,
)
from scripts.harness.state import (
    HarnessError,
    append_agent_event,
    load_command_queue,
    mutate_command_queue,
    now_iso,
    project_root,
    split_values,
)
from scripts.harness.workflow_hooks import refresh_report_index

START = "=== LEADER DISPATCH ==="
END = "=== END LEADER DISPATCH ==="
SUPPORTED_TYPES = {"dispatch_workers", "complete", "manual_required", "blocked"}
KNOWN_AGENT_ROLES = {
    "director",
    "motivation_planner",
    "literature_reviewer",
    "experiment_designer",
    "code_agent",
    "data_analyst",
    "result_interpreter",
    "writing_agent",
    "venue_reviewer",
    "critic",
}


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
    for line in body.splitlines():
        if not line.strip() or line.startswith((" ", "\t", "-")):
            continue
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if match:
            fields[match.group(1)] = match.group(2).strip()
    return fields


def worker_names(body: str) -> list[str]:
    names: list[str] = []
    for match in re.finditer(r"^\s*-\s+name:\s*([A-Za-z0-9_-]+)\s*$", body, re.MULTILINE):
        names.append(match.group(1))
    return names


def parse_worker_entries(body: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    current_key = ""
    current_lines: list[str] = []

    def flush_key() -> None:
        nonlocal current_key, current_lines
        if current is not None and current_key:
            current[current_key] = "\n".join(current_lines).strip()
        current_key = ""
        current_lines = []

    def flush_worker() -> None:
        nonlocal current
        flush_key()
        if current is not None:
            entries.append(current)
        current = None

    for line in body.splitlines():
        worker_match = re.match(r"^\s*-\s+name:\s*([A-Za-z0-9_-]+)\s*$", line)
        if worker_match:
            flush_worker()
            current = {"name": worker_match.group(1)}
            continue
        if current is None:
            continue
        field_match = re.match(r"^\s{4,}([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
        if field_match:
            flush_key()
            current_key = field_match.group(1)
            current_lines = [field_match.group(2).strip()]
            continue
        if current_key and line.strip():
            current_lines.append(line.strip())
    flush_worker()
    return entries


def parse_leader_dispatch_blocks(text: str) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for match in BLOCK_RE.finditer(text):
        body = match.group("body").strip()
        fields = parse_scalar_fields(body)
        blocks.append({
            "type": fields.get("type", ""),
            "fields": fields,
            "workers": worker_names(body),
            "worker_entries": parse_worker_entries(body),
            "body": body,
        })
    return blocks


def validate_block(block: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    body = str(block.get("body") or "")
    dispatch_type = str(block.get("type") or "").strip()
    fields = block.get("fields") or {}

    if dispatch_type not in SUPPORTED_TYPES:
        errors.append(f"unsupported or missing dispatch type: {dispatch_type or '<missing>'}")
        return errors

    if dispatch_type == "dispatch_workers":
        for needle in ("workers:", "prompt:", "next_turn_expects:", "plan_file:"):
            if needle not in body:
                errors.append(f"dispatch_workers missing {needle.rstrip(':')}")
        worker_entries = list(block.get("worker_entries") or [])
        workers = [str(worker.get("name") or "") for worker in worker_entries]
        if not workers:
            errors.append("dispatch_workers must include at least one workers[].name")
        for name in workers:
            if name not in KNOWN_AGENT_ROLES:
                errors.append(f"unknown worker role: {name}")
        for index, worker in enumerate(worker_entries, start=1):
            worker_name = worker.get("name") or f"worker {index}"
            for field in ("command_id", "depends_on", "parallel_group", "expected_outputs", "prompt"):
                if not str(worker.get(field) or "").strip():
                    errors.append(f"{worker_name} missing workers[].{field}")
            expected_outputs = str(worker.get("expected_outputs") or "").strip().lower()
            if expected_outputs in {"none", "n/a", "na", "-", "[]"}:
                errors.append(f"{worker_name} must list substantive expected_outputs")
        risk = str(fields.get("risk_level") or "").lower()
        if risk and risk not in {"low", "medium", "high", "critical"}:
            errors.append(f"invalid risk_level: {risk}")
        confidence = str(fields.get("confidence") or "").upper()
        if confidence and confidence not in {"HIGH", "MEDIUM", "LOW"}:
            errors.append(f"invalid confidence: {confidence}")

    if dispatch_type == "complete":
        for field in ("result_file", "status"):
            if not fields.get(field):
                errors.append(f"complete missing {field}")
        if not fields.get("handoff_to") and "parallel_" not in body:
            errors.append("complete should include handoff_to or a parallel handoff section")

    if dispatch_type == "manual_required":
        if not fields.get("reason"):
            errors.append("manual_required missing reason")
        if not fields.get("partial_result_file"):
            errors.append("manual_required missing partial_result_file")

    if dispatch_type == "blocked":
        if not fields.get("blocked_by"):
            errors.append("blocked missing blocked_by")
        if not fields.get("retry_suggestion"):
            errors.append("blocked missing retry_suggestion")

    return errors


def validate_text(text: str, *, allow_empty: bool = False, allow_multiple: bool = False) -> tuple[list[dict[str, Any]], list[str]]:
    errors: list[str] = []
    blocks = parse_leader_dispatch_blocks(text)
    starts = text.count(START)
    ends = text.count(END)

    if starts != ends:
        errors.append(f"dispatch delimiter mismatch: {starts} start, {ends} end")
    if not blocks and not allow_empty:
        errors.append("no complete leader dispatch block found")
    if len(blocks) > 1 and not allow_multiple:
        errors.append(f"expected one leader dispatch block, found {len(blocks)}")
    for index, block in enumerate(blocks, start=1):
        for error in validate_block(block):
            errors.append(f"block {index}: {error}")
    return blocks, errors


def normalize_list_field(value: str) -> list[str]:
    normalized = str(value or "").strip()
    if normalized.lower() in {"", "none", "n/a", "na", "-", "[]"}:
        return []
    return split_values([normalized])


def prompt_summary(prompt: str) -> str:
    for raw in str(prompt or "").splitlines():
        line = raw.strip()
        if not line or line == "|":
            continue
        return line[:240]
    return "Run dispatched worker task."


def priority_from_dispatch(block: dict[str, Any], override: str | None = None) -> str:
    if override:
        return override
    risk = str((block.get("fields") or {}).get("risk_level") or "").strip().lower()
    if risk in {"critical", "high"}:
        return "high"
    if risk == "low":
        return "low"
    return "medium"


def apply_dispatch_block(root: Path, block: dict[str, Any], *, priority: str | None = None) -> list[str]:
    errors = validate_block(block)
    if errors:
        raise HarnessError("; ".join(errors))
    if str(block.get("type") or "") != "dispatch_workers":
        raise HarnessError("apply only supports dispatch_workers blocks.")

    fields = block.get("fields") or {}
    plan_file = str(fields.get("plan_file") or "").strip()
    next_turn_expects = str(fields.get("next_turn_expects") or "").strip()
    timestamp = now_iso()
    applied: list[str] = []

    def mutate(queue_doc: dict[str, Any]) -> None:
        existing = {
            str(command.get("id") or ""): command
            for command in queue_doc.get("commands", [])
            if isinstance(command, dict)
        }
        for worker in block.get("worker_entries") or []:
            command_id = str(worker.get("command_id") or "").strip()
            if not command_id:
                continue
            command = existing.get(command_id)
            action = prompt_summary(str(worker.get("prompt") or ""))
            inputs = normalize_list_field(str(worker.get("required_inputs") or ""))
            if plan_file and plan_file not in inputs:
                inputs.insert(0, plan_file)
            payload = {
                "id": command_id,
                "action": action,
                "owner_agent": str(worker.get("name") or "").strip(),
                "priority": priority_from_dispatch(block, priority),
                "status": str((command or {}).get("status") or "open"),
                "required_inputs": inputs,
                "expected_outputs": normalize_list_field(str(worker.get("expected_outputs") or "")),
                "depends_on": normalize_list_field(str(worker.get("depends_on") or "")),
                "parallel_group": "" if str(worker.get("parallel_group") or "").strip().lower() in {"none", "-"} else str(worker.get("parallel_group") or "").strip(),
                "display_summary": action,
                "why_now": f"Generated from leader dispatch. {next_turn_expects}".strip(),
                "done_when": next_turn_expects or "Return a valid WORKER RESULT block with evidence paths and blockers.",
                "requires_vote": bool((command or {}).get("requires_vote", False)),
                "vote_id": str((command or {}).get("vote_id") or ""),
                "risk_level": str(fields.get("risk_level") or (command or {}).get("risk_level") or "medium").lower(),
                "created_at": str((command or {}).get("created_at") or timestamp),
                "updated_at": timestamp,
                "notes": "Applied from LEADER DISPATCH block by scripts.commands.review.leader_dispatch.",
            }
            if command is None:
                queue_doc.setdefault("commands", []).append(payload)
            else:
                command.update(payload)
            applied.append(command_id)

    mutate_command_queue(root, mutate)
    if applied:
        append_agent_event(
            root,
            "leader_dispatch_apply",
            "director",
            status="waiting",
            task=f"Applied leader dispatch to {len(applied)} command(s).",
            stage="leader_dispatch",
            outputs=["state/command_queue.json"],
            notes=", ".join(applied),
        )
        refresh_report_index(root)
    return applied


def dispatch_parallel_groups(block: dict[str, Any]) -> list[str]:
    groups = {
        str(worker.get("parallel_group") or "").strip()
        for worker in block.get("worker_entries") or []
    }
    return sorted(
        group for group in groups
        if group and group.lower() not in {"none", "-"}
    )


def write_parallel_prompts_for_groups(
    root: Path,
    groups: list[str],
    *,
    max_agents: int,
    prompt_dir: str,
) -> list[dict[str, str]]:
    written: list[dict[str, str]] = []
    for group in groups:
        queue = load_command_queue(root)
        commands = select_parallel_commands(root, queue, max_agents=max_agents, group=group)
        if len(commands) < 2:
            continue
        prompt_paths: list[Path] = []
        for command in commands:
            path = write_prompt(root, command, prompt_dir)
            mark_dispatched(root, command, path)
            prompt_paths.append(path)
            written.append({
                "command_id": str(command.get("id") or ""),
                "parallel_group": group,
                "prompt": path.relative_to(root).as_posix(),
            })
        record_parallel_dispatch_plan(root, commands, prompt_paths)
    return written


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Parse and validate LEADER DISPATCH blocks.")
    sub = parser.add_subparsers(dest="command", required=True)

    parse = sub.add_parser("parse", help="Parse dispatch blocks and print JSON.")
    parse.add_argument("--file", default="-", help="Input file, or '-' for stdin.")

    validate = sub.add_parser("validate", help="Validate dispatch block structure.")
    validate.add_argument("--file", default="-", help="Input file, or '-' for stdin.")
    validate.add_argument("--allow-empty", action="store_true")
    validate.add_argument("--allow-multiple", action="store_true")
    validate.add_argument("--json", action="store_true")

    apply = sub.add_parser("apply", help="Apply a dispatch_workers block to state/command_queue.json.")
    apply.add_argument("--project", required=True)
    apply.add_argument("--file", default="-", help="Input file, or '-' for stdin.")
    apply.add_argument("--priority", choices=["high", "medium", "low"], help="Override generated command priority.")
    apply.add_argument("--write-parallel-prompts", action="store_true", help="After applying, write prompts for safe parallel groups and mark them in progress.")
    apply.add_argument("--max-agents", type=int, default=4, help="Maximum agents per parallel group when --write-parallel-prompts is used.")
    apply.add_argument("--prompt-dir", default="state/orchestrator_prompts")
    apply.add_argument("--json", action="store_true")

    return parser.parse_args()


def main() -> int:
    args = parse_args()
    text = read_input(args.file)

    if args.command == "parse":
        print(json.dumps({"blocks": parse_leader_dispatch_blocks(text)}, indent=2, ensure_ascii=False))
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
            print(f"valid leader dispatch: {len(blocks)} block(s)")
        return 0 if not errors else 1

    if args.command == "apply":
        blocks, errors = validate_text(text)
        if errors:
            for error in errors:
                print(f"error: {error}", file=sys.stderr)
            return 1
        try:
            root = project_root(args.project)
            applied = apply_dispatch_block(root, blocks[0], priority=args.priority)
            groups = dispatch_parallel_groups(blocks[0])
            written_prompts = (
                write_parallel_prompts_for_groups(
                    root,
                    groups,
                    max_agents=args.max_agents,
                    prompt_dir=args.prompt_dir,
                )
                if args.write_parallel_prompts
                else []
            )
        except HarnessError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        result = {
            "project": args.project,
            "applied_commands": applied,
            "parallel_groups": groups,
            "written_prompts": written_prompts,
        }
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            print(f"applied leader dispatch commands: {len(applied)}")
            for command_id in applied:
                print(command_id)
            for prompt in written_prompts:
                print(f"wrote parallel prompt: {prompt['command_id']} -> {prompt['prompt']}")
            for group in groups:
                print(
                    "parallel hint: "
                    f"python -m scripts.commands.agents.agent_orchestrator parallel "
                    f"--project {args.project} --group {group} --max-agents {len(applied)}"
                )
                if written_prompts:
                    print(
                        "inspect prepared hint: "
                        f"python -m scripts.commands.agents.agent_orchestrator run-prepared "
                        f"--project {args.project} --group {group} --dry-run"
                    )
                    print(
                        "run prepared hint: "
                        f"python -m scripts.commands.agents.agent_orchestrator run-prepared "
                        f"--project {args.project} --group {group} "
                        "--runner-command \"<agent-cli> --prompt-file {prompt_file}\""
                    )
        return 0

    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
