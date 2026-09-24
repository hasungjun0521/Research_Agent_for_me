#!/usr/bin/env python3
"""Dispatch queued research commands to agent prompts or an external runner."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

from scripts.commands.agents.agent_vote import (
    auto_vote_decision,
    ensure_vote_for_command,
    sync_vote_lifecycle,
)
from scripts.harness.runner_commands import split_runner_command
from scripts.harness.state import (
    HarnessError,
    append_agent_event,
    command_has_approved_vote,
    load_agent_messages,
    load_command_queue,
    mutate_command_queue,
    now_iso,
    project_root,
    repo_root,
    split_values,
    update_agent_status,
)
from scripts.harness.workflow_hooks import refresh_report_index
from scripts.harness.workspace_profile import (
    ProfileError,
    workspace_agent_runner_command,
    workspace_agent_runner_default_profile,
)

ACTIVE_STATUSES = {"open"}
PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}
PARALLEL_MANAGED_STATE_PATHS = {
    "state/current_state.md",
    "state/agent_memory.md",
    "state/next_actions.md",
    "state/open_questions.md",
    "state/agent_status.json",
    "state/agent_events.jsonl",
    "state/progress_hooks.jsonl",
    "state/sessions/progress_log.md",
    "state/loop_summary.json",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create prompts and optionally dispatch queued agent work.")
    sub = parser.add_subparsers(dest="command", required=True)

    next_cmd = sub.add_parser("next", help="Show the next dispatchable command.")
    next_cmd.add_argument("--project", required=True)
    next_cmd.add_argument("--json", action="store_true")
    next_cmd.add_argument("--max-agents", type=int, default=4, help="Maximum agents to include in the parallel hint.")

    prompt = sub.add_parser("prompt", help="Render an agent prompt for a command.")
    prompt.add_argument("--project", required=True)
    prompt.add_argument("--id", required=True, dest="command_id")
    prompt.add_argument("--write", action="store_true", help="Write prompt under state/orchestrator_prompts/.")
    prompt.add_argument("--prompt-style", choices=("lean", "full"), default="lean",
                        help="lean (default) lists shared contracts as read-on-demand pointers; full inlines them.")

    dispatch = sub.add_parser("dispatch", help="Mark the command in progress and optionally run a configured runner.")
    dispatch.add_argument("--project", required=True)
    dispatch.add_argument("--id", dest="command_id")
    dispatch.add_argument("--execute", action="store_true", help="Run --runner-command after writing the prompt.")
    dispatch.add_argument(
        "--runner-command",
        help="Command template. Supports {prompt_file}, {project}, {command_id}, and {agent}.",
    )
    dispatch.add_argument(
        "--runner-profile",
        default="",
        help="Runner profile from config/workspace_profile.local.json. Uses agent_runners.default_profile when omitted.",
    )
    dispatch.add_argument("--prompt-dir", default="state/orchestrator_prompts")
    dispatch.add_argument("--prompt-style", choices=("lean", "full"), default="lean",
                          help="lean (default) lists shared contracts as read-on-demand pointers; full inlines them.")
    dispatch.add_argument("--auto-vote", action="store_true", help="Run the linked vote before dispatch when approval is missing.")
    dispatch.add_argument("--vote-runner-command", help="Auto-vote runner command. Supports {prompt_file}, {project}, {vote_id}, and {agent}.")
    dispatch.add_argument("--vote-voter", action="append", dest="vote_voters")
    dispatch.add_argument("--vote-risk-level", choices=["low", "medium", "high", "critical"], default="high")
    dispatch.add_argument("--vote-min-approvals", type=int, default=2)
    dispatch.add_argument("--vote-prompt-dir", default="state/vote_prompts")

    parallel = sub.add_parser("parallel", help="Plan or dispatch independent commands to multiple agents.")
    parallel.add_argument("--project", required=True)
    parallel.add_argument("--id", action="append", dest="command_ids", help="Specific command id to include. Repeat for a fixed batch.")
    parallel.add_argument("--max-agents", type=int, default=4)
    parallel.add_argument("--group", default="", help="Only include commands with this parallel_group value.")
    parallel.add_argument("--allow-same-agent", action="store_true", help="Allow multiple commands for the same owner agent.")
    parallel.add_argument("--write", action="store_true", help="Write prompts and mark selected commands in progress.")
    parallel.add_argument("--execute", action="store_true", help="Run --runner-command for selected prompts concurrently.")
    parallel.add_argument(
        "--runner-command",
        help="Command template. Supports {prompt_file}, {project}, {command_id}, and {agent}.",
    )
    parallel.add_argument(
        "--runner-profile",
        default="",
        help="Runner profile from config/workspace_profile.local.json. Uses agent_runners.default_profile when omitted.",
    )
    parallel.add_argument("--prompt-dir", default="state/orchestrator_prompts")
    parallel.add_argument("--prompt-style", choices=("lean", "full"), default="lean",
                          help="lean (default) lists shared contracts as read-on-demand pointers; full inlines them.")
    parallel.add_argument("--json", action="store_true")

    run_prepared = sub.add_parser("run-prepared", help="Run already-written in-progress parallel prompts with an external runner.")
    run_prepared.add_argument("--project", required=True)
    run_prepared.add_argument("--id", action="append", dest="command_ids", help="Specific prepared command id to run. Repeat for a fixed batch.")
    run_prepared.add_argument("--group", default="", help="Only include prepared commands with this parallel_group value.")
    run_prepared.add_argument("--all-prepared", action="store_true", help="Allow selecting prepared prompts across all groups.")
    run_prepared.add_argument("--max-agents", type=int, default=4)
    run_prepared.add_argument(
        "--runner-command",
        help="Command template. Supports {prompt_file}, {project}, {command_id}, and {agent}.",
    )
    run_prepared.add_argument(
        "--runner-profile",
        default="",
        help="Runner profile from config/workspace_profile.local.json. Uses agent_runners.default_profile when omitted.",
    )
    run_prepared.add_argument("--dry-run", action="store_true", help="Show prepared prompts without running the external runner.")
    run_prepared.add_argument("--json", action="store_true")

    status_parallel = sub.add_parser("status-parallel", help="Show open and prepared parallel agent work without changing state.")
    status_parallel.add_argument("--project", required=True)
    status_parallel.add_argument("--group", default="", help="Only show commands with this parallel_group value.")
    status_parallel.add_argument("--max-items", type=int, default=20)
    status_parallel.add_argument("--json", action="store_true")

    finish_parallel = sub.add_parser("finish-parallel", help="Finish a scoped set of prepared parallel commands.")
    finish_parallel.add_argument("--project", required=True)
    finish_parallel.add_argument("--id", action="append", dest="command_ids", help="Specific prepared command id to finish. Repeat for a fixed batch.")
    finish_parallel.add_argument("--group", default="", help="Only finish prepared commands with this parallel_group value.")
    finish_parallel.add_argument("--all-prepared", action="store_true", help="Allow finishing prepared commands across all groups.")
    finish_parallel.add_argument("--status", choices=["done", "blocked", "deferred"], required=True)
    finish_parallel.add_argument("--note", default="")
    finish_parallel.add_argument("--output", action="append", dest="outputs")
    finish_parallel.add_argument(
        "--result-file",
        action="append",
        dest="result_files",
        help="Per-command evidence in the form <command_id>=<path>. Repeat for multiple commands.",
    )
    finish_parallel.add_argument("--dry-run", action="store_true", help="Show commands that would be finished without changing state.")
    finish_parallel.add_argument("--json", action="store_true")

    finish = sub.add_parser("finish", help="Finish a dispatched command and update agent status.")
    finish.add_argument("--project", required=True)
    finish.add_argument("--id", required=True, dest="command_id")
    finish.add_argument("--status", choices=["done", "blocked", "deferred"], required=True)
    finish.add_argument("--note", default="")
    finish.add_argument("--output", action="append", dest="outputs")

    return parser.parse_args()


def command_owner(command: dict[str, Any]) -> str:
    owner = str(command.get("owner_agent") or "").replace(",", "/").split("/")[0].strip()
    return owner or "director"


def select_next_command(queue: dict[str, Any]) -> dict[str, Any] | None:
    candidates = [
        command for command in queue.get("commands", [])
        if not serial_readiness_reasons(queue, command)
    ]
    if not candidates:
        return None
    return sorted(
        candidates,
        key=lambda item: (
            PRIORITY_RANK.get(str(item.get("priority") or "medium").lower(), 1),
            str(item.get("created_at") or ""),
            str(item.get("id") or ""),
        ),
    )[0]


def command_values(command: dict[str, Any], key: str) -> list[str]:
    value = command.get(key)
    if isinstance(value, str):
        return split_values([value])
    if isinstance(value, list):
        return split_values([str(item) for item in value])
    return []


def command_dependencies(command: dict[str, Any]) -> list[str]:
    return command_values(command, "depends_on")


def command_by_id(queue: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(command.get("id") or "").strip(): command
        for command in queue.get("commands", [])
        if isinstance(command, dict) and str(command.get("id") or "").strip()
    }


def unfinished_command_dependencies(
    command: dict[str, Any],
    commands_by_id: dict[str, dict[str, Any]],
) -> list[str]:
    return [
        dependency_id
        for dependency_id in command_dependencies(command)
        if str(commands_by_id.get(dependency_id, {}).get("status") or "").lower() != "done"
    ]


def serial_readiness_reasons(queue: dict[str, Any], command: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if str(command.get("status") or "").lower() not in ACTIVE_STATUSES:
        reasons.append(f"status_not_open:{command.get('status', '')}")
    unfinished = unfinished_command_dependencies(command, command_by_id(queue))
    if unfinished:
        reasons.append(f"unfinished_dependencies:{','.join(unfinished)}")
    return reasons


def ensure_serial_readiness(queue: dict[str, Any], command: dict[str, Any]) -> None:
    reasons = serial_readiness_reasons(queue, command)
    if reasons:
        raise HarnessError(
            f"Command {command.get('id')} is not ready for dispatch: {', '.join(reasons)}"
        )


def command_path_set(command: dict[str, Any], key: str) -> set[str]:
    return {
        str(value).strip()
        for value in command_values(command, key)
        if str(value).strip()
    }


def command_substantive_path_set(command: dict[str, Any], key: str) -> set[str]:
    return {
        value for value in command_path_set(command, key)
        if value not in PARALLEL_MANAGED_STATE_PATHS
    }


def has_path_conflict(left: dict[str, Any], right: dict[str, Any]) -> bool:
    def overlaps(first: set[str], second: set[str]) -> bool:
        for first_value in first:
            first_path = PurePosixPath(first_value.replace("\\", "/"))
            for second_value in second:
                second_path = PurePosixPath(second_value.replace("\\", "/"))
                if (
                    first_path == second_path
                    or first_path in second_path.parents
                    or second_path in first_path.parents
                ):
                    return True
        return False

    left_outputs = command_substantive_path_set(left, "expected_outputs")
    right_outputs = command_substantive_path_set(right, "expected_outputs")
    if overlaps(left_outputs, right_outputs):
        return True
    left_inputs = command_substantive_path_set(left, "required_inputs")
    right_inputs = command_substantive_path_set(right, "required_inputs")
    return overlaps(left_outputs, right_inputs) or overlaps(right_outputs, left_inputs)


def parallel_readiness_reasons(root: Path, queue: dict[str, Any], command: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if str(command.get("status") or "").lower() != "open":
        reasons.append(f"status_not_open:{command.get('status', '')}")
    if not command_substantive_path_set(command, "expected_outputs"):
        reasons.append("missing_expected_outputs")
    if command.get("requires_vote") and not command_has_approved_vote(root, command):
        reasons.append("vote_not_approved")
    unfinished = unfinished_command_dependencies(command, command_by_id(queue))
    if unfinished:
        reasons.append(f"unfinished_dependencies:{','.join(unfinished)}")
    return reasons


def command_is_parallel_ready(root: Path, queue: dict[str, Any], command: dict[str, Any]) -> bool:
    return not parallel_readiness_reasons(root, queue, command)


def select_parallel_commands(
    root: Path,
    queue: dict[str, Any],
    *,
    command_ids: list[str] | None = None,
    max_agents: int = 4,
    group: str = "",
    allow_same_agent: bool = False,
) -> list[dict[str, Any]]:
    if max_agents < 1:
        raise HarnessError("--max-agents must be at least 1.")
    commands = queue.get("commands", [])
    if command_ids:
        requested = []
        for command_id in command_ids:
            requested.append(find_command(root, command_id))
        candidates = requested
        if len(candidates) > max_agents:
            raise HarnessError(
                f"Explicit parallel command count {len(candidates)} exceeds --max-agents {max_agents}."
            )
        for command in candidates:
            if group and str(command.get("parallel_group") or "") != group:
                raise HarnessError(
                    f"Command {command.get('id')} is not in parallel group: {group}"
                )
            reasons = parallel_readiness_reasons(root, queue, command)
            if reasons:
                raise HarnessError(
                    f"Command {command.get('id')} is not safe for parallel dispatch: {', '.join(reasons)}"
                )
    else:
        candidates = [
            command for command in commands
            if command_is_parallel_ready(root, queue, command)
        ]
    if group:
        candidates = [
            command for command in candidates
            if str(command.get("parallel_group") or "") == group
        ]
    candidates = sorted(
        candidates,
        key=lambda item: (
            PRIORITY_RANK.get(str(item.get("priority") or "medium").lower(), 1),
            str(item.get("created_at") or ""),
            str(item.get("id") or ""),
        ),
    )
    selected: list[dict[str, Any]] = []
    owners: set[str] = set()
    for command in candidates:
        if not command_is_parallel_ready(root, queue, command):
            continue
        owner = command_owner(command)
        if not allow_same_agent and owner in owners:
            if command_ids:
                raise HarnessError(
                    f"Command {command.get('id')} is not safe for parallel dispatch: owner_already_selected:{owner}"
                )
            continue
        if any(has_path_conflict(command, existing) for existing in selected):
            if command_ids:
                raise HarnessError(
                    f"Command {command.get('id')} is not safe for parallel dispatch: path_conflict"
                )
            continue
        selected.append(command)
        owners.add(owner)
        if len(selected) >= max_agents:
            break
    return selected


def parallel_command_diagnostics(
    root: Path,
    queue: dict[str, Any],
    *,
    group: str = "",
    max_agents: int = 4,
    allow_same_agent: bool = False,
    limit: int = 20,
) -> list[dict[str, Any]]:
    candidates = [
        command for command in queue.get("commands", [])
        if isinstance(command, dict)
        and str(command.get("status") or "").lower() == "open"
        and (not group or str(command.get("parallel_group") or "") == group)
    ]
    candidates = sorted(
        candidates,
        key=lambda item: (
            PRIORITY_RANK.get(str(item.get("priority") or "medium").lower(), 1),
            str(item.get("created_at") or ""),
            str(item.get("id") or ""),
        ),
    )
    selected: list[dict[str, Any]] = []
    owners: set[str] = set()
    rows: list[dict[str, Any]] = []
    for command in candidates:
        reasons = parallel_readiness_reasons(root, queue, command)
        if not reasons:
            owner = command_owner(command)
            if not allow_same_agent and owner in owners:
                reasons.append(f"owner_already_selected:{owner}")
            elif any(has_path_conflict(command, existing) for existing in selected):
                reasons.append("path_conflict")
            elif len(selected) >= max_agents:
                reasons.append("max_agents_limit")
            else:
                selected.append(command)
                owners.add(owner)
        rows.append({
            "id": command.get("id"),
            "owner_agent": command_owner(command),
            "priority": command.get("priority"),
            "action": command.get("action"),
            "parallel_group": command.get("parallel_group", ""),
            "selected": not reasons,
            "reasons": reasons,
            "depends_on": command_dependencies(command),
            "expected_outputs": command_values(command, "expected_outputs"),
        })
        if len(rows) >= limit:
            break
    return rows


def find_command(root: Path, command_id: str) -> dict[str, Any]:
    queue = load_command_queue(root)
    for command in queue.get("commands", []):
        if command.get("id") == command_id:
            return command
    raise HarnessError(f"Command not found: {command_id}")


def read_prompt_file(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace").strip()


def open_messages_for_agent(root: Path, agent_name: str) -> list[dict[str, Any]]:
    messages = load_agent_messages(root)
    return [
        message for message in messages.get("messages", [])
        if str(message.get("to_agent") or "") == agent_name
        and str(message.get("status") or "").lower() not in {"resolved", "cancelled"}
    ]


# Shared contract files referenced by every dispatched prompt. In the default
# "lean" style they are listed as read-on-demand pointers (title, path, one-line
# purpose) instead of being inlined, which keeps each worker prompt thousands of
# tokens smaller; "full" restores complete inlining for offline/file-less runners.
SHARED_CONTRACT_POINTERS: list[tuple[str, str, str]] = [
    ("prompts/shared/research_context.md", "Shared Research Context Template",
     "project folder map and working-state conventions"),
    ("prompts/shared/output_contracts.md", "Shared Output Contracts",
     "required output files and evidence rules per task type"),
    ("prompts/shared/skill_usage.md", "Skill Usage",
     "which runbook/skill to load for the current task"),
    ("prompts/shared/filesystem_safety_rules.md", "Filesystem Safety Rules",
     "what may be written or deleted, and where"),
    ("prompts/shared/research_routing_matrix.md", "Research Routing Matrix",
     "which role owns which kind of work"),
    ("prompts/shared/research_handoff_graph.md", "Research Handoff Graph",
     "what each role hands to the next role"),
    ("prompts/shared/leader_dispatch_protocol.md", "Research Leader Dispatch Protocol",
     "leader/worker dispatch and worker-result contract"),
    ("prompts/shared/risk_confidence_matrix.md", "Research Risk And Confidence Matrix",
     "risk/confidence labeling rules for claims and decisions"),
    ("prompts/shared/research_brain_protocol.md", "Research Brain Protocol",
     "durable memory and lesson capture rules"),
]
# Safety-critical enough to stay inlined even in lean prompts.
ALWAYS_INLINED_CONTRACTS = ("prompts/shared/filesystem_safety_rules.md",)


def render_shared_contracts(style: str) -> str:
    repo = repo_root()
    if style == "full":
        return "\n\n".join(
            text for text in (read_prompt_file(repo / rel) for rel, _, _ in SHARED_CONTRACT_POINTERS) if text
        )
    lines = [
        "Read the shared contracts below from the repository as needed for this",
        "command before acting; they are intentionally not inlined to keep this",
        "prompt small. Do not paste their contents into outputs.",
        "",
    ]
    for rel, title, purpose in SHARED_CONTRACT_POINTERS:
        if rel in ALWAYS_INLINED_CONTRACTS:
            continue
        lines.append(f"- `{rel}` — {title}: {purpose}.")
    inlined = "\n\n".join(
        text for text in (read_prompt_file(repo / rel) for rel in ALWAYS_INLINED_CONTRACTS) if text
    )
    if inlined:
        lines += ["", inlined]
    return "\n".join(lines)


def render_prompt(root: Path, command: dict[str, Any], style: str = "lean") -> str:
    agent = command_owner(command)
    prompts = repo_root() / "prompts"
    agent_prompt = read_prompt_file(prompts / "agents" / f"{agent}.md")
    shared = render_shared_contracts(style)
    messages = open_messages_for_agent(root, agent)
    payload = {
        "project": root.name,
        "command": command,
        "open_messages_for_agent": messages,
        "required_first_reads": [
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
        ],
    }
    return "\n\n".join([
        f"# Dispatch Prompt: {command.get('id', '')}",
        "You are being dispatched by scripts.commands.agents.agent_orchestrator.",
        "Follow the role prompt, shared contracts, and the command payload exactly.",
        "Read the required_first_reads before choosing implementation details.",
        "Use harness CLIs for structured state updates and persist progress during the pass.",
        "Do not mark the task done until verification has run or the blocker is recorded.",
        "## Agent Role Prompt",
        agent_prompt or f"Act as {agent}.",
        "## Shared Harness Contracts",
        shared,
        "## Dispatch Payload",
        "```json\n" + json.dumps(payload, indent=2, ensure_ascii=False) + "\n```",
    ]) + "\n"


def prompt_path(root: Path, prompt_dir: str, command_id: str) -> Path:
    rel = Path(prompt_dir)
    if rel.is_absolute() or ".." in rel.parts:
        raise HarnessError("--prompt-dir must be project-relative.")
    return root / rel / f"{command_id}.md"


def write_prompt(root: Path, command: dict[str, Any], prompt_dir: str, style: str = "lean") -> Path:
    path = prompt_path(root, prompt_dir, str(command["id"]))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_prompt(root, command, style), encoding="utf-8")
    return path


def ensure_vote_gate(root: Path, command: dict[str, Any]) -> None:
    if command.get("requires_vote") and not command_has_approved_vote(root, command):
        vote_id = str(command.get("vote_id") or "").strip() or "<missing>"
        raise HarnessError(f"Command {command.get('id')} requires approved vote before dispatch: {vote_id}")


def mark_dispatched(root: Path, command: dict[str, Any], prompt_file: Path) -> None:
    ensure_vote_gate(root, command)

    timestamp = now_iso()
    command_id = str(command["id"])
    agent = command_owner(command)
    prompt_rel = prompt_file.relative_to(root).as_posix()

    def mutate(queue: dict[str, Any]) -> None:
        for item in queue.get("commands", []):
            if item.get("id") != command_id:
                continue
            ensure_serial_readiness(queue, item)
            item["status"] = "in progress"
            item["updated_at"] = timestamp
            item["orchestrator_prompt"] = prompt_rel
            item["notes"] = f"Dispatched to {agent} with prompt {prompt_rel}."
            return
        raise HarnessError(f"Command not found: {command_id}")

    mutate_command_queue(root, mutate)
    update_agent_status(
        root,
        agent,
        "running",
        task=str(command.get("display_summary") or command.get("action") or command_id),
        stage="orchestrated command",
        inputs=[prompt_rel, *[str(value) for value in command.get("required_inputs", [])]],
        outputs=[str(value) for value in command.get("expected_outputs", [])],
        notes=f"Dispatched command {command_id}.",
    )
    append_agent_event(
        root,
        "dispatch",
        agent,
        status="running",
        command_id=command_id,
        task=str(command.get("display_summary") or command.get("action") or command_id),
        stage="orchestrated command",
        inputs=[prompt_rel, *[str(value) for value in command.get("required_inputs", [])]],
        outputs=[str(value) for value in command.get("expected_outputs", [])],
        notes=f"Dispatched command {command_id}.",
    )
    refresh_report_index(root)


RunnerTemplate = str | list[str]


def resolve_runner_template(command_template: str | None, runner_profile: str | None) -> tuple[RunnerTemplate, str]:
    if command_template and runner_profile:
        raise HarnessError("Use either --runner-command or --runner-profile, not both.")
    if command_template:
        return command_template, "inline"

    profile_name = str(runner_profile or "").strip()
    if profile_name == "auto":
        from scripts.harness.agent_limits import select_best_runner
        profile_name = select_best_runner()
        print(f"auto-selected runner: {profile_name}")

    if not profile_name:
        profile_name = workspace_agent_runner_default_profile()

    if not profile_name:
        raise HarnessError("--runner-command or a configured --runner-profile is required with --execute.")
    try:
        return workspace_agent_runner_command(profile_name), profile_name
    except ProfileError as exc:
        raise HarnessError(str(exc)) from exc


def command_template_to_argv(template: RunnerTemplate, *, prompt_file: Path, project: str, command_id: str, agent: str) -> list[str]:
    if not template:
        raise HarnessError("--runner-command or --runner-profile is required with --execute.")
    replacements = {
        "prompt_file": str(prompt_file),
        "project": project,
        "command_id": command_id,
        "agent": agent,
    }
    if isinstance(template, list):
        return [part.format(**replacements) for part in template]
    rendered = template.format(**replacements)
    return split_runner_command(rendered)


def execute_runner(template: RunnerTemplate, *, root: Path, prompt_file: Path, command: dict[str, Any]) -> int:
    argv = command_template_to_argv(
        template,
        prompt_file=prompt_file,
        project=root.name,
        command_id=str(command["id"]),
        agent=command_owner(command),
    )
    if not argv:
        raise HarnessError("Runner command is empty.")
    result = subprocess.run(argv, cwd=repo_root(), text=True)
    return result.returncode


def execute_parallel_runners(template: RunnerTemplate, *, root: Path, prompts: list[tuple[dict[str, Any], Path]]) -> int:
    if not template:
        raise HarnessError("--runner-command or --runner-profile is required with --execute.")
    processes: list[tuple[dict[str, Any], subprocess.Popen[str]]] = []
    for command, prompt_file in prompts:
        argv = command_template_to_argv(
            template,
            prompt_file=prompt_file,
            project=root.name,
            command_id=str(command["id"]),
            agent=command_owner(command),
        )
        try:
            processes.append((command, subprocess.Popen(argv, cwd=repo_root(), text=True)))
        except OSError as exc:
            raise HarnessError(f"Runner failed to start for {command.get('id')}: {exc}") from exc
    exit_code = 0
    for command, process in processes:
        returncode = process.wait()
        if returncode != 0:
            print(f"runner failed: {command.get('id')} -> {returncode}", file=sys.stderr)
            exit_code = returncode if exit_code == 0 else exit_code
    return exit_code


def record_parallel_dispatch_plan(root: Path, commands: list[dict[str, Any]], prompt_paths: list[Path]) -> None:
    timestamp = now_iso()
    batch_id = timestamp.replace(":", "").replace("-", "").replace("+", "_").replace(".", "")
    manifest_path = root / "state" / "orchestrator_prompts" / "parallel_batches" / f"{batch_id}.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "timestamp": timestamp,
        "commands": [
            {
                "id": command.get("id"),
                "owner_agent": command_owner(command),
                "parallel_group": command.get("parallel_group", ""),
                "priority": command.get("priority", ""),
                "action": command.get("action", ""),
                "expected_outputs": command_values(command, "expected_outputs"),
            }
            for command in commands
        ],
        "prompts": [path.relative_to(root).as_posix() for path in prompt_paths],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest_rel = manifest_path.relative_to(root).as_posix()
    append_agent_event(
        root,
        "parallel_dispatch_plan",
        "director",
        status="running" if prompt_paths else "waiting",
        task=f"Planned parallel dispatch for {len(commands)} command(s).",
        stage="agent_orchestrator_parallel",
        outputs=[manifest_rel, *[path.relative_to(root).as_posix() for path in prompt_paths]] or ["state/command_queue.json"],
        notes=", ".join(f"{command.get('id')}->{command_owner(command)}" for command in commands),
    )
    refresh_report_index(root)


def parallel_payload(commands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "id": command.get("id"),
            "owner_agent": command_owner(command),
            "priority": command.get("priority"),
            "action": command.get("action"),
            "parallel_group": command.get("parallel_group", ""),
            "depends_on": command_dependencies(command),
            "expected_outputs": command_values(command, "expected_outputs"),
        }
        for command in commands
    ]


def prepared_command_pairs(
    root: Path,
    queue: dict[str, Any],
    *,
    command_ids: list[str] | None = None,
    group: str = "",
    max_agents: int = 4,
    fail_on_unfinished_dependencies: bool = False,
) -> list[tuple[dict[str, Any], Path]]:
    if max_agents < 1:
        raise HarnessError("--max-agents must be at least 1.")
    if command_ids:
        commands = [find_command(root, command_id) for command_id in command_ids]
    else:
        commands = [
            command for command in queue.get("commands", [])
            if str(command.get("status") or "").lower() == "in progress"
            and str(command.get("orchestrator_prompt") or "").strip()
        ]
    commands_by_id = command_by_id(queue)
    pairs: list[tuple[dict[str, Any], Path]] = []
    for command in commands:
        command_id = str(command.get("id") or "")
        if str(command.get("status") or "").lower() != "in progress":
            if command_ids:
                raise HarnessError(f"Prepared command is not in progress: {command_id}")
            continue
        if group and str(command.get("parallel_group") or "") != group:
            if command_ids:
                raise HarnessError(f"Prepared command {command_id} is not in parallel group: {group}")
            continue
        prompt_rel = str(command.get("orchestrator_prompt") or "").strip()
        if not prompt_rel:
            if command_ids:
                raise HarnessError(f"Prepared command has no orchestrator_prompt: {command_id}")
            continue
        prompt_file = root / prompt_rel
        if not prompt_file.is_file():
            raise HarnessError(f"Prepared prompt is missing for {command.get('id')}: {prompt_rel}")
        unfinished_dependencies = unfinished_command_dependencies(command, commands_by_id)
        if unfinished_dependencies:
            if fail_on_unfinished_dependencies or command_ids or group:
                raise HarnessError(
                    f"Prepared command dependencies are not done for {command_id}: {', '.join(unfinished_dependencies)}"
                )
            continue
        pairs.append((command, prompt_file))
        if len(pairs) >= max_agents:
            break
    return pairs


def prepared_commands_for_scope(
    root: Path,
    queue: dict[str, Any],
    *,
    command_ids: list[str] | None = None,
    group: str = "",
    all_prepared: bool = False,
) -> list[dict[str, Any]]:
    if not command_ids and not group and not all_prepared:
        raise HarnessError("prepared command selection requires --group, --id, or --all-prepared.")
    if command_ids:
        commands = [find_command(root, command_id) for command_id in command_ids]
    else:
        commands = [
            command for command in queue.get("commands", [])
            if str(command.get("status") or "").lower() == "in progress"
            and str(command.get("orchestrator_prompt") or "").strip()
        ]
    selected: list[dict[str, Any]] = []
    for command in commands:
        command_id = str(command.get("id") or "")
        if str(command.get("status") or "").lower() != "in progress":
            if command_ids:
                raise HarnessError(f"Prepared command is not in progress: {command_id}")
            continue
        if not str(command.get("orchestrator_prompt") or "").strip():
            if command_ids:
                raise HarnessError(f"Prepared command has no orchestrator_prompt: {command_id}")
            continue
        if group and str(command.get("parallel_group") or "") != group:
            if command_ids:
                raise HarnessError(f"Prepared command {command_id} is not in parallel group: {group}")
            continue
        selected.append(command)
    return selected


def prepared_parallel_commands(queue: dict[str, Any], *, group: str = "", limit: int = 20) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []
    for command in queue.get("commands", []):
        if not isinstance(command, dict):
            continue
        if str(command.get("status") or "").lower() != "in progress":
            continue
        if not str(command.get("orchestrator_prompt") or "").strip():
            continue
        if group and str(command.get("parallel_group") or "") != group:
            continue
        commands.append(command)
        if len(commands) >= limit:
            break
    return commands


def prepared_parallel_payload(commands: list[dict[str, Any]], queue: dict[str, Any]) -> list[dict[str, Any]]:
    commands_by_id = command_by_id(queue)
    payload: list[dict[str, Any]] = []
    for command in commands:
        unfinished_dependencies = unfinished_command_dependencies(command, commands_by_id)
        payload.append({
            "id": command.get("id"),
            "owner_agent": command_owner(command),
            "priority": command.get("priority"),
            "action": command.get("action"),
            "parallel_group": command.get("parallel_group", ""),
            "prompt": command.get("orchestrator_prompt", ""),
            "status": command.get("status", ""),
            "depends_on": command_dependencies(command),
            "unfinished_dependencies": unfinished_dependencies,
            "dependency_ready": not unfinished_dependencies,
            "expected_outputs": command_values(command, "expected_outputs"),
        })
    return payload


def record_prepared_parallel_run(root: Path, prompt_pairs: list[tuple[dict[str, Any], Path]]) -> None:
    append_agent_event(
        root,
        "parallel_prepared_run",
        "director",
        status="running",
        task=f"Started external runners for {len(prompt_pairs)} prepared parallel prompt(s).",
        stage="agent_orchestrator_run_prepared",
        outputs=[path.relative_to(root).as_posix() for _, path in prompt_pairs],
        notes=", ".join(f"{command.get('id')}->{command_owner(command)}" for command, _ in prompt_pairs),
    )
    refresh_report_index(root)


def record_parallel_runner_result(
    root: Path,
    *,
    event: str,
    prompt_pairs: list[tuple[dict[str, Any], Path]],
    exit_code: int,
    runner_profile: str = "",
) -> None:
    runner_note = f"runner_profile={runner_profile}; " if runner_profile else ""
    append_agent_event(
        root,
        event,
        "director",
        status="done" if exit_code == 0 else "blocked",
        task=f"Parallel runner finished for {len(prompt_pairs)} prompt(s) with exit code {exit_code}.",
        stage="agent_orchestrator_parallel_runner",
        outputs=[path.relative_to(root).as_posix() for _, path in prompt_pairs],
        notes=runner_note + ", ".join(f"{command.get('id')}->{command_owner(command)}" for command, _ in prompt_pairs),
    )
    refresh_report_index(root)


def record_parallel_finish(root: Path, commands: list[dict[str, Any]], status: str, note: str) -> None:
    append_agent_event(
        root,
        "parallel_finish",
        "director",
        status="done" if status == "done" else "blocked" if status == "blocked" else "waiting",
        task=f"Marked {len(commands)} prepared parallel command(s) {status}.",
        stage="agent_orchestrator_finish_parallel",
        outputs=["state/command_queue.json", "state/agent_status.json"],
        notes=note or ", ".join(f"{command.get('id')}->{command_owner(command)}" for command in commands),
    )
    refresh_report_index(root)


def parse_command_result_files(values: list[str] | None) -> dict[str, list[str]]:
    results: dict[str, list[str]] = {}
    for value in values or []:
        if "=" not in str(value):
            raise HarnessError("--result-file must use <command_id>=<path>.")
        command_id, path = str(value).split("=", 1)
        command_id = command_id.strip()
        path = path.strip()
        if not command_id or not path:
            raise HarnessError("--result-file must include both command id and path.")
        results.setdefault(command_id, []).append(path)
    return results


def merged_output_paths(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for value in group:
            normalized = str(value or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            merged.append(normalized)
    return merged


def execute_and_record_parallel_result(
    root: Path,
    *,
    event: str,
    prompt_pairs: list[tuple[dict[str, Any], Path]],
    runner_template: RunnerTemplate,
    runner_profile: str = "",
) -> int:
    try:
        exit_code = execute_parallel_runners(runner_template, root=root, prompts=prompt_pairs)
    except HarnessError:
        record_parallel_runner_result(
            root,
            event=event,
            prompt_pairs=prompt_pairs,
            exit_code=1,
            runner_profile=runner_profile,
        )
        raise
    record_parallel_runner_result(
        root,
        event=event,
        prompt_pairs=prompt_pairs,
        exit_code=exit_code,
        runner_profile=runner_profile,
    )
    return exit_code


def finish_command(root: Path, command_id: str, status: str, note: str, outputs: list[str]) -> None:
    command = find_command(root, command_id)
    agent = command_owner(command)
    timestamp = now_iso()

    def mutate(queue: dict[str, Any]) -> None:
        for item in queue.get("commands", []):
            if item.get("id") != command_id:
                continue
            item["status"] = status
            item["updated_at"] = timestamp
            if note:
                item["notes"] = note
            if outputs:
                item["expected_outputs"] = outputs
            return
        raise HarnessError(f"Command not found: {command_id}")

    mutate_command_queue(root, mutate)
    agent_status = "done" if status == "done" else "blocked" if status == "blocked" else "waiting"
    update_agent_status(
        root,
        agent,
        agent_status,
        task=str(command.get("display_summary") or command.get("action") or command_id),
        stage="orchestrated command",
        outputs=outputs or [str(value) for value in command.get("expected_outputs", [])],
        notes=note or f"Command {command_id} marked {status}.",
    )
    append_agent_event(
        root,
        "finish",
        agent,
        status=agent_status,
        command_id=command_id,
        task=str(command.get("display_summary") or command.get("action") or command_id),
        stage="orchestrated command",
        outputs=outputs or [str(value) for value in command.get("expected_outputs", [])],
        notes=note or f"Command {command_id} marked {status}.",
    )
    refresh_report_index(root)


def main() -> int:
    args = parse_args()
    try:
        root = project_root(args.project)
        if args.command == "next":
            queue = load_command_queue(root)
            command = select_next_command(queue)
            parallel_commands = select_parallel_commands(root, queue, max_agents=args.max_agents)
            open_diagnostics = parallel_command_diagnostics(root, queue, max_agents=args.max_agents)
            if args.json:
                print(json.dumps({
                    "project": args.project,
                    "command": command,
                    "parallel_commands": parallel_payload(parallel_commands) if len(parallel_commands) >= 2 else [],
                    "open_parallel_diagnostics": open_diagnostics,
                }, indent=2, ensure_ascii=False))
            elif command:
                print(f"{command['id']}\t{command.get('priority', '')}\t{command_owner(command)}\t{command.get('action', '')}")
                if len(parallel_commands) >= 2:
                    print("")
                    print("Parallel batch available; prefer this before serial dispatch when suitable:")
                    print(f"python -m scripts.commands.agents.agent_orchestrator parallel --project {args.project} --max-agents {len(parallel_commands)}")
                    for candidate in parallel_commands:
                        print(f"{candidate['id']}\t{candidate.get('priority', '')}\t{command_owner(candidate)}\t{candidate.get('action', '')}")
            else:
                print("No dispatchable commands.")
            return 0

        if args.command == "prompt":
            command = find_command(root, args.command_id)
            if args.write:
                path = write_prompt(root, command, "state/orchestrator_prompts", args.prompt_style)
                print(path.relative_to(root).as_posix())
            else:
                print(render_prompt(root, command, args.prompt_style).rstrip())
            return 0

        if args.command == "dispatch":
            dispatch_runner_template: RunnerTemplate = ""
            dispatch_runner_profile = ""
            if args.execute:
                dispatch_runner_template, dispatch_runner_profile = resolve_runner_template(
                    args.runner_command,
                    args.runner_profile,
                )
            command = find_command(root, args.command_id) if args.command_id else select_next_command(load_command_queue(root))
            if not command:
                print("No dispatchable commands.")
                return 0
            ensure_serial_readiness(load_command_queue(root), command)
            if args.auto_vote and command.get("requires_vote") and not command_has_approved_vote(root, command):
                vote_id = ensure_vote_for_command(
                    root,
                    str(command["id"]),
                    voters=split_values(args.vote_voters),
                    risk_level=args.vote_risk_level,
                    min_approvals=args.vote_min_approvals,
                )
                decision = auto_vote_decision(
                    root,
                    vote_id,
                    voters=split_values(args.vote_voters),
                    prompt_dir=args.vote_prompt_dir,
                    execute=bool(args.vote_runner_command),
                    runner_command=args.vote_runner_command,
                )
                sync_vote_lifecycle(
                    root,
                    event_type="agent_vote_auto",
                    agent="director",
                    decision_id=vote_id,
                    status="waiting",
                    task=f"Ran automatic voting for {vote_id}.",
                    notes=f"Automatic vote status is {decision.get('status')}; invoked by agent_orchestrator dispatch.",
                    outputs=["state/agent_votes.json", f"{args.vote_prompt_dir}/{vote_id}/"],
                )
                print(f"auto vote: {decision.get('id')} -> {decision.get('status')}")
                command = find_command(root, str(command["id"]))
            ensure_vote_gate(root, command)
            path = write_prompt(root, command, args.prompt_dir, args.prompt_style)
            mark_dispatched(root, command, path)
            print(f"dispatched: {command['id']} -> {path.relative_to(root).as_posix()}")
            if args.execute:
                return execute_runner(dispatch_runner_template, root=root, prompt_file=path, command=command)
            return 0

        if args.command == "parallel":
            parallel_runner_template: RunnerTemplate = ""
            parallel_runner_profile = ""
            if args.execute:
                parallel_runner_template, parallel_runner_profile = resolve_runner_template(
                    args.runner_command,
                    args.runner_profile,
                )
            queue = load_command_queue(root)
            command_ids = split_values(args.command_ids)
            commands = select_parallel_commands(
                root,
                queue,
                command_ids=command_ids,
                max_agents=args.max_agents,
                group=args.group,
                allow_same_agent=args.allow_same_agent,
            )
            open_diagnostics = [] if command_ids else parallel_command_diagnostics(
                root,
                queue,
                group=args.group,
                max_agents=args.max_agents,
                allow_same_agent=args.allow_same_agent,
            )
            payload = {
                "project": args.project,
                "max_agents": args.max_agents,
                "dry_run": not args.write and not args.execute,
                "scope": {
                    "group": args.group,
                    "command_ids": command_ids,
                    "allow_same_agent": args.allow_same_agent,
                },
                "commands": parallel_payload(commands),
                "open_parallel_diagnostics": open_diagnostics,
            }
            if args.json:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                if not commands:
                    print("No independent parallel commands.")
                for command in commands:
                    print(f"{command['id']}\t{command.get('priority', '')}\t{command_owner(command)}\t{command.get('action', '')}")
                if open_diagnostics:
                    print("")
                    print("Open parallel diagnostics:")
                    for item in open_diagnostics:
                        state = "selected" if item.get("selected") else "excluded"
                        reasons = ",".join(item.get("reasons") or []) or "-"
                        print(f"{item['id']}\t{state}\t{reasons}\t{item.get('owner_agent', '')}\t{item.get('parallel_group', '')}")
            if not args.write and not args.execute:
                return 0
            if not commands:
                return 0
            prompt_pairs: list[tuple[dict[str, Any], Path]] = []
            for command in commands:
                ensure_vote_gate(root, command)
                path = write_prompt(root, command, args.prompt_dir, args.prompt_style)
                mark_dispatched(root, command, path)
                prompt_pairs.append((command, path))
            record_parallel_dispatch_plan(root, commands, [path for _, path in prompt_pairs])
            if args.execute:
                return execute_and_record_parallel_result(
                    root,
                    event="parallel_runner_result",
                    prompt_pairs=prompt_pairs,
                    runner_template=parallel_runner_template,
                    runner_profile=parallel_runner_profile,
                )
            return 0

        if args.command == "run-prepared":
            runner_template: RunnerTemplate = ""
            runner_profile = ""
            if not args.dry_run:
                runner_template, runner_profile = resolve_runner_template(args.runner_command, args.runner_profile)
            if not args.command_ids and not args.group and not args.all_prepared:
                raise HarnessError("run-prepared requires --group, --id, or --all-prepared.")
            queue = load_command_queue(root)
            prompt_pairs = prepared_command_pairs(
                root,
                queue,
                command_ids=split_values(args.command_ids),
                group=args.group,
                max_agents=args.max_agents,
                fail_on_unfinished_dependencies=args.all_prepared,
            )
            payload = {
                "project": args.project,
                "max_agents": args.max_agents,
                "dry_run": args.dry_run,
                "runner_profile": runner_profile,
                "scope": {
                    "group": args.group,
                    "command_ids": split_values(args.command_ids),
                    "all_prepared": args.all_prepared,
                },
                "commands": [
                    {
                        "id": command.get("id"),
                        "owner_agent": command_owner(command),
                        "priority": command.get("priority"),
                        "action": command.get("action"),
                        "parallel_group": command.get("parallel_group", ""),
                        "prompt": path.relative_to(root).as_posix(),
                    }
                    for command, path in prompt_pairs
                ],
            }
            if args.json:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                if not prompt_pairs:
                    print("No prepared parallel prompts.")
                for command, path in prompt_pairs:
                    print(f"{command['id']}\t{command.get('priority', '')}\t{command_owner(command)}\t{path.relative_to(root).as_posix()}")
                if args.dry_run:
                    print("dry run: no external runner started.")
            if not prompt_pairs:
                return 0
            if args.dry_run:
                return 0
            record_prepared_parallel_run(root, prompt_pairs)
            return execute_and_record_parallel_result(
                root,
                event="parallel_prepared_runner_result",
                prompt_pairs=prompt_pairs,
                runner_template=runner_template,
                runner_profile=runner_profile,
            )

        if args.command == "status-parallel":
            queue = load_command_queue(root)
            open_commands = select_parallel_commands(
                root,
                queue,
                max_agents=args.max_items,
                group=args.group,
            )
            prepared_commands = prepared_parallel_commands(
                queue,
                group=args.group,
                limit=args.max_items,
            )
            open_diagnostics = parallel_command_diagnostics(
                root,
                queue,
                group=args.group,
                max_agents=args.max_items,
                limit=args.max_items,
            )
            payload = {
                "project": args.project,
                "group": args.group,
                "read_only": True,
                "open_parallel_candidates": parallel_payload(open_commands) if len(open_commands) >= 2 else [],
                "open_parallel_diagnostics": open_diagnostics,
                "prepared_parallel_commands": prepared_parallel_payload(prepared_commands, queue),
            }
            if args.json:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                print("Open parallel candidates:")
                if len(open_commands) < 2:
                    print("No safe open parallel batch.")
                else:
                    for command in open_commands:
                        print(f"{command['id']}\t{command.get('priority', '')}\t{command_owner(command)}\t{command.get('parallel_group', '')}\t{command.get('action', '')}")
                print("")
                print("Open parallel diagnostics:")
                if not open_diagnostics:
                    print("No open commands to diagnose.")
                else:
                    for item in open_diagnostics:
                        state = "selected" if item.get("selected") else "excluded"
                        reasons = ",".join(item.get("reasons") or []) or "-"
                        print(f"{item['id']}\t{state}\t{reasons}\t{item.get('owner_agent', '')}\t{item.get('parallel_group', '')}")
                print("")
                print("Prepared parallel commands:")
                if not prepared_commands:
                    print("No prepared parallel commands.")
                else:
                    commands_by_id = command_by_id(queue)
                    for command in prepared_commands:
                        unfinished = unfinished_command_dependencies(command, commands_by_id)
                        readiness = "ready" if not unfinished else f"waiting:{','.join(unfinished)}"
                        print(f"{command['id']}\t{command.get('status', '')}\t{readiness}\t{command_owner(command)}\t{command.get('parallel_group', '')}\t{command.get('orchestrator_prompt', '')}")
            return 0

        if args.command == "finish-parallel":
            if not args.command_ids and not args.group and not args.all_prepared:
                raise HarnessError("finish-parallel requires --group, --id, or --all-prepared.")
            result_files = parse_command_result_files(args.result_files)
            if args.status == "done" and not args.dry_run and not args.note and not args.outputs and not result_files:
                raise HarnessError("finish-parallel --status done requires --note, --output, or --result-file evidence.")
            if args.status in {"blocked", "deferred"} and not args.dry_run and not args.note:
                raise HarnessError("finish-parallel --status blocked/deferred requires --note explaining the reason.")
            queue = load_command_queue(root)
            commands = prepared_commands_for_scope(
                root,
                queue,
                command_ids=split_values(args.command_ids),
                group=args.group,
                all_prepared=args.all_prepared,
            )
            payload = {
                "project": args.project,
                "status": args.status,
                "dry_run": args.dry_run,
                "scope": {
                    "group": args.group,
                    "command_ids": split_values(args.command_ids),
                    "all_prepared": args.all_prepared,
                },
                "commands": [
                    {
                        "id": command.get("id"),
                        "owner_agent": command_owner(command),
                        "parallel_group": command.get("parallel_group", ""),
                        "orchestrator_prompt": command.get("orchestrator_prompt", ""),
                        "result_files": result_files.get(str(command.get("id") or ""), []),
                    }
                    for command in commands
                ],
            }
            if args.json:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                if not commands:
                    print("No prepared parallel commands to finish.")
                for command in commands:
                    print(f"{command['id']}\t{args.status}\t{command_owner(command)}\t{command.get('parallel_group', '')}")
                if args.dry_run:
                    print("dry run: no command status changed.")
            if not commands:
                return 0
            if args.dry_run:
                return 0
            for command in commands:
                command_id = str(command["id"])
                outputs = merged_output_paths(
                    command_values(command, "expected_outputs"),
                    split_values(args.outputs),
                    result_files.get(command_id, []),
                )
                finish_command(root, command_id, args.status, args.note, outputs)
            record_parallel_finish(root, commands, args.status, args.note)
            return 0

        if args.command == "finish":
            finish_command(root, args.command_id, args.status, args.note, split_values(args.outputs))
            print(f"finished: {args.command_id} -> {args.status}")
            return 0

        raise HarnessError(f"Unknown command: {args.command}")
    except (HarnessError, KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
