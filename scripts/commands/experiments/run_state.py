#!/usr/bin/env python3
"""Manage per-experiment 03_experiments/<exp_id>/run_state.json."""

from __future__ import annotations

import argparse
import sys

from scripts.harness.state import (
    RUN_STATUSES,
    append_agent_event,
    append_run_history,
    mutate_run_state,
    now_iso,
    project_root,
    update_agent_status,
)


def setup_subparsers(subparsers: argparse._SubParsersAction) -> None:
    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--project", required=True)
        p.add_argument("--exp-id", required=True)
        p.add_argument("--step", help="Current step or task.")
        p.add_argument("--note", default="")
        p.add_argument("--owner", dest="owner_agent")
        p.add_argument("--tmux-session")
        p.add_argument("--slurm-job-name")
        p.add_argument("--slurm-job-id")
        p.add_argument("--gpu-type")
        p.add_argument("--node")
        p.add_argument("--log-path")
        p.add_argument("--result-path")
        p.add_argument("--expected-output")
        p.add_argument("--check-procedure")
        p.add_argument("--display-summary", help="Human-readable run summary for file-state/status surfaces.")
        p.add_argument("--judgement", help="Current interpretation or pass/fail judgement.")
        p.add_argument("--next-action", help="Plain-language follow-up for this run.")

    state = subparsers.add_parser("state", help="Manage experiment run state.")
    state_sub = state.add_subparsers(dest="state_command", required=True)

    init = state_sub.add_parser("init", help="Create run_state.json if missing.")
    add_common(init)

    start = state_sub.add_parser("start", help="Mark run as running.")
    add_common(start)

    heartbeat = state_sub.add_parser("heartbeat", help="Refresh run heartbeat.")
    add_common(heartbeat)

    finish = state_sub.add_parser("finish", help="Finish a run.")
    add_common(finish)
    finish.add_argument("--status", required=True, choices=["succeeded", "failed", "blocked", "cancelled"])

    set_status = state_sub.add_parser("set", help="Set an explicit run status.")
    add_common(set_status)
    set_status.add_argument("--status", required=True, choices=sorted(RUN_STATUSES))


def apply_fields(data: dict, args: argparse.Namespace) -> None:
    for attr in (
        "owner_agent", "tmux_session", "slurm_job_name", "slurm_job_id", "gpu_type", "node", "log_path", "result_path", "expected_output", "check_procedure", "display_summary", "judgement", "next_action",
    ):
        value = getattr(args, attr, None)
        if value is not None:
            data[attr] = value
    if getattr(args, "step", None) is not None:
        data["current_step"] = args.step


def agent_status_for_run_status(status: str) -> str:
    if status in {"running", "queued"}:
        return "running"
    if status in {"failed", "blocked"}:
        return "blocked"
    return "waiting"


def output_paths(data: dict) -> list[str]:
    return [str(data.get(f) or "") for f in ("log_path", "result_path", "expected_output") if data.get(f)]


def sync_agent_lifecycle(root, args: argparse.Namespace, data: dict) -> None:
    owner = str(data.get("owner_agent") or "code_agent")
    run_status = str(data.get("status") or "planned").lower()
    agent_status = agent_status_for_run_status(run_status)
    summary = str(data.get("display_summary") or data.get("current_step") or f"Experiment {args.exp_id} is {run_status}.")
    notes = getattr(args, "note", "") or str(data.get("judgement") or data.get("next_action") or "")
    outputs = output_paths(data)
    update_agent_status(root, owner, agent_status, task=summary, stage="experiment_run", outputs=outputs, notes=notes, append_note=True)
    cmd = getattr(args, "state_command", "") or "update"
    append_agent_event(root, f"run_state_{cmd}", owner, status=agent_status, task=summary, stage="experiment_run", outputs=outputs, notes=notes)


def run_state(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    timestamp = now_iso()
    cmd = getattr(args, "state_command", "")

    def mutate(data: dict) -> None:
        apply_fields(data, args)
        if cmd == "start":
            data["status"] = "running"
            data["started_at"] = data.get("started_at") or timestamp
            data["finished_at"] = ""
            append_run_history(data, "start", getattr(args, "note", ""))
        elif cmd == "heartbeat":
            data["status"] = "running"
            data["finished_at"] = ""
            data["heartbeat_count"] = int(data.get("heartbeat_count") or 0) + 1
            append_run_history(data, "heartbeat", getattr(args, "note", ""))
        elif cmd == "finish":
            data["status"] = getattr(args, "status", "succeeded")
            data["finished_at"] = timestamp
            append_run_history(data, data["status"], getattr(args, "note", ""))
        elif cmd == "set":
            status = getattr(args, "status", "planned")
            data["status"] = status
            if status in {"planned", "queued", "running"}:
                data["finished_at"] = ""
            append_run_history(data, f"set:{status}", getattr(args, "note", ""))
        elif cmd == "init":
            append_run_history(data, "init", getattr(args, "note", ""))
        data["updated_at"] = timestamp

    data = mutate_run_state(root, args.exp_id, mutate)
    sync_agent_lifecycle(root, args, data)
    print(f"{args.project}:{args.exp_id} -> {data['status']}")
    return 0


def main() -> int:
    from scripts.commands.experiments.experiments import main as experiments_main
    if len(sys.argv) > 1 and sys.argv[1] in {"init", "start", "heartbeat", "finish", "set"}:
        sys.argv.insert(1, "state")
    elif len(sys.argv) < 2 or (len(sys.argv) >= 2 and sys.argv[1] != "state"):
        sys.argv.insert(1, "state")
    return experiments_main()

if __name__ == "__main__":
    raise SystemExit(main())
