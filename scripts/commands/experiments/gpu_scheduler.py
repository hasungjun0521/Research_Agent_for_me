#!/usr/bin/env python3
"""Plan and launch bounded parallel GPU experiment jobs."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts.harness.state import (
    GPU_JOB_STATUSES,
    GPU_TYPES,
    RUN_STATUSES,
    HarnessError,
    append_agent_event,
    append_run_history,
    default_gpu_queue,
    gpu_queue_path,
    load_gpu_queue,
    mutate_gpu_queue,
    mutate_run_state,
    now_iso,
    project_root,
    update_agent_status,
    write_gpu_queue,
)
from scripts.harness.workflow_hooks import refresh_report_index
from scripts.harness.workspace_profile import (
    ProfileError,
    workspace_gpu_auto_order,
    workspace_gpu_command,
    workspace_gpu_default_type,
    workspace_gpu_enabled,
    workspace_gpu_max_user_gpus,
    workspace_gpu_profiles,
)


def _safe_gpu_profiles() -> dict[str, dict[str, Any]]:
    """Resolve GPU profiles without letting a broken local profile kill the import."""
    try:
        return workspace_gpu_profiles()
    except ProfileError as exc:
        print(
            f"warning: workspace profile is invalid ({exc}); no GPU profiles are available. "
            "Run 'python -m scripts.commands.release.workspace_profile validate' to diagnose.",
            file=sys.stderr,
        )
        return {}


GPU_PROFILES = _safe_gpu_profiles()
PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bounded GPU experiment scheduler.")
    sub = parser.add_subparsers(dest="action", required=True)

    init = sub.add_parser("init", help="Create state/gpu_experiment_queue.json if missing.")
    init.add_argument("--project", required=True)

    add = sub.add_parser("add", help="Add a queued GPU experiment job.")
    add_common(add)
    add.add_argument("--id", required=True)
    add.add_argument("--exp-id", required=True)
    add.add_argument("--command", required=True, dest="experiment_command")
    add.add_argument("--priority", choices=["high", "medium", "low"], default="medium")
    add.add_argument("--owner", dest="owner_agent", default="code_agent")
    add.add_argument("--result-path", default="")
    add.add_argument("--expected-output", default="", help="Expected artifact or metric output for this GPU job.")
    add.add_argument("--check-procedure", default="", help="How to verify this job succeeded after completion.")
    add.add_argument(
        "--depends-on",
        action="append",
        dest="depends_on",
        help="Queue job id this job depends on. May be repeated or comma-separated.",
    )

    status = sub.add_parser("status", help="Show current GPU capacity and queue summary.")
    add_status_common(status)

    plan = sub.add_parser("plan", help="Plan jobs that can be launched under the GPU cap.")
    add_status_common(plan)
    plan.add_argument("--json", action="store_true", help="Print machine-readable plan.")

    launch = sub.add_parser("launch", help="Launch planned jobs through sbatch.")
    add_status_common(launch)
    launch.add_argument("--id", help="Launch exactly one currently planned queue job.")
    launch.add_argument(
        "--all-planned",
        action="store_true",
        help="Launch all currently planned jobs. Prefer dispatch for normal parallel batches.",
    )
    launch.add_argument("--execute", action="store_true", help="Actually submit planned jobs with sbatch.")
    launch.add_argument(
        "--allow-disabled-profile",
        action="store_true",
        help=(
            "Allow --execute even when config/workspace_profile.local.json has "
            "gpu.enabled=false. Intended for explicit test fixtures or one-off overrides."
        ),
    )

    dispatch = sub.add_parser("dispatch", help="Plan and optionally execute queued jobs through sbatch.")
    add_status_common(dispatch)
    dispatch.add_argument("--ids", help="Comma-separated queue IDs to constrain dispatch (defaults to all queued jobs).")
    dispatch.add_argument(
        "--max-parallel",
        type=int,
        default=0,
        help="Maximum jobs to dispatch in this command (defaults to all planned jobs that fit available capacity).",
    )
    dispatch.add_argument("--json", action="store_true", help="Print machine-readable dry-run dispatch plan.")
    dispatch.add_argument("--execute", action="store_true", help="Actually submit planned jobs with sbatch.")
    dispatch.add_argument(
        "--allow-disabled-profile",
        action="store_true",
        help=(
            "Allow --execute even when config/workspace_profile.local.json has "
            "gpu.enabled=false. Intended for explicit test fixtures or one-off overrides."
        ),
    )

    refresh = sub.add_parser("refresh", help="Refresh queued/running GPU jobs from scheduler state.")
    add_status_common(refresh)
    refresh.add_argument("--write", action="store_true", help="Persist terminal or heartbeat state updates.")
    refresh.add_argument("--json", action="store_true", help="Print machine-readable lifecycle diagnostics.")
    refresh.add_argument(
        "--mark-missing",
        choices=["blocked", "failed", "cancelled", "succeeded"],
        help="Status to assign to running jobs that are no longer visible in scheduler output.",
    )

    list_cmd = sub.add_parser("list", help="List GPU jobs.")
    list_cmd.add_argument("--project", required=True)
    list_cmd.add_argument("--status", choices=sorted(GPU_JOB_STATUSES))
    list_cmd.add_argument("--json", action="store_true", help="Print machine-readable jobs with dependency readiness.")

    update = sub.add_parser("update", help="Update a GPU job status or metadata.")
    update.add_argument("--project", required=True)
    update.add_argument("--id", required=True)
    update.add_argument("--status", choices=sorted(GPU_JOB_STATUSES))
    update.add_argument("--note")
    update.add_argument("--result-path")
    update.add_argument("--expected-output")
    update.add_argument("--check-procedure")

    return parser.parse_args()


def add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", required=True)
    parser.add_argument("--gpu-type", choices=sorted(GPU_TYPES), default="auto")
    parser.add_argument("--gpus", type=int, default=1)
    parser.add_argument("--partition")
    parser.add_argument("--node")
    parser.add_argument("--mem")
    parser.add_argument("--cpus", type=int)
    parser.add_argument("--tmux-session")
    parser.add_argument("--slurm-job-name")
    parser.add_argument("--log-path")
    parser.add_argument(
        "--shell-mode",
        choices=["login", "plain"],
        default="login",
        help="Use a login shell (-lc) or a plain shell (-c) for sbatch --wrap. Use plain when conda run must preserve the target environment.",
    )


def add_status_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", required=True)
    parser.add_argument("--max-user-gpus", type=int)
    parser.add_argument("--squeue-output", help="Mock or captured squeue output file.")
    parser.add_argument("--scontrol-output", help="Mock or captured scontrol show node output file.")
    parser.add_argument("--available-gpus", help="Override free GPUs, e.g. a4000=2,a5000=1.")


def read_optional(path: str | None) -> str:
    if not path:
        return ""
    return Path(path).read_text(encoding="utf-8")


def run_capture(command: list[str], timeout: int = 15) -> tuple[str, str]:
    try:
        result = subprocess.run(command, text=True, capture_output=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return "", str(exc)
    if result.returncode != 0:
        return result.stdout, result.stderr.strip() or f"exit {result.returncode}"
    return result.stdout, ""


def parse_gpu_tokens(text: str) -> int:
    total = 0
    for line in text.splitlines():
        lower = line.lower()
        if not lower.strip() or "jobid" in lower:
            continue
        matches = re.findall(r"(?:gres/)?gpu(?:[:=][a-z0-9_]+)?[:=](\d+)", lower)
        if matches:
            total += sum(int(value) for value in matches)
            continue
        if re.search(r"\bgpu\b", lower):
            total += 1
    return total


def parse_squeue_rows(text: str) -> dict[str, dict[str, str]]:
    rows: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        if not line.strip() or "jobid" in line.lower():
            continue
        if "|" in line:
            parts = [part.strip() for part in line.split("|")]
            job_id = parts[0] if parts else ""
            name = parts[1] if len(parts) > 1 else ""
            state = parts[2] if len(parts) > 2 else ""
        else:
            parts = line.split()
            job_id = parts[0] if parts else ""
            name = parts[1] if len(parts) > 1 else ""
            state = parts[2] if len(parts) > 2 else ""
        if job_id:
            rows[job_id] = {"job_id": job_id, "name": name, "state": state.upper()}
    return rows


def scheduler_state_to_status(state: str) -> str:
    normalized = state.strip().upper()
    if normalized in {"COMPLETED", "COMPLETING"}:
        return "succeeded"
    if normalized in {"FAILED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL", "PREEMPTED", "BOOT_FAIL"}:
        return "failed"
    if normalized in {"CANCELLED", "CANCELLED+"}:
        return "cancelled"
    return "running"


def parse_scontrol_available(text: str) -> dict[str, int]:
    available = {gpu_type: 0 for gpu_type in GPU_PROFILES}
    for line in text.splitlines():
        if not line.strip():
            continue
        node_match = re.search(r"\bNodeName=(\S+)", line)
        if not node_match:
            continue
        node = node_match.group(1)
        gpu_type = next((kind for kind, profile in GPU_PROFILES.items() if profile["node"] == node), "")
        if not gpu_type:
            continue
        state_match = re.search(r"\bState=(\S+)", line)
        state = state_match.group(1).lower() if state_match else ""
        if any(bad in state for bad in ("down", "drain", "fail", "maint")):
            continue
        cfg_match = re.search(r"\bCfgTRES=\S*?gres/gpu=(\d+)", line)
        alloc_match = re.search(r"\bAllocTRES=\S*?gres/gpu=(\d+)", line)
        gres_match = re.search(r"\bGres=\S*?gpu(?::[a-z0-9_]+)?:(\d+)", line, flags=re.IGNORECASE)
        cfg = int(cfg_match.group(1)) if cfg_match else int(gres_match.group(1)) if gres_match else 0
        alloc = int(alloc_match.group(1)) if alloc_match else 0
        available[gpu_type] += max(0, cfg - alloc)
    return available


def parse_available_override(value: str | None) -> dict[str, int]:
    if not value:
        return {}
    result: dict[str, int] = {}
    for chunk in value.split(","):
        if not chunk.strip():
            continue
        key, _, raw_count = chunk.partition("=")
        key = key.strip().lower()
        if key not in GPU_PROFILES:
            raise HarnessError(f"Unknown GPU type in --available-gpus: {key}")
        result[key] = int(raw_count.strip())
    return result


def gpu_status(args: argparse.Namespace, queue: dict[str, Any]) -> dict[str, Any]:
    warnings: list[str] = []
    enabled = workspace_gpu_enabled()
    if not enabled:
        warnings.append(
            "gpu.enabled is false in the workspace profile; --execute will be blocked "
            "unless explicitly overridden."
        )
    squeue_text = read_optional(args.squeue_output)
    if not squeue_text and not args.squeue_output:
        squeue_text, error = run_capture(workspace_gpu_command("queue_status"))
        if error:
            warnings.append(f"squeue unavailable: {error}")
    own_gpus = parse_gpu_tokens(squeue_text)

    available = {gpu_type: 0 for gpu_type in GPU_PROFILES}
    override = parse_available_override(args.available_gpus)
    if override:
        available.update(override)
    else:
        scontrol_text = read_optional(args.scontrol_output)
        if not scontrol_text and not args.scontrol_output:
            lines = []
            for profile in GPU_PROFILES.values():
                text, error = run_capture(workspace_gpu_command("node_status", node=str(profile["node"])))
                if error:
                    warnings.append(f"scontrol unavailable for {profile['node']}: {error}")
                lines.append(text)
            scontrol_text = "\n".join(lines)
        available.update(parse_scontrol_available(scontrol_text))

    max_user_gpus = args.max_user_gpus or workspace_gpu_max_user_gpus()
    remaining_user_slots = max(0, max_user_gpus - own_gpus)
    return {
        "project": queue.get("project"),
        "profile_enabled": enabled,
        "own_gpus": own_gpus,
        "max_user_gpus": max_user_gpus,
        "remaining_user_slots": remaining_user_slots,
        "available_gpus": available,
        "warnings": warnings,
    }


def default_job_fields(args: argparse.Namespace) -> dict[str, Any]:
    default_type = workspace_gpu_default_type()
    fallback_type = default_type if default_type != "auto" else workspace_gpu_auto_order()[0]
    profile_key = args.gpu_type if args.gpu_type != "auto" else fallback_type
    profile = GPU_PROFILES.get(profile_key, next(iter(GPU_PROFILES.values())))
    exp_id = getattr(args, "exp_id", "")
    job_id = getattr(args, "id", exp_id or "gpu_job")
    slurm_job_name = args.slurm_job_name or f"{job_id}_{args.gpu_type}".replace("auto", "gpu")
    log_path = args.log_path or f"03_experiments/{exp_id}/logs/{job_id}.log"
    result_path = getattr(args, "result_path", "")
    return {
        "id": job_id,
        "exp_id": exp_id,
        "command": getattr(args, "experiment_command", ""),
        "priority": getattr(args, "priority", "medium"),
        "status": "queued",
        "gpu_type": args.gpu_type,
        "gpus": args.gpus,
        "partition": args.partition or profile["partition"],
        "node": args.node or profile["node"],
        "mem": args.mem or profile["mem"],
        "cpus": args.cpus or profile["cpus"],
        "tmux_session": args.tmux_session or "",
        "slurm_job_name": slurm_job_name,
        "slurm_job_id": "",
        "log_path": log_path,
        "result_path": result_path,
        "expected_output": args.expected_output or result_path or log_path,
        "check_procedure": args.check_procedure or "Inspect the scheduler log and expected output path, then update the GPU job and run_state outcome.",
        "depends_on": parse_dependency_values(getattr(args, "depends_on", None)),
        "shell_mode": args.shell_mode,
        "owner_agent": getattr(args, "owner_agent", "code_agent"),
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "notes": "",
    }


def selectable_jobs(queue: dict[str, Any]) -> list[dict[str, Any]]:
    jobs = [job for job in queue.get("jobs", []) if str(job.get("status") or "").lower() == "queued"]
    return sorted(jobs, key=lambda job: (PRIORITY_RANK.get(str(job.get("priority") or "medium"), 1), job.get("created_at", ""), job.get("id", "")))


def choose_gpu_type(job: dict[str, Any], available: dict[str, int]) -> str:
    requested = str(job.get("gpu_type") or "auto").lower()
    if requested != "auto":
        return requested
    for gpu_type in workspace_gpu_auto_order():
        if available.get(gpu_type, 0) >= int(job.get("gpus") or 1):
            return gpu_type
    return "auto"


def parse_ids(value: str | None) -> list[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def parse_dependency_values(values: list[str] | None) -> list[str]:
    dependencies: list[str] = []
    for value in values or []:
        for item in parse_ids(value):
            if item not in dependencies:
                dependencies.append(item)
    return dependencies


def gpu_job_status_by_id(queue: dict[str, Any]) -> dict[str, str]:
    return {
        str(job.get("id") or ""): str(job.get("status") or "").lower()
        for job in queue.get("jobs", [])
        if str(job.get("id") or "")
    }


def unfinished_gpu_dependencies(job: dict[str, Any], job_status: dict[str, str]) -> list[str]:
    return [
        str(dependency)
        for dependency in job.get("depends_on", [])
        if str(dependency).strip() and job_status.get(str(dependency)) != "succeeded"
    ]


def gpu_job_with_readiness(job: dict[str, Any], job_status: dict[str, str]) -> dict[str, Any]:
    unfinished = unfinished_gpu_dependencies(job, job_status)
    enriched = dict(job)
    enriched["dependency_ready"] = not unfinished
    enriched["unfinished_dependencies"] = unfinished
    return enriched


def select_jobs_for_dispatch(
    planned: list[dict[str, Any]],
    ids: str | None,
    max_parallel: int,
    diagnostics: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    selected = planned
    if ids:
        requested = parse_ids(ids)
        if max_parallel > 0 and len(requested) > max_parallel:
            raise HarnessError(
                f"Explicit GPU job count {len(requested)} exceeds --max-parallel {max_parallel}."
            )
        selected_map = {job["id"]: job for job in planned}
        missing = [job_id for job_id in requested if job_id not in selected_map]
        if missing:
            diagnostic_map = {
                str(item.get("id") or ""): item
                for item in diagnostics or []
                if str(item.get("id") or "")
            }
            missing_parts = []
            for job_id in missing:
                reasons = diagnostic_map.get(job_id, {}).get("reasons") or []
                reason_text = ",".join(reasons) if reasons else "not_planned"
                missing_parts.append(f"{job_id} ({reason_text})")
            missing_text = ", ".join(missing_parts)
            raise HarnessError(f"Requested jobs are not currently dispatchable: {missing_text}")
        selected = [selected_map[job_id] for job_id in requested]
    if max_parallel > 0:
        selected = selected[:max_parallel]
    return selected


def default_log_path(job: dict[str, Any]) -> str:
    exp_id = str(job.get("exp_id") or "gpu_jobs")
    job_id = str(job.get("id") or exp_id or "gpu_job")
    return f"03_experiments/{exp_id}/logs/{job_id}.log"


def _normalized_path(root: Path, raw_path: str | None) -> str:
    if not raw_path:
        return ""
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return str(candidate.resolve())
    return str((root / candidate).resolve())


def assert_no_dispatch_collisions(root: Path, selected: list[dict[str, Any]], queue: dict[str, Any]) -> None:
    target_paths: dict[str, list[str]] = {}

    def add_path(path: str, job_id: str) -> None:
        if not path:
            return
        normalized = _normalized_path(root, path)
        target_paths.setdefault(normalized, []).append(job_id)

    for job in selected:
        add_path(str(job.get("log_path") or default_log_path(job)), job["id"])
        result_path = str(job.get("result_path") or "").strip()
        add_path(result_path, job["id"])

    running_jobs = [job for job in queue.get("jobs", []) if job.get("status") == "running"]
    for job in running_jobs:
        add_path(str(job.get("log_path") or default_log_path(job)), f"{job['id']} (running)")
        result_path = str(job.get("result_path") or "").strip()
        add_path(result_path, f"{job['id']} (running)")

    collisions = [f"{path} (jobs: {', '.join(job_ids)})" for path, job_ids in target_paths.items() if len(job_ids) > 1]
    if collisions:
        raise HarnessError(
            "Output path collision in GPU dispatch plan: "
            + "; ".join(collisions)
        )


def plan_jobs(queue: dict[str, Any], status: dict[str, Any]) -> list[dict[str, Any]]:
    remaining = int(status["remaining_user_slots"])
    available = dict(status["available_gpus"])
    job_status = {str(job.get("id") or ""): str(job.get("status") or "").lower() for job in queue.get("jobs", [])}
    planned: list[dict[str, Any]] = []
    for job in selectable_jobs(queue):
        dependencies = [str(item) for item in job.get("depends_on", []) if str(item).strip()]
        if any(job_status.get(dependency) != "succeeded" for dependency in dependencies):
            continue
        needed = int(job.get("gpus") or 1)
        gpu_type = choose_gpu_type(job, available)
        if gpu_type == "auto" or needed > remaining or needed > available.get(gpu_type, 0):
            continue
        profile = GPU_PROFILES[gpu_type]
        planned_job = dict(job)
        planned_job["gpu_type"] = gpu_type
        planned_job["partition"] = job.get("partition") or profile["partition"]
        planned_job["node"] = job.get("node") or profile["node"]
        planned_job["mem"] = job.get("mem") or profile["mem"]
        planned_job["cpus"] = job.get("cpus") or profile["cpus"]
        planned.append(planned_job)
        remaining -= needed
        available[gpu_type] -= needed
    return planned


def gpu_plan_diagnostics(queue: dict[str, Any], status: dict[str, Any], planned: list[dict[str, Any]]) -> list[dict[str, Any]]:
    planned_ids = {str(job.get("id") or "") for job in planned}
    job_status = {str(job.get("id") or ""): str(job.get("status") or "").lower() for job in queue.get("jobs", [])}
    remaining = int(status["remaining_user_slots"])
    available = dict(status["available_gpus"])
    rows: list[dict[str, Any]] = []
    for job in selectable_jobs(queue):
        job_id = str(job.get("id") or "")
        needed = int(job.get("gpus") or 1)
        dependencies = [str(item) for item in job.get("depends_on", []) if str(item).strip()]
        reasons: list[str] = []
        unfinished = [dependency for dependency in dependencies if job_status.get(dependency) != "succeeded"]
        if unfinished:
            reasons.append(f"unfinished_dependencies:{','.join(unfinished)}")
        gpu_type = choose_gpu_type(job, available)
        if gpu_type == "auto":
            reasons.append("no_available_gpu_type")
        if needed > remaining:
            reasons.append(f"user_gpu_cap:{needed}>{remaining}")
        elif gpu_type != "auto" and needed > available.get(gpu_type, 0):
            reasons.append(f"gpu_capacity:{gpu_type}:{needed}>{available.get(gpu_type, 0)}")
        selected = job_id in planned_ids
        if selected and not reasons:
            remaining -= needed
            available[gpu_type] -= needed
        rows.append({
            "id": job_id,
            "exp_id": job.get("exp_id", ""),
            "priority": job.get("priority", ""),
            "selected": selected,
            "gpu_type": gpu_type,
            "gpus": needed,
            "depends_on": dependencies,
            "reasons": [] if selected else reasons,
            "expected_output": job.get("expected_output", ""),
            "check_procedure": job.get("check_procedure", ""),
        })
    return rows


def scale_mem_per_gpu(mem: Any, gpus: int) -> str:
    """Profile/job mem is PER-GPU; total request scales with the GPU count.

    Parses a SLURM mem string ("50G", "16000", "32GB") and multiplies the numeric
    part by the GPU count, preserving the unit. A 1-GPU job is unchanged.
    """
    text = str(mem).strip()
    match = re.match(r"^(\d+)\s*([A-Za-z]*)$", text)
    if not match:
        return text  # leave unrecognized formats untouched
    value = int(match.group(1)) * max(1, int(gpus or 1))
    return f"{value}{match.group(2)}"


def sbatch_args(root: Path, job: dict[str, Any]) -> list[str]:
    log_path = root / str(job.get("log_path") or default_log_path(job))
    body = f"cd {shlex.quote(str(root))} && {str(job['command'])}"
    shell_mode = str(job.get("shell_mode") or "login").lower()
    if shell_mode not in {"login", "plain"}:
        raise HarnessError(f"Unknown shell_mode for {job['id']}: {shell_mode}")
    shell_flag = "-lc" if shell_mode == "login" else "-c"
    gpus = int(job.get("gpus") or 1)
    return [
        "sbatch",
        "--parsable",
        f"--job-name={str(job['slurm_job_name'])}",
        f"--partition={str(job['partition'])}",
        f"--nodelist={str(job['node'])}",
        f"--gres=gpu:{gpus}",
        f"--mem={scale_mem_per_gpu(job['mem'], gpus)}",
        f"--cpus-per-task={int(job.get('cpus') or 8) * gpus}",
        f"--output={str(log_path)}",
        f"--error={str(log_path)}",
        "--open-mode=append",
        f"--wrap=bash {shell_flag} {shlex.quote(body)}",
    ]


def launch_command(root: Path, job: dict[str, Any]) -> str:
    log_path = root / str(job.get("log_path") or default_log_path(job))
    return " ".join([
        "mkdir",
        "-p",
        shlex.quote(str(log_path.parent)),
        "&&",
        *(shlex.quote(part) for part in sbatch_args(root, job)),
    ])


def job_output_paths(job: dict[str, Any]) -> list[str]:
    return [
        value
        for value in (
            str(job.get("log_path") or default_log_path(job)),
            str(job.get("result_path") or ""),
            str(job.get("expected_output") or ""),
        )
        if value
    ]


def record_gpu_dispatch_plan(root: Path, selected: list[dict[str, Any]], *, action: str) -> None:
    if not selected:
        return
    owners = sorted({str(job.get("owner_agent") or "code_agent") for job in selected})
    owner = owners[0] if len(owners) == 1 else "director"
    outputs = sorted({path for job in selected for path in job_output_paths(job)})
    job_notes = []
    for job in selected:
        job_notes.append(
            (
                f"{job['id']} exp_id={job.get('exp_id', '')} gpu={job.get('gpu_type', '')} "
                f"command={job.get('command', '')} expected_output={job.get('expected_output', '')} "
                f"check_procedure={job.get('check_procedure', '')}"
            ).strip()
        )
    append_agent_event(
        root,
        "gpu_dispatch_plan",
        owner,
        status="running" if action == "execute" else "waiting",
        task=f"GPU scheduler selected {len(selected)} job(s) for {action}.",
        stage="gpu_experiment",
        outputs=outputs,
        notes="; ".join(job_notes),
    )


def agent_status_for_gpu_update(queue: dict[str, Any], owner: str, updated_job_id: str, job_status: str) -> str:
    active_for_owner = [
        job for job in queue.get("jobs", [])
        if str(job.get("id") or "") != updated_job_id
        and str(job.get("owner_agent") or "code_agent") == owner
        and str(job.get("status") or "").lower() in {"queued", "running"}
    ]
    if active_for_owner or job_status == "running":
        return "running"
    if job_status == "succeeded":
        return "waiting"
    if job_status in {"failed", "blocked"}:
        return "blocked"
    return "waiting"


def sync_gpu_agent_status(
    root: Path,
    queue: dict[str, Any],
    job: dict[str, Any],
    *,
    event: str,
    job_status: str,
    note: str,
) -> None:
    owner = str(job.get("owner_agent") or "code_agent")
    job_id = str(job.get("id") or "")
    exp_id = str(job.get("exp_id") or "")
    agent_status = agent_status_for_gpu_update(queue, owner, job_id, job_status)
    task = f"GPU job {job_id} is {job_status} for {exp_id}."
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
        event,
        owner,
        status=agent_status,
        task=task,
        stage="gpu_experiment",
        outputs=outputs,
        notes=note,
    )


def sync_gpu_run_state(
    root: Path,
    queue_after: dict[str, Any],
    updated_job: dict[str, Any],
    *,
    next_status: str,
    note: str,
    event: str,
) -> None:
    exp_id = str(updated_job.get("exp_id") or "")
    if exp_id and next_status in RUN_STATUSES:
        timestamp = now_iso()

        def update_run(data: dict[str, Any]) -> None:
            data["status"] = next_status
            data["owner_agent"] = updated_job.get("owner_agent") or data.get("owner_agent") or "code_agent"
            data["current_step"] = f"GPU job {updated_job['id']} is {next_status}."
            data["gpu_type"] = str(updated_job.get("gpu_type") or data.get("gpu_type") or "").upper()
            data["node"] = str(updated_job.get("node") or data.get("node") or "")
            data["log_path"] = str(updated_job.get("log_path") or data.get("log_path") or "")
            if updated_job.get("slurm_job_name"):
                data["slurm_job_name"] = updated_job["slurm_job_name"]
            if updated_job.get("slurm_job_id"):
                data["slurm_job_id"] = updated_job["slurm_job_id"]
            if updated_job.get("result_path"):
                data["result_path"] = updated_job["result_path"]
            if updated_job.get("expected_output"):
                data["expected_output"] = updated_job["expected_output"]
            if updated_job.get("check_procedure"):
                data["check_procedure"] = updated_job["check_procedure"]
            data["display_summary"] = f"GPU job {updated_job['id']} is {next_status} for {exp_id}."
            if note:
                data["notes"] = note
            if next_status == "succeeded":
                data["next_action"] = (
                    "Analyze why the experiment result improved, regressed, "
                    "or stayed flat; update 03_experiments/"
                    f"{exp_id}/analysis.md, 05_results/experiment_journal.md, "
                    "and 05_results/experiment_journal.csv. Prefer "
                    "scripts.commands.experiments.experiment_complete for the completion ledger."
                )
            if next_status in {"failed", "blocked"}:
                data["next_action"] = (
                    "Diagnose the failed GPU run, inspect logs and expected outputs, "
                    "then record the completed or blocked outcome through experiment_complete."
                )
            data["updated_at"] = timestamp
            if next_status in {"succeeded", "failed", "blocked", "cancelled"}:
                data["finished_at"] = timestamp
            append_run_history(data, event, note or f"job_id={updated_job['id']}")

        mutate_run_state(root, exp_id, update_run)
    sync_gpu_agent_status(
        root,
        queue_after,
        updated_job,
        event=event.replace(":", "_"),
        job_status=next_status,
        note=note or f"GPU job {updated_job['id']} is {next_status}.",
    )


def mark_launched(root: Path, job: dict[str, Any], slurm_job_id: str) -> None:
    timestamp = now_iso()

    def update_queue(queue: dict[str, Any]) -> None:
        for candidate in queue["jobs"]:
            if candidate.get("id") == job["id"]:
                candidate.update({
                    "status": "running",
                    "launcher": "sbatch",
                    "gpu_type": job["gpu_type"],
                    "partition": job["partition"],
                    "node": job["node"],
                    "mem": job["mem"],
                    "cpus": job["cpus"],
                    "tmux_session": job.get("tmux_session", ""),
                    "slurm_job_name": job["slurm_job_name"],
                    "slurm_job_id": slurm_job_id,
                    "updated_at": timestamp,
                })
                return
        raise HarnessError(f"GPU job not found: {job['id']}")

    queue_after = mutate_gpu_queue(root, update_queue)

    def update_run_state(data: dict[str, Any]) -> None:
        data["status"] = "running"
        data["owner_agent"] = job.get("owner_agent") or "code_agent"
        data["current_step"] = f"Running GPU job {job['id']}"
        data["tmux_session"] = job.get("tmux_session", "")
        data["slurm_job_name"] = job["slurm_job_name"]
        data["slurm_job_id"] = slurm_job_id
        data["gpu_type"] = job["gpu_type"].upper()
        data["node"] = job["node"]
        data["log_path"] = job.get("log_path", "")
        if job.get("result_path"):
            data["result_path"] = job["result_path"]
        if job.get("expected_output"):
            data["expected_output"] = job["expected_output"]
        if job.get("check_procedure"):
            data["check_procedure"] = job["check_procedure"]
        data["display_summary"] = f"GPU job {job['id']} is running for {job['exp_id']}."
        data["started_at"] = data.get("started_at") or timestamp
        data["updated_at"] = timestamp
        append_run_history(data, "gpu_launch", f"sbatch_job_id={slurm_job_id} slurm_job={job['slurm_job_name']}")

    mutate_run_state(root, job["exp_id"], update_run_state)
    launched_job = dict(job)
    launched_job["slurm_job_id"] = slurm_job_id
    sync_gpu_agent_status(
        root,
        queue_after,
        launched_job,
        event="gpu_launch",
        job_status="running",
        note=f"Launched GPU job {job['id']} with scheduler job id {slurm_job_id}.",
    )
    refresh_report_index(root)


def execute_launch(root: Path, job: dict[str, Any]) -> None:
    executable = shutil.which("sbatch")
    if not executable:
        raise HarnessError("sbatch is required for --execute.")
    log_path = root / str(job.get("log_path") or default_log_path(job))
    log_path.parent.mkdir(parents=True, exist_ok=True)
    argv = sbatch_args(root, job)
    argv[0] = executable
    result = subprocess.run(argv, cwd=root, text=True, capture_output=True)
    if result.returncode != 0:
        raise HarnessError(result.stderr.strip() or f"launch failed for {job['id']}")
    output = result.stdout.strip().splitlines()
    slurm_job_id = output[-1].split(";")[0].strip() if output else ""
    if not slurm_job_id:
        raise HarnessError(f"sbatch did not return a job id for {job['id']}")
    mark_launched(root, job, slurm_job_id)


def print_status(status: dict[str, Any], queue: dict[str, Any]) -> None:
    queued = len([job for job in queue.get("jobs", []) if job.get("status") == "queued"])
    running = len([job for job in queue.get("jobs", []) if job.get("status") == "running"])
    print(f"profile_enabled: {str(status.get('profile_enabled', False)).lower()}")
    print(f"own_gpus: {status['own_gpus']}/{status['max_user_gpus']}")
    print(f"remaining_user_slots: {status['remaining_user_slots']}")
    print("available_gpus: " + ", ".join(f"{key}={value}" for key, value in status["available_gpus"].items()))
    print(f"queue: queued={queued}, running={running}")
    for warning in status["warnings"]:
        print(f"warning: {warning}", file=sys.stderr)


def refresh_gpu_lifecycle(root: Path, queue: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    squeue_text = read_optional(args.squeue_output)
    if not squeue_text and not args.squeue_output:
        squeue_text, _ = run_capture(workspace_gpu_command("queue_status"))
    scheduler_rows = parse_squeue_rows(squeue_text)
    scheduler_names = {row.get("name", ""): row for row in scheduler_rows.values() if row.get("name")}
    diagnostics: list[dict[str, Any]] = []
    pending_updates: list[tuple[str, str, str]] = []
    for job in queue.get("jobs", []):
        job_id = str(job.get("id") or "")
        current_status = str(job.get("status") or "").lower()
        if current_status not in {"queued", "running"}:
            continue
        slurm_job_id = str(job.get("slurm_job_id") or "")
        slurm_job_name = str(job.get("slurm_job_name") or "")
        scheduler_row = scheduler_rows.get(slurm_job_id) if slurm_job_id else None
        scheduler_row = scheduler_row or scheduler_names.get(slurm_job_name)
        if scheduler_row:
            scheduler_state = str(scheduler_row.get("state") or "")
            next_status = scheduler_state_to_status(scheduler_state)
            diagnostics.append({
                "id": job_id,
                "exp_id": job.get("exp_id", ""),
                "current_status": current_status,
                "scheduler_state": scheduler_state,
                "next_status": next_status,
                "action": "sync" if next_status != current_status else "heartbeat",
            })
            if args.write:
                pending_updates.append((job_id, next_status, f"Scheduler refresh saw state {scheduler_state}."))
        elif current_status == "running":
            diagnostics.append({
                "id": job_id,
                "exp_id": job.get("exp_id", ""),
                "current_status": current_status,
                "scheduler_state": "missing",
                "next_status": args.mark_missing or current_status,
                "action": "mark_missing" if args.mark_missing else "needs_manual_check",
            })
            if args.write and args.mark_missing:
                pending_updates.append((job_id, args.mark_missing, "Scheduler refresh no longer sees this running job."))
        else:
            diagnostics.append({
                "id": job_id,
                "exp_id": job.get("exp_id", ""),
                "current_status": current_status,
                "scheduler_state": "not_submitted",
                "next_status": current_status,
                "action": "queued_waiting",
            })

    updated_jobs: list[dict[str, Any]] = []
    queue_after = queue
    for job_id, next_status, note in pending_updates:
        updated_job: dict[str, Any] = {}

        def update_job(
            data: dict[str, Any],
            *,
            job_id: str = job_id,
            next_status: str = next_status,
            note: str = note,
        ) -> None:
            nonlocal updated_job
            for candidate in data["jobs"]:
                if candidate.get("id") != job_id:
                    continue
                candidate["status"] = next_status
                candidate["notes"] = note
                candidate["updated_at"] = now_iso()
                updated_job = dict(candidate)
                return
            raise HarnessError(f"GPU job not found: {job_id}")

        queue_after = mutate_gpu_queue(root, update_job)
        sync_gpu_run_state(
            root,
            queue_after,
            updated_job,
            next_status=next_status,
            note=note,
            event=f"gpu_refresh:{next_status}",
        )
        updated_jobs.append(updated_job)
    if args.write and updated_jobs:
        refresh_report_index(root)
    return {
        "project": root.name,
        "write": bool(args.write),
        "updated_jobs": updated_jobs,
        "diagnostics": diagnostics,
    }


def main() -> int:
    args = parse_args()
    try:
        if not GPU_PROFILES:
            raise HarnessError(
                "no GPU profiles are configured (the workspace profile is missing or invalid); "
                "run 'python -m scripts.commands.release.workspace_profile validate' and fix "
                "config/workspace_profile.local.json before scheduling GPU jobs."
            )
        root = project_root(args.project)
        if args.action == "init":
            path = gpu_queue_path(root)
            if path.exists():
                queue = load_gpu_queue(root)
            else:
                queue = default_gpu_queue(args.project)
                write_gpu_queue(root, queue)
            refresh_report_index(root)
            print(f"gpu jobs: {len(queue['jobs'])}")
            return 0

        if args.action == "add":
            job = default_job_fields(args)
            if job["gpus"] < 1:
                raise HarnessError("--gpus must be positive.")

            def add_job(queue: dict[str, Any]) -> None:
                if any(existing.get("id") == job["id"] for existing in queue["jobs"]):
                    raise HarnessError(f"GPU job already exists: {job['id']}")
                queue["jobs"].append(job)

            queue_after = mutate_gpu_queue(root, add_job)
            sync_gpu_agent_status(
                root,
                queue_after,
                job,
                event="gpu_add",
                job_status="queued",
                note=(
                    f"Queued GPU job {job['id']} with command, expected output, "
                    "and check procedure recorded in state/gpu_experiment_queue.json."
                ),
            )
            refresh_report_index(root)
            print(f"added gpu job: {job['id']}")
            return 0

        if args.action == "list":
            queue = load_gpu_queue(root)
            jobs = [
                job for job in queue["jobs"]
                if not args.status or job.get("status") == args.status
            ]
            if args.json:
                job_status = gpu_job_status_by_id(queue)
                print(json.dumps(
                    {
                        "project": args.project,
                        "jobs": [
                            gpu_job_with_readiness(job, job_status)
                            for job in jobs
                        ],
                    },
                    indent=2,
                    ensure_ascii=False,
                ))
                return 0
            for job in jobs:
                print(f"{job['id']}\t{job['status']}\t{job.get('priority', '')}\t{job.get('gpu_type', '')}\t{job.get('exp_id', '')}")
            return 0

        if args.action == "update":
            updated_job: dict[str, Any] = {}

            def update_job(queue: dict[str, Any]) -> None:
                nonlocal updated_job
                for job in queue["jobs"]:
                    if job.get("id") != args.id:
                        continue
                    if args.status:
                        job["status"] = args.status
                    if args.note is not None:
                        job["notes"] = args.note
                    if args.result_path is not None:
                        job["result_path"] = args.result_path
                    if args.expected_output is not None:
                        job["expected_output"] = args.expected_output
                    if args.check_procedure is not None:
                        job["check_procedure"] = args.check_procedure
                    job["updated_at"] = now_iso()
                    updated_job = dict(job)
                    return
                raise HarnessError(f"GPU job not found: {args.id}")

            queue_after = mutate_gpu_queue(root, update_job)
            next_status = str(updated_job.get("status") or "").lower()
            metadata_changed = any(
                value is not None
                for value in (args.note, args.result_path, args.expected_output, args.check_procedure)
            )
            if next_status and (args.status or metadata_changed):
                sync_gpu_run_state(
                    root,
                    queue_after,
                    updated_job,
                    event=f"gpu_update:{next_status}",
                    next_status=next_status,
                    note=args.note or f"GPU job {updated_job['id']} is {next_status}.",
                )
            refresh_report_index(root)
            print(f"updated gpu job: {args.id}")
            return 0

        queue = load_gpu_queue(root)
        status = gpu_status(args, queue)
        if args.action == "status":
            print_status(status, queue)
            return 0

        if args.action == "refresh":
            payload = refresh_gpu_lifecycle(root, queue, args)
            if args.json:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                for item in payload["diagnostics"]:
                    print(
                        "refresh\t{id}\t{current_status}\t{scheduler_state}\t{next_status}\t{action}".format(
                            **item
                        )
                    )
                if not payload["diagnostics"]:
                    print("no queued or running GPU jobs")
            return 0

        planned = plan_jobs(queue, status)
        plan_diagnostics = gpu_plan_diagnostics(queue, status, planned)
        if args.action == "plan":
            if args.json:
                print(json.dumps({"status": status, "planned_jobs": planned, "plan_diagnostics": plan_diagnostics}, indent=2))
            else:
                print_status(status, queue)
                for job in planned:
                    print(f"plan\t{job['id']}\t{job['exp_id']}\t{job['gpu_type']}\t{job['slurm_job_name']}")
                if plan_diagnostics:
                    print("diagnostics:")
                    for item in plan_diagnostics:
                        state = "selected" if item.get("selected") else "excluded"
                        reasons = ",".join(item.get("reasons") or []) or "-"
                        print(f"diagnostic\t{item['id']}\t{state}\t{reasons}\t{item.get('gpu_type', '')}\t{item.get('gpus', '')}")
            return 0

        if args.action in {"launch", "dispatch"}:
            if (
                args.execute
                and not status.get("profile_enabled", False)
                and not args.allow_disabled_profile
            ):
                raise HarnessError(
                    "GPU execution is disabled in config/workspace_profile.local.json. "
                    "Set gpu.enabled=true after configuring local scheduler rules, or pass "
                    "--allow-disabled-profile for an explicit test fixture override."
                )
            max_parallel = int(getattr(args, "max_parallel", 0))
            if args.action == "launch":
                launch_id = getattr(args, "id", None)
                if launch_id:
                    selected = select_jobs_for_dispatch(planned, launch_id, 1, plan_diagnostics)
                elif getattr(args, "all_planned", False):
                    selected = planned
                elif len(planned) > 1:
                    raise HarnessError(
                        "launch is single-job by default and multiple jobs are planned. "
                        "Use dispatch for parallel batches, launch --id <job_id> for one job, "
                        "or launch --all-planned for an explicit compatibility override."
                    )
                else:
                    selected = planned
            else:
                selected_ids = getattr(args, "ids", None)
                selected = select_jobs_for_dispatch(planned, selected_ids, max_parallel, plan_diagnostics)
            assert_no_dispatch_collisions(root, selected, queue)
            if args.action == "dispatch" and args.json:
                if args.execute:
                    raise HarnessError("dispatch --json is only supported for dry-run dispatch without --execute.")
                print(json.dumps(
                    {
                        "status": status,
                        "selected_jobs": selected,
                        "plan_diagnostics": plan_diagnostics,
                        "launch_commands": [
                            launch_command(root, job)
                            for job in selected
                        ],
                    },
                    indent=2,
                    ensure_ascii=False,
                ))
                return 0
            if args.execute:
                record_gpu_dispatch_plan(root, selected, action="execute")
            for job in selected:
                command = launch_command(root, job)
                if not args.execute:
                    print(command)
                else:
                    execute_launch(root, job)
                    print(f"launched: {job['id']}")
            if not selected:
                print("no launchable GPU jobs")
            if not args.execute and args.action == "dispatch":
                for item in plan_diagnostics:
                    if item.get("selected"):
                        continue
                    reasons = ",".join(item.get("reasons") or []) or "-"
                    print(f"diagnostic\t{item['id']}\texcluded\t{reasons}")
            return 0

        raise HarnessError(f"Unknown command: {args.action}")
    except (HarnessError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
