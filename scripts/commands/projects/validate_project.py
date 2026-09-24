#!/usr/bin/env python3
"""Validate a project state harness."""

from __future__ import annotations

import argparse
import csv
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from scripts.commands.experiments.preregistration_helper import audit_preregistration, placeholder_after
from scripts.harness.state import (
    HarnessError,
    agent_messages_path,
    agent_votes_path,
    baseline_registry_path,
    command_has_approved_vote,
    discover_run_states,
    gpu_queue_path,
    load_agent_status,
    load_agent_events,
    load_agent_messages,
    load_agent_votes,
    load_baseline_registry,
    load_command_queue,
    load_gpu_queue,
    load_loop_summary,
    load_pattern_memory,
    load_ralph_loop,
    load_review_form_registry,
    loop_summary_path,
    owner_matches,
    pattern_memory_path,
    project_root,
    ralph_loop_path,
    review_form_registry_path,
    validate_agent_status_doc,
    validate_agent_messages_doc,
    validate_agent_votes_doc,
    validate_agent_events,
    validate_baseline_registry_doc,
    validate_command_queue_doc,
    validate_gpu_queue_doc,
    validate_loop_summary_doc,
    validate_pattern_memory_doc,
    validate_ralph_loop_doc,
    validate_review_form_registry_doc,
    validate_run_state_doc,
)

PROGRESS_CHECKPOINT_KINDS = {
    "observation",
    "result",
    "experiment_result",
    "memory",
    "direction",
    "blocker",
    "handoff",
}

V6_RESEARCH_SURFACES = [
    "state/project_health.md",
    "state/state_doctor.md",
    "00_brief/intake_wizard.md",
    "02_planning/experiment_plan.md",
    "03_experiments/experiment_dag.json",
    "05_results/claim_graph.md",
    "05_results/claim_graph.json",
    "08_baselines/baseline_compare.md",
    "07_reviews/agent_quality_audit.md",
]

STARTER_MARKERS = (
    "not yet generated",
    "not yet refreshed",
    "has not been generated yet",
    "no experiment family has been planned yet",
    "pending_project_terms",
    "to_be_defined",
)

