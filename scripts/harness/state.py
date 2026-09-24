#!/usr/bin/env python3
"""Shared state helpers for the research-agent harness."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from scripts.harness import (
    HarnessError,
    atomic_write_json,
    atomic_write_json_unlocked,
    load_json,
    locked_state_file,
    now_iso,
    project_root,  # noqa: F401
    repo_root,
    split_values,  # noqa: F401
)
from scripts.harness.command_mirror import sync_next_actions
from scripts.harness.state_base import StateDoc
from scripts.harness.workspace_profile import (
    ProfileError,
    workspace_gpu_max_user_gpus,
    workspace_gpu_types,
)


def _known_gpu_types() -> set[str]:
    try:
        return workspace_gpu_types()
    except ProfileError as exc:
        print(
            f"warning: workspace profile is invalid ({exc}); fallback to 'auto'.", file=sys.stderr
        )
        return {"auto"}


AGENT_STATUSES = {"idle", "running", "waiting", "blocked", "done"}
QUEUE_STATUSES = {"open", "in progress", "blocked", "done", "deferred"}
QUEUE_PRIORITIES = {"high", "medium", "low"}
RISK_LEVELS = {"low", "medium", "high", "critical"}
VOTE_STATUSES = {"open", "approved", "rejected", "cancelled"}
VOTE_VALUES = {"approve", "reject", "abstain"}
RUN_STATUSES = {"planned", "queued", "running", "succeeded", "failed", "blocked", "cancelled"}
LOOP_STATUSES = {"planned", "running", "done", "blocked", "waiting"}
MESSAGE_STATUSES = {"open", "acknowledged", "resolved", "blocked", "cancelled"}
MESSAGE_PRIORITIES = {"high", "medium", "low"}
MESSAGE_KINDS = {"request", "question", "handoff", "review", "blocker", "decision", "info"}
PATTERN_STATUSES = {"candidate", "active", "deprecated"}
RALPH_LOOP_STATUSES = {
    "idle",
    "running",
    "complete",
    "blocked",
    "timeout",
    "max_iterations",
    "cancelled",
}
GPU_JOB_STATUSES = {"queued", "running", "succeeded", "failed", "blocked", "cancelled", "deferred"}
GPU_TYPES = _known_gpu_types()
BASELINE_STATUSES = {
    "candidate",
    "source_found",
    "porting",
    "runnable",
    "reproduced",
    "failed",
    "rejected",
    "deprecated",
}
REVIEW_FORM_STAGES = {"review", "meta_review", "rebuttal", "camera_ready", "custom"}


def ensure_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise HarnessError(f"{name} must be a list.")
    return value


# --- Agent Events (JSONL special case) ---


def agent_events_path(root: Path) -> Path:
    return root / "state" / "agent_events.jsonl"


def append_agent_event(
    root: Path,
    event: str,
    agent_name: str,
    *,
    status: str = "",
    command_id: str = "",
    task: str = "",
    stage: str = "",
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
    notes: str = "",
) -> dict[str, Any]:
    event, agent_name = str(event or "").strip(), str(agent_name or "").strip()
    status = str(status or "").strip().lower()
    if not event or not agent_name:
        raise HarnessError("Event and agent must not be empty.")
    if status and status not in AGENT_STATUSES:
        raise HarnessError(f"Invalid status: {status}")
    record = {
        "timestamp": now_iso(),
        "event": event,
        "agent": agent_name,
        "status": status,
        "command_id": command_id,
        "task": task,
        "stage": stage,
        "inputs": inputs or [],
        "outputs": outputs or [],
        "notes": notes,
    }
    path = agent_events_path(root)
    with locked_state_file(path):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as h:
            h.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def load_agent_events(root: Path) -> list[dict[str, Any]]:
    path = agent_events_path(root)
    if not path.exists():
        return []
    events = []
    for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as e:
            raise HarnessError(f"Invalid JSONL in {path} line {i}: {e.msg}.") from e
    return events


def validate_agent_events(root: Path) -> list[str]:
    warnings = []
    if not agent_events_path(root).exists():
        return ["Missing state/agent_events.jsonl."]
    for i, e in enumerate(load_agent_events(root), 1):
        for f in ("timestamp", "event", "agent"):
            if not str(e.get(f) or "").strip():
                warnings.append(f"agent_events.jsonl row {i} missing {f}.")
        s = str(e.get("status") or "").strip().lower()
        if s and s not in AGENT_STATUSES:
            raise HarnessError(f"Row {i} invalid status: {s}")
    return warnings


# --- Document Validation Functions ---


def validate_agent_status_doc(data: dict[str, Any]) -> list[str]:
    warnings = []
    agents = data.get("agents")
    if not isinstance(agents, list):
        raise HarnessError("Missing agents array.")
    seen = set()
    for i, a in enumerate(agents):
        name = str(a.get("name") or "").strip()
        if not name or name in seen:
            raise HarnessError(f"Agent name missing or duplicate: {name or i}")
        seen.add(name)
        s = str(a.get("status") or "").strip()
        if s not in AGENT_STATUSES:
            raise HarnessError(f"Agent {name} invalid status: {s}")
    return warnings


def validate_command_queue_doc(data: dict[str, Any]) -> list[str]:
    warnings = []
    cmds = data.get("commands")
    if not isinstance(cmds, list):
        raise HarnessError("Missing commands array.")
    cmd_by_id = {}
    for i, c in enumerate(cmds):
        cid = str(c.get("id") or "").strip()
        if not cid:
            raise HarnessError(f"Command at index {i} is missing id.")
        if cid in cmd_by_id:
            raise HarnessError(f"Duplicate command id found: {cid}")
        cmd_by_id[cid] = c
        s, p = (
            str(c.get("status") or "").strip().lower(),
            str(c.get("priority") or "").strip().lower(),
        )
        if s not in QUEUE_STATUSES:
            raise HarnessError(f"Command {cid} has invalid status: {s}")
        if p not in QUEUE_PRIORITIES:
            raise HarnessError(f"Command {cid} has invalid priority: {p}")

    # Cycle and existence detection
    visited, visiting, stack = set(), set(), []

    def visit(cid):
        if cid in visited:
            return
        if cid in visiting:
            path = " -> ".join(stack + [cid])
            raise HarnessError(f"Command dependency cycle detected: {path}")
        visiting.add(cid)
        stack.append(cid)
        for dep in cmd_by_id[cid].get("depends_on") or []:
            if dep == cid:
                raise HarnessError(f"Command {cid} depends on itself.")
            if dep not in cmd_by_id:
                raise HarnessError(f"Command {cid} depends on unknown command id: {dep}")
            visit(dep)
        stack.pop()
        visiting.remove(cid)
        visited.add(cid)

    for cid in cmd_by_id:
        visit(cid)

    # Duplicate check for audit needle
    for cid, cmd in cmd_by_id.items():
        deps = cmd.get("depends_on") or []
        if len(deps) != len(set(deps)):
            raise HarnessError(f"Command {cid} has duplicate dependency.")
    return warnings


def validate_agent_votes_doc(data: dict[str, Any]) -> list[str]:
    warnings = []
    decs = data.get("decisions")
    if not isinstance(decs, list):
        raise HarnessError("Missing decisions array.")
    seen = set()
    for i, d in enumerate(decs):
        did = str(d.get("id") or "").strip()
        if not did or did in seen:
            raise HarnessError(f"Decision ID missing or duplicate: {did or i}")
        seen.add(did)
    return warnings


def validate_pattern_memory_doc(data: dict[str, Any]) -> list[str]:
    if not isinstance(data.get("patterns"), list):
        raise HarnessError("Missing patterns array.")
    return []


def validate_ralph_loop_doc(data: dict[str, Any]) -> list[str]:
    if not isinstance(data.get("runs"), list):
        raise HarnessError("Missing runs array.")
    return []


def validate_run_state_doc(data: dict[str, Any]) -> list[str]:
    s = str(data.get("status") or "").strip().lower()
    if s not in RUN_STATUSES:
        raise HarnessError(f"Invalid run status: {s}")
    return []


def validate_gpu_queue_doc(data: dict[str, Any]) -> list[str]:
    if not isinstance(data.get("jobs"), list):
        raise HarnessError("Missing jobs array.")
    return []


def validate_loop_summary_doc(data: dict[str, Any]) -> list[str]:
    if not isinstance(data.get("completed_commands"), list):
        raise HarnessError("Missing completed_commands array.")
    return []


def validate_agent_messages_doc(data: dict[str, Any]) -> list[str]:
    if not isinstance(data.get("messages"), list):
        raise HarnessError("Missing messages array.")
    return []


def validate_baseline_registry_doc(data: dict[str, Any]) -> list[str]:
    if not isinstance(data.get("baselines"), list):
        raise HarnessError("Missing baselines array.")
    return []


def validate_review_form_registry_doc(data: dict[str, Any]) -> list[str]:
    if not isinstance(data.get("forms"), list):
        raise HarnessError("Missing forms array.")
    return []


# --- Path Functions ---


def agent_status_path(root: Path) -> Path:
    return root / "state" / "agent_status.json"


def command_queue_path(root: Path) -> Path:
    return root / "state" / "command_queue.json"


def agent_votes_path(root: Path) -> Path:
    return root / "state" / "agent_votes.json"


def pattern_memory_path(root: Path) -> Path:
    return root / "state" / "pattern_memory.json"


def ralph_loop_path(root: Path) -> Path:
    return root / "state" / "ralph_loop.json"


def run_state_path(root: Path, exp_id: str) -> Path:
    return root / "03_experiments" / exp_id / "run_state.json"


def gpu_queue_path(root: Path) -> Path:
    return root / "state" / "gpu_experiment_queue.json"


def loop_summary_path(root: Path) -> Path:
    return root / "state" / "loop_summary.json"


def agent_messages_path(root: Path) -> Path:
    return root / "state" / "agent_messages.json"


def baseline_registry_path(root: Path) -> Path:
    return root / "08_baselines" / "baseline_registry.json"


def review_form_registry_path() -> Path:
    return repo_root() / "review_forms" / "form_registry.json"


# --- Default Document Functions ---


def default_command_queue(name: str) -> dict:
    return {
        "project": name,
        "last_updated": now_iso(),
        "status_values": sorted(QUEUE_STATUSES),
        "priority_values": ["high", "medium", "low"],
        "commands": [],
    }


def default_agent_votes(name: str) -> dict:
    return {
        "project": name,
        "schema_version": 1,
        "last_updated": now_iso(),
        "status_values": sorted(VOTE_STATUSES),
        "vote_values": sorted(VOTE_VALUES),
        "risk_levels": sorted(RISK_LEVELS),
        "decisions": [],
    }


def default_pattern_memory(name: str) -> dict:
    return {
        "project": name,
        "schema_version": 1,
        "last_updated": now_iso(),
        "status_values": sorted(PATTERN_STATUSES),
        "patterns": [],
    }


def default_ralph_loop(name: str) -> dict:
    return {
        "project": name,
        "schema_version": 1,
        "last_updated": now_iso(),
        "status_values": sorted(RALPH_LOOP_STATUSES),
        "active_run_id": "",
        "runs": [],
    }


def default_gpu_queue(name: str) -> dict:
    return {
        "project": name,
        "schema_version": 1,
        "last_updated": now_iso(),
        "max_user_gpus": workspace_gpu_max_user_gpus(),
        "status_values": sorted(GPU_JOB_STATUSES),
        "gpu_types": sorted(workspace_gpu_types()),
        "jobs": [],
    }


def default_loop_summary(name: str) -> dict:
    return {
        "project": name,
        "loop_id": "loop_001",
        "status": "planned",
        "last_updated": now_iso(),
        "completed_commands": [],
        "results": [],
        "next_actions": [],
    }


def default_agent_messages(name: str) -> dict:
    return {
        "project": name,
        "schema_version": 1,
        "last_updated": now_iso(),
        "status_values": sorted(MESSAGE_STATUSES),
        "priority_values": ["high", "medium", "low"],
        "kind_values": sorted(MESSAGE_KINDS),
        "messages": [],
    }


def default_baseline_registry(name: str) -> dict:
    return {
        "project": name,
        "schema_version": 1,
        "last_updated": now_iso(),
        "status_values": sorted(BASELINE_STATUSES),
        "baselines": [],
    }


def default_review_form_registry(_) -> dict:
    return {"schema_version": 1, "last_updated": now_iso(), "forms": []}


def default_run_state(name: str, exp_id: str) -> dict:
    return {
        "project": name,
        "exp_id": exp_id,
        "status": "planned",
        "updated_at": now_iso(),
        "history": [],
    }


# --- StateDoc Instances ---

AGENT_STATUS_DOC = StateDoc(agent_status_path, validate_agent_status_doc)
COMMAND_QUEUE_DOC = StateDoc(command_queue_path, validate_command_queue_doc, default_command_queue)
AGENT_VOTES_DOC = StateDoc(agent_votes_path, validate_agent_votes_doc, default_agent_votes)
PATTERN_MEMORY_DOC = StateDoc(
    pattern_memory_path, validate_pattern_memory_doc, default_pattern_memory
)
RALPH_LOOP_DOC = StateDoc(ralph_loop_path, validate_ralph_loop_doc, default_ralph_loop)
GPU_QUEUE_DOC = StateDoc(gpu_queue_path, validate_gpu_queue_doc, default_gpu_queue)
LOOP_SUMMARY_DOC = StateDoc(loop_summary_path, validate_loop_summary_doc, default_loop_summary)
AGENT_MESSAGES_DOC = StateDoc(
    agent_messages_path, validate_agent_messages_doc, default_agent_messages
)
BASELINE_REGISTRY_DOC = StateDoc(
    baseline_registry_path, validate_baseline_registry_doc, default_baseline_registry
)
REVIEW_FORM_REGISTRY_DOC = StateDoc(
    lambda _: review_form_registry_path(),
    validate_review_form_registry_doc,
    default_review_form_registry,
)

# --- Document Wrappers ---


def load_agent_status(root: Path) -> dict:
    return AGENT_STATUS_DOC.load(root)


def find_agent(data: dict, name: str) -> dict:
    for a in data.get("agents", []):
        if a.get("name") == name:
            return a
    raise HarnessError(f"Agent not found: {name}")


def update_agent_status(
    root: Path,
    agent_name: str,
    status: str,
    *,
    task: str | None = None,
    stage: str | None = None,
    inputs: list[str] | None = None,
    outputs: list[str] | None = None,
    notes: str | None = None,
    append_note: bool = False,
) -> dict:
    status = status.strip().lower()
    if status not in AGENT_STATUSES:
        raise HarnessError(f"Invalid status: {status}")

    def mut(d):
        ts = now_iso()
        a = find_agent(d, agent_name)
        a["status"] = status
        if task is not None:
            a["current_task"] = task
        if stage is not None:
            a["stage"] = stage
        if status == "running" and a.get("status") != "running":
            a["started_at"] = ts
        a["updated_at"] = ts
        if inputs is not None:
            a["last_input_files"] = inputs
        if outputs is not None:
            a["last_output_files"] = outputs
        if notes is not None:
            n = f"{ts}: {notes}" if append_note else notes
            a["notes"] = f"{a.get('notes', '')}\n{n}" if append_note and a.get("notes") else n

    return AGENT_STATUS_DOC.mutate(root, mut)


def load_command_queue(root: Path) -> dict:
    return COMMAND_QUEUE_DOC.load(root)


def mutate_command_queue(root: Path, mutator: Callable) -> dict:
    def wrapped(d):
        mutator(d)
        sync_next_actions(root, d)

    return COMMAND_QUEUE_DOC.mutate(root, wrapped)


def load_agent_votes(root: Path) -> dict:
    return AGENT_VOTES_DOC.load(root)


def mutate_agent_votes(root: Path, mutator: Callable) -> dict:
    return AGENT_VOTES_DOC.mutate(root, mutator)


def load_pattern_memory(root: Path) -> dict:
    return PATTERN_MEMORY_DOC.load(root)


def mutate_pattern_memory(root: Path, mutator: Callable) -> dict:
    return PATTERN_MEMORY_DOC.mutate(root, mutator)


def load_ralph_loop(root: Path) -> dict:
    return RALPH_LOOP_DOC.load(root)


def mutate_ralph_loop(root: Path, mutator: Callable) -> dict:
    return RALPH_LOOP_DOC.mutate(root, mutator)


def load_gpu_queue(root: Path) -> dict:
    return GPU_QUEUE_DOC.load(root)


def mutate_gpu_queue(root: Path, mutator: Callable) -> dict:
    def wrapped(d):
        mutator(d)
        d["gpu_types"] = sorted(workspace_gpu_types())

    return GPU_QUEUE_DOC.mutate(root, wrapped)


def load_loop_summary(root: Path) -> dict:
    return LOOP_SUMMARY_DOC.load(root)


def mutate_loop_summary(root: Path, mutator: Callable) -> dict:
    return LOOP_SUMMARY_DOC.mutate(root, mutator)


def load_agent_messages(root: Path) -> dict:
    return AGENT_MESSAGES_DOC.load(root)


def mutate_agent_messages(root: Path, mutator: Callable) -> dict:
    return AGENT_MESSAGES_DOC.mutate(root, mutator)


def load_baseline_registry(root: Path) -> dict:
    return BASELINE_REGISTRY_DOC.load(root)


def mutate_baseline_registry(root: Path, mutator: Callable) -> dict:
    return BASELINE_REGISTRY_DOC.mutate(root, mutator)


def load_review_form_registry() -> dict:
    return REVIEW_FORM_REGISTRY_DOC.load(Path("."))


def mutate_review_form_registry(mutator: Callable) -> dict:
    return REVIEW_FORM_REGISTRY_DOC.mutate(Path("."), mutator)


# --- Run State (Special factory) ---


def load_run_state(root: Path, exp_id: str) -> dict:
    p = run_state_path(root, exp_id)
    d = load_json(p, fallback=default_run_state(root.name, exp_id))
    validate_run_state_doc(d)
    return d


def mutate_run_state(root: Path, exp_id: str, mutator: Callable) -> dict:
    p = run_state_path(root, exp_id)
    with locked_state_file(p):
        d = load_run_state(root, exp_id)
        mutator(d)
        validate_run_state_doc(d)
        atomic_write_json_unlocked(p, d)
        return d


# --- Restored Helper Functions ---


def latest_vote_counts(decision: dict[str, Any]) -> dict[str, int]:
    counts = {"approve": 0, "reject": 0, "abstain": 0}
    for vote in decision.get("votes", []):
        value = str(vote.get("vote") or "").strip().lower()
        if value in counts:
            counts[value] += 1
    return counts


def evaluate_vote_decision(decision: dict[str, Any]) -> str:
    status = str(decision.get("status") or "").strip().lower()
    if status == "cancelled":
        return "cancelled"
    counts = latest_vote_counts(decision)
    max_rejections = int(decision.get("max_rejections", 0) or 0)
    min_approvals = int(decision.get("min_approvals", 2) or 2)
    required_voters = [
        str(voter).strip() for voter in decision.get("required_voters", []) if str(voter).strip()
    ]
    voted_agents = {
        str(vote.get("agent") or "").strip()
        for vote in decision.get("votes", [])
        if str(vote.get("agent") or "").strip()
    }
    if counts["reject"] > max_rejections:
        return "rejected"
    if counts["approve"] >= min_approvals and all(
        voter in voted_agents for voter in required_voters
    ):
        return "approved"
    return "open"


def find_vote_decision(data: dict[str, Any], decision_id: str) -> dict[str, Any] | None:
    for decision in data.get("decisions", []):
        if decision.get("id") == decision_id:
            return decision
    return None


def find_pattern(data: dict[str, Any], pattern_id: str) -> dict[str, Any] | None:
    for pattern in data.get("patterns", []):
        if pattern.get("id") == pattern_id:
            return pattern
    return None


def find_ralph_run(data: dict[str, Any], run_id: str) -> dict[str, Any] | None:
    for run in data.get("runs", []):
        if run.get("id") == run_id:
            return run
    return None


def find_message(data: dict[str, Any], message_id: str) -> dict[str, Any] | None:
    for message in data.get("messages", []):
        if message.get("id") == message_id:
            return message
    return None


def find_baseline(data: dict[str, Any], baseline_id: str) -> dict[str, Any]:
    for baseline in data["baselines"]:
        if baseline.get("id") == baseline_id:
            return baseline
    raise HarnessError(f"Baseline not found: {baseline_id}")


def safe_repo_relative_path(value: object, field_name: str) -> Path:
    path_text = str(value or "").strip()
    if not path_text:
        raise HarnessError(f"{field_name} is required.")
    path = Path(path_text)
    if path.is_absolute() or ".." in path.parts:
        raise HarnessError(f"{field_name} must be a repo-relative path without '..'.")
    return path


# --- Other helpers ---


def owner_matches(owner: Any, name: str) -> bool:
    return name in [p.strip() for p in str(owner or "").replace(",", "/").split("/") if p.strip()]


def update_command_for_agent(
    root: Path, cid: str | None, name: str, status: str, note: str | None = None
) -> None:
    if not cid:
        return

    def mut(q):
        c = next((x for x in q["commands"] if x.get("id") == cid), None)
        if not c:
            raise HarnessError(f"Command not found: {cid}")
        if not owner_matches(c.get("owner_agent"), name):
            raise HarnessError(f"Command {cid} is owned by {c.get('owner_agent')!r}, not {name!r}")
        c["status"] = status
        c["updated_at"] = now_iso()
        if note:
            c["notes"] = note

    mutate_command_queue(root, mut)


def owned_active_commands(root: Path, name: str) -> list[dict]:
    return [
        c
        for c in load_command_queue(root)["commands"]
        if owner_matches(c.get("owner_agent"), name)
        and str(c.get("status", "")).lower() in {"open", "in progress"}
    ]


def append_run_history(data: dict, event: str, note: str = "") -> None:
    data.setdefault("history", []).append({"at": now_iso(), "event": event, "note": note})


def discover_run_states(root: Path) -> list[dict]:
    states = []
    exp_dir = root / "03_experiments"
    if not exp_dir.is_dir():
        return []
    for p in sorted(exp_dir.glob("*/run_state.json")):
        try:
            d = load_json(p)
            validate_run_state_doc(d)
            states.append(d)
        except HarnessError as e:
            states.append(
                {
                    "project": root.name,
                    "exp_id": p.parent.name,
                    "status": "blocked",
                    "current_step": str(e),
                    "history": [],
                }
            )
    return states


def command_has_approved_vote(root: Path, cmd: dict) -> bool:
    if not cmd.get("requires_vote"):
        return True
    vid = str(cmd.get("vote_id") or "").strip()
    if not vid:
        return False
    dec = find_vote_decision(load_agent_votes(root), vid)
    return bool(dec and str(dec.get("status", "")).lower() == "approved")


# Final legacy exports if needed
def write_command_queue(root, data):
    atomic_write_json(command_queue_path(root), data)
    sync_next_actions(root, data)


def write_agent_status(root, data):
    atomic_write_json(agent_status_path(root), data)


def write_agent_votes(root, data):
    atomic_write_json(agent_votes_path(root), data)


def write_pattern_memory(root, data):
    atomic_write_json(pattern_memory_path(root), data)


def write_ralph_loop(root, data):
    atomic_write_json(ralph_loop_path(root), data)


def write_run_state(root, exp_id, data):
    atomic_write_json(run_state_path(root, exp_id), data)


def write_gpu_queue(root, data):
    atomic_write_json(gpu_queue_path(root), data)


def write_loop_summary(root, data):
    atomic_write_json(loop_summary_path(root), data)


def write_agent_messages(root, data):
    atomic_write_json(agent_messages_path(root), data)


def write_baseline_registry(root, data):
    atomic_write_json(baseline_registry_path(root), data)


def write_review_form_registry(data):
    atomic_write_json(review_form_registry_path(), data)
