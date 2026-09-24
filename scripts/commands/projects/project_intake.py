#!/usr/bin/env python3
"""Initialize a research project from a compact intake brief."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from scripts.harness.data_roots import sync_dataset_to_data_roots
from scripts.harness.state import (
    HarnessError,
    append_agent_event,
    atomic_write_json,
    load_command_queue,
    load_json,
    load_loop_summary,
    now_iso,
    project_root,
    update_agent_status,
    write_command_queue,
    write_loop_summary,
)
from scripts.harness.workflow_hooks import refresh_report_index


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply a researcher-friendly project intake brief.")
    sub = parser.add_subparsers(dest="command", required=True)

    apply_cmd = sub.add_parser("apply", help="Write the initial brief, registries, and intake summary.")
    apply_cmd.add_argument("--project", required=True)
    apply_cmd.add_argument("--agent", default="motivation_planner")
    apply_cmd.add_argument("--research-question", required=True)
    apply_cmd.add_argument("--motivation", required=True)
    apply_cmd.add_argument("--contribution", required=True)
    apply_cmd.add_argument("--claim-id", default="claim_001")
    apply_cmd.add_argument("--target-venue", default="")
    apply_cmd.add_argument("--compute-budget", default="")
    apply_cmd.add_argument("--dataset-id", default="")
    apply_cmd.add_argument("--dataset-name", default="")
    apply_cmd.add_argument("--dataset-source", default="")
    apply_cmd.add_argument("--dataset-split", default="")
    apply_cmd.add_argument("--metric-id", default="")
    apply_cmd.add_argument("--metric-name", default="")
    apply_cmd.add_argument("--metric-direction", "--direction", choices=["higher", "lower", "target", "none"], default="")
    apply_cmd.add_argument("--metric-definition", default="")
    apply_cmd.add_argument("--force", action="store_true", help="Overwrite starter brief files even when they already contain text.")

    return parser.parse_args()


def is_starter_text(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return True
    starter_markers = (
        "{{PROJECT_NAME}}",
        "Not yet",
        "Describe the question",
        "Use this file",
        "List current",
        "Replace this starter",
    )
    return any(marker in stripped for marker in starter_markers)


def write_markdown(path: Path, content: str, *, force: bool) -> None:
    if path.exists() and not force and not is_starter_text(path.read_text(encoding="utf-8", errors="replace")):
        raise HarnessError(f"Refusing to overwrite non-starter file without --force: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def upsert_registry(root: Path, kind: str, item: dict[str, Any]) -> None:
    if not item.get("id"):
        return
    key = "datasets" if kind == "dataset" else "metrics"
    path = root / "03_experiments" / f"{kind}_registry.json"
    data = load_json(path, fallback={"project": root.name, "schema_version": 1, "last_updated": "", key: []})
    rows = data.setdefault(key, [])
    timestamp = now_iso()
    for existing in rows:
        if existing.get("id") == item["id"]:
            existing.update({field: value for field, value in item.items() if value not in ("", [], None)})
            existing["updated_at"] = timestamp
            break
    else:
        item["created_at"] = timestamp
        item["updated_at"] = timestamp
        rows.append(item)
    data["last_updated"] = timestamp
    atomic_write_json(path, data)


def project_display_name(root: Path) -> str:
    return "{{PROJECT_NAME}}" if root.name == "template" else root.name


def is_local_absolute_reference(value: str) -> bool:
    stripped = str(value or "").strip()
    if not stripped:
        return False
    return stripped.startswith(("/", "~")) or (
        len(stripped) >= 3 and stripped[1] == ":" and stripped[2] in {"\\", "/"}
    )


def markdown_cell(value: str) -> str:
    return value.replace("|", "\\|")


def write_data_roots_seed(root: Path, args: argparse.Namespace) -> None:
    if not (args.dataset_id or args.dataset_name or args.dataset_source or args.dataset_split):
        return
    data_id = args.dataset_id or args.dataset_name or "intake_dataset"
    sync_dataset_to_data_roots(
        root,
        {
            "id": data_id,
            "name": args.dataset_name or data_id,
            "source": args.dataset_source,
            "split": args.dataset_split,
            "status": "candidate",
        },
        producer="project_intake",
        used_by=["exp_001"],
        notes="seeded from project intake; confirm checksum/version before expensive runs",
        update_existing=False,
    )


def write_working_claim_seed(root: Path, args: argparse.Namespace, *, force: bool) -> None:
    write_markdown(
        root / "05_results" / "claim_evidence_board.md",
        "\n".join([
            "# Claim-Evidence Board",
            "",
            f"- Project: `{project_display_name(root)}`",
            "- Mode: working claim seed from project intake",
            "",
            "## Claims",
            "",
            "| Claim ID | Status | Evidence | Next Needed |",
            "| --- | --- | --- | --- |",
            (
                f"| `{markdown_cell(args.claim_id)}` | untested | `02_planning/intake_summary.md` | "
                "Run literature review, preregister exp_001, and ingest result evidence. |"
            ),
            "",
            "## Export Rule",
            "",
            "- Do not export this claim to `09_report/results/claim_evidence.csv` until the status is stable enough for reader-facing review.",
        ]),
        force=force,
    )


def append_markdown_section(path: Path, title: str, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    separator = "\n" if existing and not existing.endswith("\n") else ""
    block = "\n".join(["", f"## {title}", "", *lines]).rstrip() + "\n"
    path.write_text(existing + separator + block, encoding="utf-8")


def sync_file_state_after_intake(root: Path, args: argparse.Namespace) -> None:
    timestamp = now_iso()
    queue = load_command_queue(root)
    for command in queue.get("commands", []):
        command_id = str(command.get("id") or "")
        if command_id == "cmd_001":
            command["status"] = "done"
            command["updated_at"] = timestamp
            command["notes"] = "Project intake supplied the initial research brief."
        elif command_id == "cmd_002" and str(command.get("status") or "").lower() in {"deferred", "blocked"}:
            command["status"] = "open"
            command["updated_at"] = timestamp
            command["notes"] = "Brief is available; director triage can run next."
    write_command_queue(root, queue)

    summary = load_loop_summary(root)
    summary["project"] = root.name
    summary["status"] = "planned"
    summary["goal"] = "Turn the project intake into a concrete research plan."
    summary["summary"] = (
        "Project intake seeded the research question, motivation, contribution, "
        "working claim, and optional dataset/metric metadata. Director triage is next."
    )
    summary["last_updated"] = timestamp
    summary["results"] = [{
        "title": "Project intake applied",
        "status": "done",
        "summary": f"Seeded claim `{args.claim_id}` and starter brief files from user intake.",
        "evidence_files": [
            "00_brief/research_question.md",
            "00_brief/motivation.md",
            "00_brief/contribution_candidates.md",
            "02_planning/intake_summary.md",
            "05_results/claim_evidence_board.md",
        ],
        "updated_at": timestamp,
    }]
    summary["next_actions"] = [{
        "action": "Run director triage and choose the next research step.",
        "owner_agent": "director",
        "priority": "high",
        "expected_outputs": [
            "02_planning/director_plan.md",
            "state/command_queue.json",
            "HANDOFF.md",
        ],
        "display_summary": "Choose the next research step from the seeded brief.",
        "why_now": "The brief is now concrete enough to route literature, baseline, or experiment work.",
        "done_when": "Director plan and command queue identify the next owner and completion condition.",
        "created_at": timestamp,
    }]
    write_loop_summary(root, summary)

    append_markdown_section(
        root / "state" / "current_state.md",
        f"Project Intake Applied: {timestamp}",
        [
            f"- Research question: {args.research_question}",
            f"- First claim: `{args.claim_id}` - {args.contribution}",
            f"- Dataset: {args.dataset_name or args.dataset_id or 'to be selected'}",
            f"- Metric: {args.metric_name or args.metric_id or 'to be selected'}",
            "- Next: run director triage from the seeded brief.",
        ],
    )
    append_markdown_section(
        root / "state" / "agent_memory.md",
        f"Intake Memory: {timestamp}",
        [
            "- The initial brief was supplied through `project_intake.py apply`.",
            "- Do not ask the user to repeat the same research question before director triage.",
            "- Treat `02_planning/intake_summary.md` as the durable intake source.",
        ],
    )
    append_markdown_section(
        root / "HANDOFF.md",
        f"Latest Intake: {timestamp}",
        [
            f"- Research question: {args.research_question}",
            f"- First claim: `{args.claim_id}` - {args.contribution}",
            "- Completed starter command: `cmd_001`.",
            "- Next best action: run director triage from `02_planning/intake_summary.md`.",
        ],
    )
    missing_questions: list[str] = []
    if not args.dataset_id and not args.dataset_name:
        missing_questions.append("- Which dataset or data source should anchor the first experiment?")
    if not args.metric_id and not args.metric_name:
        missing_questions.append("- Which primary metric should decide success for the first experiment?")
    if missing_questions:
        append_markdown_section(root / "state" / "open_questions.md", f"Intake Open Questions: {timestamp}", missing_questions)


def sync_intake_agent(root: Path, args: argparse.Namespace) -> None:
    outputs = [
        "00_brief/research_question.md",
        "00_brief/motivation.md",
        "00_brief/contribution_candidates.md",
        "02_planning/intake_summary.md",
        "05_results/claim_evidence_board.md",
        "state/command_queue.json",
        "state/loop_summary.json",
        "HANDOFF.md",
    ]
    if args.dataset_id:
        outputs.extend([
            "03_experiments/dataset_registry.json",
            "03_experiments/data_roots.md",
        ])
    if args.metric_id:
        outputs.append("03_experiments/metric_registry.json")
    task = "Applied project intake and prepared director triage."
    notes = "Initial brief, claim seed, optional dataset/metric metadata, queue, loop summary, and handoff were updated."
    update_agent_status(
        root,
        args.agent,
        "waiting",
        task=task,
        stage="project_intake",
        outputs=outputs,
        notes=notes,
        append_note=True,
    )
    append_agent_event(
        root,
        "project_intake",
        args.agent,
        status="waiting",
        task=task,
        stage="project_intake",
        outputs=outputs,
        notes=notes,
    )


def apply_intake(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    if is_local_absolute_reference(args.dataset_source):
        raise HarnessError(
            "--dataset-source must not be a local absolute path. Store private "
            "paths in config/workspace_profile.local.json and put a stable URI here."
        )
    dataset_label = args.dataset_name or args.dataset_id or "to be selected"
    metric_label = args.metric_name or args.metric_id or "to be selected"

    write_markdown(
        root / "00_brief" / "research_question.md",
        "\n".join([
            "# Research Question",
            "",
            args.research_question,
            "",
            "## Evidence Needed",
            "",
            f"- Dataset or setting: {dataset_label}",
            f"- Primary metric: {metric_label}",
            "- Baselines and prior work must be registered before claims are strengthened.",
        ]),
        force=args.force,
    )
    write_markdown(
        root / "00_brief" / "motivation.md",
        "\n".join([
            "# Motivation",
            "",
            args.motivation,
            "",
            "## Target Reader",
            "",
            f"- Target venue: {args.target_venue or 'not specified'}",
            f"- Compute budget: {args.compute_budget or 'not specified'}",
        ]),
        force=args.force,
    )
    write_markdown(
        root / "00_brief" / "contribution_candidates.md",
        "\n".join([
            "# Contribution Candidates",
            "",
            "| Claim ID | Candidate Contribution | Status | Evidence Needed |",
            "| --- | --- | --- | --- |",
            (
                f"| `{markdown_cell(args.claim_id)}` | {markdown_cell(args.contribution)} | "
                "untested | literature support, preregistered experiment, result rows |"
            ),
        ]),
        force=args.force,
    )
    write_markdown(
        root / "02_planning" / "intake_summary.md",
        "\n".join([
            "# Project Intake Summary",
            "",
            f"- Research question: {args.research_question}",
            f"- Motivation: {args.motivation}",
            f"- First claim: `{args.claim_id}` - {args.contribution}",
            f"- Dataset: {dataset_label}",
            f"- Metric: {metric_label}",
            f"- Target venue: {args.target_venue or 'not specified'}",
            f"- Compute budget: {args.compute_budget or 'not specified'}",
            "",
            "## Next Workflow Steps",
            "",
            "1. Keep the working claim seed aligned with contribution candidates.",
            "2. Complete preregistration for `exp_001` before execution.",
            "3. Export final claim rows only after literature, experiment, and interpretation evidence are stable.",
        ]),
        force=True,
    )
    if args.dataset_id:
        upsert_registry(root, "dataset", {
            "id": args.dataset_id,
            "name": args.dataset_name or args.dataset_id,
            "status": "candidate",
            "source": args.dataset_source,
            "split": args.dataset_split,
            "preprocessing": "",
            "path": "",
            "checksum": "",
            "evidence_files": ["02_planning/intake_summary.md"],
            "aliases": [],
        })
    if args.metric_id:
        upsert_registry(root, "metric", {
            "id": args.metric_id,
            "name": args.metric_name or args.metric_id,
            "status": "candidate",
            "direction": args.metric_direction,
            "definition": args.metric_definition,
            "implementation": "",
            "evidence_files": ["02_planning/intake_summary.md"],
            "aliases": [],
        })
    write_data_roots_seed(root, args)
    write_working_claim_seed(root, args, force=args.force)
    sync_file_state_after_intake(root, args)
    sync_intake_agent(root, args)
    refresh_report_index(root)
    print("intake applied")
    print("02_planning/intake_summary.md")
    return 0


def main() -> int:
    args = parse_args()
    try:
        if args.command == "apply":
            return apply_intake(args)
        raise HarnessError(f"Unknown command: {args.command}")
    except (HarnessError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
