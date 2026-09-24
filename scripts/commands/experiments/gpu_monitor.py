#!/usr/bin/env python3
"""Monitor launched GPU jobs and synchronize queue/run_state outcomes."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from scripts.harness.state import (
    HarnessError,
    append_agent_event,
    append_run_history,
    load_gpu_queue,
    mutate_gpu_queue,
    mutate_run_state,
    now_iso,
    project_root,
    update_agent_status,
)
from scripts.harness.workflow_hooks import refresh_report_index

FAIL_PATTERNS = (
    "traceback (most recent call last)",
    "runtimeerror:",
    "cuda out of memory",
    "outofmemoryerror",
    "exception:",
    "error:",
    "failed",
)
SUCCESS_PATTERNS = (
    "training complete",
    "evaluation complete",
    "finished successfully",
    "success",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check running GPU jobs and update project state.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--squeue-output", help="Mock or captured squeue output file.")
    parser.add_argument("--stale-minutes", type=int, default=60)
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--assume-missing-squeue-finished",
        action="store_true",
        help="When squeue is available and the job vanished, finish jobs without requiring a result path.",
    )
    return parser.parse_args()


def read_optional(path: str | None) -> str:
    if not path:
        return ""
    return Path(path).read_text(encoding="utf-8")


def run_capture(command: list[str], timeout: int = 5) -> tuple[str, str]:
    try:
        result = subprocess.run(command, text=True, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "", str(exc)
    if result.returncode != 0:
        return result.stdout, result.stderr.strip() or f"exit {result.returncode}"
    return result.stdout, ""


def parse_squeue(text: str) -> tuple[set[str], set[str]]:
    job_ids: set[str] = set()
    job_names: set[str] = set()
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.lower().startswith("jobid"):
            continue
        parts = stripped.split("|")
        if len(parts) >= 2:
            job_ids.add(parts[0].strip())
            job_names.add(parts[1].strip())
        else:
            tokens = stripped.split()
            if tokens:
                job_ids.add(tokens[0])
            if len(tokens) > 1:
                job_names.add(tokens[1])
    return job_ids, job_names


def project_relative(root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise HarnessError(f"Path must be project-relative: {value}")
    return root / path


def read_tail(path: Path, limit: int = 80_000) -> str:
    if not path.is_file():
        return ""
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    return data[-limit:].decode("utf-8", errors="replace")


def has_nonempty_result(path: Path) -> bool:
    if path.is_file():
        return path.stat().st_size > 0
    if not path.is_dir():
        return False
    for child in path.rglob("*"):
        if child.is_file() and child.stat().st_size > 0:
            return True
    return False


def tmux_session_exists(name: str) -> bool | None:
    if not name or not shutil.which("tmux"):
        return None
    result = subprocess.run(["tmux", "has-session", "-t", name], text=True, capture_output=True)
    return result.returncode == 0


def parse_timestamp(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def stale_minutes(job: dict[str, Any]) -> float:
    timestamp = parse_timestamp(job.get("updated_at"))
    if not timestamp:
        return 0.0
    return (datetime.now().astimezone() - timestamp).total_seconds() / 60.0


def classify_job(
    root: Path,
    job: dict[str, Any],
    *,
    squeue_available: bool,
    active_job_ids: set[str],
    active_job_names: set[str],
    stale_after: int,
    assume_missing_finished: bool,
) -> tuple[str | None, str]:
    log_path = project_relative(root, str(job.get("log_path") or "")) if job.get("log_path") else None
    result_path = project_relative(root, str(job.get("result_path") or "")) if job.get("result_path") else None
    log_tail = read_tail(log_path) if log_path else ""
    lower_tail = log_tail.lower()
    if lower_tail and any(pattern in lower_tail for pattern in FAIL_PATTERNS):
        return "failed", "failure pattern found in log"
    if lower_tail and any(pattern in lower_tail for pattern in SUCCESS_PATTERNS) and result_path and has_nonempty_result(result_path):
        return "succeeded", "success pattern and non-empty result path"

    slurm_job_id = str(job.get("slurm_job_id") or "").strip()
    slurm_job_name = str(job.get("slurm_job_name") or "").strip()
    in_squeue = (slurm_job_id and slurm_job_id in active_job_ids) or (slurm_job_name and slurm_job_name in active_job_names)
    tmux_alive = tmux_session_exists(str(job.get("tmux_session") or ""))
    result_ready = bool(result_path and has_nonempty_result(result_path))

    if squeue_available and in_squeue:
        return None, "still running in scheduler"
    if result_ready and (not squeue_available or not in_squeue):
        return "succeeded", "non-empty result path and no active scheduler signal"
    if squeue_available and not in_squeue:
        if tmux_alive is True:
            return None, "legacy tmux session still exists after scheduler job vanished"
        if result_ready or assume_missing_finished:
            return "succeeded", "job vanished from scheduler"
        return "failed", "job vanished before result path was populated"
    if stale_minutes(job) >= stale_after:
        return "blocked", f"running heartbeat is stale for at least {stale_after} minutes"
    return None, "still running"


def job_output_paths(job: dict[str, Any]) -> list[str]:
    return [
        value
        for value in (
            str(job.get("log_path") or ""),
            str(job.get("result_path") or ""),
            str(job.get("expected_output") or ""),
        )
        if value
    ]


def agent_status_for_gpu_update(queue: dict[str, Any], owner: str, updated_job_id: str, job_status: str) -> str:
    active_for_owner = [
        job for job in queue.get("jobs", [])
        if str(job.get("id") or "") != updated_job_id
        and str(job.get("owner_agent") or "code_agent") == owner
        and str(job.get("status") or "").lower() in {"queued", "running"}
    ]
    if active_for_owner:
        return "running"
    if job_status == "succeeded":
        return "waiting"
    if job_status in {"failed", "blocked"}:
        return "blocked"
    return "waiting"


def sync_gpu_agent_status(root: Path, queue: dict[str, Any], job: dict[str, Any], status: str, note: str) -> None:
    owner = str(job.get("owner_agent") or "code_agent")
    job_id = str(job.get("id") or "")
    exp_id = str(job.get("exp_id") or "")
    agent_status = agent_status_for_gpu_update(queue, owner, job_id, status)
    task = f"GPU job {job_id} is {status} for {exp_id}."
    outputs = job_output_paths(job)
    update_agent_status(
        root,
        owner,
        agent_status,
        task=task,
        stage="gpu_experiment",
        outputs=outputs,
        notes=note,
        append_note=True,
    )
    append_agent_event(
        root,
        f"gpu_monitor_{status}",
        owner,
        status=agent_status,
        task=task,
        stage="gpu_experiment",
        outputs=outputs,
        notes=note,
    )


def apply_outcome(root: Path, job: dict[str, Any], status: str, note: str) -> None:
    timestamp = now_iso()
    job_id = str(job["id"])

    def update_queue(queue: dict[str, Any]) -> None:
        for candidate in queue.get("jobs", []):
            if candidate.get("id") != job_id:
                continue
            candidate["status"] = status
            candidate["updated_at"] = timestamp
            candidate["notes"] = note
            return
        raise HarnessError(f"GPU job not found: {job_id}")

    queue_after = mutate_gpu_queue(root, update_queue)

    exp_id = str(job.get("exp_id") or "").strip()
    updated_job = dict(job)
    updated_job["status"] = status
    updated_job["notes"] = note

    if exp_id:
        def update_run(data: dict[str, Any]) -> None:
            data["status"] = "succeeded" if status == "succeeded" else "failed" if status == "failed" else "blocked"
            data["updated_at"] = timestamp
            if status in {"succeeded", "failed"}:
                data["finished_at"] = timestamp
            if job.get("result_path"):
                data["result_path"] = str(job["result_path"])
            if job.get("expected_output"):
                data["expected_output"] = str(job["expected_output"])
            if job.get("check_procedure"):
                data["check_procedure"] = str(job["check_procedure"])
            data["judgement"] = note
            data["display_summary"] = f"GPU job {job_id} {status}: {note}"
            append_run_history(data, f"gpu_monitor:{status}", note)

        mutate_run_state(root, exp_id, update_run)
    sync_gpu_agent_status(root, queue_after, updated_job, status, note)


def check_jobs(args: argparse.Namespace) -> dict[str, Any]:
    root = project_root(args.project)
    squeue_text = read_optional(args.squeue_output)
    squeue_error = ""
    if not squeue_text and not args.squeue_output:
        squeue_text, squeue_error = run_capture(["squeue", "--me", "-h", "-o", "%i|%j|%T|%b|%D|%R"])
    squeue_available = bool(squeue_text) or (not squeue_error and not args.squeue_output)
    active_ids, active_names = parse_squeue(squeue_text)
    queue = load_gpu_queue(root)
    outcomes: list[dict[str, str]] = []
    changed = False
    for job in queue.get("jobs", []):
        if str(job.get("status") or "").lower() != "running":
            continue
        status, note = classify_job(
            root,
            job,
            squeue_available=squeue_available,
            active_job_ids=active_ids,
            active_job_names=active_names,
            stale_after=args.stale_minutes,
            assume_missing_finished=args.assume_missing_squeue_finished,
        )
        if status:
            apply_outcome(root, job, status, note)
            changed = True
            outcomes.append({"id": str(job.get("id")), "status": status, "note": note})
        else:
            outcomes.append({"id": str(job.get("id")), "status": "running", "note": note})
    if changed:
        refresh_report_index(root)
    return {
        "project": args.project,
        "squeue_available": squeue_available,
        "squeue_warning": squeue_error,
        "active_job_ids": sorted(active_ids),
        "active_job_names": sorted(active_names),
        "outcomes": outcomes,
    }


def main() -> int:
    args = parse_args()
    try:
        result = check_jobs(args)
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            if result["squeue_warning"]:
                print(f"warning: squeue unavailable: {result['squeue_warning']}", file=sys.stderr)
            if not result["outcomes"]:
                print("no running GPU jobs")
            for outcome in result["outcomes"]:
                print(f"{outcome['id']}\t{outcome['status']}\t{outcome['note']}")
        return 0
    except (HarnessError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
