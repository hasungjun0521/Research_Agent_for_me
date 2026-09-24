#!/usr/bin/env python3
"""Diagnose stale or inconsistent project file state."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.harness.project_diagnostics import build_diagnostics, render_state_doctor
from scripts.harness.command_mirror import sync_next_actions
from scripts.harness.state import (
    HarnessError,
    append_agent_event,
    load_command_queue,
    project_root,
    update_agent_status,
    validate_agent_messages_doc,
    validate_agent_status_doc,
    validate_agent_votes_doc,
    validate_baseline_registry_doc,
    validate_command_queue_doc,
    validate_gpu_queue_doc,
    validate_loop_summary_doc,
    validate_pattern_memory_doc,
    validate_ralph_loop_doc,
)
from scripts.harness.state_io import locked_state_file, quarantine_corrupt_json
from scripts.harness.workflow_hooks import refresh_report_index
from scripts.commands.projects.project_health import enqueue_suggestions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Diagnose whether project file state is missing, stale, or contradictory "
            "without opening the dashboard."
        )
    )
    parser.add_argument("--project", required=True)
    parser.add_argument("--agent", default="director")
    parser.add_argument("--write-report", action="store_true", help="Write state/state_doctor.md.")
    parser.add_argument("--repair", action="store_true", help="Create missing optional diagnostic output placeholders.")
    parser.add_argument(
        "--dry-run-repair",
        action="store_true",
        help="Preview missing starter files that --repair would create without writing files.",
    )
    parser.add_argument(
        "--enqueue-suggestions",
        action="store_true",
        help="Add suggested doctor actions to state/command_queue.json when not already present.",
    )
    parser.add_argument(
        "--dry-run-enqueue",
        action="store_true",
        help="Preview suggested command_queue entries without writing them.",
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def corrupt_json_reason(path: Path) -> str:
    """Return the parse error for an existing-but-corrupt JSON file, else an empty string."""
    if not path.is_file():
        return ""
    try:
        json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except json.JSONDecodeError as exc:
        return str(exc)
    except OSError:
        return ""
    return ""


def validate_template_json(relative: str, content: str) -> list[str]:
    validators = {
        "state/command_queue.json": validate_command_queue_doc,
        "state/agent_status.json": validate_agent_status_doc,
        "state/agent_messages.json": validate_agent_messages_doc,
        "state/agent_votes.json": validate_agent_votes_doc,
        "state/loop_summary.json": validate_loop_summary_doc,
        "state/pattern_memory.json": validate_pattern_memory_doc,
        "state/gpu_experiment_queue.json": validate_gpu_queue_doc,
        "state/ralph_loop.json": validate_ralph_loop_doc,
        "08_baselines/baseline_registry.json": validate_baseline_registry_doc,
    }
    if not relative.endswith(".json"):
        return []
    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        return [f"{relative}: invalid JSON repair starter: {exc.msg}"]
    validator = validators.get(relative)
    if not validator:
        return []
    try:
        return [f"{relative}: {warning}" for warning in validator(data)]
    except HarnessError as exc:
        return [f"{relative}: {exc}"]


def repair_placeholders(root: Path, *, dry_run: bool = False) -> tuple[list[str], list[str]]:
    created: list[str] = []
    repair_errors: list[str] = []
    template_repair_relatives = [
        "HANDOFF.md",
        "state/current_state.md",
        "state/agent_memory.md",
        "state/next_actions.md",
        "state/open_questions.md",
        "state/command_queue.json",
        "state/agent_status.json",
        "state/agent_messages.json",
        "state/agent_votes.json",
        "state/loop_summary.json",
        "state/pattern_memory.json",
        "state/gpu_experiment_queue.json",
        "state/ralph_loop.json",
        "08_baselines/baseline_registry.json",
    ]
    template_root = root.parent / "template"
    if root.name != "template" and template_root.is_dir():
        for relative in template_repair_relatives:
            source = template_root / relative
            target = root / relative
            corrupt_reason = corrupt_json_reason(target) if relative.endswith(".json") else ""
            if (target.exists() and not corrupt_reason) or not source.is_file():
                continue
            content = source.read_text(encoding="utf-8", errors="replace")
            warnings = validate_template_json(relative, content.replace("{{PROJECT_NAME}}", root.name))
            if warnings:
                repair_errors.extend(warnings)
                continue
            if not dry_run:
                if corrupt_reason:
                    try:
                        with locked_state_file(target):
                            quarantine_corrupt_json(target, corrupt_reason)
                            write_text(target, content.replace("{{PROJECT_NAME}}", root.name))
                    except HarnessError as exc:
                        repair_errors.append(f"{relative}: {exc}")
                        continue
                else:
                    write_text(target, content.replace("{{PROJECT_NAME}}", root.name))
            created.append(
                f"{relative} (quarantined corrupt original to .corrupt-*)" if corrupt_reason else relative
            )
    placeholders = {
        root / "00_brief" / "intake_wizard.md": "\n".join([
            "# Brief Intake Wizard",
            "",
            "Not yet generated.",
            "",
            "## Known Inputs",
            "",
            "- Research idea:",
            "- Target problem:",
            "- Dataset or environment:",
            "- Method family:",
            "- Baselines:",
            "- Metrics:",
            "- Compute constraints:",
            "",
            "## Missing Inputs",
            "",
            "- To be filled by brief intake.",
            "",
            "## Next Intake Action",
            "",
            "- Ask the user only for the missing fields that block director triage.",
            "",
        ]),
        root / "02_planning" / "experiment_plan.md": "\n".join([
            "# Experiment Plan",
            "",
            "Not yet generated.",
            "",
            "## Goal",
            "",
            "- To be filled before expensive runs.",
            "",
            "## Smoke Test",
            "",
            "- Command:",
            "- Expected output:",
            "- Check procedure:",
            "",
            "## Main Runs",
            "",
            "- Independent runs:",
            "- Dependencies:",
            "- GPU requirements:",
            "",
            "## Analysis Plan",
            "",
            "- Explain why performance improves, regresses, or stays flat.",
            "",
        ]),
        root / "03_experiments" / "data_roots.md": "\n".join([
            "# Data Roots",
            "",
            "Not yet generated.",
            "",
            "## Source Data",
            "",
            "- Dataset:",
            "- Root path:",
            "- Version or snapshot:",
            "- Split:",
            "- Access constraints:",
            "",
            "## Derived Data",
            "",
            "- Path:",
            "- Generation command:",
            "- Upstream source:",
            "- Validation check:",
            "",
        ]),
        root / "03_experiments" / "artifact_registry.csv": (
            "artifact_id,exp_id,kind,path,producer,created_at,description,check_procedure\n"
        ),
        root / "03_experiments" / "experiment_dag.json": json.dumps(
            {
                "schema_version": 1,
                "plans": [],
                "notes": "Starter DAG. Add smoke-first plans before expensive runs.",
            },
            indent=2,
        ) + "\n",
        root / "05_results" / "experiment_results.csv": (
            "experiment_id,claim_id,dataset,split,method,baseline_id,metric,value,delta,status,evidence,caveat\n"
        ),
        root / "05_results" / "experiment_journal.md": "\n".join([
            "# Experiment Journal",
            "",
            "Not yet generated.",
            "",
            "Each completed experiment should record why it was run, what happened, and why performance improved, regressed, or stayed flat.",
            "",
            "## Entries",
            "",
            "- To be filled through experiment completion or progress checkpoint hooks.",
            "",
        ]),
        root / "05_results" / "experiment_journal.csv": (
            "updated_at,experiment,rationale,dataset,method,baseline_id,result_summary,result_analysis,evidence,next_action\n"
        ),
        root / "05_results" / "claim_evidence_board.md": "\n".join([
            "# Claim Evidence Board",
            "",
            "Not yet generated.",
            "",
            "Use this working board to connect claims to experiment evidence before final export.",
            "",
        ]),
        root / "state" / "progress_hooks.jsonl": "",
        root / "state" / "sessions" / "progress_log.md": "\n".join([
            "# Progress Log",
            "",
            "Not yet generated.",
            "",
            "This file is the human-readable companion to `state/progress_hooks.jsonl`.",
            "Use progress checkpoints during long or multi-step work so future agents can resume from files.",
            "",
        ]),
        root / "state" / "project_health.md": "\n".join([
            "# Project Health Report",
            "",
            "Not yet generated.",
            "",
            "This is a working-state research progress health report, not a final paper report or dashboard.",
            "",
            "## Expected Contents",
            "",
            "- Overall status",
            "- Highest-priority blocker",
            "- Stale or missing research evidence",
            "- GPU queue gaps",
            "- Best next action",
            "- Suggested agent requests",
            "",
        ]),
        root / "state" / "state_doctor.md": "\n".join([
            "# State Doctor",
            "",
            "Not yet generated.",
            "",
            "This is a file-state consistency diagnosis for fresh agent continuation.",
            "",
            "## Expected Contents",
            "",
            "- Missing files",
            "- Contradictory queue/status state",
            "- Stale diagnostics",
            "- Safe repairs",
            "- Suggested routed actions",
            "",
        ]),
        root / "05_results" / "claim_graph.md": "\n".join([
            "# Claim Graph",
            "",
            "Not yet generated.",
            "",
            "## Claims",
            "",
            "- To be filled after claims or result rows exist.",
            "",
            "## Evidence",
            "",
            "- Link experiments, analyses, baselines, and robustness checks.",
            "",
            "## Weak Or Unsupported Claims",
            "",
            "- To be filled before strengthening writing.",
            "",
        ]),
        root / "05_results" / "claim_graph.json": json.dumps(
            {
                "schema_version": 1,
                "nodes": [],
                "edges": [],
                "notes": "Starter graph. Add nodes and edges when claims or evidence exist.",
            },
            indent=2,
        ) + "\n",
        root / "06_writing" / "terminology.md": "\n".join([
            "# Terminology",
            "",
            "pending_project_terms",
            "",
            "## Canonical Terms",
            "",
            "| Term | Definition | Use Instead Of | Notes |",
            "| --- | --- | --- | --- |",
            "| pending_project_terms | To be defined. | - | Replace before drafting. |",
            "",
        ]),
        root / "08_baselines" / "baseline_compare.md": "\n".join([
            "# Baseline Compare",
            "",
            "Not yet generated.",
            "",
            "## Source Snapshots",
            "",
            "- To be filled from 08_baselines/source_snapshots/<baseline_id>/.",
            "",
            "## Structure Comparison",
            "",
            "- Config layout:",
            "- Data pipeline:",
            "- Model or method modules:",
            "- Evaluation modules:",
            "- Scripts and entrypoints:",
            "",
            "## Project Code Implications",
            "",
            "- Update 08_baselines/code_structure_plan.md before shaping 04_code/src/.",
            "",
        ]),
        root / "08_baselines" / "code_structure_plan.md": "\n".join([
            "# Code Structure Plan",
            "",
            "Not yet generated.",
            "",
            "## Baseline-Informed Interfaces",
            "",
            "- Config:",
            "- Data loading:",
            "- Model or method:",
            "- Training or inference:",
            "- Evaluation:",
            "- Logging and artifacts:",
            "",
            "## Project Layout Decision",
            "",
            "- To be filled before substantial 04_code/src/ implementation.",
            "",
        ]),
        root / "07_reviews" / "agent_quality_audit.md": "\n".join([
            "# Agent Quality Audit",
            "",
            "Not yet generated.",
            "",
            "## Resumability",
            "",
            "- Can a fresh agent continue from files without chat history?",
            "",
            "## Evidence Coverage",
            "",
            "- Are outputs, blockers, decisions, and next actions saved in files?",
            "",
            "## Repair Actions",
            "",
            "- To be filled when prior agent work lacks durable evidence.",
            "",
        ]),
    }
    for path, content in placeholders.items():
        if not path.exists():
            relative = path.relative_to(root).as_posix()
            warnings = validate_template_json(relative, content)
            if warnings:
                repair_errors.extend(warnings)
                continue
            if not dry_run:
                write_text(path, content)
            created.append(relative)
    if not dry_run and (
        "state/command_queue.json" in created or "state/next_actions.md" in created
    ):
        try:
            sync_next_actions(root, load_command_queue(root))
            if "state/next_actions.md" not in created:
                created.append("state/next_actions.md")
        except HarnessError:
            pass
    return created, repair_errors


def run_audit(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    repaired, repair_errors = repair_placeholders(root, dry_run=args.dry_run_repair) if args.repair or args.dry_run_repair else ([], [])
    diagnostics = build_diagnostics(root, caller="state_doctor")
    diagnostics["repair_mode"] = "dry_run" if args.dry_run_repair else "apply" if args.repair else "none"
    diagnostics["repaired_count"] = len(repaired)
    diagnostics["repair_errors"] = repair_errors
    if repaired:
        diagnostics["repaired"] = repaired
    if args.dry_run_repair:
        diagnostics["repair_dry_run"] = True
    enqueued = []
    planned_enqueue = []
    enqueue_dry_run = args.dry_run_enqueue or args.dry_run_repair
    if args.enqueue_suggestions or args.dry_run_enqueue:
        enqueued, planned_enqueue = enqueue_suggestions(
            root,
            diagnostics,
            dry_run=enqueue_dry_run,
            id_prefix="doctor",
            source_label="state doctor",
        )
        diagnostics["planned_enqueue_commands"] = planned_enqueue
        if not enqueue_dry_run:
            diagnostics["enqueued_commands"] = enqueued
    content = render_state_doctor(diagnostics)
    write_state = (args.write_report or args.repair) and not args.dry_run_repair
    if write_state:
        write_text(root / "state" / "state_doctor.md", content)
    outputs = ["state/state_doctor.md"] if write_state else []
    outputs.extend(item for item in repaired if item not in outputs)
    if args.dry_run_repair:
        outputs = []
    if enqueued and not enqueue_dry_run:
        outputs.extend(["state/command_queue.json", "state/next_actions.md"])
    if outputs:
        try:
            update_agent_status(
                root,
                args.agent,
                "done",
                task="Diagnose project state health.",
                stage="state doctor",
                outputs=outputs,
                notes=(
                    f"State doctor found {diagnostics['counts']['issues']} issue(s); "
                    f"enqueued {len(enqueued)} suggestion(s)."
                ),
            )
        except HarnessError:
            pass
        append_agent_event(
            root,
            "state_doctor",
            args.agent,
            status="done",
            task="Diagnose project state health.",
            stage="state doctor",
            outputs=outputs,
            notes=(
                f"State doctor overall={diagnostics['overall']} score={diagnostics['score']}; "
                f"enqueued {len(enqueued)} suggestion(s)."
            ),
        )
        refresh_report_index(root)
    if args.json:
        print(json.dumps(diagnostics, indent=2, ensure_ascii=False))
    else:
        print(content, end="")
    return 0


def main() -> int:
    from scripts.commands.projects.projects import main as projects_main
    if len(sys.argv) < 2 or sys.argv[1] != "doctor":
        # Note: state_doctor was actually a child of doctor in v9 plan
        # but in v8 it's its own command.
        # However, for smoke_test to work with consolidated projects.py:
        if len(sys.argv) > 1 and sys.argv[1] == "--project":
            # Direct call, not a subcommand yet.
            pass
    return run_audit(parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
