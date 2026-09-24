"""Project health and state diagnostics helpers."""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STARTER_MARKERS = (
    "{{PROJECT_NAME}}",
    "not yet",
    "not generated yet",
    "pending_project_terms",
    "Replace with",
    "Describe",
    "Use this file",
    "YYYY-MM-DD",
    "to_be_defined",
)

REQUIRED_STATE_FILES = [
    "HANDOFF.md",
    "state/current_state.md",
    "state/agent_memory.md",
    "state/next_actions.md",
    "state/open_questions.md",
    "state/command_queue.json",
    "state/agent_status.json",
    "state/loop_summary.json",
]

DIAGNOSTIC_STATE_FILES = [
    "state/project_health.md",
    "state/state_doctor.md",
]

RECENT_ACTIVITY_FILES = [
    "HANDOFF.md",
    "state/current_state.md",
    "state/agent_memory.md",
    "state/next_actions.md",
    "state/open_questions.md",
    "state/command_queue.json",
    "state/progress_hooks.jsonl",
    "03_experiments/data_roots.md",
    "03_experiments/artifact_registry.csv",
    "03_experiments/experiment_dag.json",
    "05_results/experiment_results.csv",
    "05_results/experiment_journal.md",
    "05_results/experiment_journal.csv",
    "05_results/claim_graph.md",
    "05_results/claim_graph.json",
    "06_writing/terminology.md",
    "07_reviews/agent_quality_audit.md",
    "08_baselines/baseline_compare.md",
    "08_baselines/code_structure_plan.md",
]

DIAGNOSTIC_TELEMETRY_FILES = [
    "state/agent_status.json",
    "state/agent_events.jsonl",
]

WORKING_EVIDENCE_FILES = [
    "00_brief/intake_wizard.md",
    "02_planning/experiment_plan.md",
    "03_experiments/data_roots.md",
    "03_experiments/experiment_dag.json",
    "03_experiments/artifact_registry.csv",
    "05_results/experiment_results.csv",
    "05_results/experiment_journal.md",
    "05_results/experiment_journal.csv",
    "05_results/claim_evidence_board.md",
    "05_results/claim_graph.md",
    "05_results/claim_graph.json",
    "06_writing/terminology.md",
    "07_reviews/agent_quality_audit.md",
    "08_baselines/baseline_compare.md",
    "08_baselines/code_structure_plan.md",
]

SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}

RECONCILIATION_STALE_HOURS = 24.0


def project_display_name(root: Path) -> str:
    return "{{PROJECT_NAME}}" if root.name == "template" else root.name


