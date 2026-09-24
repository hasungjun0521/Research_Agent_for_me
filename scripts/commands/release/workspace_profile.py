#!/usr/bin/env python3
"""CLI for inspecting or initializing the machine-local workspace profile.

The profile core (loading, validation, caching, accessors) lives in
scripts/harness/workspace_profile.py so the harness layer never imports
command modules. This module keeps the CLI plus backward-compatible
re-exports for existing importers.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys

from scripts.harness.workspace_profile import (  # noqa: F401 - re-exported for compatibility
    DEFAULT_PROFILE,
    ProfileError,
    deep_merge,
    load_json_file,
    load_workspace_profile,
    profile_paths,
    public_workspace_profile,
    repo_root,
    validate_profile,
    workspace_agent_limit_enabled,
    workspace_agent_limit_json_paths,
    workspace_agent_limit_status_command,
    workspace_agent_limit_threshold,
    workspace_agent_limit_timeout,
    workspace_agent_limits,
    workspace_agent_runner_command,
    workspace_agent_runner_default_profile,
    workspace_agent_runner_profiles,
    workspace_gpu_auto_order,
    workspace_gpu_command,
    workspace_gpu_default_type,
    workspace_gpu_enabled,
    workspace_gpu_max_user_gpus,
    workspace_gpu_profiles,
    workspace_gpu_types,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inspect or initialize the workspace profile.")
    sub = parser.add_subparsers(dest="command", required=True)
    show = sub.add_parser("show", help="Print the merged workspace profile.")
    show.add_argument("--json", action="store_true")
    sub.add_parser("validate", help="Validate the merged workspace profile.")
    init = sub.add_parser("init-local", help="Create config/workspace_profile.local.json from the example.")
    init.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        example_path, local_path = profile_paths()
        if args.command == "init-local":
            if local_path.exists() and not args.force:
                raise ProfileError(f"{local_path} already exists; pass --force to overwrite.")
            local_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(example_path, local_path)
            print(local_path.relative_to(repo_root()).as_posix())
            return 0

        profile = load_workspace_profile()
        if args.command == "validate":
            print("workspace profile OK")
            for warning in profile.get("_meta", {}).get("warnings", []):
                print(f"warning: {warning}", file=sys.stderr)
            return 0
        if args.command == "show":
            if args.json:
                print(json.dumps(profile, indent=2, ensure_ascii=False))
            else:
                display = profile.get("display", {})
                gpu = profile.get("gpu", {})
                print(f"summary_language: {display.get('summary_language', 'en')}")
                print(f"preferred_language: {profile.get('agent_output', {}).get('preferred_language', 'en')}")
                runners = public_workspace_profile().get("agent_runners", {})
                runner_names = ", ".join(sorted(runners.get("profiles", {}).keys())) or "none"
                print(f"agent_runner_default: {runners.get('default_profile') or 'none'}")
                print(f"agent_runner_profiles: {runner_names}")
                print(f"gpu_scheduler: {gpu.get('scheduler', 'slurm')}")
                print(f"max_user_gpus: {gpu.get('max_user_gpus', 1)}")
                print("gpu_types: " + ", ".join(sorted(workspace_gpu_types() - {"auto"})))
            return 0
        raise ProfileError(f"Unknown command: {args.command}")
    except ProfileError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
