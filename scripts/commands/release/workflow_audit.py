#!/usr/bin/env python3
"""Audit harness workflow wiring without modifying project state."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from scripts.harness import repo_root as harness_repo_root
    from scripts.harness.commands import command_module
except ModuleNotFoundError:
    from scripts.harness import repo_root as harness_repo_root
    from scripts.harness.commands import command_module


REQUIRED_REFRESH_SCRIPTS = (
    "agent_events.py",
    "agent_orchestrator.py",
    "agent_quality_audit.py",
    "agent_status.py",
    "baseline_compare.py",
    "brief_intake.py",
    "claim_evidence_board.py",
    "claim_graph.py",
    "command_queue.py",
    "create_project.py",
    "experiment_planner.py",
    "gpu_monitor.py",
    "gpu_scheduler.py",
    "import_research_repo.py",
    "leader_dispatch.py",
    "loop_summary.py",
    "migrate_project.py",
    "project_intake.py",
    "project_health.py",
    "progress_checkpoint.py",
    "research_audit.py",
    "research_loop.py",
    "result_ingest.py",
    "state_doctor.py",
)

REQUIRED_ORCHESTRATION_DOCS = (
    "prompts/shared/research_routing_matrix.md",
    "prompts/shared/research_handoff_graph.md",
    "prompts/shared/leader_dispatch_protocol.md",
    "prompts/shared/risk_confidence_matrix.md",
    "prompts/shared/research_brain_protocol.md",
)


def repo_root() -> Path:
    return harness_repo_root()


def command_file(script_or_name: str) -> Path:
    return repo_root() / f"{command_module(script_or_name).replace('.', '/')}.py"


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def require_contains(warnings: list[str], path: Path, needle: str, description: str) -> None:
    if needle not in read(path):
        warnings.append(f"{path.relative_to(repo_root())}: missing {description}")


def generated_inventory_text(project_yaml: str) -> str:
    start_marker = "# PROJECT_INDEX:START"
    end_marker = "# PROJECT_INDEX:END"
    start = project_yaml.find(start_marker)
    end = project_yaml.find(end_marker)
    if start == -1 or end == -1 or end < start:
        return ""
    return project_yaml[start : end + len(end_marker)]


def is_dashboard_warning(warning: str) -> bool:
    return "dashboard" in warning.lower()


def audit(include_dashboard: bool = False) -> dict:
    root = repo_root()
    scripts = root / "scripts"
    commands_root = scripts / "commands"
    warnings: list[str] = []

    report_index = command_file("report_index.py")
    agent_dashboard = command_file("agent_dashboard.py")
    dashboard = root / "dashboard" / "index.html"
    dashboard_core = root / "dashboard" / "core.js"
    dashboard_app = root / "dashboard" / "app.js"
    dashboard_styles = root / "dashboard" / "styles.css"
    workflow_hooks = scripts / "harness" / "workflow_hooks.py"
    report_snapshot = command_file("report_snapshot.py")
    dashboard_sources = command_file("dashboard_sources.py")
    dashboard_refresh = command_file("dashboard_refresh.py")
    project_closeout = command_file("project_closeout.py")
    dashboard_command_runner = command_file("dashboard_command_runner.py")
    workspace_profile = command_file("workspace_profile.py")
    project_index = command_file("project_index.py")
    privacy_audit = command_file("privacy_audit.py")
    source_credibility = command_file("source_credibility_audit.py")
    experiment_diagnosis = command_file("experiment_diagnosis.py")
    resource_ledger = command_file("resource_ledger.py")
    phase_gate = command_file("phase_gate.py")
    run_checkpoint = command_file("run_checkpoint.py")
    progress_checkpoint = command_file("progress_checkpoint.py")
    import_research_repo = command_file("import_research_repo.py")
    project_resume = command_file("project_resume.py")
    architecture = root / "ARCHITECTURE.md"
    changelog = root / "CHANGELOG.md"
    project_yaml = root / "project.yaml"

    for required_root_file in ("AGENTS.md", "project.yaml", "pyproject.toml"):
        if not (root / required_root_file).is_file():
            warnings.append(f"{required_root_file} is missing.")
    if (root / "AGENTS.md").is_file():
        require_contains(warnings, root / "AGENTS.md", "scripts.commands.release.verify_harness", "root agent verification command")
        require_contains(warnings, root / "AGENTS.md", "scripts/commands", "grouped command implementation structure")
        require_contains(warnings, root / "AGENTS.md", "plan_diagnostics", "GPU plan diagnostics operating rule")
    if (root / "pyproject.toml").is_file():
        require_contains(warnings, root / "pyproject.toml", "project_index_check", "project index command entry")
    if project_yaml.is_file():
        for needle, description in (
            ("repo_discovery", "repo discovery tool metadata"),
            ("baseline_sandbox", "baseline sandbox tool metadata"),
            ("result_ingest", "result ingest tool metadata"),
            ("gpu_monitor", "GPU monitor tool metadata"),
            ("list --json", "GPU list JSON readiness metadata"),
            ("plan_diagnostics", "GPU plan diagnostics metadata"),
            ("dispatch --json", "GPU dispatch JSON dry-run metadata"),
            ("dispatch --ids", "GPU explicit dispatch diagnostics metadata"),
            ("data_roots", "data-root state metadata"),
            ("experiment_journal", "experiment journal state metadata"),
            ("terminology", "terminology state metadata"),
            ("code_structure_plan", "baseline code structure plan metadata"),
            ("dashboard_optional", "optional dashboard operating rule"),
            ("report_index", "final report index operating rule"),
            ("claim_board", "claim board final export operating rule"),
            ("next --json", "next JSON diagnostics metadata"),
            ("parallel --json", "parallel planner JSON diagnostics metadata"),
            ("proactive_multi_agent", "proactive multi-agent routing metadata"),
            ("state_health", "dashboard-free state health metadata"),
            ("--dry-run-repair", "state doctor repair preview metadata"),
            ("repair_errors", "state doctor repair error metadata"),
            ("template-backed continuity files", "state doctor no-inference repair metadata"),
            ("sync the human-readable next_actions mirror", "state doctor queue mirror sync metadata"),
            ("brief_intake", "brief intake metadata"),
            ("experiment_planning", "experiment planning metadata"),
            ("claim_graph", "claim graph metadata"),
            ("baseline_compare", "baseline comparison metadata"),
            ("agent_quality_audit", "agent quality audit metadata"),
            ("include_report=True", "report index opt-in metadata"),
            ("include-dashboard", "dashboard release opt-in metadata"),
        ):
            require_contains(warnings, project_yaml, needle, description)
    for workflow in ("default_research_flow.yaml", "experiment_debug_flow.yaml", "paper_iteration_flow.yaml"):
        workflow_path = root / "workflows" / workflow
        if not workflow_path.is_file():
            warnings.append(f"workflows/{workflow} is missing.")
        else:
            require_contains(warnings, workflow_path, "progress_capture", "workflow progress checkpoint contract")
    template_agent_status = root / "projects" / "template" / "state" / "agent_status.json"
    if '"09_report/"' in read(template_agent_status):
        warnings.append("projects/template/state/agent_status.json should not make 09_report/ a default initial agent input.")

    required_command_domains = (
        "agents",
        "baselines",
        "dashboard",
        "experiments",
        "projects",
        "reports",
        "research",
        "review",
        "release",
    )
    if not commands_root.is_dir():
        warnings.append("scripts/commands/ is missing.")
    else:
        if not (commands_root / "__init__.py").is_file():
            warnings.append("scripts/commands/__init__.py is missing.")
        for domain in required_command_domains:
            package = commands_root / domain
            if not package.is_dir():
                warnings.append(f"scripts/commands/{domain}/ is missing.")
            elif not (package / "__init__.py").is_file():
                warnings.append(f"scripts/commands/{domain}/__init__.py is missing.")
    root_python_files = sorted(path.name for path in scripts.glob("*.py"))
    if root_python_files:
        warnings.append(f"scripts/ root should not contain Python entry-point wrappers: {', '.join(root_python_files)}")
    for implementation in (
        "commands/projects/create_project.py",
        "commands/agents/agent_dashboard.py",
        "commands/dashboard/dashboard_refresh.py",
        "commands/projects/project_index.py",
        "commands/release/release_check.py",
        "harness/state.py",
        "harness/workflow_hooks.py",
        "harness/commands.py",
    ):
        target = scripts / implementation
        if not target.is_file():
            warnings.append(f"scripts/{implementation} is missing.")

    if not architecture.is_file():
        warnings.append("ARCHITECTURE.md is missing.")
    else:
        for needle, description in (
            ("System Topology", "system topology section"),
            ("Project Filesystem Contract", "project filesystem contract section"),
            ("Agent Workflow", "agent workflow section"),
            ("State Model", "state model section"),
            ("Report And Artifact Flow", "report and artifact flow section"),
            ("Safety And Release Gates", "safety and release gates section"),
        ):
            require_contains(warnings, architecture, needle, description)
        require_contains(warnings, root / "README.md", "ARCHITECTURE.md", "README architecture link")
    if not changelog.is_file():
        warnings.append("CHANGELOG.md is missing.")
    else:
        require_contains(warnings, changelog, "## v4.0.0", "V4 changelog entry")
        require_contains(warnings, changelog, "scripts/commands/release/release_check.py", "release check changelog note")
        require_contains(warnings, changelog, "status-parallel", "parallel orchestrator changelog note")
        require_contains(warnings, changelog, "dispatch --json", "GPU dispatch JSON changelog note")
        require_contains(warnings, changelog, "--dry-run-repair", "state doctor repair preview changelog note")
        require_contains(warnings, changelog, "template-backed state doctor repair", "state doctor template repair changelog note")
        require_contains(warnings, changelog, "command-queue mirror sync", "state doctor repair mirror sync changelog note")
        require_contains(warnings, changelog, "template-backed JSON repair validation", "state doctor repair validation changelog note")
        require_contains(warnings, changelog, "stale diagnostic reports", "diagnostic staleness changelog note")

    if not report_snapshot.is_file():
        warnings.append("scripts/commands/reports/report_snapshot.py is missing.")
    else:
        require_contains(warnings, report_snapshot, "def build_report_snapshot", "build_report_snapshot helper")
        require_contains(warnings, report_snapshot, "def report_tables", "shared report table helper")

    if not dashboard_sources.is_file():
        warnings.append("scripts/commands/dashboard/dashboard_sources.py is missing.")
    else:
        require_contains(warnings, dashboard_sources, "def build_dashboard_sources", "dashboard source manifest helper")
    workspace_profile_core = scripts / "harness" / "workspace_profile.py"
    if not workspace_profile_core.is_file():
        warnings.append("scripts/harness/workspace_profile.py is missing.")
    else:
        for needle, description in (
            ("def load_workspace_profile", "workspace profile loader"),
            ("workspace_profile.local.json", "local profile override path"),
            ("def validate_profile", "workspace profile validator"),
        ):
            require_contains(warnings, workspace_profile_core, needle, description)
    if not workspace_profile.is_file():
        warnings.append("scripts/commands/release/workspace_profile.py is missing.")
    else:
        for needle, description in (
            ("scripts.harness.workspace_profile", "harness-backed profile core import"),
            ("workspace_gpu_profiles", "GPU profile helper"),
            ("summary_language", "dashboard language preference"),
        ):
            require_contains(warnings, workspace_profile, needle, description)
    require_contains(warnings, root / ".gitignore", "config/workspace_profile.local.json", "ignored local workspace profile")
    require_contains(warnings, project_index, "PUBLIC_INVENTORY_EXCLUDES", "public inventory exclusion list")
    require_contains(warnings, project_index, "config/workspace_profile.local.json", "local profile exclusion from generated inventory")
    generated_inventory = generated_inventory_text(read(root / "project.yaml"))
    if "config/workspace_profile.local.json" in generated_inventory:
        warnings.append("project.yaml generated inventory must not list config/workspace_profile.local.json.")
    profile_example = root / "config" / "workspace_profile.example.json"
    if not profile_example.is_file():
        warnings.append("config/workspace_profile.example.json is missing.")
    else:
        require_contains(warnings, profile_example, "summary_language", "workspace profile example display language")
        require_contains(warnings, profile_example, "max_user_gpus", "workspace profile example GPU cap")
    if not dashboard_refresh.is_file():
        warnings.append("scripts.commands.dashboard.dashboard_refresh is missing.")
    else:
        for needle, description in (
            ("def refresh_dashboard_inputs", "dashboard input refresh helper"),
            ("claim_evidence_board", "claim-evidence board refresh step"),
            ("research_audit", "research audit refresh step"),
            ("refresh_project_index", "report index refresh step"),
            ("build_dashboard_sources", "source-manifest refresh step"),
            ("--check", "non-writing dashboard refresh check mode"),
            ("--final-export", "dashboard refresh final export option"),
            ("skipped_final_export", "dashboard refresh working-only default mode"),
        ):
            require_contains(warnings, dashboard_refresh, needle, description)
    if not project_closeout.is_file():
        warnings.append("scripts/commands/projects/project_closeout.py is missing.")
    else:
        for needle, description in (
            ("def build_project_closeout", "project closeout helper"),
            ("dashboard_refresh", "dashboard refresh closeout step"),
            ("workflow_warnings", "workflow-state closeout check"),
            ("voting_warnings", "vote-gate closeout check"),
            ("report_hygiene", "report hygiene closeout routing"),
            ("data_roots", "data-root closeout check"),
            ("experiment_journal", "experiment-journal closeout check"),
            ("terminology", "terminology closeout check"),
            ("recommended_skills", "skill routing output"),
        ):
            require_contains(warnings, project_closeout, needle, description)
    for path, checks in (
        (source_credibility, (
            ("def audit_project", "source credibility audit helper"),
            ("citation_integrity", "citation integrity check"),
            ("source_credibility_audit.csv", "source credibility result table"),
        )),
        (experiment_diagnosis, (
            ("def diagnose_project", "experiment diagnosis helper"),
            ("likely_cause", "failure cause classifier"),
            ("experiment_diagnosis.csv", "experiment diagnosis result table"),
        )),
        (resource_ledger, (
            ("def summarize", "resource summary helper"),
            ("state/resource_ledger.json", "resource ledger state path"),
            ("resource_ledger.csv", "resource ledger result table"),
        )),
        (phase_gate, (
            ("def audit_gates", "phase gate audit helper"),
            ("state/phase_gates.json", "phase gate state path"),
            ("phase_gate_audit.csv", "phase gate result table"),
        )),
        (run_checkpoint, (
            ("def create_checkpoint", "run checkpoint creation helper"),
            ("def checkpoints_dir", "checkpoint state folder helper"),
            ("restore_supported", "non-destructive checkpoint contract"),
        )),
        (progress_checkpoint, (
            ("limit-handoff", "agent usage limit handoff subcommand"),
            ("check-limits", "agent usage limit status check subcommand"),
            ("state/limit_handoff.md", "limit handoff state file"),
            ("write_text(limit_handoff_md", "latest limit handoff overwrite behavior"),
            ("03_experiments/data_roots.md", "limit handoff data-root reminder"),
            ("05_results/experiment_results.csv", "limit handoff working-result reminder"),
            ("06_writing/terminology.md", "limit handoff terminology reminder"),
            ("workspace_agent_limit_status_command", "workspace profile agent limit command helper"),
        )),
        (command_file("state_doctor.py"), (
            ("--dry-run-repair", "state doctor repair preview option"),
            ("repair_dry_run", "state doctor repair dry-run diagnostics flag"),
            ("repair_mode", "state doctor repair mode diagnostics field"),
            ("repaired_count", "state doctor repaired count diagnostics field"),
            ("repair_errors", "state doctor repair errors diagnostics field"),
            ("validate_template_json", "state doctor template JSON repair validation helper"),
            ("validate_command_queue_doc", "state doctor command queue repair validation"),
            ("validate_agent_status_doc", "state doctor agent status repair validation"),
            ("dry_run: bool = False", "state doctor repair dry-run helper parameter"),
            ("write_state = (args.write_report or args.repair) and not args.dry_run_repair", "state doctor dry-run write suppression"),
            ("enqueue_dry_run = args.dry_run_enqueue or args.dry_run_repair", "state doctor dry-run enqueue suppression"),
            ("sync_next_actions(root, load_command_queue(root))", "state doctor repair command mirror sync"),
            ("template_repair_relatives", "state doctor template-backed core state repair list"),
            ("content.replace(\"{{PROJECT_NAME}}\", root.name)", "state doctor template placeholder replacement"),
            ("state/command_queue.json", "state doctor command queue template repair"),
            ("state/agent_status.json", "state doctor agent status template repair"),
            ("state/agent_messages.json", "state doctor agent messages template repair"),
            ("state/agent_votes.json", "state doctor agent votes template repair"),
            ("state/loop_summary.json", "state doctor loop summary template repair"),
            ("00_brief", "state doctor brief-intake placeholder repair"),
            ("02_planning", "state doctor experiment-plan placeholder repair"),
            ("data_roots.md", "state doctor data-root ledger repair"),
            ("artifact_registry.csv", "state doctor artifact-registry ledger repair"),
            ("03_experiments", "state doctor experiment-DAG placeholder repair"),
            ("experiment_dag.json", "state doctor experiment-DAG placeholder repair"),
            ("experiment_results.csv", "state doctor working-result ledger repair"),
            ("experiment_journal.csv", "state doctor experiment-journal CSV repair"),
            ("experiment_journal.md", "state doctor experiment-journal Markdown repair"),
            ("progress_hooks.jsonl", "state doctor progress-hook placeholder repair"),
            ("progress_log.md", "state doctor progress-log placeholder repair"),
            ("claim_evidence_board.md", "state doctor claim-evidence board repair"),
            ("claim_graph.json", "state doctor claim-graph placeholder repair"),
            ("terminology.md", "state doctor terminology ledger repair"),
            ("baseline_compare.md", "state doctor baseline-compare placeholder repair"),
            ("code_structure_plan.md", "state doctor code-structure-plan repair"),
            ("agent_quality_audit.md", "state doctor agent-quality-audit placeholder repair"),
            ("outputs.extend(item for item in repaired", "state doctor repaired-file status outputs"),
        )),
        (command_file("create_project.py"), (
            ("project_created", "project creation lifecycle event"),
            ("sync_project_created", "project creation lifecycle helper"),
        )),
        (import_research_repo, (
            ("def run_import", "research repo import helper"),
            ("04_code/imported_repo", "safe imported repo destination"),
            ("EXCLUDED_DIR_NAMES", "private/generated directory skip list"),
            ("record-source-path", "privacy-preserving source path option"),
            ("imported_repo_triage", "file-state next-step command"),
        )),
        (project_resume, (
            ("def build_resume", "project resume summary builder"),
            ("continuation_prompt", "project resume continuation prompt"),
            ("READ_FIRST", "project resume read-first file list"),
            ("05_results/experiment_results.csv", "project resume working result table prompt"),
            ("select_parallel_commands", "project resume parallel batch candidate selection"),
            ("Parallel Agent Batch Candidates", "project resume parallel batch section"),
            ("prepared_parallel_prompt_summary", "project resume prepared parallel prompt summary"),
            ("Prepared Or In-Progress Parallel Prompts", "project resume prepared parallel prompt section"),
            ("unfinished_dependencies", "project resume prepared dependency readiness"),
            ("is not ready to run", "project resume waiting prepared group guard"),
            ("run-prepared", "project resume prepared prompt execution guidance"),
            ("parallel_batch_manifest_summary", "project resume parallel batch manifest summary"),
            ("Parallel Batch Manifests", "project resume parallel batch manifest section"),
            ("parallel_event_summary", "project resume parallel lifecycle event summary"),
            ("Recent Parallel Lifecycle Events", "project resume parallel lifecycle event section"),
            ("status-parallel", "project resume parallel status guidance"),
            ("agent_orchestrator parallel", "project resume parallel dispatch guidance"),
        )),
    ):
        if not path.is_file():
            warnings.append(f"{path.relative_to(root)} is missing.")
            continue
        for needle, description in checks:
            require_contains(warnings, path, needle, description)
    require_contains(warnings, workflow_hooks, "register_dashboard_sources_hook", "dashboard source hook registration point")
    require_contains(
        warnings,
        commands_root / "__init__.py",
        "build_dashboard_sources",
        "dashboard source coverage hook registration",
    )
    require_contains(
        warnings,
        commands_root / "__init__.py",
        "register_report_index_hook",
        "report index hook registration",
    )
    require_contains(warnings, workflow_hooks, "refresh_workflow_surfaces", "workflow surface refresh helper")
    require_contains(warnings, workflow_hooks, "Compatibility wrapper", "legacy refresh_report_index wrapper note")
    require_contains(warnings, workflow_hooks, "include_report: bool = False", "report index refresh opt-in default")
    require_contains(warnings, workflow_hooks, "include_report", "report index opt-in flag")
    require_contains(warnings, root / "scripts" / "harness" / "report_lifecycle.py", "refresh_report: bool = False", "report lifecycle safe default")
    require_contains(warnings, root / "scripts" / "harness" / "report_lifecycle.py", "include_report=True", "report lifecycle opt-in report index refresh")
    if not dashboard_command_runner.is_file():
        warnings.append("scripts/commands/dashboard/dashboard_command_runner.py is missing.")
    else:
        require_contains(warnings, dashboard_command_runner, "ALLOWED_COMMANDS", "safe command allowlist")
        require_contains(warnings, dashboard_command_runner, "dashboard_refresh", "dashboard refresh allowlist command")
        require_contains(warnings, dashboard_command_runner, "project_closeout", "project closeout allowlist command")
        require_contains(warnings, dashboard_command_runner, "source_credibility", "source credibility allowlist command")
        require_contains(warnings, dashboard_command_runner, "experiment_diagnosis", "experiment diagnosis allowlist command")
        require_contains(warnings, dashboard_command_runner, "phase_gate_audit", "phase gate allowlist command")
        require_contains(warnings, dashboard_command_runner, "resource_ledger", "resource ledger allowlist command")
        require_contains(warnings, dashboard_command_runner, "run_checkpoints", "run checkpoint allowlist command")
        require_contains(warnings, dashboard_command_runner, "subprocess.run", "non-shell command execution")
        if '"smoke_test"' in read(dashboard_command_runner) or '"verify_harness"' in read(dashboard_command_runner):
            warnings.append("dashboard command runner should not expose heavy harness checks from the optional dashboard console.")
        if "shell=True" in read(dashboard_command_runner):
            warnings.append("scripts/commands/dashboard/dashboard_command_runner.py must not use shell=True.")

    require_contains(warnings, report_index, "from scripts.commands.reports.report_snapshot import", "shared report_snapshot import")
    require_contains(warnings, report_index, "Final Artifact Index", "final artifact report index heading")
    require_contains(warnings, report_index, "Working state belongs", "working-state exclusion note in report index")
    if "## Current Snapshot" in read(report_index) or "## Current Work" in read(report_index):
        warnings.append("scripts/commands/reports/report_index.py should not write working-state dashboard sections into 09_report/README.md.")
    if "def build_report_snapshot" in read(report_index):
        warnings.append("scripts/commands/reports/report_index.py should not define its own build_report_snapshot.")

    require_contains(warnings, agent_dashboard, "build_report_snapshot", "dashboard report snapshot usage")
    require_contains(warnings, agent_dashboard, "build_dashboard_sources", "dashboard source manifest usage")
    require_contains(warnings, agent_dashboard, "public_workspace_profile", "workspace profile dashboard API usage")
    require_contains(warnings, agent_dashboard, "run_dashboard_command", "dashboard command runner usage")
    require_contains(warnings, agent_dashboard, "--enable-command-runner", "explicit command runner opt-in")
    require_contains(warnings, agent_dashboard, 'parsed.path == "/core.js"', "dashboard core asset route")
    require_contains(warnings, agent_dashboard, 'dashboard_asset("core.js")', "dashboard core asset serving")
    if "def build_report_snapshot" in read(agent_dashboard):
        warnings.append("scripts/commands/agents/agent_dashboard.py should not define its own build_report_snapshot.")

    if not dashboard_app.is_file():
        warnings.append("dashboard/app.js is missing.")
    if not dashboard_core.is_file():
        warnings.append("dashboard/core.js is missing.")
    if not dashboard_styles.is_file():
        warnings.append("dashboard/styles.css is missing.")
    require_contains(warnings, dashboard, 'href="styles.css"', "external dashboard stylesheet")
    require_contains(warnings, dashboard, 'src="core.js"', "external dashboard core script")
    require_contains(warnings, dashboard, 'src="app.js"', "external dashboard app script")
    if "<style>" in read(dashboard) or "<script>" in read(dashboard):
        warnings.append("dashboard/index.html should keep CSS and JavaScript in external dashboard assets.")

    for needle, description in (
        ("Run Readiness Gate", "run readiness gate panel"),
        ("Research Readiness", "research readiness panel"),
        ("Command Board", "command board panel"),
        ("Blocker Triage", "blocker triage panel"),
        ("Command Console", "safe command console view"),
        ("Command Output", "safe command output panel"),
        ("Data Coverage", "dashboard data coverage panel"),
        ("Evidence Map", "evidence map panel"),
        ("Experiment Comparison", "experiment comparison panel"),
        ("Table Preview", "result table preview panel"),
        ("09_report Snapshot", "09_report snapshot panel"),
        ("Report Results", "Report Results panel"),
        ("Results and artifacts", "overview results lane"),
        ("What is blocked", "overview blocker lane"),
        ("Pipeline & Handoff", "compact pipeline/handoff panel"),
        ('data-view="results"', "Results dashboard view"),
        ('data-view="console"', "Console dashboard view"),
        ('data-view="debug"', "Debug dashboard view"),
    ):
        require_contains(warnings, dashboard, needle, description)
    if 'data-view="raw"' in read(dashboard):
        warnings.append("dashboard/index.html should expose Debug instead of the old Raw view.")
    if "Harness Health" in read(dashboard):
        warnings.append("dashboard/index.html should not expose the old Harness Health panel.")

    if dashboard_app.is_file():
        for needle, description in (
            ("renderOverviewBoard", "overview operations board renderer"),
            ("renderResearchReadiness", "research readiness renderer"),
            ("renderCommandBoard", "command board renderer"),
            ("renderCommandConsole", "command console renderer"),
            ("renderRunReadinessGate", "run readiness gate renderer"),
            ("renderEvidenceMap", "evidence map renderer"),
            ("renderExperimentComparison", "experiment comparison renderer"),
            ("renderBlockerTriage", "blocker triage renderer"),
            ("renderDataSources", "dashboard data source coverage renderer"),
            ("renderTablePreviews", "result table preview renderer"),
            ("renderReportSnapshot", "report snapshot renderer"),
            ("completedActivityFromEvents", "terminal-event completion fallback"),
            ("data-run-command", "safe command runner button wiring"),
            ("data_sources", "dashboard source manifest data flow"),
            ("report_snapshot", "report_snapshot data flow"),
            ("dashboard_refresh", "dashboard refresh console command"),
            ("project_closeout", "project closeout console command"),
            ("workspaceProfile", "workspace profile data flow"),
        ):
            require_contains(warnings, dashboard_app, needle, description)
        if "harness health" in read(dashboard_app).lower():
            warnings.append("dashboard/app.js should not surface Harness Health wording.")
    if dashboard_core.is_file():
        for needle, description in (
            ("window.DashboardCore", "dashboard core namespace"),
            ("dashboardSourceDefinitions", "dashboard source definitions"),
            ("normalizeWorkspaceProfile", "workspace profile normalization helper"),
            ("summary_language", "workspace profile summary language"),
        ):
            require_contains(warnings, dashboard_core, needle, description)
    if report_snapshot.is_file():
        require_contains(warnings, report_snapshot, "csv_table_info", "CSV preview helper for dashboard result tables")
        if "Agent Command Flow" in read(dashboard_app):
            warnings.append("dashboard/app.js should use the compact Pipeline & Handoff panel, not the old Agent Command Flow title.")
    if "Agent Command Flow" in read(dashboard):
        warnings.append("dashboard/index.html should use the compact Pipeline & Handoff panel, not the old Agent Command Flow title.")

    for filename in REQUIRED_REFRESH_SCRIPTS:
        path = command_file(filename)
        if not path.is_file():
            warnings.append(f"{path.relative_to(root)} is missing.")
            continue
        text = read(path)
        if "refresh_report_index" not in text:
            warnings.append(f"{path.relative_to(root)}: missing workflow-surface refresh hook.")
    research_loop = command_file("research_loop.py")
    for needle, description in (
        ("action_dependencies", "research loop generated command dependency metadata"),
        ("action_parallel_group", "research loop generated command parallel group metadata"),
        ("research_loop_auto", "research loop generated parallel group label"),
    ):
        require_contains(warnings, research_loop, needle, description)

    smoke_test = command_file("smoke_test.py")
    for event_type, description in (
        ("agent_message_send", "agent message event trail smoke coverage"),
        ("command_queue_update", "command queue event trail smoke coverage"),
        ("loop_summary_finish", "loop summary event trail smoke coverage"),
        ("pattern_memory_add", "pattern memory event trail smoke coverage"),
        ("session_state_finish", "session state event trail smoke coverage"),
        ("resource_ledger_record", "resource ledger record event smoke coverage"),
        ("research_loop_enqueue", "research loop enqueue event smoke coverage"),
        ("agent_orchestrator.py next --json did not expose open parallel diagnostics", "next JSON diagnostics smoke coverage"),
        ("agent_orchestrator.py parallel JSON did not expose open parallel diagnostics", "parallel planner JSON diagnostics smoke coverage"),
        ("leader_dispatch_apply", "leader dispatch apply smoke coverage"),
        ("--write-parallel-prompts", "leader dispatch apply prompt write smoke coverage"),
        ("command_queue list --json did not expose dependency readiness", "command queue JSON dependency readiness smoke coverage"),
        ("explicit parallel --id failure", "explicit parallel id failure smoke coverage"),
        ("status-parallel", "parallel status smoke coverage"),
        ("open parallel diagnostics", "parallel status diagnostics smoke coverage"),
        ("dependency_ready", "prepared dependency readiness smoke coverage"),
        ("unfinished_dependencies", "prepared unfinished dependency smoke coverage"),
        ("run-prepared", "prepared parallel prompt execution smoke coverage"),
        ("--dry-run", "prepared parallel prompt dry-run smoke coverage"),
        ("--all-prepared", "prepared all-groups dependency guard smoke coverage"),
        ("Prepared command dependencies are not done", "prepared dependency failure smoke coverage"),
        ("parallel_prepared_run", "prepared parallel prompt lifecycle smoke coverage"),
        ("parallel_prepared_runner_result", "prepared parallel runner result smoke coverage"),
        ("--runner-profile", "agent runner profile smoke coverage"),
        ("smoke_default", "default agent runner profile smoke fixture"),
        ("finish-parallel", "prepared parallel finish smoke coverage"),
        ("dry run: no command status changed", "prepared parallel finish dry-run smoke coverage"),
        ("--result-file", "prepared parallel per-command result smoke coverage"),
        ("parallel_finish", "prepared parallel finish lifecycle smoke coverage"),
        ("parallel batch manifest", "leader dispatch apply manifest smoke coverage"),
        ("baseline_library_update", "baseline library lifecycle smoke coverage"),
        ("artifact_packager", "artifact packager lifecycle smoke coverage"),
        ("--allow-incomplete", "artifact packager incomplete override smoke coverage"),
        ("gpu_add", "GPU queue lifecycle smoke coverage"),
        ("gpu_scheduler list --json did not expose dependency readiness", "GPU list JSON dependency readiness smoke coverage"),
        ("gpu_dispatch_plan", "GPU dispatch plan lifecycle smoke coverage"),
        ("plan_diagnostics", "GPU plan diagnostics smoke coverage"),
        ("unfinished_dependencies:gpu_smoke_1", "GPU unfinished dependency diagnostics smoke coverage"),
        ("GPU dispatch --ids failure did not explain", "GPU explicit dispatch failure smoke coverage"),
        ("GPU dispatch --ids max-parallel failure did not explain", "GPU explicit dispatch max-parallel smoke coverage"),
        ("GPU scheduler dry-run dispatch did not print excluded job diagnostics", "GPU dispatch dry-run diagnostics smoke coverage"),
        ("GPU scheduler dispatch --json did not expose selected jobs", "GPU dispatch JSON selected jobs smoke coverage"),
        ("GPU scheduler dispatch --json did not expose diagnostics and launch commands", "GPU dispatch JSON diagnostics smoke coverage"),
        ("gpu_scheduler refresh", "GPU lifecycle refresh smoke coverage"),
        ("gpu_refresh:succeeded", "GPU refresh run_state history smoke coverage"),
        ("Analyze why the experiment result", "GPU success analysis follow-up smoke coverage"),
        ("experiment_complete.py", "experiment completion CLI smoke coverage"),
        ("artifact_registry.csv", "experiment artifact registry smoke coverage"),
        ("Canonical Project Layout To Apply", "baseline code structure plan smoke coverage"),
        ("--write-smoke", "baseline inspect write-smoke smoke coverage"),
        ("baseline_inspect", "baseline inspect lifecycle smoke coverage"),
        ("parallel_dispatch_plan", "parallel agent dispatch smoke coverage"),
        ("parallel_smoke", "parallel agent dispatch fixture"),
        ("state_doctor.py", "state doctor smoke coverage"),
        ("project_health.py", "project health smoke coverage"),
        ("--dry-run-enqueue", "health/state doctor enqueue dry-run smoke coverage"),
        ("--dry-run-repair", "state doctor repair dry-run smoke coverage"),
        ("state doctor dry-run repair wrote a planned repair file", "state doctor repair dry-run write-leak smoke guard"),
        ("brief_intake.py", "brief intake smoke coverage"),
        ("experiment_planner.py", "experiment planner smoke coverage"),
        ("claim_graph.py", "claim graph smoke coverage"),
        ("baseline_compare.py", "baseline compare smoke coverage"),
        ("agent_quality_audit.py", "agent quality audit smoke coverage"),
    ):
        require_contains(warnings, smoke_test, event_type, description)
    require_contains(warnings, smoke_test, "include-dashboard", "optional dashboard smoke option")
    smoke_text = read(smoke_test)
    if "args.include_dashboard" not in smoke_text:
        warnings.append("scripts/commands/release/smoke_test.py should gate dashboard compatibility checks behind --include-dashboard.")
    if "run_dashboard_project_smoke" not in smoke_text:
        warnings.append("scripts/commands/release/smoke_test.py should isolate dashboard project compatibility checks in a gated helper.")
    smoke_header = "\n".join(smoke_text.splitlines()[:40])
    for module_name in (
        "agent_dashboard",
        "dashboard_command_runner",
        "dashboard_sources",
        "report_snapshot",
    ):
        if module_name in smoke_header:
            warnings.append(
                "scripts/commands/release/smoke_test.py should not import "
                f"{module_name} at module load time; keep parked dashboard checks opt-in."
            )

    verify_harness = command_file("verify_harness.py")
    result_ingest = command_file("result_ingest.py")
    if not result_ingest.is_file():
        warnings.append("scripts/commands/experiments/result_ingest.py is missing.")
    else:
        require_contains(warnings, result_ingest, "statistical_robustness.csv", "robustness result table support")
        require_contains(warnings, result_ingest, "include_report=args.final_export", "result ingest final report refresh gating")
        require_contains(warnings, result_ingest, "09_report/results/statistical_robustness.csv", "robustness final export path")
    gpu_scheduler = command_file("gpu_scheduler.py")
    if not gpu_scheduler.is_file():
        warnings.append("scripts/commands/experiments/gpu_scheduler.py is missing.")
    else:
        require_contains(warnings, gpu_scheduler, "gpu_plan_diagnostics", "GPU plan diagnostics helper")
        require_contains(warnings, gpu_scheduler, "plan_diagnostics", "GPU plan diagnostics JSON output")
        require_contains(warnings, gpu_scheduler, "gpu_job_with_readiness", "GPU list JSON dependency readiness helper")
        require_contains(warnings, gpu_scheduler, "unfinished_gpu_dependencies", "GPU unfinished dependency helper")
        require_contains(warnings, gpu_scheduler, "no_available_gpu_type", "GPU unavailable capacity diagnostic")
        require_contains(warnings, gpu_scheduler, "not_planned", "GPU explicit dispatch fallback diagnostic")
        require_contains(warnings, gpu_scheduler, "Requested jobs are not currently dispatchable", "GPU explicit dispatch failure reason")
        require_contains(warnings, gpu_scheduler, "Explicit GPU job count", "GPU explicit dispatch max-parallel guard")
        require_contains(warnings, gpu_scheduler, "dispatch --json is only supported", "GPU dispatch JSON dry-run guard")
        require_contains(warnings, gpu_scheduler, "launch_commands", "GPU dispatch JSON launch command payload")
    require_contains(warnings, smoke_test, "robustness working ingest leaked into the final robustness table", "robustness working-only smoke guard")
    require_contains(warnings, smoke_test, "robustness final export did not write the final robustness table", "robustness final-export smoke guard")
    if not project_index.is_file():
        warnings.append("scripts/commands/projects/project_index.py is missing.")
    else:
        require_contains(warnings, project_index, "PROJECT_INDEX:START", "project index marker support")
        require_contains(warnings, project_index, "def discover_inventory", "project inventory discovery helper")
    require_contains(warnings, verify_harness, "workflow_audit.py", "workflow audit verification step")
    require_contains(warnings, verify_harness, "project_index.py", "project index verification step")
    require_contains(warnings, verify_harness, "release_check.py", "release check verification step")
    require_contains(warnings, verify_harness, "privacy_audit.py", "privacy audit verification step")
    require_contains(warnings, verify_harness, "source_credibility_audit.py", "source credibility verification step")
    require_contains(warnings, verify_harness, "experiment_diagnosis.py", "experiment diagnosis verification step")
    require_contains(warnings, verify_harness, "resource_ledger.py", "resource ledger verification step")
    require_contains(warnings, verify_harness, "phase_gate.py", "phase gate verification step")
    require_contains(warnings, verify_harness, "run_checkpoint.py", "checkpoint verification step")
    require_contains(warnings, verify_harness, "progress_checkpoint.py", "progress checkpoint verification step")
    for command_name, description in (
        ("state_doctor.py", "state doctor command registry/verification awareness"),
        ("project_health.py", "project health command registry/verification awareness"),
        ("--dry-run-enqueue", "health/state doctor enqueue dry-run verification awareness"),
        ("--dry-run-repair", "state doctor repair dry-run verification awareness"),
        ("brief_intake.py", "brief intake command registry/verification awareness"),
        ("experiment_planner.py", "experiment planner command registry/verification awareness"),
        ("claim_graph.py", "claim graph command registry/verification awareness"),
        ("baseline_compare.py", "baseline compare command registry/verification awareness"),
        ("agent_quality_audit.py", "agent quality audit command registry/verification awareness"),
    ):
        require_contains(warnings, verify_harness, command_name, description)
    for needle, description in (
        ("recommended {source_label} repair", "health/state doctor source-specific done_when"),
        ("required_inputs = split_outputs", "health/state doctor suggestion-specific required inputs"),
        ("isinstance(value, list)", "health/state doctor list-valued routing fields"),
    ):
        require_contains(warnings, command_file("project_health.py"), needle, description)
    diagnostics_helper = root / "scripts" / "harness" / "project_diagnostics.py"
    for needle, description in (
        ("DIAGNOSTIC_STATE_FILES", "dashboard-free diagnostic state surface awareness"),
        ("generated_at", "diagnostic report generation timestamp"),
        ("now_utc", "diagnostic report timestamp helper"),
        ("RECENT_ACTIVITY_FILES", "diagnostic staleness activity source list"),
        ("DIAGNOSTIC_TELEMETRY_FILES", "diagnostic staleness telemetry exclusion list"),
        ("latest_activity_mtime", "diagnostic staleness helper"),
        ("relative not in telemetry_files", "diagnostic staleness telemetry exclusion"),
        ("Diagnostic surface is older than recent project progress", "diagnostic staleness issue"),
        ("state doctor first", "diagnostic refresh order guidance"),
        ("caller: str", "diagnostic caller context"),
        ("caller == \"project_health\"", "project health self-missing guard"),
        ("caller == \"state_doctor\"", "state doctor self-missing guard"),
        ("marker.lower() in lowered", "case-insensitive starter marker detection"),
        ("to_be_defined", "legacy starter marker detection"),
        ("Run state doctor repair for safe missing starter surfaces", "state/evidence diagnostic repair routing"),
        ("HANDOFF.md, state/current_state.md, state/command_queue.json", "state repair routing required inputs"),
        ("state/progress_hooks.jsonl", "diagnostic repair routing expected output"),
        ("| Owner Agent | Priority | Action | Required Inputs | Expected Outputs |", "suggested command required-input visibility"),
        ("| Command ID | Owner Agent | Priority | Action | Required Inputs | Expected Outputs |", "enqueue preview required-input visibility"),
        ("## Repaired Files", "state doctor repaired-file report section"),
        ("## Repair Errors", "state doctor repair error report section"),
        ("No repair errors.", "state doctor no repair error fallback"),
        ("repair_dry_run", "state doctor repair dry-run render flag"),
        ("Repair mode:", "state doctor repair mode rendered field"),
        ("Repair file count:", "state doctor repaired count rendered field"),
        ("Repair dry run only; no files were created.", "state doctor repair dry-run render message"),
        ("Repair dry run only; no files would be created.", "state doctor empty repair dry-run render message"),
        ("does not infer research content", "state doctor repair scope warning"),
        ("No repair files were created in this run.", "state doctor no-repair report fallback"),
    ):
        require_contains(warnings, diagnostics_helper, needle, description)
    require_contains(warnings, command_file("project_health.py"), 'caller="project_health"', "project health diagnostic caller context")
    require_contains(warnings, command_file("state_doctor.py"), 'caller="state_doctor"', "state doctor diagnostic caller context")
    require_contains(warnings, root / "README.md", "Preview state doctor repair", "README repair preview-first wording")
    require_contains(warnings, root / "README.md", "repair errors", "README repair error reporting wording")
    require_contains(warnings, root / "projects" / "template" / "README.md", "It must not invent research content", "template README repair no-inference wording")
    require_contains(warnings, root / "projects" / "template" / "README.md", "repair errors", "template README repair error reporting wording")
    require_contains(warnings, root / "scripts" / "README.md", "Repair output includes the repair mode", "scripts README repair reporting wording")
    require_contains(warnings, root / "prompts" / "skills" / "state_doctor.md", "report the repair mode", "state doctor skill repair reporting wording")
    require_contains(warnings, root / "prompts" / "skills" / "privacy_publish_audit.md", "v8.0.0", "privacy publish audit current release-check version")
    require_contains(warnings, root / "scripts" / "README.md", "--dry-run-repair", "scripts README state doctor repair preview option")
    require_contains(warnings, root / "scripts" / "README.md", "v8.0.0", "scripts README current release-check version")
    require_contains(warnings, root / "project.yaml", "Preview state_doctor repairs", "project metadata state doctor repair preview rule")
    require_contains(warnings, root / "prompts" / "skills" / "state_doctor.md", "Preview repair before writing", "state doctor repair preview-first skill rule")
    require_contains(warnings, root / "prompts" / "skills" / "state_doctor.md", "Repair must not invent research content", "state doctor repair no-inference skill rule")
    require_contains(warnings, root / "prompts" / "skills" / "state_doctor.md", "next-actions mirror should be synced", "state doctor repair mirror sync skill rule")
    require_contains(warnings, root / "prompts" / "skills" / "state_doctor.md", "validated before writing", "state doctor repair validation skill rule")
    require_contains(warnings, smoke_test, "import_research_repo.py", "research repo import smoke coverage")
    claim_evidence_board = command_file("claim_evidence_board.py")
    if not claim_evidence_board.is_file():
        warnings.append("scripts/commands/reports/claim_evidence_board.py is missing.")
    else:
        require_contains(warnings, claim_evidence_board, "--final-export", "claim board final export option")
        require_contains(warnings, claim_evidence_board, "refresh_report=final_export", "claim board final report refresh gating")
        require_contains(warnings, claim_evidence_board, "final_export=args.final_export", "claim board lifecycle final export gating")
    require_contains(warnings, smoke_test, "working write leaked a final report output", "claim board working-only smoke guard")
    require_contains(warnings, smoke_test, "final export did not sync the report-facing output", "claim board final-export smoke guard")
    require_contains(warnings, smoke_test, "--final-export", "claim board final export smoke coverage")

    validate_project = command_file("validate_project.py")
    for needle, description in (
        ("working_artifact_warnings", "project validation working artifact warnings"),
        ("v6_research_surface_warnings", "v6 research surface validation warnings"),
        ("state/project_health.md", "project health surface validation"),
        ("state/state_doctor.md", "state doctor surface validation"),
        ("pending_project_terms", "terminology starter marker validation"),
        ("is_starter_text(data_roots_text)", "data-root starter validation helper usage"),
        ("is_starter_text(terminology_text)", "terminology starter validation helper usage"),
        ("03_experiments/experiment_dag.json has no DAG plans", "experiment DAG/result consistency warning"),
        ("05_results/claim_graph.json has no claim/evidence graph", "claim graph/result consistency warning"),
        ("05_results/experiment_results.csv has rows", "working result/journal consistency warning"),
        ("Succeeded experiment run_state entries exist", "succeeded run/result table consistency warning"),
        ("06_writing/terminology.md still contains starter placeholders", "terminology starter validation warning"),
        ("Baseline source snapshots exist", "baseline snapshot comparison validation warning"),
        ("Baseline structure reports exist", "baseline structure plan validation warning"),
        ("code_structure_plan.md", "baseline code structure plan validation"),
        ("parallel_batch_manifest_warnings", "parallel batch manifest validation"),
        ("prompt path is missing", "parallel batch prompt path validation"),
    ):
        require_contains(warnings, validate_project, needle, description)

    artifact_packager = command_file("artifact_packager.py")
    for needle, description in (
        ("REQUIRED_ARTIFACTS", "artifact packager required working artifacts"),
        ("--allow-incomplete", "artifact packager explicit incomplete package override"),
        ("03_experiments/data_roots.md", "artifact packager data-root requirement"),
        ("03_experiments/artifact_registry.csv", "artifact packager artifact-registry requirement"),
        ("05_results/experiment_journal.csv", "artifact packager experiment-journal requirement"),
        ("06_writing/terminology.md", "artifact packager terminology requirement"),
    ):
        require_contains(warnings, artifact_packager, needle, description)

    baseline_intake = command_file("baseline_intake.py")
    for needle, description in (
        ("Canonical Project Layout To Apply", "baseline-informed canonical project layout"),
        ("04_code/src/data/", "baseline structure data module recommendation"),
        ("04_code/src/evaluation/", "baseline structure evaluation module recommendation"),
        ("args.write_smoke", "inspect write-smoke smoke script behavior"),
        ("08_baselines/run_scripts", "baseline smoke script destination"),
    ):
        require_contains(warnings, baseline_intake, needle, description)

    if not privacy_audit.is_file():
        warnings.append("scripts/commands/release/privacy_audit.py is missing.")
    else:
        for needle, description in (
            ("def audit_privacy", "privacy audit helper"),
            ("private_project_markers", "private project marker discovery"),
            ("git ls-files", "publishable file discovery"),
        ):
            require_contains(warnings, privacy_audit, needle, description)

    check_publishable = command_file("check_publishable.py")
    require_contains(warnings, check_publishable, "audit_privacy", "publishable check privacy audit usage")

    release_check = command_file("release_check.py")
    if not release_check.is_file():
        warnings.append("scripts.commands.release.release_check is missing.")
    else:
        require_contains(warnings, release_check, "verify_harness.py", "full harness verification step")
        require_contains(warnings, release_check, "strict-template-state", "strict template state release option")
        require_contains(warnings, release_check, "include-dashboard", "optional dashboard release option")
        require_contains(warnings, release_check, "audit_privacy", "release privacy audit usage")
    if verify_harness.is_file():
        require_contains(warnings, verify_harness, "include-dashboard", "optional dashboard verify option")
        if "args.include_dashboard" not in read(verify_harness):
            warnings.append("scripts/commands/release/verify_harness.py should gate optional dashboard syntax checks behind --include-dashboard.")
        require_contains(
            warnings,
            verify_harness,
            'smoke_test.py", *(["--include-dashboard"]',
            "optional dashboard smoke propagation",
        )

    leader_dispatch = command_file("leader_dispatch.py")
    if not leader_dispatch.is_file():
        warnings.append("scripts/commands/review/leader_dispatch.py is missing.")
    else:
        require_contains(warnings, leader_dispatch, "parse_leader_dispatch_blocks", "leader dispatch parser")
        require_contains(warnings, leader_dispatch, "validate_text", "leader dispatch validator")
        require_contains(warnings, leader_dispatch, "apply_dispatch_block", "leader dispatch command queue apply helper")
        require_contains(warnings, leader_dispatch, "dispatch_parallel_groups", "leader dispatch parallel group hint helper")
        require_contains(warnings, leader_dispatch, "write_parallel_prompts_for_groups", "leader dispatch parallel prompt writer")
        require_contains(warnings, leader_dispatch, "--write-parallel-prompts", "leader dispatch parallel prompt write option")
        require_contains(warnings, leader_dispatch, "run prepared hint", "leader dispatch prepared prompt execution hint")
        require_contains(warnings, leader_dispatch, "leader_dispatch_apply", "leader dispatch apply lifecycle event")

    worker_result = command_file("worker_result.py")
    if not worker_result.is_file():
        warnings.append("scripts/commands/review/worker_result.py is missing.")
    else:
        require_contains(warnings, worker_result, "parse_worker_result_blocks", "worker result parser")
        require_contains(warnings, worker_result, "validate_text", "worker result validator")

    dashboard_skill = root / "prompts" / "skills" / "dashboard_refresh.md"
    if not dashboard_skill.is_file():
        warnings.append("prompts/skills/dashboard_refresh.md is missing.")
    else:
        require_contains(warnings, dashboard_skill, "scripts.commands.dashboard.dashboard_refresh", "dashboard refresh command in skill")
        require_contains(warnings, dashboard_skill, "Do not hand-edit", "state-editing safety rule")
    require_contains(warnings, root / "prompts" / "skills" / "README.md", "dashboard_refresh.md", "dashboard refresh skill listing")
    require_contains(warnings, root / "prompts" / "shared" / "skill_usage.md", "dashboard_refresh.md", "dashboard refresh shared skill mapping")
    for skill_name in (
        "agent_orchestration.md",
        "agent_quality_audit.md",
        "artifact_packaging.md",
        "baseline_compare.md",
        "brief_intake.md",
        "claim_and_result_evidence.md",
        "claim_graph.md",
        "claim_table_backfill.md",
        "context_budgeting.md",
        "experiment_completion.md",
        "experiment_planning.md",
        "experiment_repair.md",
        "experiment_smoke_first.md",
        "fast_baseline_intake.md",
        "gpu_parallel_execution.md",
        "literature_review.md",
        "paper_claim_compression.md",
        "performance_measurement.md",
        "phase_gate.md",
        "privacy_publish_audit.md",
        "progress_checkpoint.md",
        "project_closeout.md",
        "project_health.md",
        "project_hygiene.md",
        "report_hygiene.md",
        "research_repo_import.md",
        "resource_ledger.md",
        "reviewer_risk_matrix.md",
        "run_checkpoint.md",
        "skill_synthesis.md",
        "source_credibility_audit.md",
        "state_doctor.md",
        "weekly_deck.md",
        "workflow_state_reconcile.md",
        "workspace_profile.md",
    ):
        skill_path = root / "prompts" / "skills" / skill_name
        if not skill_path.is_file():
            warnings.append(f"prompts/skills/{skill_name} is missing.")
            continue
        require_contains(warnings, root / "prompts" / "skills" / "README.md", skill_name, f"{skill_name} skill listing")
        require_contains(warnings, root / "prompts" / "shared" / "skill_usage.md", skill_name, f"{skill_name} shared skill mapping")

    agent_skills_dir = root / ".claude" / "skills"
    if not agent_skills_dir.is_dir():
        warnings.append(".claude/skills/ is missing.")
    else:
        for skill_dir in sorted(p for p in agent_skills_dir.iterdir() if p.is_dir()):
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.is_file():
                warnings.append(f".claude/skills/{skill_dir.name}/SKILL.md is missing.")
                continue
            text = skill_md.read_text(encoding="utf-8")
            front_matter = ""
            if text.startswith("---"):
                parts = text.split("---", 2)
                if len(parts) >= 3:
                    front_matter = parts[1]
            declared_name = ""
            for line in front_matter.splitlines():
                if line.strip().startswith("name:"):
                    declared_name = line.split(":", 1)[1].strip()
                    break
            if declared_name != skill_dir.name:
                warnings.append(
                    f".claude/skills/{skill_dir.name}/SKILL.md front-matter name should match the directory name."
                )
            require_contains(
                warnings, root / "docs" / "installed_agent_skills.md", skill_dir.name,
                f"{skill_dir.name} installed agent skill row")
            require_contains(
                warnings, root / "README.md", skill_dir.name,
                f"{skill_dir.name} README agent skill mention")

    orchestrator = command_file("agent_orchestrator.py")
    for needle, description in (
        ("parallel", "parallel agent orchestrator subcommand"),
        ("status-parallel", "parallel status read-only subcommand"),
        ("read_only", "parallel status read-only JSON metadata"),
        ("scope", "parallel command scope JSON metadata"),
        ("open_parallel_diagnostics", "parallel status exclusion diagnostics metadata"),
        ("parallel_command_diagnostics", "parallel command exclusion diagnostics helper"),
        ("parallel_readiness_reasons", "parallel explicit command readiness helper"),
        ("not safe for parallel dispatch", "parallel explicit command failure reason"),
        ("Explicit parallel command count", "parallel explicit command max-agent guard"),
        ("missing_expected_outputs", "parallel diagnostics missing output reason"),
        ("owner_already_selected", "parallel diagnostics duplicate owner reason"),
        ("path_conflict", "parallel diagnostics path conflict reason"),
        ("expected_outputs", "parallel JSON output boundary metadata"),
        ("dependency_ready", "prepared parallel dependency readiness metadata"),
        ("unfinished_dependencies", "prepared parallel unfinished dependency metadata"),
        ("prepared_parallel_commands", "prepared parallel status helper"),
        ("select_parallel_commands", "parallel command selection helper"),
        ("PARALLEL_MANAGED_STATE_PATHS", "managed checkpoint paths excluded from parallel conflicts"),
        ("command_substantive_path_set", "substantive output conflict helper"),
        ("parallel_commands", "parallel candidates in next JSON output"),
        ("open_parallel_diagnostics", "parallel diagnostics in next/status/parallel JSON output"),
        ("Parallel batch available", "parallel candidates in next text output"),
        ("parallel_dispatch_plan", "parallel dispatch lifecycle event"),
        ("parallel_batches", "parallel batch manifest directory"),
        ("run-prepared", "prepared parallel prompt execution subcommand"),
        ("--dry-run", "prepared parallel prompt dry-run option"),
        ("--all-prepared", "prepared parallel explicit all-groups option"),
        ("fail_on_unfinished_dependencies", "all-prepared dependency readiness guard"),
        ("Prepared command is not in progress", "prepared explicit id strict status guard"),
        ("Prepared command has no orchestrator_prompt", "prepared explicit id prompt guard"),
        ("Prepared command dependencies are not done", "prepared dependency readiness guard"),
        ("finish-parallel", "prepared parallel batch finish subcommand"),
        ("dry run: no command status changed", "prepared parallel finish dry-run output"),
        ("--result-file", "prepared parallel per-command result evidence option"),
        ("merged_output_paths", "prepared parallel result output merge helper"),
        ("finish-parallel --status done requires --note, --output, or --result-file evidence", "prepared parallel finish evidence guard"),
        ("finish-parallel --status blocked/deferred requires --note explaining the reason", "prepared parallel blocked/deferred reason guard"),
        ("parallel_finish", "prepared parallel batch finish lifecycle event"),
        ("parallel_prepared_run", "prepared parallel prompt lifecycle event"),
        ("parallel_runner_result", "parallel runner result lifecycle event"),
        ("parallel_prepared_runner_result", "prepared parallel runner result lifecycle event"),
        ("execute_and_record_parallel_result", "parallel runner result wrapper"),
        ("execute_parallel_runners", "parallel external runner execution helper"),
    ):
        require_contains(warnings, orchestrator, needle, description)
    command_queue = command_file("command_queue.py")
    for needle, description in (
        ("--depends-on", "command queue dependency metadata option"),
        ("--parallel-group", "command queue parallel group option"),
        ("--verbose", "command queue verbose dependency listing option"),
        ("depends_on=", "command queue verbose dependency output"),
        ("dependency_ready=", "command queue verbose dependency readiness output"),
        ("unfinished=", "command queue verbose unfinished dependency output"),
        ("command_with_readiness", "command queue JSON dependency readiness helper"),
        ("unfinished_dependencies", "command queue JSON unfinished dependency output"),
    ):
        require_contains(warnings, command_queue, needle, description)
    require_contains(warnings, root / "scripts" / "harness" / "state.py", "depends_on", "command queue dependency validation")
    require_contains(warnings, root / "scripts" / "harness" / "state.py", "depends on unknown command id", "command queue unknown dependency validation")
    require_contains(warnings, root / "scripts" / "harness" / "state.py", "has duplicate dependency", "command queue duplicate dependency validation")
    require_contains(warnings, root / "scripts" / "harness" / "state.py", "Command dependency cycle detected", "command queue dependency cycle validation")
    require_contains(warnings, root / "scripts" / "harness" / "command_mirror.py", "Depends On", "next actions dependency mirror column")
    require_contains(warnings, root / "scripts" / "harness" / "command_mirror.py", "Parallel Group", "next actions parallel group mirror column")
    require_contains(warnings, root / "scripts" / "harness" / "command_mirror.py", "state/project_health.md", "next actions suggested prompt health read-first")
    require_contains(warnings, root / "scripts" / "harness" / "command_mirror.py", "state/state_doctor.md", "next actions suggested prompt state doctor read-first")
    require_contains(warnings, root / "scripts" / "harness" / "command_mirror.py", "older than recent project progress", "next actions stale diagnostic refresh prompt")
    require_contains(warnings, root / "scripts" / "harness" / "command_mirror.py", "--dry-run-repair", "next actions suggested prompt repair preview")
    require_contains(warnings, root / "scripts" / "harness" / "command_mirror.py", "status-parallel", "next actions parallel status prompt")
    require_contains(warnings, root / "scripts" / "harness" / "command_mirror.py", "ready scoped group", "next actions prepared readiness prompt")
    require_contains(warnings, root / "scripts" / "harness" / "command_mirror.py", "silently skipping unsafe commands", "next actions explicit parallel id prompt")
    require_contains(warnings, root / "project.yaml", "parallel_agents", "parallel agent operating rule")
    require_contains(warnings, root / "project.yaml", "run-prepared", "prepared parallel prompt operating rule")
    require_contains(warnings, root / "prompts" / "skills" / "agent_orchestration.md", "agent_orchestrator parallel", "parallel agent orchestration skill")
    for relative in REQUIRED_ORCHESTRATION_DOCS:
        path = root / relative
        if not path.is_file():
            warnings.append(f"{relative} is missing.")
            continue
        require_contains(warnings, orchestrator, Path(relative).name, f"{Path(relative).name} in orchestrator prompts")
        require_contains(warnings, root / "prompts" / "shared" / "output_contracts.md", relative, f"{relative} in output contracts")
    leader_dispatch = command_file("leader_dispatch.py")
    for needle, description in (
        ("parse_worker_entries", "leader dispatch worker metadata parser"),
        ("apply_dispatch_block", "leader dispatch command queue apply helper"),
        ("parallel hint", "leader dispatch apply parallel command hint"),
        ("--write-parallel-prompts", "leader dispatch apply prompt write option"),
        ("depends_on", "leader dispatch dependency metadata validation"),
        ("expected_outputs", "leader dispatch expected output metadata validation"),
        ("parallel_group", "leader dispatch parallel group metadata validation"),
    ):
        require_contains(warnings, leader_dispatch, needle, description)
    require_contains(warnings, root / "prompts" / "shared" / "leader_dispatch_protocol.md", "workers[].depends_on", "leader dispatch dependency field documentation")
    require_contains(warnings, root / "prompts" / "shared" / "leader_dispatch_protocol.md", "workers[].expected_outputs", "leader dispatch expected outputs documentation")

    dashboard_warnings = [warning for warning in warnings if is_dashboard_warning(warning)]
    active_warnings = warnings if include_dashboard else [
        warning for warning in warnings if not is_dashboard_warning(warning)
    ]
    return {
        "ok": not active_warnings,
        "warnings": active_warnings,
        "dashboard_warnings": dashboard_warnings,
        "dashboard_audit": "included" if include_dashboard else "optional_skipped",
        "checked_refresh_scripts": list(REQUIRED_REFRESH_SCRIPTS),
        "checked_orchestration_docs": list(REQUIRED_ORCHESTRATION_DOCS),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit workflow wiring consistency.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable audit result.")
    parser.add_argument(
        "--include-dashboard",
        action="store_true",
        help="Treat optional dashboard compatibility warnings as release-blocking.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = audit(include_dashboard=args.include_dashboard)
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        if result["ok"]:
            print("workflow audit OK")
            if result.get("dashboard_warnings") and not args.include_dashboard:
                print("dashboard compatibility warnings skipped; pass --include-dashboard to enforce them.")
        else:
            for warning in result["warnings"]:
                print(f"warning: {warning}")
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
