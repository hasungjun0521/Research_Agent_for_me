#!/usr/bin/env python3
"""Run a bounded Ralph-style fresh-context agent loop."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from scripts.commands.agents.agent_orchestrator import (
    command_owner,
    find_command,
    render_prompt,
    select_next_command,
)
from scripts.harness.runner_commands import split_runner_command
from scripts.harness.state import (
    HarnessError,
    append_agent_event,
    default_ralph_loop,
    find_ralph_run,
    load_command_queue,
    load_loop_summary,
    load_ralph_loop,
    mutate_ralph_loop,
    now_iso,
    project_root,
    ralph_loop_path,
    repo_root,
    validate_ralph_loop_doc,
    write_ralph_loop,
)

TERMINAL_STATUSES = {"complete", "blocked", "timeout", "max_iterations", "cancelled"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage bounded Ralph-style fresh-context loops.")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create state/ralph_loop.json if missing.")
    init.add_argument("--project", required=True)

    run = sub.add_parser("run", help="Run until result, max iterations, or deadline.")
    run.add_argument("--project", required=True)
    run.add_argument("--id", dest="run_id")
    run.add_argument("--goal", required=True)
    run.add_argument("--command-id", default="")
    run.add_argument("--duration-hours", type=float, default=0.0)
    run.add_argument("--duration-minutes", type=float, default=0.0)
    run.add_argument("--max-iterations", type=int, default=0, help="Optional safety cap. 0 means no iteration cap; the deadline/result condition controls stopping.")
    run.add_argument("--completion-promise", default="RALPH_COMPLETE")
    run.add_argument("--result-file", action="append", dest="result_files")
    run.add_argument("--result-mode", choices=["any", "all"], default="any")
    run.add_argument("--runner-command", help="External command template. Supports {prompt_file}, {project}, {run_id}, {command_id}, {agent}, and {iteration}.")
    run.add_argument("--execute", action="store_true", help="Execute the configured runner every iteration. Without this, write one prompt and stop.")
    run.add_argument("--codex-runner", action="store_true", help="Execute local Codex CLI every iteration with the Ralph prompt on stdin. Implies --execute.")
    run.add_argument("--codex-bin", default="codex", help="Codex CLI executable to use with --codex-runner.")
    run.add_argument("--codex-model", default="", help="Optional Codex model override for --codex-runner.")
    run.add_argument("--codex-profile", default="", help="Optional Codex config profile for --codex-runner.")
    run.add_argument("--codex-sandbox", choices=["read-only", "workspace-write", "danger-full-access"], default="workspace-write", help="Codex sandbox mode for --codex-runner.")
    run.add_argument("--codex-approval", choices=["untrusted", "on-failure", "on-request", "never"], default="never", help="Codex approval policy for --codex-runner.")
    run.add_argument("--codex-search", action="store_true", help="Enable Codex CLI web search for --codex-runner.")
    run.add_argument("--sleep-seconds", type=float, default=0.0)
    run.add_argument("--doom-threshold", type=int, default=0, help="Stop as blocked after N repeated no-progress signatures. 0 disables this guard.")
    run.add_argument("--prompt-dir", default="state/ralph_prompts")

    status = sub.add_parser("status", help="Show Ralph loop state.")
    status.add_argument("--project", required=True)
    status.add_argument("--id", dest="run_id")
    status.add_argument("--json", action="store_true")

    validate = sub.add_parser("validate", help="Validate state/ralph_loop.json.")
    validate.add_argument("--project", required=True)

    cancel = sub.add_parser("cancel", help="Cancel a running Ralph loop.")
    cancel.add_argument("--project", required=True)
    cancel.add_argument("--id", required=True, dest="run_id")
    cancel.add_argument("--reason", default="")

    compact = sub.add_parser("compact", help="Trim stored iteration history for a terminal run.")
    compact.add_argument("--project", required=True)
    compact.add_argument("--id", required=True, dest="run_id")
    compact.add_argument("--keep", type=int, default=5, help="Number of most recent iterations to keep.")
    compact.add_argument("--delete-prompts", action="store_true", help="Delete prompt files from removed iterations.")

    reset = sub.add_parser("reset", help="Reset Ralph loop state for a clean template or project.")
    reset.add_argument("--project", required=True)
    reset.add_argument(
        "--delete-prompts",
        action="store_true",
        help="Delete Markdown prompt files under state/ralph_prompts/ after clearing runs.",
    )

    return parser.parse_args()


def parse_duration_seconds(hours: float, minutes: float) -> int:
    if hours < 0 or minutes < 0:
        raise HarnessError("Duration values must be non-negative.")
    seconds = int((hours * 3600) + (minutes * 60))
    if seconds <= 0:
        raise HarnessError("Set --duration-hours or --duration-minutes to a positive value.")
    return seconds


def parse_iso(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def safe_relpath(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise HarnessError("Paths must be project-relative and must not contain '..'.")
    return path


def next_run_id(root: Path) -> str:
    timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S")
    return f"ralph_{root.name}_{timestamp}"


def make_run(
    root: Path,
    *,
    run_id: str,
    goal: str,
    command_id: str,
    duration_seconds: int,
    max_iterations: int,
    completion_promise: str,
    result_files: list[str],
    result_mode: str,
    doom_threshold: int,
) -> dict[str, Any]:
    if max_iterations < 0:
        raise HarnessError("--max-iterations must be non-negative.")
    if doom_threshold < 0:
        raise HarnessError("--doom-threshold must be non-negative.")
    started_at = datetime.now().astimezone()
    return {
        "id": run_id,
        "goal": goal,
        "status": "running",
        "command_id": command_id,
        "duration_seconds": duration_seconds,
        "max_iterations": max_iterations,
        "completion_promise": completion_promise,
        "result_files": result_files,
        "result_mode": result_mode,
        "doom_threshold": doom_threshold,
        "started_at": started_at.isoformat(timespec="seconds"),
        "deadline_at": (started_at + timedelta(seconds=duration_seconds)).isoformat(timespec="seconds"),
        "finished_at": "",
        "stop_reason": "",
        "last_prompt_file": "",
        "last_signature": "",
        "repeated_signature_count": 0,
        "iterations": [],
        "notes": "Ralph loop uses fresh prompts and file-based state each iteration.",
    }


def select_command(root: Path, command_id: str) -> dict[str, Any] | None:
    if command_id:
        return find_command(root, command_id)
    return select_next_command(load_command_queue(root))


def result_files_satisfied(root: Path, result_files: list[str], mode: str) -> tuple[bool, list[str]]:
    if not result_files:
        return False, []
    existing = [
        path for path in result_files
        if (root / safe_relpath(path)).exists()
    ]
    if mode == "all":
        return len(existing) == len(result_files), existing
    return bool(existing), existing


def command_result_status(root: Path, command_id: str) -> tuple[str, str]:
    if not command_id:
        return "", ""
    command = find_command(root, command_id)
    status = str(command.get("status") or "").lower()
    if status == "done":
        return "complete", f"Command {command_id} is done."
    if status == "blocked":
        return "blocked", f"Command {command_id} is blocked."
    if status == "deferred":
        return "blocked", f"Command {command_id} is deferred."
    return "", ""


def detect_result(root: Path, run: dict[str, Any], stdout: str = "") -> tuple[str, str]:
    promise = str(run.get("completion_promise") or "").strip()
    if promise and f"<promise>{promise}</promise>" in stdout:
        return "complete", f"Completion promise matched: {promise}."
    command_status, command_reason = command_result_status(root, str(run.get("command_id") or ""))
    if command_status:
        return command_status, command_reason
    satisfied, existing = result_files_satisfied(
        root,
        [str(path) for path in run.get("result_files", [])],
        str(run.get("result_mode") or "any"),
    )
    if satisfied:
        return "complete", f"Result file condition met: {', '.join(existing)}."
    loop_summary = load_loop_summary(root)
    if str(loop_summary.get("status") or "").lower() == "done" and not run.get("command_id"):
        return "complete", f"Loop summary {loop_summary.get('loop_id')} is done."
    return "", ""


def progress_signature(root: Path, run: dict[str, Any]) -> str:
    queue = load_command_queue(root)
    commands = [
        {
            "id": command.get("id"),
            "status": command.get("status"),
            "updated_at": command.get("updated_at"),
        }
        for command in queue.get("commands", [])
        if not run.get("command_id") or command.get("id") == run.get("command_id")
    ]
    files = {
        path: (root / safe_relpath(str(path))).exists()
        for path in run.get("result_files", [])
    }
    loop_summary = load_loop_summary(root)
    payload = {
        "commands": commands,
        "result_files": files,
        "loop_status": loop_summary.get("status"),
        "loop_updated": loop_summary.get("last_updated"),
    }
    return json.dumps(payload, sort_keys=True)


def ralph_prompt(root: Path, run: dict[str, Any], command: dict[str, Any] | None, iteration: int, remaining_seconds: int) -> str:
    command_prompt = render_prompt(root, command) if command else "No dispatchable command is selected. Diagnose the project state and update the command queue."
    payload = {
        "project": root.name,
        "ralph_run_id": run["id"],
        "iteration": iteration,
        "deadline_at": run["deadline_at"],
        "remaining_seconds": remaining_seconds,
        "completion_promise": run["completion_promise"],
        "result_files": run.get("result_files", []),
        "result_mode": run.get("result_mode", "any"),
        "goal": run["goal"],
    }
    return "\n\n".join([
        f"# Ralph Loop Iteration {iteration}: {run['id']}",
        "You are running one fresh-context iteration of a bounded Ralph loop.",
        "Read state from files, make measurable progress, update files through scripts, and stop honestly when blocked.",
        f"If and only if the result is complete, include `<promise>{run['completion_promise']}</promise>` in the final response.",
        "Do not rely on prior chat context. Persist progress in project files.",
        "## Ralph Run Payload",
        "```json\n" + json.dumps(payload, indent=2, ensure_ascii=False) + "\n```",
        "## Selected Command Prompt",
        command_prompt,
    ]) + "\n"


def prompt_path(root: Path, prompt_dir: str, run_id: str, iteration: int) -> Path:
    rel = safe_relpath(prompt_dir)
    return root / rel / f"{run_id}_iter_{iteration:03d}.md"


def write_prompt(root: Path, prompt_dir: str, run: dict[str, Any], command: dict[str, Any] | None, iteration: int, remaining_seconds: int) -> Path:
    path = prompt_path(root, prompt_dir, str(run["id"]), iteration)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(ralph_prompt(root, run, command, iteration, remaining_seconds), encoding="utf-8")
    return path


def runner_argv(template: str, *, prompt_file: Path, root: Path, run: dict[str, Any], command: dict[str, Any] | None, iteration: int) -> list[str]:
    if not template:
        raise HarnessError("--runner-command is required when --execute is set.")
    rendered = template.format(
        prompt_file=str(prompt_file),
        project=root.name,
        run_id=run["id"],
        command_id=str(command.get("id") if command else ""),
        agent=command_owner(command) if command else "director",
        iteration=iteration,
    )
    return split_runner_command(rendered)


def should_execute(args: argparse.Namespace) -> bool:
    return bool(args.execute or args.codex_runner)


def validate_runner_args(args: argparse.Namespace) -> None:
    if args.codex_runner and args.runner_command:
        raise HarnessError("Use either --codex-runner or --runner-command, not both.")
    if args.execute and not args.runner_command and not args.codex_runner:
        raise HarnessError("--runner-command or --codex-runner is required when --execute is set.")


def codex_runner_argv(args: argparse.Namespace) -> list[str]:
    argv = [args.codex_bin]
    if args.codex_approval:
        argv.extend(["-a", args.codex_approval])
    if args.codex_search:
        argv.append("--search")
    argv.append("exec")
    argv.extend(["-C", str(repo_root()), "-s", args.codex_sandbox])
    if args.codex_model:
        argv.extend(["-m", args.codex_model])
    if args.codex_profile:
        argv.extend(["-p", args.codex_profile])
    argv.append("-")
    return argv


def runner_invocation(
    args: argparse.Namespace,
    *,
    prompt_file: Path,
    root: Path,
    run: dict[str, Any],
    command: dict[str, Any] | None,
    iteration: int,
) -> tuple[list[str], str | None]:
    if args.codex_runner:
        return codex_runner_argv(args), prompt_file.read_text(encoding="utf-8")
    return runner_argv(
        args.runner_command or "",
        prompt_file=prompt_file,
        root=root,
        run=run,
        command=command,
        iteration=iteration,
    ), None


def finalize_run(root: Path, run_id: str, status: str, reason: str) -> dict[str, Any]:
    if status not in TERMINAL_STATUSES:
        raise HarnessError(f"Invalid final Ralph status: {status}")

    def mutate(data: dict[str, Any]) -> None:
        run = find_ralph_run(data, run_id)
        if run is None:
            raise HarnessError(f"Ralph run not found: {run_id}")
        run["status"] = status
        run["stop_reason"] = reason
        run["finished_at"] = now_iso()
        if data.get("active_run_id") == run_id:
            data["active_run_id"] = ""

    return mutate_ralph_loop(root, mutate)


def settle_blocking_active_run(root: Path, requested_run_id: str) -> None:
    """Finalize stale active runs before starting a different Ralph run.

    A previous process can exit after recording an active run but before it
    notices that the run has already completed, blocked, or timed out. Without
    this preflight, a later run with a different id is forced to fail forever on
    the stale active_run_id.
    """

    state = load_ralph_loop(root)
    active_run_id = str(state.get("active_run_id") or "").strip()
    if not active_run_id or active_run_id == requested_run_id:
        return
    active_run = find_ralph_run(state, active_run_id)
    if active_run is None or str(active_run.get("status") or "") != "running":
        def clear_active(data: dict[str, Any]) -> None:
            if data.get("active_run_id") == active_run_id:
                data["active_run_id"] = ""

        mutate_ralph_loop(root, clear_active)
        return

    result_status, result_reason = detect_result(root, active_run)
    if result_status:
        finalize_run(root, active_run_id, result_status, result_reason)
        return

    deadline = parse_iso(active_run.get("deadline_at"))
    if deadline is not None and int((deadline - datetime.now().astimezone()).total_seconds()) <= 0:
        finalize_run(root, active_run_id, "timeout", "Deadline reached before another Ralph run resumed.")


def record_iteration(
    root: Path,
    run_id: str,
    *,
    iteration: int,
    status: str,
    prompt_file: Path,
    command: dict[str, Any] | None,
    returncode: int | None,
    reason: str,
    signature: str,
) -> dict[str, Any]:
    prompt_rel = prompt_file.relative_to(root).as_posix()
    command_id = str(command.get("id") if command else "")

    def mutate(data: dict[str, Any]) -> None:
        run = find_ralph_run(data, run_id)
        if run is None:
            raise HarnessError(f"Ralph run not found: {run_id}")
        previous = str(run.get("last_signature") or "")
        repeated = int(run.get("repeated_signature_count", 0) or 0)
        repeated = repeated + 1 if previous and previous == signature else 1
        run["last_signature"] = signature
        run["repeated_signature_count"] = repeated
        run["last_prompt_file"] = prompt_rel
        run.setdefault("iterations", []).append({
            "iteration": iteration,
            "status": status,
            "started_at": now_iso(),
            "prompt_file": prompt_rel,
            "command_id": command_id,
            "agent": command_owner(command) if command else "director",
            "returncode": returncode,
            "reason": reason,
            "signature": signature,
        })

    return mutate_ralph_loop(root, mutate)


def start_or_resume_run(root: Path, run_doc: dict[str, Any]) -> str:
    mode = "started"

    def mutate(data: dict[str, Any]) -> None:
        nonlocal mode
        existing = find_ralph_run(data, run_doc["id"])
        active_run_id = str(data.get("active_run_id") or "").strip()
        if existing:
            status = str(existing.get("status") or "").strip().lower()
            if status != "running":
                raise HarnessError(f"Ralph run already exists with terminal status {status}: {run_doc['id']}")
            if active_run_id and active_run_id != run_doc["id"]:
                active = find_ralph_run(data, active_run_id)
                if active and str(active.get("status") or "") == "running":
                    raise HarnessError(f"Ralph run already active: {active_run_id}")
            existing["notes"] = (
                str(existing.get("notes") or "Ralph loop uses fresh prompts and file-based state each iteration.").rstrip()
                + f"\nResumed at {now_iso()}."
            )
            data["active_run_id"] = run_doc["id"]
            mode = "resumed"
            return
        if active_run_id:
            active = find_ralph_run(data, active_run_id)
            if active and str(active.get("status") or "") == "running":
                raise HarnessError(f"Ralph run already active: {active_run_id}")
        data["runs"].append(run_doc)
        data["active_run_id"] = run_doc["id"]

    mutate_ralph_loop(root, mutate)
    return mode


def run_loop(args: argparse.Namespace) -> int:
    validate_runner_args(args)
    execute = should_execute(args)
    root = project_root(args.project)
    duration_seconds = parse_duration_seconds(args.duration_hours, args.duration_minutes)
    run_id = args.run_id or next_run_id(root)
    result_files = [str(safe_relpath(path)) for path in (args.result_files or [])]
    command = select_command(root, args.command_id)
    command_id = args.command_id or str(command.get("id") if command else "")
    run_doc = make_run(
        root,
        run_id=run_id,
        goal=args.goal,
        command_id=command_id,
        duration_seconds=duration_seconds,
        max_iterations=args.max_iterations,
        completion_promise=args.completion_promise,
        result_files=result_files,
        result_mode=args.result_mode,
        doom_threshold=args.doom_threshold,
    )
    settle_blocking_active_run(root, run_id)
    mode = start_or_resume_run(root, run_doc)
    state = load_ralph_loop(root)
    active_run = find_ralph_run(state, run_id) or run_doc
    command_id = str(active_run.get("command_id") or "")
    command = select_command(root, command_id)
    append_agent_event(
        root,
        "ralph_resume" if mode == "resumed" else "ralph_start",
        command_owner(command) if command else "director",
        status="running",
        command_id=command_id,
        task=str(active_run.get("goal") or args.goal),
        stage="ralph loop",
    )

    try:
        iteration = len(active_run.get("iterations", []))
        while True:
            state = load_ralph_loop(root)
            run = find_ralph_run(state, run_id)
            if run is None:
                raise HarnessError(f"Ralph run disappeared: {run_id}")
            if str(run.get("status") or "") != "running":
                print(f"{run_id}\t{run.get('status')}\t{run.get('stop_reason')}")
                return 0 if run.get("status") == "complete" else 1

            result_status, result_reason = detect_result(root, run)
            if result_status:
                finalize_run(root, run_id, result_status, result_reason)
                print(f"{run_id}\t{result_status}\t{result_reason}")
                return 0 if result_status == "complete" else 1

            deadline = parse_iso(run.get("deadline_at"))
            if deadline is None:
                raise HarnessError(f"Ralph run {run_id} has invalid deadline_at.")
            remaining_seconds = int((deadline - datetime.now().astimezone()).total_seconds())
            if remaining_seconds <= 0:
                finalize_run(root, run_id, "timeout", "Deadline reached before result was detected.")
                print(f"{run_id}\ttimeout\tDeadline reached before result was detected.")
                return 1

            iteration += 1
            max_iterations = int(run.get("max_iterations", 0) or 0)
            if max_iterations and iteration > max_iterations:
                finalize_run(root, run_id, "max_iterations", "Maximum iterations reached before result was detected.")
                print(f"{run_id}\tmax_iterations\tMaximum iterations reached before result was detected.")
                return 1

            command = select_command(root, str(run.get("command_id") or ""))
            prompt_file = write_prompt(root, args.prompt_dir, run, command, iteration, remaining_seconds)
            stdout = ""
            returncode: int | None = None
            reason = "Prompt written."
            if execute:
                argv, stdin_text = runner_invocation(
                    args,
                    prompt_file=prompt_file,
                    root=root,
                    run=run,
                    command=command,
                    iteration=iteration,
                )
                timeout_seconds = max(1, remaining_seconds)
                completed = subprocess.run(
                    argv,
                    cwd=repo_root(),
                    input=stdin_text,
                    text=True,
                    capture_output=True,
                    timeout=timeout_seconds,
                    check=False,
                )
                stdout = (completed.stdout or "") + (completed.stderr or "")
                returncode = completed.returncode
                reason = f"Runner exited with {returncode}."
                if stdout:
                    sys.stdout.write(stdout)
                    if not stdout.endswith("\n"):
                        sys.stdout.write("\n")
            signature = progress_signature(root, run)
            state = record_iteration(
                root,
                run_id,
                iteration=iteration,
                status="running",
                prompt_file=prompt_file,
                command=command,
                returncode=returncode,
                reason=reason,
                signature=signature,
            )
            run = find_ralph_run(state, run_id) or run
            result_status, result_reason = detect_result(root, run, stdout)
            if result_status:
                finalize_run(root, run_id, result_status, result_reason)
                print(f"{run_id}\t{result_status}\t{result_reason}")
                return 0 if result_status == "complete" else 1
            threshold = int(run.get("doom_threshold", 0) or 0)
            if threshold and int(run.get("repeated_signature_count", 0) or 0) >= threshold:
                reason = f"No-progress signature repeated {threshold} times."
                finalize_run(root, run_id, "blocked", reason)
                print(f"{run_id}\tblocked\t{reason}")
                return 1
            if not execute:
                print(
                    f"{run_id}\trunning\tprompt: {prompt_file.relative_to(root).as_posix()}"
                    "\tmanual prompt written; rerun this id to resume until result or deadline"
                )
                return 0
            if args.sleep_seconds > 0:
                time.sleep(min(args.sleep_seconds, max(0, remaining_seconds)))
    except subprocess.TimeoutExpired:
        finalize_run(root, run_id, "timeout", "Runner timed out at the configured deadline.")
        print(f"{run_id}\ttimeout\tRunner timed out at the configured deadline.")
        return 1


def print_status(root: Path, run_id: str, as_json: bool) -> None:
    data = load_ralph_loop(root)
    if run_id:
        run = find_ralph_run(data, run_id)
        if run is None:
            raise HarnessError(f"Ralph run not found: {run_id}")
        payload = {"project": root.name, "run": run}
    else:
        payload = data
    if as_json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    runs = [payload["run"]] if run_id else data.get("runs", [])
    for run in runs:
        print(f"{run.get('id')}\t{run.get('status')}\titer={len(run.get('iterations', []))}\tdeadline={run.get('deadline_at')}\t{run.get('goal')}")


def compact_run(root: Path, run_id: str, keep: int, delete_prompts: bool) -> tuple[int, int]:
    if keep < 0:
        raise HarnessError("--keep must be non-negative.")
    removed_prompt_files: list[str] = []
    removed_count = 0

    def mutate(data: dict[str, Any]) -> None:
        nonlocal removed_count
        run = find_ralph_run(data, run_id)
        if run is None:
            raise HarnessError(f"Ralph run not found: {run_id}")
        if str(run.get("status") or "") == "running":
            raise HarnessError("Refusing to compact a running Ralph loop.")
        iterations = list(run.get("iterations", []))
        if keep == 0:
            kept: list[dict[str, Any]] = []
            removed = iterations
        else:
            kept = iterations[-keep:]
            removed = iterations[:-keep]
        removed_count = len(removed)
        for iteration in removed:
            prompt_file = str(iteration.get("prompt_file") or "").strip()
            if prompt_file:
                removed_prompt_files.append(prompt_file)
        run["iterations"] = kept
        run["notes"] = (
            str(run.get("notes") or "").rstrip()
            + f"\nCompacted at {now_iso()}: removed {removed_count} stored iterations, kept {len(kept)}."
        ).strip()

    mutate_ralph_loop(root, mutate)

    deleted_count = 0
    if delete_prompts:
        for prompt_file in removed_prompt_files:
            path = root / safe_relpath(prompt_file)
            if path.is_file():
                path.unlink()
                deleted_count += 1
    return removed_count, deleted_count


def reset_ralph_loop(root: Path, delete_prompts: bool) -> tuple[int, int]:
    data = load_ralph_loop(root) if ralph_loop_path(root).exists() else default_ralph_loop(root.name)
    removed_runs = len(data.get("runs", []))
    project_name = "{{PROJECT_NAME}}" if root.name == "template" else root.name
    write_ralph_loop(root, default_ralph_loop(project_name))

    deleted_prompts = 0
    if delete_prompts:
        prompt_dir = root / "state" / "ralph_prompts"
        if prompt_dir.is_dir():
            for path in sorted(prompt_dir.glob("*.md")):
                path.unlink()
                deleted_prompts += 1
    return removed_runs, deleted_prompts


def main() -> int:
    args = parse_args()
    try:
        root = project_root(args.project)
        if args.command == "init":
            data = load_ralph_loop(root) if ralph_loop_path(root).exists() else default_ralph_loop(root.name)
            write_ralph_loop(root, data)
            print(f"ralph runs: {len(data.get('runs', []))}")
            return 0

        if args.command == "run":
            return run_loop(args)

        if args.command == "status":
            print_status(root, args.run_id or "", args.json)
            return 0

        if args.command == "validate":
            data = load_ralph_loop(root)
            warnings = validate_ralph_loop_doc(data)
            if warnings:
                for warning in warnings:
                    print(f"warning: {warning}", file=sys.stderr)
                return 1
            print(f"valid ralph loop: {args.project}")
            return 0

        if args.command == "cancel":
            finalize_run(root, args.run_id, "cancelled", args.reason or "cancelled by operator")
            print(f"cancelled ralph run: {args.run_id}")
            return 0

        if args.command == "compact":
            removed, deleted = compact_run(root, args.run_id, args.keep, args.delete_prompts)
            print(f"compacted ralph run: {args.run_id}; removed={removed}; deleted_prompts={deleted}")
            return 0

        if args.command == "reset":
            removed, deleted = reset_ralph_loop(root, args.delete_prompts)
            print(f"reset ralph loop: removed_runs={removed}; deleted_prompts={deleted}")
            return 0

        raise HarnessError(f"Unknown command: {args.command}")
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
