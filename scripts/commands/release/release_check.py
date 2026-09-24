#!/usr/bin/env python3
"""Run the release-readiness gate for the research-agent harness."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

try:
    from scripts.harness import repo_root as harness_repo_root
    from scripts.harness.commands import python_module_command
except ModuleNotFoundError:
    from scripts.harness import repo_root as harness_repo_root
    from scripts.harness.commands import python_module_command

from scripts.commands.release.privacy_audit import audit_privacy


def repo_root() -> Path:
    return harness_repo_root()


def git_command(*args: str) -> list[str]:
    return ["git", "-c", f"safe.directory={repo_root()}", *args]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run harness release-readiness checks.")
    parser.add_argument("--project", default="template", help="Project to validate. Default: template.")
    parser.add_argument("--version", default="v8.0.0", help="Expected changelog release heading.")
    parser.add_argument("--skip-paper-build", action="store_true", help="Skip LaTeX paper build validation.")
    parser.add_argument(
        "--skip-verify-harness",
        action="store_true",
        help="Skip the full verify_harness.py suite. Intended only for fast local iteration.",
    )
    parser.add_argument(
        "--strict-template-state",
        action="store_true",
        help="Fail if projects/template contains generated runs, sessions, prompts, events, or lock files.",
    )
    parser.add_argument(
        "--include-dashboard",
        action="store_true",
        help="Include optional dashboard JavaScript syntax checks in the release gate.",
    )
    parser.add_argument("--json", action="store_true", help="Print a JSON summary.")
    return parser.parse_args()


def run_step(name: str, cmd: list[str]) -> dict[str, object]:
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(cmd, cwd=repo_root(), text=True, capture_output=True, env=env)
    return {
        "name": name,
        "cmd": cmd,
        "returncode": result.returncode,
        "stdout": result.stdout.rstrip(),
        "stderr": result.stderr.rstrip(),
        "ok": result.returncode == 0,
    }


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def generated_inventory_text(project_yaml: str) -> str:
    start_marker = "# PROJECT_INDEX:START"
    end_marker = "# PROJECT_INDEX:END"
    start = project_yaml.find(start_marker)
    end = project_yaml.find(end_marker)
    if start == -1 or end == -1 or end < start:
        return ""
    return project_yaml[start : end + len(end_marker)]


def publishable_paths() -> list[Path]:
    result = subprocess.run(
        git_command("ls-files", "--cached", "--others", "--exclude-standard"),
        cwd=repo_root(),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    paths: list[Path] = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        path = repo_root() / line
        if path.is_file():
            paths.append(path)
    return paths


def private_content_warnings() -> list[str]:
    root = repo_root()
    relative_paths = [path.relative_to(root).as_posix() for path in publishable_paths()]
    result = audit_privacy(root, relative_paths)
    return [f"{finding['path']} contains a private or local marker." for finding in result["findings"]]


def static_release_warnings(version: str) -> list[str]:
    root = repo_root()
    required_files = [
        "AGENTS.md",
        "README.md",
        "ARCHITECTURE.md",
        "CHANGELOG.md",
        "HANDOFF.md",
        "project.yaml",
        "pyproject.toml",
        "scripts/README.md",
        "scripts/commands/__init__.py",
        "scripts/commands/baselines/baseline_intake.py",
        "scripts/commands/baselines/baseline_library.py",
        "scripts/commands/experiments/experiment_complete.py",
        "scripts/commands/experiments/gpu_scheduler.py",
        "scripts/commands/experiments/result_ingest.py",
        "scripts/commands/projects/create_project.py",
        "scripts/commands/projects/import_research_repo.py",
        "scripts/commands/projects/migrate_project.py",
        "scripts/commands/projects/project_closeout.py",
        "scripts/commands/projects/project_intake.py",
        "scripts/commands/projects/project_index.py",
        "scripts/commands/projects/project_resume.py",
        "scripts/commands/release/workflow_audit.py",
        "scripts/commands/release/release_check.py",
        "scripts/commands/reports/artifact_packager.py",
        "scripts/commands/reports/resource_ledger.py",
        "scripts/commands/research/phase_gate.py",
        "scripts/harness/state.py",
        "scripts/harness/workflow_hooks.py",
        "scripts/harness/data_roots.py",
        "scripts/harness/experiment_registry.py",
        "scripts/harness/experiment_journal.py",
        "scripts/harness/report_lifecycle.py",
        "scripts/commands/release/verify_harness.py",
        "scripts/commands/release/smoke_test.py",
        "scripts/commands/review/leader_dispatch.py",
        "scripts/commands/review/progress_checkpoint.py",
        "scripts/commands/review/ralph_loop.py",
    ]
    warnings = [f"missing required release file: {path}" for path in required_files if not (root / path).is_file()]
    if f"## {version}" not in read(root / "CHANGELOG.md"):
        warnings.append(f"CHANGELOG.md is missing release heading: ## {version}")
    if "status-parallel" not in read(root / "CHANGELOG.md"):
        warnings.append("CHANGELOG.md should mention parallel agent orchestration.")
    if "dispatch --json" not in read(root / "CHANGELOG.md"):
        warnings.append("CHANGELOG.md should mention GPU dispatch JSON diagnostics.")
    if "--dry-run-repair" not in read(root / "CHANGELOG.md"):
        warnings.append("CHANGELOG.md should mention state doctor repair preview.")
    if "template-backed state doctor repair" not in read(root / "CHANGELOG.md"):
        warnings.append("CHANGELOG.md should mention template-backed state doctor repair.")
    if "command-queue mirror sync" not in read(root / "CHANGELOG.md"):
        warnings.append("CHANGELOG.md should mention state doctor repair command-queue mirror sync.")
    if "template-backed JSON repair validation" not in read(root / "CHANGELOG.md"):
        warnings.append("CHANGELOG.md should mention state doctor repair validation.")
    if "stale diagnostic reports" not in read(root / "CHANGELOG.md"):
        warnings.append("CHANGELOG.md should mention diagnostic staleness handling.")
    for relative, needle in (
        ("AGENTS.md", "scripts.commands.release.verify_harness"),
        ("AGENTS.md", "scripts.commands.experiments.gpu_scheduler dispatch"),
        ("AGENTS.md", "plan_diagnostics"),
        ("AGENTS.md", "scripts.commands.agents.agent_orchestrator parallel"),
        ("AGENTS.md", "scripts.commands.agents.agent_orchestrator status-parallel"),
        ("AGENTS.md", "scripts.commands.agents.agent_orchestrator run-prepared"),
        ("AGENTS.md", "scripts.commands.agents.agent_orchestrator finish-parallel"),
        ("AGENTS.md", "Proactively look for multi-agent parallelization"),
        ("AGENTS.md", "scripts.commands.review.progress_checkpoint record"),
        ("pyproject.toml", "project_index_check"),
        ("README.md", "scripts.commands.release.release_check"),
        ("README.md", "scripts.commands.experiments.gpu_scheduler dispatch"),
        ("README.md", "plan_diagnostics"),
        ("README.md", "scripts.commands.agents.agent_orchestrator run-prepared"),
        ("README.md", "scripts.commands.agents.agent_orchestrator status-parallel"),
        ("README.md", "scripts.commands.agents.agent_orchestrator finish-parallel"),
        ("README.md", "Do not wait for me to explicitly ask for multi-agent work"),
        ("README.md", "--all-prepared"),
        ("README.md", "scripts.commands.review.progress_checkpoint record"),
        ("README.md", "Preview state doctor repair"),
        ("README.md", "repair errors"),
        ("prompts/skills/privacy_publish_audit.md", "v8.0.0"),
        ("prompts/skills/state_doctor.md", "report the repair mode"),
        ("projects/template/README.md", "It must not invent research content"),
        ("projects/template/README.md", "repair errors"),
        ("scripts/README.md", "scripts.commands.release.release_check"),
        ("scripts/README.md", "--dry-run-repair"),
        ("scripts/README.md", "Repair output includes the repair mode"),
        ("scripts/README.md", "v8.0.0"),
        ("scripts/README.md", "scripts.commands.experiments.gpu_scheduler"),
        ("scripts/README.md", "list --json"),
        ("scripts/README.md", "plan_diagnostics"),
        ("scripts/README.md", "dispatch --json"),
        ("scripts/README.md", "dispatch --ids"),
        ("scripts/README.md", "scripts.commands.agents.agent_orchestrator parallel"),
        ("scripts/README.md", "scripts.commands.review.progress_checkpoint"),
        ("scripts/README.md", "scripts.commands.reports.artifact_packager"),
        ("scripts/README.md", "scripts.commands.projects.project_index"),
        ("project.yaml", "artifact_packager"),
        ("project.yaml", "result_ingest"),
        ("project.yaml", "parallel_agents"),
        ("project.yaml", "proactive_multi_agent"),
        ("project.yaml", "next --json"),
        ("project.yaml", "parallel --json"),
        ("project.yaml", "status-parallel"),
        ("project.yaml", "run-prepared"),
        ("project.yaml", "--all-prepared"),
        ("project.yaml", "finish-parallel"),
        ("project.yaml", "gpu_scheduler"),
        ("project.yaml", "list --json"),
        ("project.yaml", "plan_diagnostics"),
        ("project.yaml", "dispatch --json"),
        ("project.yaml", "dispatch --ids"),
        ("project.yaml", "gpu_monitor"),
        ("project.yaml", "progress_checkpoint"),
        ("project.yaml", "experiment_complete"),
        ("project.yaml", "artifact_registry"),
        ("project.yaml", "agent_runner_profiles"),
        ("project.yaml", "project_closeout"),
        ("project.yaml", "repo_discovery"),
        ("project.yaml", "baseline_sandbox"),
        ("project.yaml", "data_roots"),
        ("project.yaml", "experiment_journal"),
        ("project.yaml", "terminology"),
        ("project.yaml", "code_structure_plan"),
        ("project.yaml", "state_health"),
        ("project.yaml", "Preview state_doctor repairs"),
        ("project.yaml", "--dry-run-repair"),
        ("project.yaml", "repair_errors"),
        ("project.yaml", "template-backed continuity files"),
        ("project.yaml", "sync the human-readable next_actions mirror"),
        ("project.yaml", "brief_intake"),
        ("project.yaml", "experiment_planning"),
        ("project.yaml", "claim_graph"),
        ("project.yaml", "baseline_compare"),
        ("project.yaml", "agent_quality_audit"),
        ("project.yaml", "resource_ledger"),
        ("project.yaml", "dashboard_optional"),
        ("project.yaml", "report_index"),
        ("project.yaml", "include_report=True"),
        ("project.yaml", "include-dashboard"),
        ("HANDOFF.md", "scripts.commands.release.release_check"),
        ("scripts/commands/projects/project_closeout.py", "data_roots"),
        ("scripts/commands/projects/project_closeout.py", "experiment_journal"),
        ("scripts/commands/projects/project_closeout.py", "terminology"),
        ("scripts/commands/projects/validate_project.py", "working_artifact_warnings"),
        ("scripts/commands/projects/validate_project.py", "v6_research_surface_warnings"),
        ("scripts/commands/projects/validate_project.py", "state/project_health.md"),
        ("scripts/commands/projects/validate_project.py", "state/state_doctor.md"),
        ("scripts/commands/projects/validate_project.py", "pending_project_terms"),
        ("scripts/commands/projects/validate_project.py", "is_starter_text(data_roots_text)"),
        ("scripts/commands/projects/validate_project.py", "is_starter_text(terminology_text)"),
        ("scripts/commands/projects/validate_project.py", "03_experiments/experiment_dag.json has no DAG plans"),
        ("scripts/commands/projects/validate_project.py", "05_results/claim_graph.json has no claim/evidence graph"),
        ("scripts/commands/projects/validate_project.py", "Succeeded experiment run_state entries exist"),
        ("scripts/commands/projects/validate_project.py", "Baseline source snapshots exist"),
        ("scripts/commands/projects/validate_project.py", "Baseline structure reports exist"),
        ("scripts/commands/projects/validate_project.py", "parallel_batch_manifest_warnings"),
        ("scripts/commands/projects/validate_project.py", "prompt path is missing"),
        ("scripts/commands/projects/state_doctor.py", "state_doctor"),
        ("scripts/commands/projects/state_doctor.py", "--dry-run-enqueue"),
        ("scripts/commands/projects/state_doctor.py", "--dry-run-repair"),
        ("prompts/skills/state_doctor.md", "Preview repair before writing"),
        ("scripts/commands/projects/state_doctor.py", "repair_dry_run"),
        ("scripts/commands/projects/state_doctor.py", "repair_mode"),
        ("scripts/commands/projects/state_doctor.py", "repaired_count"),
        ("scripts/commands/projects/state_doctor.py", "repair_errors"),
        ("scripts/commands/projects/state_doctor.py", "validate_template_json"),
        ("scripts/commands/projects/state_doctor.py", "validate_command_queue_doc"),
        ("scripts/commands/projects/state_doctor.py", "validate_agent_status_doc"),
        ("scripts/commands/projects/state_doctor.py", "dry_run: bool = False"),
        ("scripts/commands/projects/state_doctor.py", "write_state = (args.write_report or args.repair) and not args.dry_run_repair"),
        ("scripts/commands/projects/state_doctor.py", "enqueue_dry_run = args.dry_run_enqueue or args.dry_run_repair"),
        ("scripts/commands/projects/state_doctor.py", "sync_next_actions(root, load_command_queue(root))"),
        ("scripts/commands/projects/state_doctor.py", "template_repair_relatives"),
        ("scripts/commands/projects/state_doctor.py", "content.replace(\"{{PROJECT_NAME}}\", root.name)"),
        ("scripts/commands/projects/state_doctor.py", "state/command_queue.json"),
        ("scripts/commands/projects/state_doctor.py", "state/agent_status.json"),
        ("scripts/commands/projects/state_doctor.py", "state/agent_messages.json"),
        ("scripts/commands/projects/state_doctor.py", "state/agent_votes.json"),
        ("scripts/commands/projects/state_doctor.py", "state/loop_summary.json"),
        ("scripts/commands/projects/state_doctor.py", "00_brief"),
        ("scripts/commands/projects/state_doctor.py", "02_planning"),
        ("scripts/commands/projects/state_doctor.py", "data_roots.md"),
        ("scripts/commands/projects/state_doctor.py", "artifact_registry.csv"),
        ("scripts/commands/projects/state_doctor.py", "experiment_dag.json"),
        ("scripts/commands/projects/state_doctor.py", "experiment_results.csv"),
        ("scripts/commands/projects/state_doctor.py", "experiment_journal.csv"),
        ("scripts/commands/projects/state_doctor.py", "experiment_journal.md"),
        ("scripts/commands/projects/state_doctor.py", "progress_hooks.jsonl"),
        ("scripts/commands/projects/state_doctor.py", "progress_log.md"),
        ("scripts/commands/projects/state_doctor.py", "claim_evidence_board.md"),
        ("scripts/commands/projects/state_doctor.py", "claim_graph.json"),
        ("scripts/commands/projects/state_doctor.py", "terminology.md"),
        ("scripts/commands/projects/state_doctor.py", "baseline_compare.md"),
        ("scripts/commands/projects/state_doctor.py", "code_structure_plan.md"),
        ("scripts/commands/projects/state_doctor.py", "agent_quality_audit.md"),
        ("scripts/commands/projects/state_doctor.py", "outputs.extend(item for item in repaired"),
        ("scripts/commands/projects/project_health.py", "project_health"),
        ("scripts/commands/projects/project_health.py", "--dry-run-enqueue"),
        ("scripts/commands/projects/project_health.py", "recommended {source_label} repair"),
        ("scripts/commands/projects/project_health.py", "required_inputs = split_outputs"),
        ("scripts/commands/projects/project_health.py", "isinstance(value, list)"),
        ("scripts/commands/projects/project_health.py", "caller=\"project_health\""),
        ("scripts/harness/project_diagnostics.py", "DIAGNOSTIC_STATE_FILES"),
        ("scripts/harness/project_diagnostics.py", "generated_at"),
        ("scripts/harness/project_diagnostics.py", "now_utc"),
        ("scripts/harness/project_diagnostics.py", "RECENT_ACTIVITY_FILES"),
        ("scripts/harness/project_diagnostics.py", "DIAGNOSTIC_TELEMETRY_FILES"),
        ("scripts/harness/project_diagnostics.py", "latest_activity_mtime"),
        ("scripts/harness/project_diagnostics.py", "relative not in telemetry_files"),
        ("scripts/harness/project_diagnostics.py", "Diagnostic surface is older than recent project progress"),
        ("README.md", "state doctor first"),
        ("projects/template/README.md", "state doctor first"),
        ("scripts/commands/projects/project_resume.py", "state doctor first"),
        ("scripts/harness/command_mirror.py", "state doctor first"),
        ("scripts/harness/project_diagnostics.py", "caller: str"),
        ("scripts/harness/project_diagnostics.py", "caller == \"project_health\""),
        ("scripts/harness/project_diagnostics.py", "caller == \"state_doctor\""),
        ("scripts/harness/project_diagnostics.py", "marker.lower() in lowered"),
        ("scripts/harness/project_diagnostics.py", "to_be_defined"),
        ("scripts/harness/project_diagnostics.py", "Run state doctor repair for safe missing starter surfaces"),
        ("scripts/harness/project_diagnostics.py", "HANDOFF.md, state/current_state.md, state/command_queue.json"),
        ("scripts/harness/project_diagnostics.py", "state/progress_hooks.jsonl"),
        ("scripts/harness/project_diagnostics.py", "| Owner Agent | Priority | Action | Required Inputs | Expected Outputs |"),
        ("scripts/harness/project_diagnostics.py", "| Command ID | Owner Agent | Priority | Action | Required Inputs | Expected Outputs |"),
        ("scripts/harness/project_diagnostics.py", "## Repaired Files"),
        ("scripts/harness/project_diagnostics.py", "## Repair Errors"),
        ("scripts/harness/project_diagnostics.py", "No repair errors."),
        ("scripts/harness/project_diagnostics.py", "repair_dry_run"),
        ("scripts/harness/project_diagnostics.py", "Repair mode:"),
        ("scripts/harness/project_diagnostics.py", "Repair file count:"),
        ("scripts/harness/project_diagnostics.py", "Repair dry run only; no files were created."),
        ("scripts/harness/project_diagnostics.py", "Repair dry run only; no files would be created."),
        ("scripts/harness/project_diagnostics.py", "does not infer research content"),
        ("scripts/harness/project_diagnostics.py", "No repair files were created in this run."),
        ("scripts/commands/projects/state_doctor.py", "caller=\"state_doctor\""),
        ("scripts/commands/projects/brief_intake.py", "brief_intake"),
        ("scripts/commands/experiments/experiment_planner.py", "experiment_planner"),
        ("scripts/commands/reports/claim_graph.py", "claim_graph"),
        ("scripts/commands/baselines/baseline_compare.py", "baseline_compare"),
        ("scripts/commands/review/agent_quality_audit.py", "agent_quality_audit"),
        ("scripts/commands/agents/agent_orchestrator.py", "select_parallel_commands"),
        ("scripts/commands/agents/agent_orchestrator.py", "status-parallel"),
        ("scripts/commands/agents/agent_orchestrator.py", "read_only"),
        ("scripts/commands/agents/agent_orchestrator.py", "scope"),
        ("scripts/commands/agents/agent_orchestrator.py", "open_parallel_diagnostics"),
        ("scripts/commands/agents/agent_orchestrator.py", "parallel_command_diagnostics"),
        ("scripts/commands/agents/agent_orchestrator.py", "parallel_readiness_reasons"),
        ("scripts/commands/agents/agent_orchestrator.py", "not safe for parallel dispatch"),
        ("scripts/commands/agents/agent_orchestrator.py", "Explicit parallel command count"),
        ("scripts/commands/agents/agent_orchestrator.py", "--runner-profile"),
        ("scripts/commands/agents/agent_orchestrator.py", "resolve_runner_template"),
        ("scripts/commands/agents/agent_orchestrator.py", "missing_expected_outputs"),
        ("scripts/commands/agents/agent_orchestrator.py", "owner_already_selected"),
        ("scripts/commands/agents/agent_orchestrator.py", "path_conflict"),
        ("scripts/commands/agents/agent_orchestrator.py", "expected_outputs"),
        ("scripts/commands/agents/agent_orchestrator.py", "prepared_parallel_commands"),
        ("scripts/commands/agents/agent_orchestrator.py", "PARALLEL_MANAGED_STATE_PATHS"),
        ("scripts/commands/agents/agent_orchestrator.py", "command_substantive_path_set"),
        ("scripts/commands/agents/agent_orchestrator.py", "parallel_commands"),
        ("scripts/commands/agents/agent_orchestrator.py", "open_parallel_diagnostics"),
        ("scripts/commands/agents/agent_orchestrator.py", "Parallel batch available"),
        ("scripts/commands/agents/agent_orchestrator.py", "parallel_dispatch_plan"),
        ("scripts/commands/agents/agent_orchestrator.py", "parallel_batches"),
        ("scripts/commands/agents/agent_orchestrator.py", "run-prepared"),
        ("scripts/commands/agents/agent_orchestrator.py", "--dry-run"),
        ("scripts/commands/agents/agent_orchestrator.py", "--all-prepared"),
        ("scripts/commands/agents/agent_orchestrator.py", "fail_on_unfinished_dependencies"),
        ("scripts/commands/agents/agent_orchestrator.py", "dependency_ready"),
        ("scripts/commands/agents/agent_orchestrator.py", "unfinished_dependencies"),
        ("scripts/commands/agents/agent_orchestrator.py", "Prepared command is not in progress"),
        ("scripts/commands/agents/agent_orchestrator.py", "Prepared command has no orchestrator_prompt"),
        ("scripts/commands/agents/agent_orchestrator.py", "Prepared command dependencies are not done"),
        ("scripts/commands/agents/agent_orchestrator.py", "finish-parallel"),
        ("scripts/commands/agents/agent_orchestrator.py", "dry run: no command status changed"),
        ("scripts/commands/agents/agent_orchestrator.py", "--result-file"),
        ("scripts/commands/agents/agent_orchestrator.py", "merged_output_paths"),
        ("scripts/commands/agents/agent_orchestrator.py", "finish-parallel --status done requires --note, --output, or --result-file evidence"),
        ("scripts/commands/agents/agent_orchestrator.py", "finish-parallel --status blocked/deferred requires --note explaining the reason"),
        ("scripts/commands/agents/agent_orchestrator.py", "parallel_finish"),
        ("scripts/commands/agents/agent_orchestrator.py", "parallel_prepared_run"),
        ("scripts/commands/agents/agent_orchestrator.py", "parallel_runner_result"),
        ("scripts/commands/agents/agent_orchestrator.py", "parallel_prepared_runner_result"),
        ("scripts/commands/agents/agent_orchestrator.py", "execute_and_record_parallel_result"),
        ("scripts/commands/projects/project_resume.py", "select_parallel_commands"),
        ("scripts/commands/projects/project_resume.py", "Parallel Agent Batch Candidates"),
        ("scripts/commands/projects/project_resume.py", "prepared_parallel_prompt_summary"),
        ("scripts/commands/projects/project_resume.py", "Prepared Or In-Progress Parallel Prompts"),
        ("scripts/commands/projects/project_resume.py", "unfinished_dependencies"),
        ("scripts/commands/projects/project_resume.py", "is not ready to run"),
        ("scripts/commands/projects/project_resume.py", "run-prepared"),
        ("scripts/commands/projects/project_resume.py", "finish-parallel"),
        ("scripts/commands/projects/project_resume.py", "status-parallel"),
        ("scripts/commands/projects/project_resume.py", "parallel_batch_manifest_summary"),
        ("scripts/commands/projects/project_resume.py", "Parallel Batch Manifests"),
        ("scripts/commands/projects/project_resume.py", "parallel_event_summary"),
        ("scripts/commands/projects/project_resume.py", "Recent Parallel Lifecycle Events"),
        ("scripts/commands/projects/project_resume.py", "agent_orchestrator parallel"),
        ("scripts/commands/review/command_queue.py", "--depends-on"),
        ("scripts/commands/review/command_queue.py", "--parallel-group"),
        ("scripts/commands/review/command_queue.py", "--verbose"),
        ("scripts/commands/review/command_queue.py", "depends_on="),
        ("scripts/commands/review/command_queue.py", "dependency_ready="),
        ("scripts/commands/review/command_queue.py", "unfinished="),
        ("scripts/commands/review/command_queue.py", "command_with_readiness"),
        ("scripts/commands/review/command_queue.py", "unfinished_dependencies"),
        ("scripts/harness/state.py", "depends_on"),
        ("scripts/harness/state.py", "depends on unknown command id"),
        ("scripts/harness/state.py", "has duplicate dependency"),
        ("scripts/harness/state.py", "Command dependency cycle detected"),
        ("scripts/harness/command_mirror.py", "Depends On"),
        ("scripts/harness/command_mirror.py", "Parallel Group"),
        ("scripts/harness/command_mirror.py", "state/project_health.md"),
        ("scripts/harness/command_mirror.py", "state/state_doctor.md"),
        ("scripts/harness/command_mirror.py", "older than recent project progress"),
        ("scripts/harness/command_mirror.py", "--dry-run-repair"),
        ("scripts/harness/command_mirror.py", "status-parallel"),
        ("scripts/harness/command_mirror.py", "ready scoped group"),
        ("scripts/harness/command_mirror.py", "silently skipping unsafe commands"),
        ("scripts/commands/research/research_loop.py", "action_dependencies"),
        ("scripts/commands/research/research_loop.py", "action_parallel_group"),
        ("scripts/commands/research/research_loop.py", "research_loop_auto"),
        ("scripts/commands/review/leader_dispatch.py", "parse_worker_entries"),
        ("scripts/commands/review/leader_dispatch.py", "apply_dispatch_block"),
        ("scripts/commands/review/leader_dispatch.py", "dispatch_parallel_groups"),
        ("scripts/commands/review/leader_dispatch.py", "write_parallel_prompts_for_groups"),
        ("scripts/commands/review/leader_dispatch.py", "--write-parallel-prompts"),
        ("scripts/commands/review/leader_dispatch.py", "run prepared hint"),
        ("scripts/commands/review/leader_dispatch.py", "parallel hint"),
        ("scripts/commands/review/leader_dispatch.py", "leader_dispatch_apply"),
        ("scripts/commands/review/leader_dispatch.py", "depends_on"),
        ("scripts/commands/review/leader_dispatch.py", "expected_outputs"),
        ("prompts/shared/leader_dispatch_protocol.md", "workers[].depends_on"),
        ("prompts/shared/leader_dispatch_protocol.md", "workers[].expected_outputs"),
        ("scripts/commands/baselines/baseline_intake.py", "Canonical Project Layout To Apply"),
        ("scripts/commands/baselines/baseline_intake.py", "args.write_smoke"),
        ("scripts/commands/reports/report_index.py", "Final Artifact Index"),
        ("scripts/commands/reports/report_index.py", "Working state belongs"),
        ("scripts/harness/workflow_hooks.py", "include_report: bool = False"),
        ("scripts/harness/workflow_hooks.py", "refresh_workflow_surfaces"),
        ("scripts/harness/workflow_hooks.py", "Compatibility wrapper for older call sites"),
        ("scripts/harness/report_lifecycle.py", "refresh_report: bool = False"),
        ("scripts/harness/report_lifecycle.py", "include_report=True"),
        ("scripts/commands/experiments/result_ingest.py", "include_report=args.final_export"),
        ("scripts/commands/experiments/result_ingest.py", "09_report/results/statistical_robustness.csv"),
        ("scripts/commands/experiments/experiment_complete.py", "artifact_registry.csv"),
        ("scripts/commands/experiments/experiment_complete.py", "--result-analysis is required"),
        ("scripts/commands/experiments/gpu_scheduler.py", "refresh"),
        ("scripts/commands/experiments/gpu_scheduler.py", "--mark-missing"),
        ("scripts/commands/reports/artifact_packager.py", "REQUIRED_ARTIFACTS"),
        ("scripts/commands/reports/artifact_packager.py", "--allow-incomplete"),
        ("scripts/commands/reports/artifact_packager.py", "05_results/experiment_journal.csv"),
        ("scripts/commands/reports/claim_evidence_board.py", "--final-export"),
        ("scripts/commands/reports/claim_evidence_board.py", "refresh_report=final_export"),
        ("scripts/commands/dashboard/dashboard_refresh.py", "--final-export"),
        ("scripts/commands/dashboard/dashboard_refresh.py", "skipped_final_export"),
        ("project.yaml", "claim_board"),
        ("project.yaml", "05_results/claim_evidence_board.md"),
        ("scripts/commands/review/progress_checkpoint.py", "check-limits"),
        ("scripts/commands/review/progress_checkpoint.py", "limit-handoff"),
        ("scripts/commands/review/progress_checkpoint.py", "state/limit_handoff.md"),
        ("scripts/commands/review/progress_checkpoint.py", "write_text(limit_handoff_md"),
        ("scripts/commands/experiments/gpu_scheduler.py", "Analyze why the experiment result"),
        ("scripts/commands/experiments/gpu_scheduler.py", "gpu_plan_diagnostics"),
        ("scripts/commands/experiments/gpu_scheduler.py", "plan_diagnostics"),
        ("scripts/commands/experiments/gpu_scheduler.py", "gpu_job_with_readiness"),
        ("scripts/commands/experiments/gpu_scheduler.py", "unfinished_gpu_dependencies"),
        ("scripts/commands/experiments/gpu_scheduler.py", "no_available_gpu_type"),
        ("scripts/commands/experiments/gpu_scheduler.py", "not_planned"),
        ("scripts/commands/experiments/gpu_scheduler.py", "Requested jobs are not currently dispatchable"),
        ("scripts/commands/experiments/gpu_scheduler.py", "Explicit GPU job count"),
        ("scripts/commands/experiments/gpu_scheduler.py", "dispatch --json is only supported"),
        ("scripts/commands/experiments/gpu_scheduler.py", "launch_commands"),
        ("scripts/commands/release/smoke_test.py", "artifact_packager"),
        ("scripts/commands/release/smoke_test.py", "--allow-incomplete"),
        ("scripts/commands/release/smoke_test.py", "Canonical Project Layout To Apply"),
        ("scripts/commands/release/smoke_test.py", "--write-smoke"),
        ("scripts/commands/release/smoke_test.py", "baseline_inspect"),
        ("scripts/commands/release/smoke_test.py", "\"apply\", \"--project\""),
        ("scripts/commands/release/smoke_test.py", "--write-parallel-prompts"),
        ("scripts/commands/release/smoke_test.py", "command_queue list --json did not expose dependency readiness"),
        ("scripts/commands/release/smoke_test.py", "agent_orchestrator.py next --json did not expose open parallel diagnostics"),
        ("scripts/commands/release/smoke_test.py", "explicit parallel --id failure"),
        ("scripts/commands/release/smoke_test.py", "agent_orchestrator.py parallel JSON did not expose open parallel diagnostics"),
        ("scripts/commands/release/smoke_test.py", "status-parallel"),
        ("scripts/commands/release/smoke_test.py", "open parallel diagnostics"),
        ("scripts/commands/release/smoke_test.py", "dependency_ready"),
        ("scripts/commands/release/smoke_test.py", "unfinished_dependencies"),
        ("scripts/commands/release/smoke_test.py", "run-prepared"),
        ("scripts/commands/release/smoke_test.py", "--dry-run"),
        ("scripts/commands/release/smoke_test.py", "--all-prepared"),
        ("scripts/commands/release/smoke_test.py", "Prepared command dependencies are not done"),
        ("scripts/commands/release/smoke_test.py", "finish-parallel"),
        ("scripts/commands/release/smoke_test.py", "--dry-run"),
        ("scripts/commands/release/smoke_test.py", "--result-file"),
        ("scripts/commands/release/smoke_test.py", "parallel_finish"),
        ("scripts/commands/release/smoke_test.py", "parallel_prepared_run"),
        ("scripts/commands/release/smoke_test.py", "parallel_prepared_runner_result"),
        ("scripts/commands/release/smoke_test.py", "parallel batch manifest"),
        ("scripts/commands/release/smoke_test.py", "cmd_leader_smoke"),
        ("scripts/commands/release/smoke_test.py", "cmd_leader_smoke_critic"),
        ("scripts/commands/release/smoke_test.py", "Analyze why the experiment result"),
        ("scripts/commands/release/smoke_test.py", "gpu_add"),
        ("scripts/commands/release/smoke_test.py", "gpu_scheduler list --json did not expose dependency readiness"),
        ("scripts/commands/release/smoke_test.py", "gpu_dispatch_plan"),
        ("scripts/commands/release/smoke_test.py", "plan_diagnostics"),
        ("scripts/commands/release/smoke_test.py", "unfinished_dependencies:gpu_smoke_1"),
        ("scripts/commands/release/smoke_test.py", "GPU dispatch --ids failure did not explain"),
        ("scripts/commands/release/smoke_test.py", "GPU dispatch --ids max-parallel failure did not explain"),
        ("scripts/commands/release/smoke_test.py", "GPU scheduler dry-run dispatch did not print excluded job diagnostics"),
        ("scripts/commands/release/smoke_test.py", "GPU scheduler dispatch --json did not expose selected jobs"),
        ("scripts/commands/release/smoke_test.py", "GPU scheduler dispatch --json did not expose diagnostics and launch commands"),
        ("scripts/commands/release/smoke_test.py", "parallel_dispatch_plan"),
        ("scripts/commands/release/smoke_test.py", "parallel_smoke"),
        ("scripts/commands/release/smoke_test.py", "progress_checkpoint"),
        ("scripts/commands/release/smoke_test.py", "--dry-run-repair"),
        ("scripts/commands/release/smoke_test.py", "state doctor dry-run repair wrote a planned repair file"),
        ("scripts/commands/release/verify_harness.py", "--dry-run-repair"),
        ("scripts/commands/release/smoke_test.py", "working state leaked into the final report README index"),
        ("scripts/commands/release/smoke_test.py", "robustness working ingest leaked into the final robustness table"),
        ("scripts/commands/release/smoke_test.py", "robustness final export did not write the final robustness table"),
        ("scripts/commands/release/smoke_test.py", "working write leaked a final report output"),
        ("scripts/commands/release/smoke_test.py", "final export did not sync the report-facing output"),
        ("scripts/commands/release/smoke_test.py", "dashboard refresh default write leaked into the final report index"),
        ("scripts/commands/release/smoke_test.py", "dashboard refresh final export mode failed"),
        ("scripts/commands/release/smoke_test.py", "--final-export"),
        ("scripts/commands/release/smoke_test.py", "--include-dashboard"),
        ("scripts/commands/release/smoke_test.py", "run_dashboard_project_smoke"),
        ("scripts/commands/release/verify_harness.py", 'smoke_test.py", *(["--include-dashboard"]'),
        ("scripts/commands/release/workflow_audit.py", "project_created"),
        ("scripts/commands/release/workflow_audit.py", "gpu_dispatch_plan"),
        ("scripts/commands/release/workflow_audit.py", "progress_checkpoint"),
        ("workflows/default_research_flow.yaml", "progress_capture"),
        ("workflows/experiment_debug_flow.yaml", "progress_capture"),
        ("workflows/paper_iteration_flow.yaml", "progress_capture"),
        ("scripts/commands/projects/project_index.py", "PUBLIC_INVENTORY_EXCLUDES"),
        ("scripts/commands/projects/project_index.py", "config/workspace_profile.local.json"),
    ):
        if needle not in read(root / relative):
            warnings.append(f"{relative} should document {needle}.")
    inventory_text = generated_inventory_text(read(root / "project.yaml"))
    if "config/workspace_profile.local.json" in inventory_text:
        warnings.append("project.yaml generated inventory must not list config/workspace_profile.local.json.")
    for relative, forbidden, reason in (
        ("README.md", "Ralph Loop And Dashboard", "root README should not foreground legacy Ralph/dashboard workflow"),
        ("README.md", "Standalone browser dashboard", "root README should stay agent-first, not dashboard-first"),
        ("README.md", "manual-first", "root README should not describe the workspace as manual-first"),
        ("scripts/README.md", "Standalone browser dashboard", "internal script README should label dashboard as optional support tooling"),
        ("scripts/commands/reports/report_index.py", "## Current Snapshot", "report index should not write working current-stage snapshots into 09_report"),
        ("scripts/commands/reports/report_index.py", "## Current Work", "report index should not write command/GPU working state into 09_report"),
        ("projects/template/README.md", "manual-first", "template README should be Claude/Codex-first"),
        ("projects/template/README.md", "dashboard command queue", "template README should not make the dashboard queue the default workflow"),
        ("projects/template/state/current_state.md", "Ralph-loop initialized", "template state should not initialize legacy Ralph as default"),
        ("projects/template/state/next_actions.md", "dashboard command queue", "template next actions should not foreground dashboard workflow"),
        ("projects/template/state/agent_status.json", "\"09_report/\"", "template initial agent status should not make 09_report a default input"),
    ):
        if forbidden in read(root / relative):
            warnings.append(f"{relative} contains forbidden legacy/default wording: {reason}.")
    warnings.extend(private_content_warnings())
    return warnings


def generated_template_state() -> list[str]:
    root = repo_root() / "projects" / "template"
    findings: list[str] = []
    ralph_loop = root / "state" / "ralph_loop.json"
    if ralph_loop.is_file():
        try:
            data = json.loads(ralph_loop.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            findings.append("projects/template/state/ralph_loop.json is invalid JSON.")
        else:
            if data.get("runs"):
                findings.append("projects/template/state/ralph_loop.json contains generated run history.")
            if data.get("active_run_id"):
                findings.append("projects/template/state/ralph_loop.json contains active_run_id.")
    events = root / "state" / "agent_events.jsonl"
    if events.is_file() and events.read_text(encoding="utf-8").strip():
        findings.append("projects/template/state/agent_events.jsonl contains generated event history.")
    progress_hooks = root / "state" / "progress_hooks.jsonl"
    if progress_hooks.is_file() and progress_hooks.read_text(encoding="utf-8").strip():
        findings.append("projects/template/state/progress_hooks.jsonl contains generated progress history.")
    progress_log = root / "state" / "sessions" / "progress_log.md"
    if progress_log.is_file() and progress_log.read_text(encoding="utf-8").strip():
        findings.append("projects/template/state/sessions/progress_log.md contains generated progress history.")
    prompt_dir = root / "state" / "ralph_prompts"
    if prompt_dir.is_dir() and any(prompt_dir.glob("*.md")):
        findings.append("projects/template/state/ralph_prompts/ contains generated prompt files.")
    sessions_dir = root / "state" / "sessions"
    if sessions_dir.is_dir():
        session_dirs = [path.name for path in sessions_dir.iterdir() if path.is_dir()]
        if session_dirs:
            findings.append(f"projects/template/state/sessions/ contains generated session dirs: {', '.join(sorted(session_dirs))}.")
    lock_files = sorted(path.relative_to(root).as_posix() for path in (root / "state").rglob("*.lock"))
    if lock_files:
        findings.append(f"projects/template/state/ contains lock files: {', '.join(lock_files)}.")
    return findings


def print_step(step: dict[str, object]) -> None:
    print(f"== {step['name']}")
    if step["stdout"]:
        print(step["stdout"])
    if step["stderr"]:
        print(step["stderr"], file=sys.stderr)
    if not step["ok"]:
        print(f"FAILED: {step['name']}", file=sys.stderr)


def main() -> int:
    args = parse_args()
    root = repo_root()
    warnings = static_release_warnings(args.version)
    template_state_findings = generated_template_state()
    if args.strict_template_state:
        warnings.extend(template_state_findings)

    py_files = sorted(str(path.relative_to(root)) for path in (root / "scripts").rglob("*.py"))
    checks: list[tuple[str, list[str]]] = [
        ("python syntax", [sys.executable, "-m", "py_compile", *py_files]),
        ("workflow audit", python_module_command("workflow_audit.py")),
        ("project index check", python_module_command("project_index.py", "check")),
        ("publishable file check", python_module_command("check_publishable.py")),
        ("diff whitespace check", git_command("diff", "--check")),
        ("staged diff whitespace check", git_command("diff", "--cached", "--check")),
    ]
    if args.include_dashboard and shutil.which("node") and (root / "dashboard" / "core.js").is_file():
        checks.append(("dashboard core syntax", ["node", "--check", "dashboard/core.js"]))
    if args.include_dashboard and shutil.which("node") and (root / "dashboard" / "app.js").is_file():
        checks.append(("dashboard app syntax", ["node", "--check", "dashboard/app.js"]))
    if not args.skip_verify_harness:
        verify_cmd = python_module_command("verify_harness.py", "--project", args.project)
        if args.skip_paper_build:
            verify_cmd.append("--skip-paper-build")
        if args.include_dashboard:
            verify_cmd.append("--include-dashboard")
        checks.insert(2, ("full harness verification", verify_cmd))

    steps = [run_step(name, cmd) for name, cmd in checks]
    ok = not warnings and all(step["ok"] for step in steps)
    payload = {
        "ok": ok,
        "project": args.project,
        "version": args.version,
        "warnings": warnings,
        "template_state_findings": template_state_findings,
        "checks": steps,
    }
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        for warning in warnings:
            print(f"warning: {warning}", file=sys.stderr)
        if template_state_findings and not args.strict_template_state:
            print("note: generated template state is present; pass --strict-template-state to fail on it before tagging.")
            for finding in template_state_findings:
                print(f"- {finding}")
        for step in steps:
            print_step(step)
        if ok:
            print(f"release check OK for {args.version}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