USER_VOTER_ALIASES = {"user", "user_explicit_instruction"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate project state JSON files.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--strict", action="store_true", help="Fail when validation warnings are present.")
    parser.add_argument(
        "--check-paper-build",
        action="store_true",
        help="Also compile 09_report/paper/main.tex when xelatex, latexmk, or pdflatex is available.",
    )
    return parser.parse_args()


def read_text(path) -> str:
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def current_stage(root) -> str:
    lines = read_text(root / "state" / "current_state.md").splitlines()
    for index, line in enumerate(lines):
        if line.strip().lower() == "## current stage":
            for candidate in lines[index + 1 :]:
                stripped = candidate.strip().strip("`").lower()
                if stripped:
                    return stripped
    return ""


def latest_mtime(paths) -> float:
    existing = [path for path in paths if path.exists()]
    if not existing:
        return 0.0
    mtimes = []
    for path in existing:
        try:
            mtimes.append(path.stat().st_mtime)
        except OSError:
            continue
    return max(mtimes, default=0.0)


def csv_header(path) -> list[str]:
    if not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            try:
                return next(csv.reader(handle))
            except StopIteration:
                return []
    except OSError:
        return []


def csv_rows(path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return [
                {str(key or "").strip(): str(value or "").strip() for key, value in row.items()}
                for row in csv.DictReader(handle)
                if any(str(value or "").strip() for value in row.values())
            ]
    except OSError:
        return []


def nonstarter_experiment_journal_rows(root) -> int:
    count = 0
    for row in csv_rows(root / "05_results" / "experiment_journal.csv"):
        experiment = str(row.get("experiment") or "").strip()
        result_summary = str(row.get("result_summary") or "").strip().lower()
        updated_at = str(row.get("updated_at") or "").strip()
        if experiment == "exp_001" and result_summary == "planned" and not updated_at:
            continue
        count += 1
    return count


def report_table_path(root, filename: str) -> Path:
    report = root / "09_report"
    preferred = report / "results" / filename
    fallback = report / "src" / "results" / filename
    if preferred.is_file() or not fallback.is_file():
        return preferred
    return fallback


def split_reference_list(value: str) -> list[str]:
    refs: list[str] = []
    for chunk in str(value or "").replace(";", ",").split(","):
        stripped = chunk.strip()
        if stripped:
            refs.append(stripped)
    return refs


def csv_header_warnings(root, path, expected: list[str]) -> list[str]:
    if not path.is_file():
        return []
    header = csv_header(path)
    if header == expected:
        return []
    return [
        f"{path.relative_to(root)} has unexpected header. Expected: {', '.join(expected)}."
    ]


def json_rows(path, key: str) -> list[dict]:
    if not path.is_file():
        return []
    try:
        data = json.loads(read_text(path))
    except json.JSONDecodeError:
        return []
    rows = data.get(key, []) if isinstance(data, dict) else []
    return [row for row in rows if isinstance(row, dict)]


def registry_id_set(path, key: str) -> set[str]:
    return {
        str(row.get("id") or "").strip()
        for row in json_rows(path, key)
        if str(row.get("id") or "").strip()
    }


def markdown_section_warnings(root, path, required_sections: list[str]) -> list[str]:
    if not path.is_file():
        return [f"Missing research rigor file: {path.relative_to(root)}."]
    text = read_text(path).lower()
    warnings: list[str] = []
    for section in required_sections:
        if section.lower() not in text:
            warnings.append(f"{path.relative_to(root)} is missing section: {section}.")
    return warnings


def project_handoff_warnings(root) -> list[str]:
    path = root / "HANDOFF.md"
    if not path.is_file():
        return ["Missing project-local HANDOFF.md."]
    text = read_text(path)
    warnings: list[str] = []
    for section in [
        "## Current Goal",
        "## Validation Status",
        "## Remaining Blockers",
        "## Next Best Command",
    ]:
        if section not in text:
            warnings.append(f"HANDOFF.md is missing section: {section}.")
    return warnings


def file_state_markdown_warnings(root) -> list[str]:
    warnings: list[str] = []
    for relative in [
        "state/current_state.md",
        "state/agent_memory.md",
        "state/next_actions.md",
        "state/open_questions.md",
    ]:
        path = root / relative
        if not path.is_file():
            warnings.append(f"Missing file-state continuation artifact: {relative}.")
        elif not read_text(path).strip():
            warnings.append(f"File-state continuation artifact is empty: {relative}.")
    return warnings


def normalized_text(value: object) -> str:
    return " ".join(str(value or "").lower().split())


def next_actions_mirror_warnings(root, queue: dict) -> list[str]:
    path = root / "state" / "next_actions.md"
    if not path.is_file():
        return []
    text = normalized_text(read_text(path))
    warnings: list[str] = []
    active_statuses = {"open", "in progress", "blocked", "deferred"}
    for command in queue.get("commands", []):
        if not isinstance(command, dict):
            continue
        status = str(command.get("status") or "").strip().lower()
        if status not in active_statuses:
            continue
        command_id = str(command.get("id") or "").strip()
        candidates = [
            command_id,
            str(command.get("display_summary") or "").strip(),
            str(command.get("action") or "").strip(),
        ]
        if not any(normalized_text(candidate) and normalized_text(candidate) in text for candidate in candidates):
            warnings.append(f"Active command {command_id or '<missing id>'} is not mirrored in state/next_actions.md.")
    return warnings


def template_hygiene_warnings(root, ralph_loop: dict) -> list[str]:
    if root.name != "template":
        return []
    warnings: list[str] = []
    required_template_files = [
        "03_experiments/data_roots.md",
        "03_experiments/artifact_registry.csv",
        "05_results/experiment_results.csv",
        "05_results/experiment_journal.md",
        "05_results/experiment_journal.csv",
        "06_writing/terminology.md",
    ]
    for relative in required_template_files:
        if not (root / relative).is_file():
            warnings.append(f"Template is missing required working artifact: {relative}.")
    if ralph_loop.get("project") != "{{PROJECT_NAME}}":
        warnings.append("Template state/ralph_loop.json should keep project as {{PROJECT_NAME}}.")
    if ralph_loop.get("runs"):
        warnings.append("Template state/ralph_loop.json should not contain completed or cancelled run history.")
    if load_agent_events(root):
        warnings.append("Template state/agent_events.jsonl should not contain generated event history.")
    progress_hooks = root / "state" / "progress_hooks.jsonl"
    if progress_hooks.is_file() and read_text(progress_hooks).strip():
        warnings.append("Template state/progress_hooks.jsonl should not contain generated progress history.")
    progress_log = root / "state" / "sessions" / "progress_log.md"
    if progress_log.is_file() and read_text(progress_log).strip():
        warnings.append("Template state/sessions/progress_log.md should not contain generated progress history.")
    limit_handoff = root / "state" / "limit_handoff.md"
    if limit_handoff.is_file() and read_text(limit_handoff).strip():
        warnings.append("Template state/limit_handoff.md should not contain generated limit handoff history.")
    prompt_dir = root / "state" / "ralph_prompts"
    prompt_files = sorted(prompt_dir.glob("*.md")) if prompt_dir.is_dir() else []
    if prompt_files:
        warnings.append("Template state/ralph_prompts/ should not contain generated prompt files.")
    sessions_dir = root / "state" / "sessions"
    session_dirs = sorted(path for path in sessions_dir.iterdir() if path.is_dir()) if sessions_dir.is_dir() else []
    if session_dirs:
        names = ", ".join(path.name for path in session_dirs)
        warnings.append(f"Template state/sessions/ should contain only README.md, found session dirs: {names}.")
    lock_files = sorted(path.relative_to(root).as_posix() for path in (root / "state").rglob("*.lock"))
    if lock_files:
        warnings.append(f"Template state/ should not contain lock files: {', '.join(lock_files)}.")
    return warnings


def working_artifact_warnings(root, run_states: list[dict]) -> list[str]:
    warnings: list[str] = []
    required = [
        "03_experiments/data_roots.md",
        "03_experiments/artifact_registry.csv",
        "05_results/experiment_results.csv",
        "05_results/experiment_journal.md",
        "05_results/experiment_journal.csv",
        "06_writing/terminology.md",
    ]
    for relative in required:
        path = root / relative
        if not path.is_file():
            warnings.append(f"Missing required working artifact: {relative}.")
        elif not read_text(path).strip():
            warnings.append(f"Required working artifact is empty: {relative}.")
    if root.name == "template":
        return warnings

    data_roots_text = read_text(root / "03_experiments" / "data_roots.md")
    if is_starter_text(data_roots_text):
        warnings.append("03_experiments/data_roots.md still contains starter placeholders.")
    terminology_text = read_text(root / "06_writing" / "terminology.md")
    if is_starter_text(terminology_text):
        warnings.append("06_writing/terminology.md still contains starter placeholders.")
    working_rows = csv_rows(root / "05_results" / "experiment_results.csv")
    artifact_rows = csv_rows(root / "03_experiments" / "artifact_registry.csv")
    if working_rows and not artifact_rows:
        warnings.append(
            "05_results/experiment_results.csv has rows but 03_experiments/artifact_registry.csv has no artifact rows."
        )
    if working_rows and nonstarter_experiment_journal_rows(root) == 0:
        warnings.append(
            "05_results/experiment_results.csv has rows but the experiment journal has no non-starter explanation rows."
        )
    succeeded_runs = [
        run_state for run_state in run_states
        if str(run_state.get("status") or "").strip().lower() == "succeeded"
    ]
    if succeeded_runs and not working_rows:
        warnings.append("Succeeded experiment run_state entries exist but 05_results/experiment_results.csv has no working result rows.")
    return warnings


def is_starter_text(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in STARTER_MARKERS)


def load_json_with_warning(root, relative: str) -> tuple[list[str], object | None]:
    path = root / relative
    if not path.is_file():
        return [], None
    try:
        return [], json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        return [f"{relative} is invalid JSON: {exc.msg}."], None


def baseline_snapshot_ids(root) -> list[str]:
    snapshot_root = root / "08_baselines" / "source_snapshots"
    if not snapshot_root.is_dir():
        return []
    ids: list[str] = []
    for path in sorted(snapshot_root.iterdir()):
        if path.name in {"README.md", ".gitkeep"}:
            continue
        if path.is_dir() and any(path.iterdir()):
            ids.append(path.name)
    return ids


def v6_research_surface_warnings(root, run_states: list[dict]) -> list[str]:
    warnings: list[str] = []
    for relative in V6_RESEARCH_SURFACES:
        path = root / relative
        if not path.is_file():
            warnings.append(f"Missing v6 research surface: {relative}.")
            continue
        if path.suffix != ".json" and not read_text(path).strip():
            warnings.append(f"V6 research surface is empty: {relative}.")

    dag_warnings, dag = load_json_with_warning(root, "03_experiments/experiment_dag.json")
    warnings.extend(dag_warnings)
    dag_plans: list[dict] = []
    if isinstance(dag, dict):
        plans = dag.get("plans", [])
        if not isinstance(plans, list):
            warnings.append("03_experiments/experiment_dag.json plans must be a list.")
        else:
            dag_plans = [plan for plan in plans if isinstance(plan, dict)]
            for index, plan in enumerate(plans):
                if not isinstance(plan, dict):
                    warnings.append(f"03_experiments/experiment_dag.json plans[{index}] must be an object.")
                    continue
                if root.name == "template":
                    continue
                if not str(plan.get("id") or "").strip():
                    warnings.append(f"03_experiments/experiment_dag.json plans[{index}] is missing id.")
                if not str(plan.get("smoke_test") or plan.get("smoke_command") or "").strip():
                    warnings.append(
                        f"03_experiments/experiment_dag.json plan {plan.get('id') or index} has no smoke test command."
                    )
                if not isinstance(plan.get("exp_ids", []), list):
                    warnings.append(
                        f"03_experiments/experiment_dag.json plan {plan.get('id') or index} exp_ids must be a list."
                    )
    elif dag is not None:
        warnings.append("03_experiments/experiment_dag.json must be a JSON object.")

    graph_warnings, graph = load_json_with_warning(root, "05_results/claim_graph.json")
    warnings.extend(graph_warnings)
    graph_nodes: list[dict] = []
    graph_edges: list[dict] = []
    if isinstance(graph, dict):
        nodes = graph.get("nodes", [])
        edges = graph.get("edges", [])
        if not isinstance(nodes, list):
            warnings.append("05_results/claim_graph.json nodes must be a list.")
            nodes = []
        if not isinstance(edges, list):
            warnings.append("05_results/claim_graph.json edges must be a list.")
            edges = []
        graph_nodes = [node for node in nodes if isinstance(node, dict)]
        graph_edges = [edge for edge in edges if isinstance(edge, dict)]
        node_ids = {
            str(node.get("id") or "").strip()
            for node in graph_nodes
            if str(node.get("id") or "").strip()
        }
        for index, node in enumerate(nodes):
            if not isinstance(node, dict):
                warnings.append(f"05_results/claim_graph.json nodes[{index}] must be an object.")
                continue
            if not str(node.get("id") or "").strip():
                warnings.append(f"05_results/claim_graph.json nodes[{index}] is missing id.")
        for index, edge in enumerate(edges):
            if not isinstance(edge, dict):
                warnings.append(f"05_results/claim_graph.json edges[{index}] must be an object.")
                continue
            source = str(edge.get("source") or "").strip()
            target = str(edge.get("target") or "").strip()
            if not source or not target:
                warnings.append(f"05_results/claim_graph.json edges[{index}] is missing source or target.")
            elif node_ids and (source not in node_ids or target not in node_ids):
                warnings.append(f"05_results/claim_graph.json edges[{index}] references an unknown node.")
    elif graph is not None:
        warnings.append("05_results/claim_graph.json must be a JSON object.")

    if root.name == "template":
        return warnings

    working_rows = csv_rows(root / "05_results" / "experiment_results.csv")
    report_rows = csv_rows(report_table_path(root, "experiment_results.csv"))
    result_rows = working_rows or report_rows
    succeeded_runs = [
        run_state for run_state in run_states
        if str(run_state.get("status") or "").strip().lower() == "succeeded"
    ]
    has_project_activity = bool(
        result_rows
        or succeeded_runs
        or nonstarter_experiment_journal_rows(root)
        or read_text(root / "state" / "progress_hooks.jsonl").strip()
    )
    if result_rows and not dag_plans:
        warnings.append("Experiment result rows exist but 03_experiments/experiment_dag.json has no DAG plans.")
    if succeeded_runs and not dag_plans:
        warnings.append("Succeeded experiment run_state entries exist but 03_experiments/experiment_dag.json has no DAG plans.")
    if result_rows and (not graph_nodes or not graph_edges):
        warnings.append("Experiment result rows exist but 05_results/claim_graph.json has no claim/evidence graph nodes and edges.")

    if has_project_activity:
        for relative in (
            "state/project_health.md",
            "state/state_doctor.md",
            "00_brief/intake_wizard.md",
            "02_planning/experiment_plan.md",
            "05_results/claim_graph.md",
            "07_reviews/agent_quality_audit.md",
        ):
            path = root / relative
            if path.is_file() and is_starter_text(read_text(path)):
                warnings.append(f"{relative} still looks like a starter surface; refresh it for this project.")

    snapshot_ids = baseline_snapshot_ids(root)
    baseline_compare = root / "08_baselines" / "baseline_compare.md"
    if snapshot_ids and (not baseline_compare.is_file() or not read_text(baseline_compare).strip()):
        warnings.append("Baseline source snapshots exist but 08_baselines/baseline_compare.md is missing or empty.")
    elif snapshot_ids and is_starter_text(read_text(baseline_compare)):
        warnings.append("Baseline source snapshots exist but 08_baselines/baseline_compare.md still looks like a starter surface.")
    compare_text = read_text(baseline_compare)
    for baseline_id in snapshot_ids:
        if baseline_id not in compare_text:
            warnings.append(f"Baseline source snapshot {baseline_id} is not reflected in 08_baselines/baseline_compare.md.")
    return warnings


def progress_checkpoint_warnings(root) -> list[str]:
    warnings: list[str] = []
    path = root / "state" / "progress_hooks.jsonl"
    if not path.exists():
        return warnings
    for line_number, line in enumerate(read_text(path).splitlines(), start=1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as exc:
            warnings.append(f"state/progress_hooks.jsonl line {line_number} is invalid JSON: {exc.msg}.")
            continue
        if not isinstance(record, dict):
            warnings.append(f"state/progress_hooks.jsonl line {line_number} must be a JSON object.")
            continue
        for field in ("timestamp", "project", "agent", "kind", "summary"):
            if not str(record.get(field) or "").strip():
                warnings.append(f"state/progress_hooks.jsonl line {line_number} is missing {field}.")
        kind = str(record.get("kind") or "")
        if kind and kind not in PROGRESS_CHECKPOINT_KINDS:
            warnings.append(f"state/progress_hooks.jsonl line {line_number} has invalid kind: {kind}.")
        for list_field in ("details", "evidence", "outputs", "memory_notes", "next_actions", "open_questions"):
            value = record.get(list_field, [])
            if value is not None and not isinstance(value, list):
                warnings.append(f"state/progress_hooks.jsonl line {line_number} field {list_field} must be a list.")
        for path_field in ("evidence", "outputs"):
            values = record.get(path_field, [])
            if not isinstance(values, list):
                continue
            for item in values:
                text = str(item or "")
                if "/" not in text and "." not in Path(text).name:
                    continue
                candidate = Path(text)
                if candidate.is_absolute() or ".." in candidate.parts:
                    warnings.append(
                        f"state/progress_hooks.jsonl line {line_number} field {path_field} has unsafe path: {text}."
                    )
    return warnings


def parallel_batch_manifest_warnings(root, queue: dict) -> list[str]:
    warnings: list[str] = []
    manifest_dir = root / "state" / "orchestrator_prompts" / "parallel_batches"
    if not manifest_dir.exists():
        return warnings
    manifest_files = sorted(manifest_dir.glob("*.json"))
    if root.name == "template" and manifest_files:
        warnings.append("Template state/orchestrator_prompts/parallel_batches/ should not contain generated batch manifests.")
    command_ids = {
        str(command.get("id") or "").strip()
        for command in queue.get("commands", [])
        if isinstance(command, dict) and str(command.get("id") or "").strip()
    }
    for manifest_path in manifest_files:
        relative = manifest_path.relative_to(root).as_posix()
        try:
            manifest = json.loads(read_text(manifest_path))
        except json.JSONDecodeError as exc:
            warnings.append(f"{relative} is invalid JSON: {exc.msg}.")
            continue
        if not isinstance(manifest, dict):
            warnings.append(f"{relative} must be a JSON object.")
            continue
        if not str(manifest.get("timestamp") or "").strip():
            warnings.append(f"{relative} is missing timestamp.")
        commands = manifest.get("commands")
        if not isinstance(commands, list) or not commands:
            warnings.append(f"{relative} must contain a non-empty commands array.")
            commands = []
        for index, command in enumerate(commands):
            if not isinstance(command, dict):
                warnings.append(f"{relative} commands[{index}] must be an object.")
                continue
            command_id = str(command.get("id") or "").strip()
            if not command_id:
                warnings.append(f"{relative} commands[{index}] is missing id.")
            elif command_ids and command_id not in command_ids:
                warnings.append(f"{relative} references unknown command id: {command_id}.")
            if not str(command.get("owner_agent") or "").strip():
                warnings.append(f"{relative} command {command_id or index} is missing owner_agent.")
            expected_outputs = command.get("expected_outputs")
            if expected_outputs is not None and not isinstance(expected_outputs, list):
                warnings.append(f"{relative} command {command_id or index} expected_outputs must be a list.")
        prompts = manifest.get("prompts")
        if not isinstance(prompts, list):
            warnings.append(f"{relative} must contain a prompts array.")
            continue
        if commands and not prompts:
            warnings.append(f"{relative} has commands but no prompt paths.")
        for index, prompt in enumerate(prompts):
            prompt_text = str(prompt or "").strip()
            if not prompt_text:
                warnings.append(f"{relative} prompts[{index}] is empty.")
                continue
            prompt_path = Path(prompt_text)
            if prompt_path.is_absolute() or ".." in prompt_path.parts:
                warnings.append(f"{relative} prompts[{index}] has unsafe path: {prompt_text}.")
                continue
            if not (root / prompt_path).is_file():
                warnings.append(f"{relative} prompt path is missing: {prompt_text}.")
    return warnings


def paper_warnings(root, check_build: bool) -> list[str]:
    warnings: list[str] = []
    paper_dir = root / "09_report" / "paper"
    main_tex = paper_dir / "main.tex"
    text = read_text(main_tex)
    if main_tex.is_file():
        if "\\begin{document}" not in text:
            warnings.append("09_report/paper/main.tex is missing \\begin{document}.")
        if "\\end{document}" not in text:
            warnings.append("09_report/paper/main.tex is missing \\end{document}.")
    if not check_build:
        return warnings

    xelatex = shutil.which("xelatex")
    latexmk = shutil.which("latexmk")
    pdflatex = shutil.which("pdflatex")
    if not xelatex and not latexmk and not pdflatex:
        warnings.append("Paper build check requested, but no supported LaTeX engine is installed.")
        return warnings
    if not main_tex.is_file():
        return warnings

    with tempfile.TemporaryDirectory(prefix="report_build_") as tmp_dir:
        work_paper = shutil.copytree(paper_dir, f"{tmp_dir}/paper")
        env = os.environ.copy()
        env["TEXMFVAR"] = f"{tmp_dir}/texmf-var"
        env["TEXMFCONFIG"] = f"{tmp_dir}/texmf-config"
        if xelatex:
            command = [
                xelatex,
                "-interaction=nonstopmode",
                "-halt-on-error",
                "main.tex",
            ]
        elif latexmk:
            command = [
                latexmk,
                "-pdf",
                "-interaction=nonstopmode",
                "-halt-on-error",
                "main.tex",
            ]
        else:
            command = [
                pdflatex,
                "-interaction=nonstopmode",
                "-halt-on-error",
                "main.tex",
            ]
        try:
            result = subprocess.run(
                command,
                cwd=work_paper,
                text=True,
                capture_output=True,
                timeout=90,
                check=False,
                env=env,
            )
        except subprocess.TimeoutExpired:
            warnings.append("09_report/paper/main.tex build timed out after 90 seconds.")
            return warnings
        if result.returncode != 0:
            tail = "\n".join((result.stdout + result.stderr).splitlines()[-8:])
            warnings.append(f"09_report/paper/main.tex failed to build. Last log lines: {tail}")
    return warnings


def reproducibility_manifest_warnings(root, path, exp_id: str) -> list[str]:
    if not path.is_file():
        return [f"Missing reproducibility manifest: {path.relative_to(root)}."]
    try:
        manifest = json.loads(read_text(path))
    except json.JSONDecodeError as exc:
        return [f"{path.relative_to(root)} is invalid JSON: {exc.msg}."]
    required_keys = [
        "project",
        "exp_id",
        "hypothesis",
        "dataset",
        "code",
        "environment",
        "randomness",
        "command",
        "hardware",
        "baselines",
        "evidence",
        "outputs",
    ]
    warnings = []
    for key in required_keys:
        if key not in manifest:
            warnings.append(f"{path.relative_to(root)} is missing key: {key}.")
    if str(manifest.get("exp_id") or "") not in {"", exp_id}:
        warnings.append(f"{path.relative_to(root)} exp_id does not match folder {exp_id}.")
    return warnings


def dataset_metric_registry_warnings(root) -> list[str]:
    warnings: list[str] = []
    dataset_path = root / "03_experiments" / "dataset_registry.json"
    metric_path = root / "03_experiments" / "metric_registry.json"
    if not dataset_path.is_file():
        warnings.append("Missing 03_experiments/dataset_registry.json.")
    if not metric_path.is_file():
        warnings.append("Missing 03_experiments/metric_registry.json.")
    for path, key in ((dataset_path, "datasets"), (metric_path, "metrics")):
        if not path.is_file():
            continue
        try:
            data = json.loads(read_text(path))
        except json.JSONDecodeError as exc:
            warnings.append(f"{path.relative_to(root)} is invalid JSON: {exc.msg}.")
            continue
        rows = data.get(key) if isinstance(data, dict) else None
        if not isinstance(rows, list):
            warnings.append(f"{path.relative_to(root)} must contain a {key} array.")
            continue
        seen: set[str] = set()
        for index, row in enumerate(rows):
            if not isinstance(row, dict):
                warnings.append(f"{path.relative_to(root)} {key}[{index}] must be an object.")
                continue
            item_id = str(row.get("id") or "").strip()
            if not item_id:
                warnings.append(f"{path.relative_to(root)} {key}[{index}] is missing id.")
                continue
            if item_id in seen:
                warnings.append(f"{path.relative_to(root)} duplicates id: {item_id}.")
            seen.add(item_id)
            if not str(row.get("name") or "").strip():
                warnings.append(f"{path.relative_to(root)} item {item_id} has no name.")
    dataset_ids = registry_id_set(dataset_path, "datasets")
    metric_ids = registry_id_set(metric_path, "metrics")
    result_table = report_table_path(root, "experiment_results.csv")
    working_result_table = root / "05_results" / "experiment_results.csv"
    for table in (result_table, working_result_table):
        for index, row in enumerate(csv_rows(table), start=2):
            dataset = row.get("dataset", "")
            metric = row.get("metric", "")
            if dataset and dataset_ids and dataset not in dataset_ids:
                warnings.append(f"{table.relative_to(root)} row {index} references unknown dataset id: {dataset}.")
            if metric and metric_ids and metric not in metric_ids:
                warnings.append(f"{table.relative_to(root)} row {index} references unknown metric id: {metric}.")
            if dataset and not dataset_ids:
                warnings.append("Result rows exist but dataset registry has no dataset IDs.")
            if metric and not metric_ids:
                warnings.append("Result rows exist but metric registry has no metric IDs.")
    return warnings


def claim_reference_warnings(root, baseline_registry: dict) -> list[str]:
    warnings: list[str] = []
    claim_path = report_table_path(root, "claim_evidence.csv")
    result_path = report_table_path(root, "experiment_results.csv")
    robustness_path = report_table_path(root, "statistical_robustness.csv")
    claim_rows = csv_rows(claim_path)
    result_rows = csv_rows(result_path)
    robustness_rows = csv_rows(robustness_path)
    exp_ids = {path.name for path in (root / "03_experiments").glob("exp_*") if path.is_dir()}
    baseline_ids = {
        str(baseline.get("id") or "").strip()
        for baseline in baseline_registry.get("baselines", [])
        if isinstance(baseline, dict) and str(baseline.get("id") or "").strip()
    }

    claim_ids: set[str] = set()
    for index, row in enumerate(claim_rows, start=2):
        claim_id = row.get("claim_id", "")
        if not claim_id:
            warnings.append(f"{claim_path.relative_to(root)} row {index} is missing claim_id.")
            continue
        if claim_id in claim_ids:
            warnings.append(f"{claim_path.relative_to(root)} row {index} duplicates claim_id: {claim_id}.")
        claim_ids.add(claim_id)
        for exp_id in split_reference_list(row.get("experiments", "")):
            if exp_id not in exp_ids:
                warnings.append(f"{claim_path.relative_to(root)} row {index} references unknown experiment_id: {exp_id}.")

    for path, rows in ((result_path, result_rows), (robustness_path, robustness_rows)):
        for index, row in enumerate(rows, start=2):
            exp_id = row.get("experiment_id", "")
            claim_id = row.get("claim_id", "")
            if not exp_id:
                warnings.append(f"{path.relative_to(root)} row {index} is missing experiment_id.")
            elif exp_id not in exp_ids:
                warnings.append(f"{path.relative_to(root)} row {index} references unknown experiment_id: {exp_id}.")
            if not claim_id:
                warnings.append(f"{path.relative_to(root)} row {index} is missing claim_id.")
            elif claim_id not in claim_ids:
                warnings.append(f"{path.relative_to(root)} row {index} references unknown claim_id: {claim_id}.")

    for index, row in enumerate(result_rows, start=2):
        baseline_id = row.get("baseline_id", "")
        if baseline_id and baseline_id.lower() not in {"none", "n/a", "na"} and baseline_id not in baseline_ids:
            warnings.append(f"{result_path.relative_to(root)} row {index} references unknown baseline_id: {baseline_id}.")

    return warnings


def paper_claim_consistency_warnings(root) -> list[str]:
    warnings: list[str] = []
    paper = read_text(root / "09_report" / "paper" / "main.tex").lower()
    weak_statuses = {"untested", "unsupported", "contradicted", "invalid", "rejected"}
    claim_path = report_table_path(root, "claim_evidence.csv")
    for row in csv_rows(claim_path):
        claim_id = row.get("claim_id", "")
        if not claim_id:
            continue
        status = row.get("status", "").strip().lower()
        if status in weak_statuses and claim_id.lower() in paper:
            warnings.append(
                f"09_report/paper/main.tex references weak claim_id {claim_id} with status {status}."
            )
    return warnings


def baseline_artifact_warnings(root, baseline_registry: dict) -> list[str]:
    warnings: list[str] = []
    structure_reports = sorted((root / "08_baselines" / "structure_reports").glob("*.json"))
    if structure_reports:
        plan_path = root / "08_baselines" / "code_structure_plan.md"
        plan_text = read_text(plan_path)
        if not plan_path.is_file() or not plan_text.strip():
            warnings.append("Baseline structure reports exist but 08_baselines/code_structure_plan.md is missing or empty.")
        else:
            for report_path in structure_reports:
                baseline_id = report_path.stem
                if baseline_id not in plan_text:
                    warnings.append(
                        f"Baseline structure report {report_path.relative_to(root)} is not reflected in 08_baselines/code_structure_plan.md."
                    )
    for baseline in baseline_registry.get("baselines", []):
        if not isinstance(baseline, dict):
            continue
        baseline_id = str(baseline.get("id") or "<unknown>")
        source_path = str(baseline.get("source_path") or baseline.get("local_snapshot") or "").strip()
        if source_path:
            if Path(source_path).is_absolute() or ".." in Path(source_path).parts:
                warnings.append(f"Baseline {baseline_id} source_path must be project-relative: {source_path}.")
                continue
            source = root / source_path
            if not source.exists():
                warnings.append(f"Baseline {baseline_id} source_path does not exist: {source_path}.")
            if source_path.startswith("08_baselines/source_snapshots/") and not baseline.get("structure_report"):
                warnings.append(f"Baseline {baseline_id} has a source snapshot but no structure_report.")
        structure_report = str(baseline.get("structure_report") or "").strip()
        if structure_report and (Path(structure_report).is_absolute() or ".." in Path(structure_report).parts):
            warnings.append(f"Baseline {baseline_id} structure_report must be project-relative: {structure_report}.")
        elif structure_report and not (root / structure_report).is_file():
            warnings.append(f"Baseline {baseline_id} structure_report does not exist: {structure_report}.")
        adapter_path = str(baseline.get("adapter_path") or "").strip()
        if adapter_path and (Path(adapter_path).is_absolute() or ".." in Path(adapter_path).parts):
            warnings.append(f"Baseline {baseline_id} adapter_path must be project-relative: {adapter_path}.")
        elif adapter_path and not (root / adapter_path).exists():
            warnings.append(f"Baseline {baseline_id} adapter_path does not exist: {adapter_path}.")
        smoke_script = str(baseline.get("smoke_script") or "").strip()
        if smoke_script and (Path(smoke_script).is_absolute() or ".." in Path(smoke_script).parts):
            warnings.append(f"Baseline {baseline_id} smoke_script must be project-relative: {smoke_script}.")
        elif smoke_script and not (root / smoke_script).is_file():
            warnings.append(f"Baseline {baseline_id} smoke_script does not exist: {smoke_script}.")
        if str(baseline.get("status") or "").lower() in {"runnable", "reproduced"} and baseline.get("adapter_path") and not baseline.get("smoke_script"):
            warnings.append(f"Baseline {baseline_id} has an adapter but no smoke_script.")
    return warnings


def research_rigor_warnings(root, check_paper_build: bool, baseline_registry: dict) -> list[str]:
    warnings: list[str] = []
    exp_dirs = sorted(path for path in (root / "03_experiments").glob("exp_*") if path.is_dir())
    if not exp_dirs:
        warnings.append("No experiment folders found under 03_experiments/.")
    for exp_dir in exp_dirs:
        exp_id = exp_dir.name
        warnings.extend(markdown_section_warnings(
            root,
            exp_dir / "preregistration.md",
            [
                "## Hypothesis",
                "## Success Criteria",
                "## Failure Criteria",
                "## Baselines",
                "## Metrics",
                "## Smoke Test Plan",
                "## Planned Analysis",
                "## Decision Rule",
            ],
        ))
        prereg_text = read_text(exp_dir / "preregistration.md") if (exp_dir / "preregistration.md").is_file() else ""
        run_state_path = exp_dir / "run_state.json"
        run_status = ""
        if run_state_path.is_file():
            try:
                run_state = json.loads(read_text(run_state_path))
                run_status = str(run_state.get("status") or "").strip().lower() if isinstance(run_state, dict) else ""
            except json.JSONDecodeError:
                run_status = ""
        prereg_core_markers = [
            "- Claim ID:",
            "- Claim tested:",
            "- Directional expectation:",
            "- Dataset:",
            "- Split:",
            "- Smoke command:",
            "- Smoke expected output:",
            "- Smoke check procedure:",
            "- Primary comparison:",
        ]
        prereg_has_content = any(
            not placeholder_after(prereg_text, marker)
            for marker in prereg_core_markers
        )
        prereg_audit_required = prereg_has_content or run_status in {"queued", "running", "succeeded", "failed", "blocked", "cancelled"}
        if root.name != "template" and prereg_audit_required:
            warnings.extend(audit_preregistration(root, exp_id))
        warnings.extend(reproducibility_manifest_warnings(
            root,
            exp_dir / "reproducibility_manifest.json",
            exp_id,
        ))

    warnings.extend(markdown_section_warnings(
        root,
        root / "05_results" / "statistical_robustness.md",
        [
            "## Required Checks",
            "## Robustness Table",
            "## Data Quality Notes",
        ],
    ))
    warnings.extend(markdown_section_warnings(
        root,
        root / "07_reviews" / "reviewer_attack_matrix.md",
        [
            "## Attack Matrix",
            "## Highest-Risk Claims",
            "## Response Plan",
        ],
    ))
    warnings.extend(csv_header_warnings(
        root,
        report_table_path(root, "experiment_results.csv"),
        ["experiment_id", "claim_id", "dataset", "split", "method", "baseline_id", "metric", "value", "delta", "status", "evidence", "caveat"],
    ))
    warnings.extend(csv_header_warnings(
        root,
        report_table_path(root, "claim_evidence.csv"),
        ["claim_id", "claim", "status", "evidence", "experiments", "robustness", "caveat", "next_needed"],
    ))
    warnings.extend(csv_header_warnings(
        root,
        report_table_path(root, "statistical_robustness.csv"),
        ["experiment_id", "claim_id", "check", "metric", "value", "status", "evidence", "caveat", "next_needed"],
    ))
    warnings.extend(claim_reference_warnings(root, baseline_registry))
    warnings.extend(dataset_metric_registry_warnings(root))
    warnings.extend(paper_claim_consistency_warnings(root))
    warnings.extend(baseline_artifact_warnings(root, baseline_registry))
    warnings.extend(paper_warnings(root, check_paper_build))
    return warnings


def report_freshness_warnings(root) -> list[str]:
    warnings: list[str] = []
    report = root / "09_report"
    required_dirs = [
        report / "src",
        report / "analysis",
        report / "figures",
    ]
    required_files = [
        report / "README.md",
        report / "paper" / "main.tex",
        report / "analysis" / "analysis.py",
        report_table_path(root, "experiment_results.csv"),
        report_table_path(root, "claim_evidence.csv"),
        report_table_path(root, "statistical_robustness.csv"),
    ]
    for path in required_dirs:
        if not path.is_dir():
            warnings.append(f"Missing reader-facing report directory: {path.relative_to(root)}.")
    for path in required_files:
        if not path.is_file():
            warnings.append(f"Missing reader-facing report artifact: {path.relative_to(root)}.")
    readme = report / "README.md"
    if readme.is_file() and "RESEARCH_AGENT_REPORT_INDEX:START" not in read_text(readme):
        warnings.append("09_report/README.md is missing the generated report index; run scripts.commands.reports.report_index refresh.")
    if readme.is_file():
        index_sources = [
            report_table_path(root, "experiment_results.csv"),
            report_table_path(root, "claim_evidence.csv"),
            report_table_path(root, "statistical_robustness.csv"),
            report_table_path(root, "claim_evidence_board.csv"),
            report_table_path(root, "research_audit.csv"),
        ]
        newest_index_source = max((path.stat().st_mtime for path in index_sources if path.exists()), default=0)
        if newest_index_source > readme.stat().st_mtime + 1:
            warnings.append("09_report/README.md may be stale; run scripts.commands.reports.report_index refresh.")

    legacy_files = [
        report / "method.md",
        report / "analysis_results.md",
        report / "writing.md",
        report / "claim_evidence.md",
    ]
    for path in legacy_files:
        if path.exists():
            warnings.append(
                f"Legacy 09_report markdown file should be moved or removed: {path.relative_to(root)}."
            )
    legacy_set = set(legacy_files)
    for path in sorted(report.rglob("*.md")):
        if path in legacy_set:
            continue
        if path == report / "README.md":
            continue
        if path.name == "failure_cases.md" and (
            report / "results" in path.parents or report / "src" / "results" in path.parents
        ):
            continue
        warnings.append(
            f"09_report should not contain Markdown scratch files: {path.relative_to(root)}."
        )

    stage = current_stage(root)
    stage_order = {
        "brief": 0,
        "motivation": 1,
        "literature": 2,
        "planning": 3,
        "experiment design": 4,
        "code generation": 5,
        "result analysis": 6,
        "analysis": 6,
        "interpretation": 7,
        "writing": 8,
        "critique": 9,
        "revision": 10,
    }
    rank = stage_order.get(stage, 0)
    checks = []
    if rank >= stage_order["experiment design"]:
        checks.append((
            report / "paper" / "main.tex",
            [
                root / "03_experiments" / "experiment_registry.yaml",
                root / "03_experiments" / "metrics.md",
                *sorted((root / "03_experiments").glob("*/hypothesis.md")),
                *sorted((root / "03_experiments").glob("*/config.yaml")),
                root / "04_code" / "implementation_notes.md",
            ],
            "method or evaluation design",
        ))
    if rank >= stage_order["result analysis"]:
        checks.append((
            report_table_path(root, "experiment_results.csv"),
            [
                root / "05_results" / "aggregate_results.md",
                root / "05_results" / "interpretation.md",
                root / "05_results" / "failure_cases.md",
                *sorted((root / "03_experiments").glob("*/analysis.md")),
            ],
            "analysis or result interpretation",
        ))
    if rank >= stage_order["interpretation"]:
        checks.append((
            report_table_path(root, "claim_evidence.csv"),
            [
                root / "00_brief" / "contribution_candidates.md",
                root / "05_results" / "interpretation.md",
                root / "05_results" / "aggregate_results.md",
            ],
            "claim-evidence status",
        ))
    if rank >= stage_order["writing"]:
        checks.append((
            report / "paper" / "main.tex",
            sorted((root / "06_writing").glob("*.md")),
            "reader-facing writing",
        ))

    for report_path, source_paths, label in checks:
        if not report_path.is_file():
            continue
        newest_source = latest_mtime(source_paths)
        if newest_source and newest_source > report_path.stat().st_mtime + 1:
            warnings.append(
                f"{report_path.relative_to(root)} may be stale: {label} sources are newer."
            )
    return warnings


def workflow_warnings(status: dict, queue: dict, run_states: list[dict]) -> list[str]:
    warnings: list[str] = []
    agents = {
        agent.get("name"): agent
        for agent in status.get("agents", [])
        if isinstance(agent, dict) and agent.get("name")
    }
    for command in queue.get("commands", []):
        command_status = str(command.get("status") or "").lower()
        owner = str(command.get("owner_agent") or "")
        command_id = command.get("id", "<unknown>")
        if command_status != "in progress":
            continue
        owner_agents = [part.strip() for part in owner.replace(",", "/").split("/") if part.strip()]
        concrete_owners = [agent for agent in owner_agents if agent in agents]
        if not concrete_owners:
            warnings.append(f"Command {command_id} is in progress but has no known agent owner.")
            continue
        if not any(str(agents[name].get("status") or "").lower() == "running" for name in concrete_owners):
            warnings.append(f"Command {command_id} is in progress but no owner agent is running.")

    for agent_name, agent in agents.items():
        if str(agent.get("status") or "").lower() != "done":
            continue
        active = [
            command.get("id")
            for command in queue.get("commands", [])
            if owner_matches(command.get("owner_agent"), agent_name)
            and str(command.get("status") or "").lower() == "in progress"
        ]
        if active:
            warnings.append(f"Agent {agent_name} is done while owning in-progress commands: {', '.join(active)}")

    for run_state in run_states:
        if str(run_state.get("status") or "").lower() != "running":
            continue
        owner = run_state.get("owner_agent")
        if owner in agents and str(agents[owner].get("status") or "").lower() != "running":
            warnings.append(f"Experiment {run_state.get('exp_id')} is running but owner agent {owner} is not running.")
    return warnings


def agent_message_warnings(status: dict, messages: dict, root) -> list[str]:
    warnings: list[str] = []
    agents = {
        str(agent.get("name") or "").strip()
        for agent in status.get("agents", [])
        if isinstance(agent, dict) and str(agent.get("name") or "").strip()
    }
    command_ids = {
        str(command.get("id") or "").strip()
        for command in load_command_queue(root).get("commands", [])
        if isinstance(command, dict) and str(command.get("id") or "").strip()
    }
    claim_ids = {
        row.get("claim_id", "")
        for row in csv_rows(report_table_path(root, "claim_evidence.csv"))
        if row.get("claim_id", "")
    }
    exp_ids = {path.name for path in (root / "03_experiments").glob("exp_*") if path.is_dir()}
    for message in messages.get("messages", []):
        message_id = str(message.get("id") or "<unknown>")
        from_agent = str(message.get("from_agent") or "").strip()
        to_agent = str(message.get("to_agent") or "").strip()
        if from_agent and from_agent not in agents and from_agent != "user":
            warnings.append(f"Message {message_id} references unknown from_agent: {from_agent}.")
        if to_agent and to_agent not in agents and to_agent != "user":
            warnings.append(f"Message {message_id} references unknown to_agent: {to_agent}.")
        command_id = str(message.get("related_command_id") or "").strip()
        if command_id and command_id not in command_ids:
            warnings.append(f"Message {message_id} references unknown related_command_id: {command_id}.")
        claim_id = str(message.get("related_claim_id") or "").strip()
        if claim_id and claim_id not in claim_ids:
            warnings.append(f"Message {message_id} references unknown related_claim_id: {claim_id}.")
        exp_id = str(message.get("related_exp_id") or "").strip()
        if exp_id and exp_id not in exp_ids:
            warnings.append(f"Message {message_id} references unknown related_exp_id: {exp_id}.")
        if (
            str(message.get("kind") or "").lower() == "blocker"
            and str(message.get("priority") or "").lower() == "high"
            and str(message.get("status") or "").lower() in {"open", "acknowledged", "blocked"}
        ):
            warnings.append(f"High-priority blocker message is unresolved: {message_id}.")
    return warnings


def voting_warnings(status: dict, queue: dict, votes: dict, root) -> list[str]:
    warnings: list[str] = []
    agents = {
        str(agent.get("name") or "").strip()
        for agent in status.get("agents", [])
        if isinstance(agent, dict) and str(agent.get("name") or "").strip()
    }
    command_ids = {
        str(command.get("id") or "").strip()
        for command in queue.get("commands", [])
        if isinstance(command, dict) and str(command.get("id") or "").strip()
    }
    decisions = {
        str(decision.get("id") or "").strip(): decision
        for decision in votes.get("decisions", [])
        if isinstance(decision, dict) and str(decision.get("id") or "").strip()
    }
    for decision_id, decision in decisions.items():
        command_id = str(decision.get("related_command_id") or "").strip()
        if command_id and command_id not in command_ids:
            warnings.append(f"Vote decision {decision_id} references unknown related_command_id: {command_id}.")
        for voter in decision.get("required_voters", []):
            if voter and voter not in agents and voter not in USER_VOTER_ALIASES:
                warnings.append(f"Vote decision {decision_id} requires unknown voter: {voter}.")
        for vote in decision.get("votes", []):
            voter = str(vote.get("agent") or "").strip()
            if voter and voter not in agents and voter not in USER_VOTER_ALIASES:
                warnings.append(f"Vote decision {decision_id} has vote from unknown agent: {voter}.")
    for command in queue.get("commands", []):
        command_id = str(command.get("id") or "<unknown>")
        if not command.get("requires_vote"):
            continue
        vote_id = str(command.get("vote_id") or "").strip()
        if not vote_id:
            warnings.append(f"Command {command_id} requires a vote but has no vote_id.")
            continue
        if vote_id not in decisions:
            warnings.append(f"Command {command_id} requires unknown vote_id: {vote_id}.")
            continue
        command_status = str(command.get("status") or "").lower()
        if command_status in {"in progress", "done"} and not command_has_approved_vote(root, command):
            warnings.append(f"Command {command_id} is {command_status} without approved vote {vote_id}.")
    return warnings


def session_state_warnings(root) -> list[str]:
    warnings: list[str] = []
    sessions = root / "state" / "sessions"
    if not sessions.is_dir():
        warnings.append("Missing state/sessions/ directory.")
        return warnings
    for session_dir in sorted(path for path in sessions.iterdir() if path.is_dir()):
        session_file = session_dir / "session.json"
        if not session_file.is_file():
            warnings.append(f"{session_file.relative_to(root)} is missing.")
            continue
        try:
            data = json.loads(read_text(session_file))
        except json.JSONDecodeError as exc:
            warnings.append(f"{session_file.relative_to(root)} is invalid JSON: {exc.msg}.")
            continue
        if data.get("session_id") != session_dir.name:
            warnings.append(f"{session_file.relative_to(root)} session_id does not match folder name.")
        if str(data.get("status") or "") not in {"running", "done", "blocked", "waiting"}:
            warnings.append(f"{session_file.relative_to(root)} has invalid status.")
        for child in ("plans", "results", "artifacts"):
            if not (session_dir / child).is_dir():
                warnings.append(f"{session_dir.relative_to(root)}/{child}/ is missing.")
    return warnings


def main() -> int:
    args = parse_args()
    try:
        root = project_root(args.project)
        warnings: list[str] = []
        warnings.extend(project_handoff_warnings(root))
        warnings.extend(file_state_markdown_warnings(root))

        status = load_agent_status(root)
        warnings.extend(validate_agent_status_doc(status))
        warnings.extend(validate_agent_events(root))
        warnings.extend(progress_checkpoint_warnings(root))

        queue = load_command_queue(root)
        warnings.extend(validate_command_queue_doc(queue))
        warnings.extend(next_actions_mirror_warnings(root, queue))
        warnings.extend(parallel_batch_manifest_warnings(root, queue))

        run_states = discover_run_states(root)
        for run_state in run_states:
            warnings.extend(validate_run_state_doc(run_state))
        warnings.extend(working_artifact_warnings(root, run_states))
        warnings.extend(v6_research_surface_warnings(root, run_states))
        warnings.extend(workflow_warnings(status, queue, run_states))

        if not agent_messages_path(root).exists():
            warnings.append("Missing state/agent_messages.json.")
        messages = load_agent_messages(root)
        warnings.extend(validate_agent_messages_doc(messages))
        warnings.extend(agent_message_warnings(status, messages, root))
        if not agent_votes_path(root).exists():
            warnings.append("Missing state/agent_votes.json.")
        votes = load_agent_votes(root)
        warnings.extend(validate_agent_votes_doc(votes))
        warnings.extend(voting_warnings(status, queue, votes, root))
        warnings.extend(session_state_warnings(root))
        if not pattern_memory_path(root).exists():
            warnings.append("Missing state/pattern_memory.json.")
        pattern_memory = load_pattern_memory(root)
        warnings.extend(validate_pattern_memory_doc(pattern_memory))
        if not ralph_loop_path(root).exists():
            warnings.append("Missing state/ralph_loop.json.")
        ralph_loop = load_ralph_loop(root)
        warnings.extend(validate_ralph_loop_doc(ralph_loop))
        warnings.extend(template_hygiene_warnings(root, ralph_loop))

        if not baseline_registry_path(root).exists():
            warnings.append("Missing 08_baselines/baseline_registry.json.")
        baseline_registry = load_baseline_registry(root)
        warnings.extend(validate_baseline_registry_doc(baseline_registry))

        if not loop_summary_path(root).exists():
            warnings.append("Missing state/loop_summary.json.")
        loop_summary = load_loop_summary(root)
        warnings.extend(validate_loop_summary_doc(loop_summary))
        if not gpu_queue_path(root).exists():
            warnings.append("Missing state/gpu_experiment_queue.json.")
        gpu_queue = load_gpu_queue(root)
        warnings.extend(validate_gpu_queue_doc(gpu_queue))
        warnings.extend(report_freshness_warnings(root))
        warnings.extend(research_rigor_warnings(root, args.check_paper_build, baseline_registry))

        if not review_form_registry_path().exists():
            warnings.append("Missing review_forms/form_registry.json.")
        review_form_registry = load_review_form_registry()
        warnings.extend(validate_review_form_registry_doc(review_form_registry))

        if warnings:
            print("warnings:")
            for warning in warnings:
                print(f"- {warning}")
            if args.strict:
                return 1
        print(f"valid project state: {args.project}")
        return 0
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
