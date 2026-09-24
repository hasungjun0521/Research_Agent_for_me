#!/usr/bin/env python3
"""Turn reviewer findings into concrete revision tasks."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from scripts.harness.state import (
    HarnessError,
    append_agent_event,
    mutate_command_queue,
    now_iso,
    project_root,
    update_agent_status,
)
from scripts.harness.workflow_hooks import refresh_report_index

RISK_WORDS = ("missing", "weak", "unclear", "unsupported", "concern", "risk", "limitation", "fails", "insufficient")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert review artifacts into revision tasks.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--enqueue", action="store_true")
    parser.add_argument("--max-tasks", type=int, default=8)
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def source_files(root: Path) -> list[Path]:
    files = [
        root / "07_reviews" / "critic_comments.md",
        root / "07_reviews" / "reviewer_attack_matrix.md",
        root / "07_reviews" / "revision_plan.md",
    ]
    form_dir = root / "07_reviews" / "form_reviews"
    if form_dir.is_dir():
        files.extend(sorted(path for path in form_dir.glob("*.md") if path.name != "README.md"))
    return files


def clean_task_text(line: str) -> str:
    text = re.sub(r"^\s*[-*]\s+", "", line.strip())
    text = re.sub(r"^\|", "", text).strip()
    text = " ".join(part.strip(" `") for part in text.split("|") if part.strip())
    return re.sub(r"\s+", " ", text).strip()


def task_owner(text: str) -> str:
    lower = text.lower()
    if any(word in lower for word in ("experiment", "baseline", "ablation", "dataset", "metric", "result")):
        return "experiment_designer/data_analyst"
    if any(word in lower for word in ("writing", "clarify", "abstract", "introduction", "related", "limitation")):
        return "writing_agent"
    if any(word in lower for word in ("code", "implementation", "bug", "reproduce")):
        return "code_agent"
    return "director"


def task_priority(text: str) -> str:
    lower = text.lower()
    if any(word in lower for word in ("unsupported", "missing", "fatal", "major", "high")):
        return "high"
    if any(word in lower for word in ("weak", "unclear", "concern")):
        return "medium"
    return "low"


def extract_tasks(root: Path, max_tasks: int) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in source_files(root):
        text = read_text(path)
        if not text:
            continue
        for line in text.splitlines():
            lower = line.lower()
            if not any(word in lower for word in RISK_WORDS):
                continue
            task = clean_task_text(line)
            if len(task) < 20 or task.lower() in seen:
                continue
            seen.add(task.lower())
            task_id = f"rev_{len(tasks) + 1:03d}"
            tasks.append({
                "id": task_id,
                "source": path.relative_to(root).as_posix(),
                "action": f"Resolve reviewer risk: {task[:180]}",
                "owner_agent": task_owner(task),
                "priority": task_priority(task),
                "status": "open",
                "required_inputs": [path.relative_to(root).as_posix(), "09_report/results/claim_evidence.csv"],
                "expected_outputs": ["07_reviews/revision_plan.md", "09_report/paper/main.tex"],
                "why_now": "Reviewer-facing risks should become explicit revision work instead of passive notes.",
                "done_when": "The risk has evidence, a paper revision, or a documented limitation/rejection.",
            })
            if len(tasks) >= max_tasks:
                return tasks
    return tasks


def write_tasks(root: Path, tasks: list[dict[str, Any]]) -> tuple[Path, Path]:
    json_path = root / "07_reviews" / "revision_tasks.json"
    md_path = root / "07_reviews" / "revision_tasks.md"
    json_path.write_text(json.dumps({"project": root.name, "generated_at": now_iso(), "tasks": tasks}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [
        "# Revision Tasks",
        "",
        "| ID | Priority | Owner | Action | Source |",
        "| --- | --- | --- | --- | --- |",
    ]
    for task in tasks:
        lines.append(f"| `{task['id']}` | {task['priority']} | `{task['owner_agent']}` | {task['action']} | `{task['source']}` |")
    md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return json_path, md_path


def enqueue_tasks(root: Path, tasks: list[dict[str, Any]]) -> list[str]:
    added: list[str] = []

    def mutate(queue: dict[str, Any]) -> None:
        existing = {command.get("id") for command in queue.get("commands", [])}
        timestamp = now_iso()
        for task in tasks:
            command_id = task["id"]
            if command_id in existing:
                continue
            queue["commands"].append({
                **task,
                "display_summary": task["action"],
                "created_at": timestamp,
                "updated_at": timestamp,
                "notes": "Generated by scripts.commands.review.review_to_revision.",
            })
            added.append(command_id)

    mutate_command_queue(root, mutate)
    return added


def sync_revision_lifecycle(root: Path, tasks: list[dict[str, Any]], added: list[str], outputs: list[str]) -> None:
    status = "waiting"
    task = f"Generated {len(tasks)} reviewer revision task(s)."
    note = (
        f"Enqueued revision commands: {', '.join(added)}."
        if added
        else "Revision tasks were generated; no new command queue entries were added."
    )
    update_agent_status(
        root,
        "critic",
        status,
        task=task,
        stage="review_to_revision",
        outputs=outputs,
        notes=note,
        append_note=True,
    )
    append_agent_event(
        root,
        "review_to_revision",
        "critic",
        status=status,
        task=task,
        stage="review_to_revision",
        outputs=outputs,
        notes=note,
    )


def main() -> int:
    args = parse_args()
    try:
        root = project_root(args.project)
        tasks = extract_tasks(root, args.max_tasks)
        json_path, md_path = write_tasks(root, tasks)
        added = enqueue_tasks(root, tasks) if args.enqueue else []
        outputs = [json_path.relative_to(root).as_posix(), md_path.relative_to(root).as_posix()]
        if args.enqueue:
            outputs.append("state/command_queue.json")
        sync_revision_lifecycle(root, tasks, added, outputs)
        refresh_report_index(root)
        payload = {
            "project": args.project,
            "task_count": len(tasks),
            "added": added,
            "json_path": json_path.relative_to(root).as_posix(),
            "markdown_path": md_path.relative_to(root).as_posix(),
            "tasks": tasks,
        }
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(f"revision tasks: {len(tasks)} -> {json_path.relative_to(root)}")
            if added:
                print(f"enqueued: {', '.join(added)}")
        return 0
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
