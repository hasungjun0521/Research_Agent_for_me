#!/usr/bin/env python3
"""Apply non-destructive project template upgrades to an existing project."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

from scripts.harness.command_mirror import generated_mirror_matches, sync_next_actions
from scripts.harness.data_roots import sync_datasets_to_data_roots
from scripts.harness.state import (
    HarnessError,
    append_agent_event,
    agent_events_path,
    agent_votes_path,
    default_agent_votes,
    default_agent_messages,
    default_gpu_queue,
    default_pattern_memory,
    default_ralph_loop,
    discover_run_states,
    agent_messages_path,
    gpu_queue_path,
    load_command_queue,
    load_json,
    load_loop_summary,
    now_iso,
    project_root,
    pattern_memory_path,
    ralph_loop_path,
    repo_root,
    write_command_queue,
    write_agent_votes,
    write_agent_messages,
    write_gpu_queue,
    write_loop_summary,
    write_pattern_memory,
    write_ralph_loop,
    write_run_state,
    update_agent_status,
)
from scripts.harness.workflow_hooks import refresh_report_index


EXPERIMENT_RESULT_FIELDS = [
    "experiment_id",
    "claim_id",
    "dataset",
    "split",
    "method",
    "baseline_id",
    "metric",
    "value",
    "delta",
    "status",
    "evidence",
    "caveat",
]
ARTIFACT_REGISTRY_FIELDS = [
    "updated_at",
    "experiment_id",
    "artifact_id",
    "kind",
    "path",
    "produced_by",
    "status",
    "notes",
]
STARTER_MIGRATION_MARKERS = (
    "to_be_defined",
    "pending_project_terms",
    "not yet",
    "not yet generated",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate an existing project to newer harness conventions.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--dry-run", action="store_true", help="Show planned changes without writing files.")
    parser.add_argument(
        "--overwrite-report",
        action="store_true",
        help="Replace existing 09_report starter files with the current template. Use only when intentional.",
    )
    parser.add_argument(
        "--clean-legacy-report-md",
        action="store_true",
        help="Remove known legacy Markdown files from 09_report after copying the current artifact layout.",
    )
    parser.add_argument(
        "--overwrite-rigor-gates",
        action="store_true",
        help="Replace existing preregistration, reproducibility, robustness, and reviewer-risk starter files.",
    )
    return parser.parse_args()


def template_report_dir() -> Path:
    return repo_root() / "projects" / "template" / "09_report"


def ensure_project_handoff(root: Path, dry_run: bool) -> list[str]:
    path = root / "HANDOFF.md"
    if path.exists():
        return []
    source = repo_root() / "projects" / "template" / "HANDOFF.md"
    if not source.is_file():
        raise HarnessError(f"Template project handoff missing: {source}")
    if not dry_run:
        text = source.read_text(encoding="utf-8").replace("{{PROJECT_NAME}}", root.name)
        path.write_text(text, encoding="utf-8")
    return [str(path.relative_to(root))]


def path_summary(path: str) -> str:
    lower = path.lower()
    if "09_report/paper/main.tex" in lower:
        return "reader-facing LaTeX paper"
    if "09_report/results/experiment_results.csv" in lower:
        return "experiment result table"
    if "09_report/results/claim_evidence.csv" in lower:
        return "claim-evidence table"
    if "09_report/results/statistical_robustness.csv" in lower:
        return "statistical robustness table"
    if "09_report/analysis" in lower:
        return "report analysis code"
    if "09_report/src" in lower:
        return "report source code"
    if "09_report/figures" in lower:
        return "final report figures"
    if "baseline_registry.json" in lower:
        return "baseline reproducibility registry"
    if "run_log.md" in lower:
        return "experiment run log"
    if "aggregate_results.md" in lower:
        return "aggregate result summary"
    if "interpretation.md" in lower:
        return "result interpretation"
    if "draft.md" in lower:
        return "paper draft"
    name = Path(path).name.replace("_", " ").replace("-", " ")
    return name or path


def output_summary(outputs: list[str]) -> str:
    labels = [path_summary(output) for output in outputs if output]
    if not labels:
        return "the relevant project state is updated"
    if len(labels) == 1:
        return labels[0]
    return ", ".join(labels[:-1]) + f", and {labels[-1]}"


def has_starter_marker(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in STARTER_MIGRATION_MARKERS)


def read_experiment_result_rows(root: Path) -> list[dict[str, str]]:
    path = root / "05_results" / "experiment_results.csv"
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        return [
            {str(key): str(value or "") for key, value in row.items()}
            for row in csv.DictReader(handle)
            if any(str(value or "").strip() for value in row.values())
        ]


def enrich_item(item: dict) -> bool:
    changed = False
    action = str(item.get("action") or "").strip()
    outputs = item.get("expected_outputs") or item.get("output_files") or []
    if not isinstance(outputs, list):
        outputs = []
    if "display_summary" not in item:
        item["display_summary"] = action or "Continue the next recorded project task."
        changed = True
    if "why_now" not in item:
        note = str(item.get("notes") or "").strip()
        item["why_now"] = note or "This is the next recorded step in the project workflow."
        changed = True
    if "done_when" not in item:
        item["done_when"] = f"{output_summary(outputs)} exists and file-based state explains the result."
        changed = True
    return changed


def ensure_report(root: Path, dry_run: bool, overwrite: bool) -> list[str]:
    changed: list[str] = []
    source_dir = template_report_dir()
    target_dir = root / "09_report"
    if not source_dir.is_dir():
        raise HarnessError(f"Template report folder missing: {source_dir}")
    if not dry_run:
        target_dir.mkdir(parents=True, exist_ok=True)
    for source in sorted(source_dir.rglob("*")):
        if source.is_dir():
            continue
        relative = source.relative_to(source_dir)
        target = target_dir / relative
        if target.exists() and not overwrite:
            continue
        if (
            not overwrite
            and len(relative.parts) == 2
            and relative.parts[0] == "results"
            and relative.suffix.lower() == ".csv"
            and (target_dir / "src" / "results" / relative.name).is_file()
        ):
            continue
        changed.append(str(target.relative_to(root)))
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    return changed


def copy_text_template(source: Path, target: Path, project_name: str, exp_id: str, dry_run: bool) -> None:
    if source.suffix.lower() in {".json", ".md", ".txt", ".tex", ".csv"}:
        text = source.read_text(encoding="utf-8")
        text = text.replace("{{PROJECT_NAME}}", project_name).replace("exp_001", exp_id)
        target.write_text(text, encoding="utf-8")
        return
    shutil.copy2(source, target)


def ensure_data_roots_from_registry(root: Path, dry_run: bool) -> list[str]:
    registry_path = root / "03_experiments" / "dataset_registry.json"
    data = load_json(registry_path, fallback={"datasets": []})
    if not isinstance(data, dict):
        return []
    datasets = [
        dataset for dataset in data.get("datasets", [])
        if isinstance(dataset, dict) and str(dataset.get("id") or "").strip()
    ]
    changed = sync_datasets_to_data_roots(
        root,
        datasets,
        producer="dataset_registry",
        notes="synchronized from dataset_registry during migration; keep private paths out of tracked files",
        dry_run=dry_run,
        update_existing=False,
    )
    return ["03_experiments/data_roots.md"] if changed else []


def ensure_rigor_gates(root: Path, dry_run: bool, overwrite: bool) -> list[str]:
    changed: list[str] = []
    project_name = root.name
    template = repo_root() / "projects" / "template"
    exp_template = template / "03_experiments" / "exp_001"
    for exp_dir in sorted((root / "03_experiments").glob("exp_*")):
        if not exp_dir.is_dir():
            continue
        exp_id = exp_dir.name
        for name in ["preregistration.md", "reproducibility_manifest.json"]:
            source = exp_template / name
            target = exp_dir / name
            if target.exists() and not overwrite:
                continue
            changed.append(str(target.relative_to(root)))
            if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                copy_text_template(source, target, project_name, exp_id, dry_run)

    for relative in [
        Path("05_results/statistical_robustness.md"),
        Path("07_reviews/reviewer_attack_matrix.md"),
    ]:
        source = template / relative
        target = root / relative
        if target.exists() and not overwrite:
            continue
        changed.append(str(target.relative_to(root)))
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            copy_text_template(source, target, project_name, "exp_001", dry_run)
    return changed


def ensure_research_registries(root: Path, dry_run: bool) -> list[str]:
    changed: list[str] = []
    template = repo_root() / "projects" / "template" / "03_experiments"
    for name in ["dataset_registry.json", "metric_registry.json"]:
        source = template / name
        target = root / "03_experiments" / name
        if target.exists():
            continue
        changed.append(str(target.relative_to(root)))
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    return changed


def ensure_working_research_artifacts(root: Path, dry_run: bool) -> list[str]:
    changed: list[str] = []
    template = repo_root() / "projects" / "template"
    for relative in [
        Path("03_experiments/data_roots.md"),
        Path("03_experiments/artifact_registry.csv"),
        Path("05_results/experiment_results.csv"),
        Path("05_results/experiment_journal.md"),
        Path("05_results/experiment_journal.csv"),
        Path("06_writing/terminology.md"),
    ]:
        source = template / relative
        target = root / relative
        if target.exists():
            continue
        changed.append(str(target.relative_to(root)))
        if not dry_run:
                target.parent.mkdir(parents=True, exist_ok=True)
                copy_text_template(source, target, root.name, "exp_001", dry_run)
    return changed


def ensure_experiment_results_from_run_states(root: Path, dry_run: bool) -> list[str]:
    path = root / "05_results" / "experiment_results.csv"
    if not path.exists():
        return []
    lines = [line for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
    if len(lines) > 1:
        return []
    rows: list[dict[str, str]] = []
    for run_state in discover_run_states(root):
        if str(run_state.get("status") or "") != "succeeded":
            continue
        exp_id = str(run_state.get("exp_id") or "").strip()
        if not exp_id:
            continue
        rows.append({
            "experiment_id": exp_id,
            "claim_id": "",
            "dataset": str(run_state.get("dataset") or ""),
            "split": "test",
            "method": str(run_state.get("method") or ""),
            "baseline_id": str(run_state.get("baseline_id") or ""),
            "metric": "",
            "value": str(run_state.get("judgement") or run_state.get("status") or ""),
            "delta": "",
            "status": "succeeded",
            "evidence": str(run_state.get("result_path") or run_state.get("result_dir") or ""),
            "caveat": "",
        })
    if not rows:
        return []
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=EXPERIMENT_RESULT_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
        journal_csv = root / "05_results" / "experiment_journal.csv"
        journal_md = root / "05_results" / "experiment_journal.md"
        with journal_csv.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=[
                "updated_at",
                "experiment",
                "rationale",
                "dataset",
                "method",
                "baseline",
                "result_summary",
                "result_analysis",
                "evidence",
                "caveat",
            ])
            writer.writeheader()
            for row in rows:
                writer.writerow({
                    "updated_at": now_iso(),
                    "experiment": row["experiment_id"],
                    "rationale": "Restored from succeeded run_state during project migration.",
                    "dataset": row["dataset"],
                    "method": row["method"],
                    "baseline": row["baseline_id"],
                    "result_summary": row["value"],
                    "result_analysis": "Migration restored the working experiment ledger from succeeded run_state metadata.",
                    "evidence": row["evidence"],
                    "caveat": "",
                })
        journal_lines = [
            "# Experiment Journal",
            "",
            "Append one row whenever experiment results are recorded. Keep this Markdown file",
            "as the human-readable ledger and `experiment_journal.csv` as the structured",
            "ledger for filtering, packaging, and later analysis.",
            "",
            "| Updated At | Experiment | Rationale | Dataset | Method | Baseline | Result Summary | Result Analysis | Evidence | Caveat |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ]
        for row in rows:
            journal_lines.append(
                "| {updated_at} | {experiment_id} | Restored from succeeded run_state during project migration. | "
                "{dataset} | {method} | {baseline_id} | {value} | "
                "Migration restored the working experiment ledger from succeeded run_state metadata. | {evidence} |  |".format(
                    updated_at=now_iso(),
                    **row,
                )
            )
        journal_lines.extend([
            "",
            "## Analysis Discipline",
            "",
            "- After every completed experiment, explain why performance improved, regressed, or stayed flat.",
            "- Separate confirmed causes from plausible hypotheses.",
            "- Link to `03_experiments/<exp_id>/analysis.md`, run logs, data roots, baseline registry entries, and failure-case evidence.",
            "- Keep `experiment_journal.md` and `experiment_journal.csv` synchronized through harness CLIs such as `result_ingest` and `progress_checkpoint`.",
            "- Do not strengthen claims until the analysis explains the observed movement or records why the cause is still unknown.",
            "",
        ])
        journal_md.write_text("\n".join(journal_lines), encoding="utf-8")
    return [
        str(path.relative_to(root)),
        "05_results/experiment_journal.csv",
        "05_results/experiment_journal.md",
    ]


def ensure_terminology_from_activity(root: Path, dry_run: bool) -> list[str]:
    path = root / "06_writing" / "terminology.md"
    text = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    if text.strip() and not has_starter_marker(text):
        return []
    run_states = discover_run_states(root)
    result_rows = read_experiment_result_rows(root)
    if not run_states and not result_rows:
        return []
    lines = [
        "# Terminology",
        "",
        "| term | canonical meaning | preferred usage | avoid | notes |",
        "| --- | --- | --- | --- | --- |",
        "| experiment result | Working result row restored from run state or result ledger evidence. | experiment result | final paper claim | Confirm analysis before strengthening writing claims. |",
        "| run state | Per-experiment execution status and artifact pointer. | run_state | final result table | Keep synchronized with experiment logs and result ledgers. |",
        "| data root | Dataset source or split URI recorded for reproducibility. | data root | private absolute path | Refine with concrete project dataset provenance before scaled runs. |",
        "| claim graph | Working link between claims, experiments, and evidence. | claim graph | final proof | Use as traceability before final export. |",
        "",
    ]
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines), encoding="utf-8")
    return [str(path.relative_to(root))]


def ensure_experiment_dag_from_evidence(root: Path, dry_run: bool) -> list[str]:
    path = root / "03_experiments" / "experiment_dag.json"
    try:
        existing = load_json(path, fallback={}) if path.exists() else {}
    except (HarnessError, OSError):
        return [f"{path.relative_to(root)} (skipped: existing file is not readable)"]
    if isinstance(existing, dict) and existing.get("plans"):
        return []
    rows = read_experiment_result_rows(root)
    run_states = discover_run_states(root)
    exp_ids = {
        str(row.get("experiment_id") or "").strip()
        for row in rows
        if str(row.get("experiment_id") or "").strip()
    }
    for run_state in run_states:
        exp_id = str(run_state.get("exp_id") or "").strip()
        if exp_id:
            exp_ids.add(exp_id)
    if not exp_ids:
        return []
    plans = []
    for exp_id in sorted(exp_ids):
        run_state = next(
            (state for state in run_states if str(state.get("exp_id") or "").strip() == exp_id),
            {},
        )
        result_path = str(run_state.get("result_path") or run_state.get("result_dir") or f"03_experiments/{exp_id}/results/")
        plans.append({
            "id": f"{exp_id}_migration_plan",
            "claim_id": str(run_state.get("claim_id") or ""),
            "exp_ids": [exp_id],
            "smoke_test": "Migration restored this plan from existing run_state/result evidence.",
            "expected_outputs": [result_path],
            "check_procedure": "Verify run_state, experiment result row, journal analysis, and artifact registry before using this evidence in claims.",
            "parallel_group": "",
        })
    payload = {
        "schema_version": 1,
        "project": root.name,
        "plans": plans,
        "notes": "Restored by migrate_project.py from existing experiment evidence; refine before launching new runs.",
    }
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return [str(path.relative_to(root))]


def ensure_claim_graph_from_results(root: Path, dry_run: bool) -> list[str]:
    json_path = root / "05_results" / "claim_graph.json"
    existing = load_json(json_path, fallback={}) if json_path.exists() else {}
    if (
        isinstance(existing, dict)
        and isinstance(existing.get("nodes"), list)
        and isinstance(existing.get("edges"), list)
        and existing.get("nodes")
        and existing.get("edges")
    ):
        return []
    rows = read_experiment_result_rows(root)
    if not rows:
        return []
    nodes: list[dict[str, str]] = []
    edges: list[dict[str, str]] = []
    seen: set[str] = set()

    def add_node(node: dict[str, str]) -> None:
        node_id = node["id"]
        if node_id in seen:
            return
        seen.add(node_id)
        nodes.append(node)

    for row in rows:
        exp_id = str(row.get("experiment_id") or "experiment").strip()
        claim_id = str(row.get("claim_id") or f"claim_for_{exp_id}").strip()
        evidence_id = f"evidence_for_{exp_id}"
        add_node({"id": claim_id, "type": "claim", "label": claim_id, "status": "working"})
        add_node({"id": exp_id, "type": "experiment", "label": exp_id, "status": str(row.get("status") or "recorded")})
        add_node({"id": evidence_id, "type": "evidence", "label": str(row.get("evidence") or exp_id), "status": "working"})
        edges.append({"source": claim_id, "target": exp_id, "type": "tested_by"})
        edges.append({"source": exp_id, "target": evidence_id, "type": "supported_by"})

    payload = {
        "schema_version": 1,
        "project": root.name,
        "nodes": nodes,
        "edges": edges,
        "summary": {
            "claims": sum(1 for node in nodes if node.get("type") == "claim"),
            "experiments": sum(1 for node in nodes if node.get("type") == "experiment"),
            "evidence_nodes": sum(1 for node in nodes if node.get("type") == "evidence"),
            "edges": len(edges),
        },
    }
    md_path = root / "05_results" / "claim_graph.md"
    md_lines = [
        "# Claim Graph",
        "",
        "Migration restored this working graph from existing experiment result rows.",
        "Review and refine claim IDs before final export.",
        "",
        "| Claim | Experiment | Evidence |",
        "| --- | --- | --- |",
    ]
    for row in rows:
        exp_id = str(row.get("experiment_id") or "experiment").strip()
        claim_id = str(row.get("claim_id") or f"claim_for_{exp_id}").strip()
        md_lines.append(f"| `{claim_id}` | `{exp_id}` | `{str(row.get('evidence') or '').strip()}` |")
    md_lines.append("")
    if not dry_run:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        md_path.write_text("\n".join(md_lines), encoding="utf-8")
    return [str(json_path.relative_to(root)), str(md_path.relative_to(root))]


def ensure_artifact_registry_from_run_states(root: Path, dry_run: bool) -> list[str]:
    path = root / "03_experiments" / "artifact_registry.csv"
    if not path.exists():
        return []
    lines = [line for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
    if len(lines) > 1:
        return []
    rows: list[dict[str, str]] = []
    timestamp = now_iso()
    for run_state in discover_run_states(root):
        if str(run_state.get("status") or "") != "succeeded":
            continue
        exp_id = str(run_state.get("exp_id") or "").strip()
        if not exp_id:
            continue
        owner = str(run_state.get("owner_agent") or "code_agent")
        notes = "Restored from succeeded run_state during project migration."
        candidates = [
            ("run_state", "state", f"03_experiments/{exp_id}/run_state.json"),
            ("result_path", "result", str(run_state.get("result_path") or run_state.get("result_dir") or "")),
            ("log_path", "log", str(run_state.get("log_path") or "")),
        ]
        seen_paths: set[str] = set()
        for artifact_id, kind, artifact_path in candidates:
            artifact_path = artifact_path.strip()
            if not artifact_path or artifact_path in seen_paths:
                continue
            seen_paths.add(artifact_path)
            rows.append({
                "updated_at": timestamp,
                "experiment_id": exp_id,
                "artifact_id": artifact_id,
                "kind": kind,
                "path": artifact_path,
                "produced_by": owner,
                "status": "succeeded",
                "notes": notes,
            })
    if not rows:
        return []
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=ARTIFACT_REGISTRY_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
    return [str(path.relative_to(root))]


def ensure_file_state_markdown(root: Path, dry_run: bool) -> list[str]:
    changed: list[str] = []
    template = repo_root() / "projects" / "template"
    for relative in [
        Path("state/current_state.md"),
        Path("state/agent_memory.md"),
        Path("state/next_actions.md"),
        Path("state/open_questions.md"),
    ]:
        source = template / relative
        target = root / relative
        if target.exists():
            continue
        changed.append(str(target.relative_to(root)))
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            copy_text_template(source, target, root.name, "exp_001", dry_run)
    return changed


def ensure_agent_messages(root: Path, dry_run: bool) -> list[str]:
    path = agent_messages_path(root)
    if path.exists():
        return []
    if not dry_run:
        write_agent_messages(root, default_agent_messages(root.name))
    return [str(path.relative_to(root))]


def ensure_agent_events(root: Path, dry_run: bool) -> list[str]:
    path = agent_events_path(root)
    if path.exists():
        return []
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    return [str(path.relative_to(root))]


def ensure_agent_votes(root: Path, dry_run: bool) -> list[str]:
    path = agent_votes_path(root)
    if path.exists():
        return []
    if not dry_run:
        write_agent_votes(root, default_agent_votes(root.name))
    return [str(path.relative_to(root))]


def ensure_pattern_memory(root: Path, dry_run: bool) -> list[str]:
    path = pattern_memory_path(root)
    if path.exists():
        return []
    if not dry_run:
        write_pattern_memory(root, default_pattern_memory(root.name))
    return [str(path.relative_to(root))]


def ensure_ralph_loop(root: Path, dry_run: bool) -> list[str]:
    path = ralph_loop_path(root)
    if path.exists():
        return []
    if not dry_run:
        write_ralph_loop(root, default_ralph_loop(root.name))
    return [str(path.relative_to(root))]


def ensure_sessions_dir(root: Path, dry_run: bool) -> list[str]:
    path = root / "state" / "sessions"
    readme = path / "README.md"
    if readme.exists():
        return []
    if not dry_run:
        path.mkdir(parents=True, exist_ok=True)
        readme.write_text(
            "# Session Workspaces\n\n"
            "Each `state/sessions/<session_id>/` folder isolates loop-specific scratchpads, plans, results, and artifacts.\n",
            encoding="utf-8",
        )
    return [str(readme.relative_to(root))]


def ensure_gpu_queue(root: Path, dry_run: bool) -> list[str]:
    path = gpu_queue_path(root)
    if path.exists():
        return []
    if not dry_run:
        write_gpu_queue(root, default_gpu_queue(root.name))
    return [str(path.relative_to(root))]


def ensure_baseline_intake_templates(root: Path, dry_run: bool) -> list[str]:
    changed: list[str] = []
    template = repo_root() / "projects" / "template"
    for relative in [
        Path("08_baselines/structure_reports/README.md"),
    ]:
        source = template / relative
        target = root / relative
        if target.exists():
            continue
        changed.append(str(target.relative_to(root)))
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    return changed


def clean_legacy_report_md(root: Path, dry_run: bool) -> list[str]:
    changed: list[str] = []
    for name in [
        "README.md",
        "method.md",
        "analysis_results.md",
        "writing.md",
        "claim_evidence.md",
    ]:
        path = root / "09_report" / name
        if not path.exists():
            continue
        changed.append(str(path.relative_to(root)))
        if not dry_run:
            path.unlink()
    return changed


def enrich_command_queue(root: Path, dry_run: bool) -> list[str]:
    queue = load_command_queue(root)
    changed = False
    for command in queue.get("commands", []):
        if isinstance(command, dict):
            changed = enrich_item(command) or changed
    next_actions_path = root / "state" / "next_actions.md"
    mirror_changed = (
        not next_actions_path.is_file()
        or not generated_mirror_matches(next_actions_path.read_text(encoding="utf-8", errors="replace"), root.name, queue)
    )
    if changed and not dry_run:
        write_command_queue(root, queue)
    if mirror_changed and not dry_run:
        sync_next_actions(root, queue)
    changed_files: list[str] = []
    if changed:
        changed_files.append("state/command_queue.json")
    if mirror_changed:
        changed_files.append("state/next_actions.md")
    return changed_files


def enrich_loop_summary(root: Path, dry_run: bool) -> list[str]:
    summary = load_loop_summary(root)
    changed = False
    for action in summary.get("next_actions", []):
        if isinstance(action, dict):
            changed = enrich_item(action) or changed
    if changed and not dry_run:
        write_loop_summary(root, summary)
    return ["state/loop_summary.json"] if changed else []


def enrich_run_states(root: Path, dry_run: bool) -> list[str]:
    changed_files: list[str] = []
    for run_state in discover_run_states(root):
        changed = False
        for field in ("display_summary", "judgement", "next_action"):
            if field not in run_state:
                run_state[field] = ""
                changed = True
        if changed:
            exp_id = str(run_state.get("exp_id") or "")
            changed_files.append(f"03_experiments/{exp_id}/run_state.json")
            if not dry_run and exp_id:
                run_state["updated_at"] = now_iso()
                write_run_state(root, exp_id, run_state)
    return changed_files


def sync_migration_lifecycle(root: Path, changed: list[str]) -> None:
    outputs = list(dict.fromkeys(changed))
    note = f"Project migration updated {len(outputs)} item(s)."
    update_agent_status(
        root,
        "director",
        "waiting",
        task="Review project migration changes.",
        stage="project_migration",
        outputs=outputs,
        notes=note,
        append_note=True,
    )
    append_agent_event(
        root,
        "project_migration",
        "director",
        status="waiting",
        task="Review project migration changes.",
        stage="project_migration",
        outputs=outputs,
        notes=note,
    )


def main() -> int:
    args = parse_args()
    try:
        root = project_root(args.project)
        changed = []
        changed.extend(ensure_project_handoff(root, args.dry_run))
        changed.extend(ensure_report(root, args.dry_run, args.overwrite_report))
        changed.extend(ensure_rigor_gates(root, args.dry_run, args.overwrite_rigor_gates))
        changed.extend(ensure_research_registries(root, args.dry_run))
        changed.extend(ensure_working_research_artifacts(root, args.dry_run))
        changed.extend(ensure_experiment_results_from_run_states(root, args.dry_run))
        changed.extend(ensure_artifact_registry_from_run_states(root, args.dry_run))
        changed.extend(ensure_data_roots_from_registry(root, args.dry_run))
        changed.extend(ensure_terminology_from_activity(root, args.dry_run))
        changed.extend(ensure_experiment_dag_from_evidence(root, args.dry_run))
        changed.extend(ensure_claim_graph_from_results(root, args.dry_run))
        changed.extend(ensure_file_state_markdown(root, args.dry_run))
        changed.extend(ensure_agent_messages(root, args.dry_run))
        changed.extend(ensure_agent_events(root, args.dry_run))
        changed.extend(ensure_agent_votes(root, args.dry_run))
        changed.extend(ensure_pattern_memory(root, args.dry_run))
        changed.extend(ensure_ralph_loop(root, args.dry_run))
        changed.extend(ensure_sessions_dir(root, args.dry_run))
        changed.extend(ensure_gpu_queue(root, args.dry_run))
        changed.extend(ensure_baseline_intake_templates(root, args.dry_run))
        if args.clean_legacy_report_md:
            changed.extend(clean_legacy_report_md(root, args.dry_run))
        changed.extend(enrich_command_queue(root, args.dry_run))
        changed.extend(enrich_loop_summary(root, args.dry_run))
        changed.extend(enrich_run_states(root, args.dry_run))
        if not changed:
            print(f"{args.project}: already up to date")
            return 0
        if not args.dry_run:
            sync_migration_lifecycle(root, changed)
            refresh_report_index(root, include_report=True)
        verb = "would update" if args.dry_run else "updated"
        print(f"{args.project}: {verb} {len(changed)} item(s)")
        for path in changed:
            print(f"- {path}")
        return 0
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