def rel(root: Path, path: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def read_json(path: Path, fallback: Any) -> Any:
    if not path.is_file():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            return [
                {str(key or "").strip(): str(value or "").strip() for key, value in row.items()}
                for row in csv.DictReader(handle)
                if any(str(value or "").strip() for value in row.values())
            ]
    except (OSError, csv.Error):
        return []


def jsonl_rows(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return rows
    for line in lines:
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def has_real_content(path: Path) -> bool:
    text = read_text(path).strip()
    if not text:
        return False
    lowered = text.lower()
    return not any(marker.lower() in lowered for marker in STARTER_MARKERS)


def nonstarter_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    filtered: list[dict[str, str]] = []
    for row in rows:
        joined = " ".join(row.values()).strip().lower()
        if not joined:
            continue
        if "pending" in joined and "succeeded" not in joined and "failed" not in joined:
            continue
        if "planned" in joined and "result" not in joined:
            continue
        filtered.append(row)
    return filtered


def issue(
    severity: str,
    area: str,
    summary: str,
    *,
    evidence: str = "",
    next_action: str = "",
    repairable: bool = False,
) -> dict[str, Any]:
    return {
        "severity": severity,
        "area": area,
        "summary": summary,
        "evidence": evidence,
        "next_action": next_action,
        "repairable": repairable,
    }


def sort_issues(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(issues, key=lambda item: (SEVERITY_RANK.get(str(item.get("severity")), 99), str(item.get("area"))))


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def latest_activity_mtime(root: Path) -> float:
    telemetry_files = set(DIAGNOSTIC_TELEMETRY_FILES)
    mtimes = []
    for relative in RECENT_ACTIVITY_FILES:
        if relative not in telemetry_files:
            path = root / relative
            if not path.exists():
                continue
            try:
                mtimes.append(path.stat().st_mtime)
            except OSError:
                continue
    return max(mtimes, default=0.0)


def experiment_run_states(root: Path) -> list[dict[str, Any]]:
    states: list[dict[str, Any]] = []
    experiments = root / "03_experiments"
    if not experiments.is_dir():
        return states
    for path in sorted(experiments.glob("exp_*/run_state.json")):
        data = read_json(path, {})
        if isinstance(data, dict):
            data = dict(data)
            data["_path"] = rel(root, path)
            data["_exp_id"] = path.parent.name
            states.append(data)
    return states


def baseline_snapshot_dirs(root: Path) -> list[Path]:
    base = root / "08_baselines" / "source_snapshots"
    if not base.is_dir():
        return []
    return sorted(path for path in base.iterdir() if path.is_dir() and not path.name.startswith("."))


def parse_iso_epoch(value: Any) -> float | None:
    """Parse an ISO-8601 timestamp to epoch seconds; None for placeholders/unparseable.

    Returns true epoch via datetime.timestamp(), so an offset-aware value such as
    `2026-06-09T01:50:00+09:00` compares correctly against filesystem mtimes.
    """
    text = str(value or "").strip()
    if not text or "YYYY" in text:
        return None
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.timestamp()


def md_section_first_line(text: str, heading: str) -> str:
    """Return the first non-blank line under a `## <heading>` markdown section."""
    target = heading.strip().lower()
    in_section = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("## "):
            in_section = line[3:].strip().lower() == target
            continue
        if in_section and line:
            return line
    return ""


def reconciliation_issues(
    root: Path,
    latest_activity: float,
    *,
    stale_hours: float = RECONCILIATION_STALE_HOURS,
) -> list[dict[str, Any]]:
    """Flag canonical structured state surfaces that are frozen/stale vs real activity.

    This is the resume-time reconciliation gate: it catches the "shadow workflow"
    failure where real progress only ever lands in append-only freeform surfaces
    while the machine-readable state a fresh session reads first (loop_summary,
    current_state header, phase_gates, command_queue, agent_status) stays frozen
    at the intake default and silently lies.

    Hard no-op when the project has no real experiment activity (no result rows
    and no run_state files): a pristine freshly-created template legitimately
    still holds template defaults, so the check must never fire there and the
    template/smoke/verify gates stay green.
    """
    result_rows = nonstarter_rows(csv_rows(root / "05_results" / "experiment_results.csv"))
    active_runs = [
        state for state in experiment_run_states(root)
        if str(state.get("status") or "").lower() in {"succeeded", "failed", "running"}
    ]
    # No-op until an experiment has actually run: a pristine template carries
    # only a `planned` starter run_state and a header-only result CSV, so it must
    # not trigger here (keeps the template/smoke/verify gates green).
    if not (result_rows or active_runs):
        return []

    issues: list[dict[str, Any]] = []
    n_res = len(result_rows)
    activity = f"{n_res} working result row(s)" if n_res else f"{len(active_runs)} completed/running experiment(s)"
    t_live = float(latest_activity or 0.0)
    stale_secs = max(0.0, stale_hours) * 3600.0

    def behind(epoch: float) -> int:
        return int(round((t_live - epoch) / 3600.0))

    # 1) loop_summary frozen at the initial planning loop, or far behind activity.
    loop = read_json(root / "state" / "loop_summary.json", {})
    if isinstance(loop, dict):
        status = str(loop.get("status") or "").lower()
        completed = loop.get("completed_commands") or []
        last_updated = parse_iso_epoch(loop.get("last_updated"))
        if status == "planned" and not completed:
            issues.append(issue(
                "high", "reconciliation",
                f"loop_summary.json is still at the initial `planned` loop with no completed_commands while {activity} exist.",
                evidence="state/loop_summary.json",
                next_action="Advance loop_summary (status, goal, completed_commands, last_updated) to the real current loop; do not leave it at the intake default.",
            ))
        elif last_updated and t_live > 0 and t_live - last_updated > stale_secs:
            issues.append(issue(
                "high", "reconciliation",
                f"loop_summary.last_updated is ~{behind(last_updated)}h behind the newest project activity.",
                evidence="state/loop_summary.json",
                next_action="Update loop_summary after each loop so a fresh session reads the real current loop, not a stale one.",
            ))

    # 2) current_state.md structured header still at template defaults.
    cs_text = read_text(root / "state" / "current_state.md")
    if cs_text:
        stage = md_section_first_line(cs_text, "Current Stage")
        question = md_section_first_line(cs_text, "Research Question")
        last_line = md_section_first_line(cs_text, "Last Updated")
        defaults: list[str] = []
        if stage.lower() == "brief":
            defaults.append("Current Stage=`brief`")
        if question.lower().startswith("not yet"):
            defaults.append("Research Question=`Not yet finalized`")
        if last_line.upper().startswith("YYYY"):
            defaults.append("Last Updated=`YYYY-MM-DD`")
        if defaults:
            issues.append(issue(
                "high", "reconciliation",
                f"current_state.md structured header is still at template defaults ({', '.join(defaults)}) while {activity} exist.",
                evidence="state/current_state.md",
                next_action="Rewrite the current_state header (Current Stage, Research Question, Current Hypothesis, Last Updated) to match real progress; appending to the bottom of the file is not enough.",
            ))

    # 3) phase_gates all pending while results exist (file absent on a pristine template).
    gates = read_json(root / "state" / "phase_gates.json", {})
    phases = gates.get("phases") if isinstance(gates, dict) else []
    phases = phases if isinstance(phases, list) else []
    if phases and all(str(phase.get("status") or "").lower() == "pending" for phase in phases):
        issues.append(issue(
            "medium", "reconciliation",
            f"All {len(phases)} phase gates are still `pending` while {activity} exist.",
            evidence="state/phase_gates.json",
            next_action="Advance phase_gates to reflect the phases already entered (for example experiments in_progress).",
        ))

    # 4) command queue has no open work and is stale vs activity (work outside the queue).
    queue = read_json(root / "state" / "command_queue.json", {})
    commands = queue.get("commands") if isinstance(queue, dict) else []
    commands = commands if isinstance(commands, list) else []
    open_commands = [c for c in commands if str(c.get("status") or "").lower() in {"open", "in progress", "blocked"}]
    queue_stamps = [epoch for c in commands for epoch in [parse_iso_epoch(c.get("updated_at"))] if epoch]
    if commands and not open_commands and queue_stamps and t_live > 0:
        queue_last = max(queue_stamps)
        if t_live - queue_last > stale_secs:
            issues.append(issue(
                "medium", "reconciliation",
                f"command_queue has no open work and was last updated ~{behind(queue_last)}h before the newest activity — experiments appear to be running outside the queue.",
                evidence="state/command_queue.json",
                next_action="Track ongoing experiments as queue commands (owner, depends_on, expected outputs) so the loop stays auditable.",
            ))

    # 5) zombie agents stuck running/waiting long after the last lifecycle event.
    status_doc = read_json(root / "state" / "agent_status.json", {})
    agents = status_doc.get("agents") if isinstance(status_doc, dict) else []
    agents = agents if isinstance(agents, list) else []
    newest_event = 0.0
    for event in jsonl_rows(root / "state" / "agent_events.jsonl"):
        epoch = parse_iso_epoch(event.get("timestamp"))
        if epoch:
            newest_event = max(newest_event, epoch)
    reference = max(newest_event, t_live)
    for agent in agents:
        state = str(agent.get("status") or "").lower()
        if state not in {"running", "waiting"}:
            continue
        updated = parse_iso_epoch(agent.get("updated_at"))
        if updated and reference > 0 and reference - updated > stale_secs:
            name = str(agent.get("name") or agent.get("agent") or "?")
            issues.append(issue(
                "medium", "reconciliation",
                f"Agent `{name}` has been `{state}` for ~{int(round((reference - updated) / 3600.0))}h with no newer lifecycle event — likely a zombie status.",
                evidence="state/agent_status.json",
                next_action="Transition stale running/waiting agents to a terminal status (done/blocked); every status must eventually resolve.",
            ))
    return issues


def build_diagnostics(root: Path, *, caller: str = "") -> dict[str, Any]:
    issues: list[dict[str, Any]] = []
    observations: list[str] = []
    latest_activity = latest_activity_mtime(root)

    for relative in REQUIRED_STATE_FILES:
        path = root / relative
        if not path.exists():
            issues.append(issue("critical", "state", f"Missing required state file: `{relative}`.", evidence=relative, next_action="Restore the missing starter file from the template or run the relevant harness initializer.", repairable=True))

    for relative in DIAGNOSTIC_STATE_FILES:
        if caller == "project_health" and relative == "state/project_health.md":
            continue
        if caller == "state_doctor" and relative == "state/state_doctor.md":
            continue
        path = root / relative
        if not path.exists():
            issues.append(issue("medium", "diagnostics", f"Missing dashboard-free diagnostic surface: `{relative}`.", evidence=relative, next_action="Refresh health/state diagnostics before choosing lower-priority work.", repairable=True))
        elif not has_real_content(path):
            issues.append(issue("low", "diagnostics", f"Diagnostic surface is still starter-level: `{relative}`.", evidence=relative, next_action="Refresh this diagnostic surface after project activity changes."))
        elif latest_activity and path.stat().st_mtime + 1 < latest_activity:
            issues.append(issue("low", "diagnostics", f"Diagnostic surface is older than recent project progress: `{relative}`.", evidence=relative, next_action="Refresh health/state diagnostics before relying on this report."))

    for relative in WORKING_EVIDENCE_FILES:
        path = root / relative
        if not path.exists():
            issues.append(issue("medium", "evidence", f"Missing working evidence file: `{relative}`.", evidence=relative, next_action="Create the working evidence ledger before relying on this project state.", repairable=True))

    if not has_real_content(root / "00_brief" / "research_question.md"):
        issues.append(issue("high", "brief", "Research question is still starter-level or missing.", evidence="00_brief/research_question.md", next_action="Run brief intake or motivation planning before literature, baseline, or experiment work."))
    if not has_real_content(root / "00_brief" / "motivation.md"):
        issues.append(issue("medium", "brief", "Motivation is still starter-level or missing.", evidence="00_brief/motivation.md", next_action="Capture the user-facing motivation and expected contribution."))

    queue = read_json(root / "state" / "command_queue.json", {"commands": []})
    commands = queue.get("commands") if isinstance(queue, dict) else []
    commands = commands if isinstance(commands, list) else []
    open_commands = [cmd for cmd in commands if str(cmd.get("status") or "").lower() in {"open", "in progress", "blocked"}]
    in_progress = [cmd for cmd in commands if str(cmd.get("status") or "").lower() == "in progress"]
    blocked = [cmd for cmd in commands if str(cmd.get("status") or "").lower() == "blocked"]
    observations.append(f"Command queue: {len(open_commands)} active, {len(in_progress)} in progress, {len(blocked)} blocked.")

    status_doc = read_json(root / "state" / "agent_status.json", {"agents": []})
    agents = status_doc.get("agents") if isinstance(status_doc, dict) else []
    agents = agents if isinstance(agents, list) else []
    running_agents = {str(agent.get("name") or "") for agent in agents if str(agent.get("status") or "").lower() == "running"}
    in_progress_owners = {str(cmd.get("owner_agent") or "") for cmd in in_progress}
    for cmd in in_progress:
        owner = str(cmd.get("owner_agent") or "")
        if owner and owner not in running_agents:
            issues.append(issue("medium", "agent_state", f"Command `{cmd.get('id')}` is in progress but owner `{owner}` is not running.", evidence="state/command_queue.json", next_action="Reconcile the command with agent_status or move it back to open/blocked."))
    for agent in sorted(running_agents - in_progress_owners):
        issues.append(issue("low", "agent_state", f"Agent `{agent}` is running without a matching in-progress command.", evidence="state/agent_status.json", next_action="Confirm whether this is a heartbeat-only run or stale status."))

    run_states = experiment_run_states(root)
    succeeded = [state for state in run_states if str(state.get("status") or "").lower() == "succeeded"]
    failed = [state for state in run_states if str(state.get("status") or "").lower() == "failed"]
    running = [state for state in run_states if str(state.get("status") or "").lower() == "running"]
    observations.append(f"Experiments: {len(run_states)} run_state files, {len(succeeded)} succeeded, {len(failed)} failed, {len(running)} running.")
    experiment_dag = read_json(root / "03_experiments" / "experiment_dag.json", {})
    dag_plans = experiment_dag.get("plans") if isinstance(experiment_dag, dict) else []
    if run_states and not dag_plans:
        issues.append(issue("medium", "experiments", "Experiment run_state files exist but experiment_dag.json has no plans.", evidence="03_experiments/experiment_dag.json", next_action="Record the smoke-first experiment plan and parallel-run dependencies."))
    for state in succeeded:
        exp_id = str(state.get("_exp_id") or "")
        analysis = root / "03_experiments" / exp_id / "analysis.md"
        if not has_real_content(analysis):
            issues.append(issue("high", "experiments", f"Succeeded experiment `{exp_id}` has no real analysis note.", evidence=rel(root, analysis), next_action="Analyze why performance improved, regressed, or stayed flat and record evidence-backed causes."))

    journal_rows = nonstarter_rows(csv_rows(root / "05_results" / "experiment_journal.csv"))
    result_rows = nonstarter_rows(csv_rows(root / "05_results" / "experiment_results.csv"))
    if result_rows and not journal_rows:
        issues.append(issue("high", "results", "Working result rows exist without matching experiment journal rows.", evidence="05_results/experiment_results.csv", next_action="Update experiment_journal.md/csv with why the run happened, result, and movement analysis."))
    for row in journal_rows:
        label = row.get("experiment") or row.get("experiment_id") or "unknown"
        analysis = row.get("result_analysis") or row.get("analysis") or row.get("why") or ""
        if not analysis.strip():
            issues.append(issue("medium", "results", f"Experiment journal row `{label}` is missing result_analysis.", evidence="05_results/experiment_journal.csv", next_action="Explain the likely cause of improvement/regression/flat movement."))

    data_roots_text = read_text(root / "03_experiments" / "data_roots.md")
    if result_rows and ("pending" in data_roots_text.lower() or "not yet" in data_roots_text.lower()):
        issues.append(issue("high", "data", "Results exist but data roots still look unresolved.", evidence="03_experiments/data_roots.md", next_action="Record dataset root, split/version, derived-data path, and provenance."))

    terminology = read_text(root / "06_writing" / "terminology.md")
    if "pending_project_terms" in terminology:
        issues.append(issue("medium", "writing", "Terminology glossary is still starter-level.", evidence="06_writing/terminology.md", next_action="Define canonical method, dataset, metric, baseline, and claim terms before drafting."))

    snapshots = baseline_snapshot_dirs(root)
    if snapshots and not has_real_content(root / "08_baselines" / "baseline_compare.md"):
        issues.append(issue("medium", "baselines", "Baseline source snapshots exist but no baseline comparison report is present.", evidence="08_baselines/source_snapshots/", next_action="Run baseline compare and update code_structure_plan.md before shaping 04_code/src/."))
    if snapshots and not has_real_content(root / "08_baselines" / "code_structure_plan.md"):
        issues.append(issue("medium", "baselines", "Baseline code structure plan is missing or starter-level.", evidence="08_baselines/code_structure_plan.md", next_action="Compare baseline config/data/model/eval layouts and choose project interfaces."))

    claim_graph_path = root / "05_results" / "claim_graph.json"
    if not claim_graph_path.exists():
        issues.append(issue("low", "claims", "No working claim graph has been generated yet.", evidence="05_results/claim_graph.json", next_action="Build the claim graph after claims or experiment evidence exist.", repairable=True))
    elif result_rows:
        claim_graph = read_json(claim_graph_path, {})
        nodes = claim_graph.get("nodes") if isinstance(claim_graph, dict) else []
        edges = claim_graph.get("edges") if isinstance(claim_graph, dict) else []
        if not nodes or not edges:
            issues.append(issue("medium", "claims", "Working result rows exist but the claim graph has no useful nodes or edges.", evidence="05_results/claim_graph.json", next_action="Refresh the claim graph and connect results, analysis notes, baselines, and claims before writing."))

    if not (root / "state" / "progress_hooks.jsonl").exists():
        issues.append(issue("low", "progress", "No progress checkpoint log exists yet.", evidence="state/progress_hooks.jsonl", next_action="Use progress_checkpoint during long work so mid-pass state is durable.", repairable=True))

    gpu_queue = read_json(root / "state" / "gpu_experiment_queue.json", {"jobs": []})
    jobs = gpu_queue.get("jobs") if isinstance(gpu_queue, dict) else []
    jobs = jobs if isinstance(jobs, list) else []
    queued_jobs = [job for job in jobs if str(job.get("status") or "").lower() == "queued"]
    running_jobs = [job for job in jobs if str(job.get("status") or "").lower() == "running"]
    observations.append(f"GPU queue: {len(queued_jobs)} queued, {len(running_jobs)} running.")
    for job in queued_jobs + running_jobs:
        missing = [field for field in ("command", "expected_output", "check_procedure") if not str(job.get(field) or "").strip()]
        if missing:
            issues.append(issue("medium", "gpu", f"GPU job `{job.get('id')}` is missing metadata: {', '.join(missing)}.", evidence="state/gpu_experiment_queue.json", next_action="Record command, expected output, and check procedure before launch/monitoring."))

    progress_rows = jsonl_rows(root / "state" / "progress_hooks.jsonl")
    event_rows = jsonl_rows(root / "state" / "agent_events.jsonl")
    observations.append(f"Progress checkpoints: {len(progress_rows)}. Agent events: {len(event_rows)}.")

    issues.extend(reconciliation_issues(root, latest_activity))

    sorted_issues = sort_issues(issues)
    high_or_worse = [item for item in sorted_issues if SEVERITY_RANK.get(str(item.get("severity")), 99) <= SEVERITY_RANK["high"]]
    medium = [item for item in sorted_issues if str(item.get("severity")) == "medium"]
    score = max(0, 100 - 25 * len([i for i in sorted_issues if i["severity"] == "critical"]) - 15 * len([i for i in sorted_issues if i["severity"] == "high"]) - 7 * len(medium) - 2 * len([i for i in sorted_issues if i["severity"] == "low"]))
    if any(item["severity"] == "critical" for item in sorted_issues):
        overall = "broken"
    elif high_or_worse:
        overall = "needs_attention"
    elif medium:
        overall = "usable_with_gaps"
    else:
        overall = "healthy"

    next_action = sorted_issues[0]["next_action"] if sorted_issues else "Continue the highest-value command queue item and keep progress checkpointed."
    issue_areas = {str(item.get("area") or "") for item in sorted_issues}
    recommended_requests: list[str] = []
    if "state" in issue_areas or "evidence" in issue_areas or "diagnostics" in issue_areas:
        recommended_requests.append(
            "Run state doctor repair for safe missing starter surfaces, then refresh state doctor and project health before choosing lower-priority work."
        )
    if "brief" in issue_areas:
        recommended_requests.append(
            "Run brief intake or motivation planning. Turn the rough idea into durable brief files and open questions without guessing missing dataset, metric, baseline, or compute constraints."
        )
    if "experiments" in issue_areas or "results" in issue_areas:
        recommended_requests.append(
            "Repair experiment evidence. Update the experiment journal, per-experiment analysis, result CSV, and explain why performance improved, regressed, or stayed flat."
        )
    if "data" in issue_areas:
        recommended_requests.append(
            "Normalize experiment data roots. Record dataset root, split/version, derived-data path, and provenance before trusting result rows."
        )
    if "gpu" in issue_areas:
        recommended_requests.append(
            "Repair GPU queue metadata. Record each queued/running job's command, expected output, check procedure, and scheduler job id if launched."
        )
    if "baselines" in issue_areas:
        recommended_requests.append(
            "Compare baseline source structures before shaping project code. Keep cloned snapshots read-only and update the baseline code structure plan."
        )
    if "claims" in issue_areas:
        recommended_requests.append(
            "Build the working claim graph and identify unsupported, weak, or analysis-missing claims before writing."
        )
    if "writing" in issue_areas:
        recommended_requests.append(
            "Normalize paper terminology. Define canonical method, dataset, metric, baseline, claim, and abbreviation terms before drafting or final export."
        )
    if "agent_state" in issue_areas or "progress" in issue_areas:
        recommended_requests.append(
            "Audit agent continuity. Check whether done work has output-file evidence and whether progress checkpoints are sufficient for a fresh session."
        )
    if "reconciliation" in issue_areas:
        recommended_requests.append(
            "Reconcile the canonical state surfaces (loop_summary, current_state header, phase_gates, command_queue, agent_status) with the real progress so a fresh session resumes from the truth, not the intake default."
        )
    if not recommended_requests:
        recommended_requests.append(
            "Continue the highest-value command queue item. Refresh project health after meaningful progress is saved."
        )
    suggested_commands: list[dict[str, str]] = []
    if "state" in issue_areas or "evidence" in issue_areas or "diagnostics" in issue_areas:
        suggested_commands.append({
            "owner_agent": "director",
            "priority": "high",
            "action": "Run state doctor repair for safe missing starter surfaces, then refresh state doctor and project health before continuing research work.",
            "required_inputs": "HANDOFF.md, state/current_state.md, state/command_queue.json",
            "expected_outputs": "state/state_doctor.md, state/project_health.md, state/progress_hooks.jsonl, 03_experiments/data_roots.md, 05_results/experiment_results.csv, 06_writing/terminology.md",
        })
    if "brief" in issue_areas:
        suggested_commands.append({
            "owner_agent": "motivation_planner",
            "priority": "high",
            "action": "Clarify the research brief from the user's idea, update durable brief files, and record missing dataset/metric/baseline/compute details as open questions.",
            "expected_outputs": "00_brief/, 02_planning/intake_summary.md, state/open_questions.md",
        })
    if "experiments" in issue_areas:
        suggested_commands.append({
            "owner_agent": "experiment_designer",
            "priority": "high",
            "action": "Create or repair the smoke-first experiment DAG, including dependencies, parallel main-run groups, expected outputs, and check procedures.",
            "expected_outputs": "02_planning/experiment_plan.md, 03_experiments/experiment_dag.json",
        })
    if "results" in issue_areas or "data" in issue_areas:
        suggested_commands.append({
            "owner_agent": "data_analyst",
            "priority": "high",
            "action": "Repair experiment result evidence, data roots, journal rows, and analysis explaining why performance improved, regressed, or stayed flat.",
            "expected_outputs": "03_experiments/data_roots.md, 03_experiments/<exp_id>/analysis.md, 05_results/experiment_journal.md, 05_results/experiment_journal.csv",
        })
    if "claims" in issue_areas:
        suggested_commands.append({
            "owner_agent": "result_interpreter",
            "priority": "medium",
            "action": "Refresh the working claim graph and identify unsupported, weak, or analysis-missing claims before writing or final export.",
            "expected_outputs": "05_results/claim_graph.md, 05_results/claim_graph.json, 05_results/interpretation.md",
        })
    if "baselines" in issue_areas:
        suggested_commands.append({
            "owner_agent": "code_agent",
            "priority": "medium",
            "action": "Compare cloned baseline source structures and update the project code structure plan before shaping substantial project code.",
            "expected_outputs": "08_baselines/baseline_compare.md, 08_baselines/code_structure_plan.md",
        })
    if "agent_state" in issue_areas or "progress" in issue_areas:
        suggested_commands.append({
            "owner_agent": "critic",
            "priority": "medium",
            "action": "Audit whether prior agent work is resumable from files and repair missing output-file evidence or checkpoints.",
            "expected_outputs": "07_reviews/agent_quality_audit.md, state/agent_memory.md, state/next_actions.md",
        })
    if "reconciliation" in issue_areas:
        suggested_commands.append({
            "owner_agent": "director",
            "priority": "high",
            "action": "Reconcile canonical state surfaces with real progress: rewrite the current_state header, advance loop_summary and phase_gates, reflect ongoing experiments in the command queue, and resolve zombie agent statuses.",
            "expected_outputs": "state/current_state.md, state/loop_summary.json, state/phase_gates.json, state/command_queue.json, state/agent_status.json",
        })
    if "gpu" in issue_areas:
        suggested_commands.append({
            "owner_agent": "code_agent",
            "priority": "medium",
            "action": "Repair GPU queue metadata and scheduler lifecycle state for queued or running jobs.",
            "expected_outputs": "state/gpu_experiment_queue.json, 03_experiments/<exp_id>/run_state.json",
        })
    if not suggested_commands:
        suggested_commands.append({
            "owner_agent": "director",
            "priority": "medium",
            "action": "Continue the highest-value open command and refresh project health after meaningful progress is saved.",
            "expected_outputs": "state/project_health.md, state/next_actions.md, HANDOFF.md",
        })
    return {
        "project": project_display_name(root),
        "generated_at": now_utc(),
        "overall": overall,
        "score": score,
        "next_action": next_action,
        "recommended_agent_requests": recommended_requests,
        "suggested_commands": suggested_commands,
        "issues": sorted_issues,
        "observations": observations,
        "counts": {
            "issues": len(sorted_issues),
            "critical": len([item for item in sorted_issues if item["severity"] == "critical"]),
            "high": len([item for item in sorted_issues if item["severity"] == "high"]),
            "medium": len([item for item in sorted_issues if item["severity"] == "medium"]),
            "low": len([item for item in sorted_issues if item["severity"] == "low"]),
            "open_commands": len(open_commands),
            "in_progress_commands": len(in_progress),
            "blocked_commands": len(blocked),
            "run_states": len(run_states),
            "result_rows": len(result_rows),
            "journal_rows": len(journal_rows),
            "baseline_snapshots": len(snapshots),
            "queued_gpu_jobs": len(queued_jobs),
            "running_gpu_jobs": len(running_jobs),
        },
    }


def markdown_escape(value: str) -> str:
    return str(value).replace("|", "\\|")


def render_issue_table(issues: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| Severity | Area | Issue | Evidence | Next Action |",
        "| --- | --- | --- | --- | --- |",
    ]
    if not issues:
        lines.append("| info | all | No active diagnostic issues. | - | Continue current plan. |")
        return lines
    for item in issues:
        lines.append(
            "| {severity} | {area} | {summary} | `{evidence}` | {next_action} |".format(
                severity=markdown_escape(item.get("severity", "")),
                area=markdown_escape(item.get("area", "")),
                summary=markdown_escape(item.get("summary", "")),
                evidence=markdown_escape(item.get("evidence", "")) or "-",
                next_action=markdown_escape(item.get("next_action", "")) or "-",
            )
        )
    return lines


def render_suggested_command_table(commands: list[dict[str, str]]) -> list[str]:
    lines = [
        "| Owner Agent | Priority | Action | Required Inputs | Expected Outputs |",
        "| --- | --- | --- | --- | --- |",
    ]
    if not commands:
        lines.append("| director | medium | Continue the highest-value open command. | `state/command_queue.json` | `state/next_actions.md` |")
        return lines
    for command in commands:
        lines.append(
            "| {owner_agent} | {priority} | {action} | `{required_inputs}` | `{expected_outputs}` |".format(
                owner_agent=markdown_escape(command.get("owner_agent", "")),
                priority=markdown_escape(command.get("priority", "")),
                action=markdown_escape(command.get("action", "")),
                required_inputs=markdown_escape(command.get("required_inputs", "state/project_health.md, state/state_doctor.md")),
                expected_outputs=markdown_escape(command.get("expected_outputs", "")),
            )
        )
    return lines


def render_enqueue_plan_table(commands: list[dict[str, Any]]) -> list[str]:
    lines = [
        "| Command ID | Owner Agent | Priority | Action | Required Inputs | Expected Outputs |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    if not commands:
        lines.append("| - | - | - | No enqueue entries planned. | - | - |")
        return lines
    for command in commands:
        expected_outputs = command.get("expected_outputs") or []
        if isinstance(expected_outputs, list):
            outputs = ", ".join(str(item) for item in expected_outputs)
        else:
            outputs = str(expected_outputs)
        required_inputs = command.get("required_inputs") or []
        if isinstance(required_inputs, list):
            inputs = ", ".join(str(item) for item in required_inputs)
        else:
            inputs = str(required_inputs)
        lines.append(
            "| `{id}` | {owner_agent} | {priority} | {action} | `{required_inputs}` | `{expected_outputs}` |".format(
                id=markdown_escape(command.get("id", "")),
                owner_agent=markdown_escape(command.get("owner_agent", "")),
                priority=markdown_escape(command.get("priority", "")),
                action=markdown_escape(command.get("action", "")),
                required_inputs=markdown_escape(inputs),
                expected_outputs=markdown_escape(outputs),
            )
        )
    return lines


def render_state_doctor(diagnostics: dict[str, Any]) -> str:
    repaired = diagnostics.get("repaired") or []
    repair_errors = diagnostics.get("repair_errors") or []
    repair_dry_run = bool(diagnostics.get("repair_dry_run"))
    lines = [
        "# State Doctor",
        "",
        f"- Project: `{diagnostics['project']}`",
        f"- Generated at: `{diagnostics.get('generated_at', '-')}`",
        f"- Overall: `{diagnostics['overall']}`",
        f"- Health score: {diagnostics['score']}/100",
        f"- Issues: {diagnostics['counts']['issues']} total, {diagnostics['counts']['critical']} critical, {diagnostics['counts']['high']} high, {diagnostics['counts']['medium']} medium, {diagnostics['counts']['low']} low",
        f"- Repair mode: `{diagnostics.get('repair_mode', 'none')}`",
        f"- Repair file count: {diagnostics.get('repaired_count', 0)}",
        "",
        "## Next Repair Action",
        "",
        f"- {diagnostics['next_action']}",
        "",
        "## Recommended Agent Requests",
        "",
    ]
    lines.extend(f"- {item}" for item in diagnostics.get("recommended_agent_requests", []))
    lines.extend([
        "",
        "## Suggested Command Queue Entries",
        "",
        *render_suggested_command_table(diagnostics.get("suggested_commands", [])),
        "",
        "## Enqueue Preview",
        "",
        *render_enqueue_plan_table(diagnostics.get("planned_enqueue_commands", [])),
        "",
        "## Repaired Files",
        "",
    ])
    if repaired and repair_dry_run:
        lines.append("- Repair dry run only; no files were created.")
        lines.extend(f"- Planned: `{item}`" for item in repaired)
    elif repaired:
        lines.extend(f"- `{item}`" for item in repaired)
    elif repair_dry_run:
        lines.append("- Repair dry run only; no files would be created.")
    else:
        lines.append("- No repair files were created in this run.")
    lines.extend([
        "",
        "## Repair Errors",
        "",
    ])
    if repair_errors:
        lines.extend(f"- {item}" for item in repair_errors)
    else:
        lines.append("- No repair errors.")
    lines.extend([
        "",
        "## Issues",
        "",
        *render_issue_table(diagnostics["issues"]),
        "",
        "## Observations",
        "",
    ])
    lines.extend(f"- {item}" for item in diagnostics.get("observations", []))
    lines.extend([
        "",
        "## Repair Policy",
        "",
        "- Use this report to identify stale, missing, or inconsistent project state.",
        "- Repair creates only safe starter files or template-backed continuity files; it does not infer research content.",
        "- Prefer harness CLIs for structured JSON updates; do not hand-edit state JSON unless repairing a known malformed file.",
        "- This doctor report is working state, not a final `09_report/` artifact.",
    ])
    return "\n".join(lines) + "\n"


def render_project_health(diagnostics: dict[str, Any]) -> str:
    counts = diagnostics["counts"]
    lines = [
        "# Project Health Report",
        "",
        f"- Project: `{diagnostics['project']}`",
        f"- Generated at: `{diagnostics.get('generated_at', '-')}`",
        f"- Overall: `{diagnostics['overall']}`",
        f"- Health score: {diagnostics['score']}/100",
        "",
        "## Next Best Action",
        "",
        f"- {diagnostics['next_action']}",
        "",
        "## Recommended Agent Requests",
        "",
    ]
    lines.extend(f"- {item}" for item in diagnostics.get("recommended_agent_requests", []))
    lines.extend([
        "",
        "## Suggested Command Queue Entries",
        "",
        *render_suggested_command_table(diagnostics.get("suggested_commands", [])),
        "",
        "## Enqueue Preview",
        "",
        *render_enqueue_plan_table(diagnostics.get("planned_enqueue_commands", [])),
        "",
        "## Snapshot",
        "",
        f"- Active commands: {counts['open_commands']} open/in-progress/blocked",
        f"- Experiments tracked: {counts['run_states']}",
        f"- Working result rows: {counts['result_rows']}",
        f"- Experiment journal rows: {counts['journal_rows']}",
        f"- Baseline source snapshots: {counts['baseline_snapshots']}",
        f"- GPU jobs: {counts['queued_gpu_jobs']} queued, {counts['running_gpu_jobs']} running",
        "",
        "## High Priority Issues",
        "",
    ])
    urgent = [item for item in diagnostics["issues"] if item["severity"] in {"critical", "high"}]
    lines.extend(render_issue_table(urgent))
    lines.extend([
        "",
        "## All Issues",
        "",
        *render_issue_table(diagnostics["issues"]),
        "",
        "## How To Use This Without Dashboard",
        "",
        "- Ask Claude/Codex to read this file before choosing the next project action.",
        "- Treat the first high-priority issue as the default next action unless the user overrides it.",
        "- When both diagnostic surfaces are stale, refresh state doctor first, then project health.",
        "- Keep this file in `state/`; it is a dashboard replacement, not a final report artifact.",
    ])
    return "\n".join(lines) + "\n"
