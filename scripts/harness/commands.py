"""Command-module registry for harness CLI entry points."""

from __future__ import annotations

import sys

COMMAND_MODULES: dict[str, str] = {
    "agent_dashboard": "scripts.commands.agents.agent_dashboard",
    "agent_events": "scripts.commands.agents.agent_events",
    "agent_messages": "scripts.commands.agents.agent_messages",
    "agent_orchestrator": "scripts.commands.agents.agent_orchestrator",
    "agent_runner": "scripts.commands.agents.agent_runner",
    "automation_setup": "scripts.commands.release.automation_setup",
    "agent_status": "scripts.commands.agents.agent_status",
    "agents": "scripts.commands.agents.agents",
    "agent_vote": "scripts.commands.agents.agent_vote",
    "agent_quality_audit": "scripts.commands.review.agent_quality_audit",
    "artifact_packager": "scripts.commands.reports.artifact_packager",
    "baseline_compare": "scripts.commands.baselines.baseline_compare",
    "baselines": "scripts.commands.baselines.baselines",
    "baseline_intake": "scripts.commands.baselines.baseline_intake",
    "baseline_library": "scripts.commands.baselines.baseline_library",
    "baseline_sandbox": "scripts.commands.baselines.baseline_sandbox",
    "brief_intake": "scripts.commands.projects.brief_intake",
    "check_publishable": "scripts.commands.release.check_publishable",
    "claim_evidence_board": "scripts.commands.reports.claim_evidence_board",
    "claim_graph": "scripts.commands.reports.claim_graph",
    "claims": "scripts.commands.reports.claims",
    "command_queue": "scripts.commands.review.command_queue",
    "create_project": "scripts.commands.projects.create_project",
    "dashboard_command_runner": "scripts.commands.dashboard.dashboard_command_runner",
    "dashboard_refresh": "scripts.commands.dashboard.dashboard_refresh",
    "dashboard_sources": "scripts.commands.dashboard.dashboard_sources",
    "data_metric_audit": "scripts.commands.reports.data_metric_audit",
    "env_capture": "scripts.commands.experiments.env_capture",
    "experiment_diagnosis": "scripts.commands.experiments.experiment_diagnosis",
    "experiment_complete": "scripts.commands.experiments.experiment_complete",
    "experiment_planner": "scripts.commands.experiments.experiment_planner",
    "experiments": "scripts.commands.experiments.experiments",
    "gpu_monitor": "scripts.commands.experiments.gpu_monitor",
    "gpu_scheduler": "scripts.commands.experiments.gpu_scheduler",
    "import_research_repo": "scripts.commands.projects.import_research_repo",
    "leader_dispatch": "scripts.commands.review.leader_dispatch",
    "log_digest": "scripts.commands.experiments.log_digest",
    "loop_summary": "scripts.commands.review.loop_summary",
    "memory_compact": "scripts.commands.review.memory_compact",
    "migrate_project": "scripts.commands.projects.migrate_project",
    "paper_claim_linter": "scripts.commands.reports.paper_claim_linter",
    "pattern_memory": "scripts.commands.review.pattern_memory",
    "phase_gate": "scripts.commands.research.phase_gate",
    "preregistration_helper": "scripts.commands.experiments.preregistration_helper",
    "progress_checkpoint": "scripts.commands.review.progress_checkpoint",
    "privacy_audit": "scripts.commands.release.privacy_audit",
    "project_closeout": "scripts.commands.projects.project_closeout",
    "project_doctor": "scripts.commands.projects.project_doctor",
    "project_health": "scripts.commands.projects.project_health",
    "project_hygiene": "scripts.commands.projects.project_hygiene",
    "project_index": "scripts.commands.projects.project_index",
    "project_intake": "scripts.commands.projects.project_intake",
    "project_resume": "scripts.commands.projects.project_resume",
    "projects": "scripts.commands.projects.projects",
    "ralph_loop": "scripts.commands.review.ralph_loop",
    "release_check": "scripts.commands.release.release_check",
    "repo_discovery": "scripts.commands.baselines.repo_discovery",
    "report_index": "scripts.commands.reports.report_index",
    "report_snapshot": "scripts.commands.reports.report_snapshot",
    "research_audit": "scripts.commands.research.research_audit",
    "research_loop": "scripts.commands.research.research_loop",
    "research_autopilot": "scripts.commands.research.research_autopilot",
    "research_registry": "scripts.commands.research.research_registry",
    "resource_ledger": "scripts.commands.reports.resource_ledger",
    "result_ingest": "scripts.commands.experiments.result_ingest",
    "review_forms": "scripts.commands.review.review_forms",
    "review_to_revision": "scripts.commands.review.review_to_revision",
    "run_checkpoint": "scripts.commands.experiments.run_checkpoint",
    "run_diff": "scripts.commands.experiments.run_diff",
    "run_state": "scripts.commands.experiments.run_state",
    "seed_variance": "scripts.commands.experiments.seed_variance",
    "session_state": "scripts.commands.review.session_state",
    "smoke_test": "scripts.commands.release.smoke_test",
    "source_credibility_audit": "scripts.commands.reports.source_credibility_audit",
    "state_doctor": "scripts.commands.projects.state_doctor",
    "validate_project": "scripts.commands.projects.validate_project",
    "verify_harness": "scripts.commands.release.verify_harness",
    "weekly_deck": "scripts.commands.reports.weekly_deck",
    "worker_result": "scripts.commands.review.worker_result",
    "workflow_audit": "scripts.commands.release.workflow_audit",
    "workspace_profile": "scripts.commands.release.workspace_profile",
}


def command_name(script_or_name: str) -> str:
    name = script_or_name.removeprefix("scripts/").removesuffix(".py")
    if "/" in name:
        name = name.rsplit("/", 1)[-1]
    return name


def command_module(script_or_name: str) -> str:
    name = command_name(script_or_name)
    try:
        return COMMAND_MODULES[name]
    except KeyError as exc:
        raise KeyError(f"Unknown harness command: {script_or_name}") from exc


def python_module_command(script_or_name: str, *args: str) -> list[str]:
    return [sys.executable, "-m", command_module(script_or_name), *args]
