#!/usr/bin/env python3
"""Suggest or enqueue the next research workflow actions."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from scripts.harness.state import (
    HarnessError,
    append_agent_event,
    load_agent_messages,
    load_command_queue,
    mutate_agent_messages,
    mutate_command_queue,
    now_iso,
    project_root,
    update_agent_status,
)
from scripts.harness.workflow_hooks import refresh_report_index


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Plan the next automated research loop.")
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("plan", help="Print next actions without mutating state.")
    plan.add_argument("--project", required=True)
    plan.add_argument("--json", action="store_true")
    enqueue = sub.add_parser("enqueue", help="Add missing next actions to command_queue/messages.")
    enqueue.add_argument("--project", required=True)
    enqueue.add_argument("--max-actions", type=int, default=3)
    return parser.parse_args()


def read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [
            {str(key or "").strip(): str(value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle)
            if any(str(value or "").strip() for value in row.values())
        ]


def load_json(path: Path, fallback: Any) -> Any:
    if not path.is_file():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def action_score(action: dict[str, Any]) -> int:
    priority_score = {"high": 80, "medium": 50, "low": 20}.get(str(action.get("priority") or "").lower(), 30)
    text = " ".join(str(action.get(field) or "") for field in ("id", "action", "why_now", "done_when")).lower()
    risk_bonus = 0
    for token, value in (
        ("claim", 8),
        ("baseline", 8),
        ("reviewer", 10),
        ("unsupported", 15),
        ("missing", 12),
        ("robustness", 8),
        ("evidence", 8),
        ("repo", 6),
    ):
        if token in text:
            risk_bonus += value
    output_bonus = min(10, len(action.get("expected_outputs", []) or []) * 2)
    return min(100, priority_score + risk_bonus + output_bonus)


def rank_actions(actions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for action in actions:
        enriched = dict(action)
        enriched["risk_score"] = action_score(enriched)
        ranked.append(enriched)
    return sorted(
        ranked,
        key=lambda item: (
            {"high": 0, "medium": 1, "low": 2}.get(str(item.get("priority") or "medium").lower(), 1),
            -int(item.get("risk_score") or 0),
            str(item.get("id") or ""),
        ),
    )


def next_actions(root: Path) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    question = read_text(root / "00_brief" / "research_question.md").strip()
    if "not yet" in question.lower() or len(question) < 80:
        actions.append({
            "id": "auto_refine_research_question",
            "owner_agent": "motivation_planner",
            "priority": "high",
            "action": "Refine the research question into a falsifiable, venue-ready problem statement.",
            "required_inputs": ["00_brief/research_question.md", "00_brief/motivation.md"],
            "expected_outputs": ["00_brief/research_question.md", "00_brief/problem_statement.md", "00_brief/contribution_candidates.md"],
            "why_now": "The project cannot choose valid experiments or baselines until the research question is specific.",
            "done_when": "The question states the task, target setting, expected contribution, and what evidence would validate it.",
        })

    related_work = read_text(root / "01_literature" / "related_work_matrix.md").strip()
    if len(related_work) < 300:
        actions.append({
            "id": "auto_build_literature_matrix",
            "owner_agent": "literature_reviewer",
            "priority": "high",
            "action": "Build the related-work matrix and identify required baseline comparisons.",
            "required_inputs": ["01_literature/papers.bib", "01_literature/paper_notes/", "08_baselines/baseline_registry.json"],
            "expected_outputs": ["01_literature/related_work_matrix.md", "01_literature/gap_analysis.md", "08_baselines/prior_research_inventory.md"],
            "why_now": "Baseline and novelty decisions are unsafe without a literature-grounded comparison map.",
            "done_when": "The matrix names key papers, limitations, expected baselines, and repo availability decisions.",
        })

    claim_rows = csv_rows(root / "09_report" / "results" / "claim_evidence.csv")
    if not claim_rows:
        actions.append({
            "id": "auto_define_claim_graph",
            "owner_agent": "experiment_designer",
            "priority": "high",
            "action": "Create stable claim IDs and map the first experiment to a testable claim.",
            "required_inputs": ["00_brief/contribution_candidates.md", "03_experiments/experiment_registry.yaml"],
            "expected_outputs": [
                "05_results/claim_evidence_board.md",
                "03_experiments/exp_001/preregistration.md",
            ],
            "why_now": "Experiments and result tables need claim IDs before evidence can be checked automatically.",
            "done_when": "At least one working claim has a claim_id, status, evidence need, and linked experiment ID; export final claim rows only when stable.",
        })

    baseline_registry = load_json(root / "08_baselines" / "baseline_registry.json", {"baselines": []})
    missing_repo = [
        baseline for baseline in baseline_registry.get("baselines", [])
        if isinstance(baseline, dict)
        and baseline.get("status") not in {"rejected", "deprecated"}
        and not baseline.get("repo_url")
        and not baseline.get("source_path")
    ]
    if missing_repo:
        actions.append({
            "id": "auto_discover_baseline_repos",
            "owner_agent": "literature_reviewer",
            "priority": "high",
            "action": "Find official or credible repositories for baseline papers without source links.",
            "required_inputs": ["08_baselines/baseline_registry.json", "08_baselines/repo_discovery_plan.md"],
            "expected_outputs": ["08_baselines/baseline_registry.json", "08_baselines/repo_discovery_plan.md", "state/agent_messages.json"],
            "why_now": "The code agent should not reimplement baselines from memory when source code may exist.",
            "done_when": "Each baseline has repo_url/source_path or a documented rejected/deferred reason.",
        })

    runnable_without_results = [
        baseline for baseline in baseline_registry.get("baselines", [])
        if isinstance(baseline, dict)
        and baseline.get("status") in {"source_found", "porting", "runnable"}
        and baseline.get("source_path")
        and not baseline.get("result_paths")
    ]
    if runnable_without_results:
        actions.append({
            "id": "auto_smoke_baseline_adapters",
            "owner_agent": "code_agent",
            "priority": "medium",
            "action": "Run smoke checks for cloned baseline adapters before full GPU reproduction.",
            "required_inputs": ["08_baselines/baseline_registry.json", "08_baselines/structure_reports/"],
            "expected_outputs": ["08_baselines/run_scripts/", "03_experiments/exp_001/run_log.md"],
            "why_now": "Full baseline reproduction should only start after import/config/source checks pass.",
            "done_when": "Each selected baseline has a smoke command, smoke result, and recorded next action.",
        })

    final_result_rows = csv_rows(root / "09_report" / "results" / "experiment_results.csv")
    working_result_rows = csv_rows(root / "05_results" / "experiment_results.csv")
    result_rows = final_result_rows or working_result_rows
    if result_rows and not read_text(root / "05_results" / "statistical_robustness.md").strip():
        result_input = "09_report/results/experiment_results.csv" if final_result_rows else "05_results/experiment_results.csv"
        actions.append({
            "id": "auto_run_robustness_checks",
            "owner_agent": "data_analyst",
            "priority": "medium",
            "action": "Run robustness and data-quality checks before strengthening result claims.",
            "required_inputs": [result_input, "03_experiments/exp_001/results/"],
            "expected_outputs": ["05_results/statistical_robustness.md"],
            "why_now": "Result rows exist and need uncertainty, sanity checks, and failure accounting before claim strengthening.",
            "done_when": "Working robustness checks include status, caveat, and next evidence needed for each claim; export final robustness rows only when stable.",
        })

    return rank_actions(actions)


def enqueue_actions(root: Path, actions: list[dict[str, Any]], max_actions: int) -> list[str]:
    selected = actions[:max_actions]
    queue = load_command_queue(root)
    existing = {command.get("id") for command in queue.get("commands", [])}
    added: list[str] = []
    selected_ids = {str(action.get("id") or "") for action in selected}
    brief_dependency = "auto_refine_research_question" if "auto_refine_research_question" in selected_ids else ""

    def action_dependencies(action: dict[str, Any]) -> list[str]:
        deps = [str(dep).strip() for dep in action.get("depends_on", []) if str(dep).strip()]
        action_id = str(action.get("id") or "")
        if brief_dependency and action_id != brief_dependency and brief_dependency not in deps:
            deps.append(brief_dependency)
        return deps

    def action_parallel_group(action: dict[str, Any]) -> str:
        if action_dependencies(action):
            return str(action.get("parallel_group") or "")
        return str(action.get("parallel_group") or "research_loop_auto")

    def mutate(queue_doc: dict[str, Any]) -> None:
        current = {command.get("id") for command in queue_doc.get("commands", [])}
        timestamp = now_iso()
        for action in selected:
            if action["id"] in current:
                continue
            queue_doc["commands"].append({
                "id": action["id"],
                "action": action["action"],
                "owner_agent": action["owner_agent"],
                "priority": action["priority"],
                "status": "open",
                "required_inputs": action["required_inputs"],
                "expected_outputs": action["expected_outputs"],
                "depends_on": action_dependencies(action),
                "parallel_group": action_parallel_group(action),
                "display_summary": action["action"],
                "why_now": action["why_now"],
                "done_when": action["done_when"],
                "risk_score": action.get("risk_score", 0),
                "created_at": timestamp,
                "updated_at": timestamp,
                "notes": "Generated by scripts.commands.research.research_loop.",
            })
            added.append(action["id"])

    mutate_command_queue(root, mutate)

    messages = load_agent_messages(root)
    message_existing = {message.get("id") for message in messages.get("messages", [])}

    def mutate_messages(message_doc: dict[str, Any]) -> None:
        timestamp = now_iso()
        for action in selected:
            message_id = f"loop_{action['id']}"
            if action["id"] in existing or message_id in message_existing:
                continue
            message_doc["messages"].append({
                "id": message_id,
                "from_agent": "director",
                "to_agent": action["owner_agent"],
                "kind": "handoff",
                "priority": action["priority"],
                "status": "open",
                "subject": action["action"],
                "body": f"{action['why_now']} Done when: {action['done_when']}",
                "related_command_id": action["id"],
                "related_claim_id": "",
                "related_exp_id": "exp_001" if "exp_001" in " ".join(action["expected_outputs"]) else "",
                "required_response": "Acknowledge the handoff and update command status before working.",
                "response": "",
                "created_at": timestamp,
                "updated_at": timestamp,
                "resolved_at": "",
            })

    mutate_agent_messages(root, mutate_messages)
    return added


def sync_research_loop_lifecycle(root: Path, added: list[str], actions: list[dict[str, Any]]) -> None:
    if not added:
        return
    selected = [action for action in actions if action.get("id") in set(added)]
    outputs = ["state/command_queue.json", "state/agent_messages.json"]
    for action in selected:
        for output in action.get("expected_outputs") or []:
            if output and output not in outputs:
                outputs.append(output)
    task = f"Enqueued research-loop actions: {', '.join(added)}."
    notes = "Research loop converted evidence gaps into command queue entries and agent handoff messages."
    update_agent_status(
        root,
        "director",
        "waiting",
        task=task,
        stage="research_loop_enqueue",
        outputs=outputs,
        notes=notes,
        append_note=True,
    )
    append_agent_event(
        root,
        "research_loop_enqueue",
        "director",
        status="waiting",
        task=task,
        stage="research_loop_enqueue",
        outputs=outputs,
        notes=notes,
    )


def main() -> int:
    args = parse_args()
    try:
        root = project_root(args.project)
        actions = next_actions(root)
        if args.command == "plan":
            if args.json:
                print(json.dumps({"project": args.project, "next_actions": actions}, indent=2))
            else:
                if not actions:
                    print("No automatic next actions.")
                for action in actions:
                    print(f"{action['id']}\t{action['priority']}\t{action['owner_agent']}\t{action['action']}")
            return 0
        if args.command == "enqueue":
            added = enqueue_actions(root, actions, args.max_actions)
            if added:
                sync_research_loop_lifecycle(root, added, actions)
                refresh_report_index(root)
            print(f"enqueued: {', '.join(added) if added else 'none'}")
            return 0
        raise HarnessError(f"Unknown command: {args.command}")
    except (HarnessError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
