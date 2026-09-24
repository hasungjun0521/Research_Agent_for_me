#!/usr/bin/env python3
"""Manage per-project baseline and prior-code registry files."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from scripts.harness.report_lifecycle import sync_report_lifecycle
from scripts.harness.state import (
    BASELINE_STATUSES,
    HarnessError,
    baseline_registry_path,
    default_baseline_registry,
    load_baseline_registry,
    mutate_baseline_registry,
    now_iso,
    project_root,
    split_values,
    validate_baseline_registry_doc,
    write_baseline_registry,
)

COMMAND_KINDS = ("inspect", "setup", "run", "evaluate")


def is_local_absolute_reference(value: str) -> bool:
    stripped = str(value or "").strip()
    if not stripped:
        return False
    return stripped.startswith(("/", "~")) or (
        len(stripped) >= 3 and stripped[1] == ":" and stripped[2] in {"\\", "/"}
    )


def reject_local_absolute_reference(value: str, label: str) -> None:
    if is_local_absolute_reference(value):
        raise HarnessError(
            f"{label} must not be a local absolute path. Store private paths in "
            "config/workspace_profile.local.json and use project-relative paths in the registry."
        )


def reject_local_absolute_values(values: list[str] | None, label: str) -> None:
    for value in split_values(values):
        reject_local_absolute_reference(value, label)


def setup_subparsers(subparsers: argparse._SubParsersAction) -> None:
    lib = subparsers.add_parser("lib", help="Manage 08_baselines/baseline_registry.json.")
    lib_sub = lib.add_subparsers(dest="lib_command", required=True)

    init = lib_sub.add_parser("init", help="Create baseline_registry.json if missing.")
    init.add_argument("--project", required=True)

    add = lib_sub.add_parser("add", help="Add a baseline entry.")
    add_common(add, require_name=True)

    update = lib_sub.add_parser("update", help="Update an existing baseline entry.")
    add_common(update, require_name=False)

    list_cmd = lib_sub.add_parser("list", help="List registered baselines.")
    list_cmd.add_argument("--project", required=True)

    validate = lib_sub.add_parser("validate", help="Validate the baseline registry.")
    validate.add_argument("--project", required=True)
    validate.add_argument("--strict", action="store_true", help="Fail when validation warnings are present.")


def add_common(parser: argparse.ArgumentParser, *, require_name: bool) -> None:
    parser.add_argument("--project", required=True)
    parser.add_argument("--id", required=True, help="Stable baseline id, e.g. baseline_001 or dpp_lstm.")
    parser.add_argument("--name", required=require_name)
    parser.add_argument("--status", choices=sorted(BASELINE_STATUSES))
    parser.add_argument("--paper")
    parser.add_argument("--citation-key")
    parser.add_argument("--repo-url")
    parser.add_argument("--source-path")
    parser.add_argument("--local-snapshot")
    parser.add_argument("--working-dir")
    parser.add_argument("--license")
    parser.add_argument("--repo-commit")
    parser.add_argument("--clone-command")
    parser.add_argument("--structure-report")
    parser.add_argument("--adapter-path")
    parser.add_argument("--smoke-script")
    parser.add_argument("--structure-score", type=int)
    parser.add_argument("--method-family")
    parser.add_argument("--role", dest="expected_role")
    parser.add_argument("--owner", dest="owner_agent")
    parser.add_argument("--note", dest="reproduction_notes")
    parser.add_argument("--known-difference", dest="known_differences")
    parser.add_argument("--repo-search-query", action="append", dest="repo_search_queries", help="Repo discovery query. Repeat or comma-separate.")
    parser.add_argument("--dataset", action="append", dest="datasets", help="Dataset. Repeat or comma-separate.")
    parser.add_argument("--dataset-path", action="append", dest="dataset_paths", help="Dataset path. Repeat or comma-separate.")
    parser.add_argument("--metric", action="append", dest="metrics", help="Metric. Repeat or comma-separate.")
    parser.add_argument("--config", action="append", dest="config_paths", help="Config path. Repeat or comma-separate.")
    parser.add_argument("--result-path", action="append", dest="result_paths", help="Result path. Repeat or comma-separate.")
    parser.add_argument("--evidence", action="append", dest="evidence_files", help="Evidence file. Repeat or comma-separate.")
    parser.add_argument("--inspect-command", action="append", dest="inspect_commands", help="Command for inspecting source.")
    parser.add_argument("--setup-command", action="append", dest="setup_commands", help="Command for installing or preparing.")
    parser.add_argument("--run-command", action="append", dest="run_commands", help="Command for running the baseline.")
    parser.add_argument("--eval-command", action="append", dest="evaluate_commands", help="Command for evaluating outputs.")


def find_baseline(registry: dict[str, Any], baseline_id: str) -> dict[str, Any]:
    for baseline in registry["baselines"]:
        if baseline.get("id") == baseline_id:
            return baseline
    raise HarnessError(f"Baseline not found: {baseline_id}")


def empty_baseline(baseline_id: str) -> dict[str, Any]:
    return {
        "id": baseline_id,
        "name": "",
        "paper": "",
        "citation_key": "",
        "repo_url": "",
        "source_path": "",
        "local_snapshot": "",
        "working_dir": "",
        "license": "",
        "repo_commit": "",
        "clone_command": "",
        "structure_report": "",
        "adapter_path": "",
        "smoke_script": "",
        "structure_score": 0,
        "method_family": "",
        "expected_role": "baseline",
        "status": "candidate",
        "datasets": [],
        "dataset_paths": [],
        "metrics": [],
        "config_paths": [],
        "commands": {
            "inspect": [],
            "setup": [],
            "run": [],
            "evaluate": [],
        },
        "result_paths": [],
        "reproduction_notes": "",
        "known_differences": "",
        "evidence_files": [],
        "repo_search_queries": [],
        "owner_agent": "",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }


def append_unique(target: list[str], values: list[str] | None) -> None:
    for value in values or []:
        if value not in target:
            target.append(value)


def append_split_values(baseline: dict[str, Any], field: str, values: list[str] | None) -> None:
    if values is None:
        return
    current = baseline.setdefault(field, [])
    if not isinstance(current, list):
        raise HarnessError(f"Baseline {baseline.get('id')} field {field} must be a list.")
    append_unique(current, split_values(values))


def append_commands(baseline: dict[str, Any], kind: str, values: list[str] | None) -> None:
    if values is None:
        return
    commands = baseline.setdefault("commands", {})
    if not isinstance(commands, dict):
        raise HarnessError(f"Baseline {baseline.get('id')} commands must be an object.")
    for command_kind in COMMAND_KINDS:
        commands.setdefault(command_kind, [])
    target = commands[kind]
    if not isinstance(target, list):
        raise HarnessError(f"Baseline {baseline.get('id')} commands.{kind} must be a list.")
    append_unique(target, [value.strip() for value in values if value.strip()])


def baseline_output_paths(baseline: dict[str, Any]) -> list[str]:
    outputs = ["08_baselines/baseline_registry.json"]

    def remember(value: str) -> None:
        if value and value not in outputs:
            outputs.append(value)

    for field in ("source_path", "local_snapshot", "structure_report", "adapter_path", "smoke_script"):
        remember(str(baseline.get(field) or ""))
    for field in ("dataset_paths", "config_paths", "result_paths", "evidence_files"):
        for value in baseline.get(field) or []:
            remember(str(value))
    return outputs


def sync_baseline_library_lifecycle(root, baseline: dict[str, Any], event_type: str, action: str) -> None:
    owner = str(baseline.get("owner_agent") or "code_agent")
    baseline_id = str(baseline.get("id") or "")
    status = str(baseline.get("status") or "candidate")
    task = f"{action} baseline {baseline_id} ({status})."
    outputs = baseline_output_paths(baseline)
    notes = (
        "Baseline registry changed. Read 08_baselines/baseline_registry.json "
        "before planning comparisons, adapters, or reproduced-result claims."
    )
    try:
        sync_report_lifecycle(
            root,
            agent=owner,
            event_type=event_type,
            status="waiting",
            task=task,
            outputs=outputs,
            notes=notes,
            refresh_report=False,
        )
    except HarnessError as exc:
        if "Agent not found" not in str(exc):
            raise
        sync_report_lifecycle(
            root,
            agent="code_agent",
            event_type=event_type,
            status="waiting",
            task=task,
            outputs=outputs,
            notes=f"{notes} Requested owner {owner} was not found; recorded under code_agent.",
            refresh_report=False,
        )


def apply_args(baseline: dict[str, Any], args: argparse.Namespace) -> None:
    for attr in (
        "repo_url",
        "source_path",
        "local_snapshot",
        "working_dir",
        "structure_report",
        "adapter_path",
        "smoke_script",
    ):
        reject_local_absolute_reference(getattr(args, attr, "") or "", f"--{attr.replace('_', '-')}")
    for attr in ("dataset_paths", "config_paths", "result_paths", "evidence_files"):
        reject_local_absolute_values(getattr(args, attr, None), f"--{attr.replace('_', '-')}")
    for attr in (
        "name",
        "paper",
        "citation_key",
        "repo_url",
        "source_path",
        "local_snapshot",
        "working_dir",
        "license",
        "repo_commit",
        "clone_command",
        "structure_report",
        "adapter_path",
        "smoke_script",
        "structure_score",
        "method_family",
        "expected_role",
        "status",
        "owner_agent",
        "reproduction_notes",
        "known_differences",
    ):
        value = getattr(args, attr, None)
        if value is not None:
            baseline[attr] = value

    for field in ("datasets", "dataset_paths", "metrics", "config_paths", "result_paths", "evidence_files", "repo_search_queries"):
        append_split_values(baseline, field, getattr(args, field, None))

    append_commands(baseline, "inspect", getattr(args, "inspect_commands", None))
    append_commands(baseline, "setup", getattr(args, "setup_commands", None))
    append_commands(baseline, "run", getattr(args, "run_commands", None))
    append_commands(baseline, "evaluate", getattr(args, "evaluate_commands", None))
    baseline["updated_at"] = now_iso()


def run_lib(args: argparse.Namespace) -> int:
    root = project_root(args.project)
    cmd = getattr(args, "lib_command", "")
    if not cmd:
        # handle direct calls through the legacy wrapper
        cmd = getattr(args, "command", "")

    if cmd == "init":
        path = baseline_registry_path(root)
        if path.exists():
            registry = load_baseline_registry(root)
        else:
            registry = default_baseline_registry(args.project)
            write_baseline_registry(root, registry)
        print(f"baselines: {len(registry['baselines'])}")
        return 0

    if cmd == "add":
        added_baseline: dict[str, Any] = {}

        def add_baseline(registry: dict[str, Any]) -> None:
            nonlocal added_baseline
            if any(baseline.get("id") == args.id for baseline in registry["baselines"]):
                raise HarnessError(f"Baseline already exists: {args.id}")
            baseline = empty_baseline(args.id)
            apply_args(baseline, args)
            registry["baselines"].append(baseline)
            added_baseline = dict(baseline)

        mutate_baseline_registry(root, add_baseline)
        sync_baseline_library_lifecycle(root, added_baseline, "baseline_library_add", "Registered")
        print(f"added: {args.id}")
        return 0

    if cmd == "update":
        updated_baseline: dict[str, Any] = {}

        def update_baseline(registry: dict[str, Any]) -> None:
            nonlocal updated_baseline
            baseline = find_baseline(registry, args.id)
            apply_args(baseline, args)
            updated_baseline = dict(baseline)

        mutate_baseline_registry(root, update_baseline)
        sync_baseline_library_lifecycle(root, updated_baseline, "baseline_library_update", "Updated")
        print(f"updated: {args.id}")
        return 0

    if cmd == "list":
        registry = load_baseline_registry(root)
        for baseline in registry["baselines"]:
            print(
                f"{baseline['id']}\t{baseline.get('status', '')}\t"
                f"{baseline.get('name', '')}\t{baseline.get('paper', '')}"
            )
        return 0

    if cmd == "validate":
        registry = load_baseline_registry(root)
        warnings = validate_baseline_registry_doc(registry)
        if warnings:
            print("warnings:")
            for warning in warnings:
                print(f"- {warning}")
            if args.strict:
                return 1
        print(f"valid baseline registry: {args.project}")
        return 0

    raise HarnessError(f"Unknown lib command: {cmd}")


def main() -> int:
    from scripts.commands.baselines.baselines import main as baselines_main
    if len(sys.argv) > 1 and sys.argv[1] in {"init", "add", "update", "list", "validate"}:
        sys.argv.insert(1, "lib")
    elif len(sys.argv) < 2 or (len(sys.argv) >= 2 and sys.argv[1] not in {"lib", "intake", "compare", "sandbox", "discovery"}):
        sys.argv.insert(1, "lib")
    return baselines_main()

if __name__ == "__main__":
    raise SystemExit(main())
