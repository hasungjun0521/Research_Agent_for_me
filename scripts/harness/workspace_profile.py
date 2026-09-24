"""Machine-local workspace profile loading, validation, and accessors.

This is the harness-layer core. The CLI lives in
scripts/commands/release/workspace_profile.py, which re-exports these names
for backward compatibility. Harness modules must import from here so the
foundation never depends on command modules.
"""

from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from scripts.harness.errors import HarnessError
from scripts.harness.paths import repo_root as harness_repo_root

DEFAULT_PROFILE: dict[str, Any] = {
    "schema_version": 1,
    "display": {
        "summary_language": "en",
        "top_summary_labels": {
            "work": "What happened this instruction",
            "result": "Result analysis",
            "next": "Next action",
        },
    },
    "agent_output": {
        "preferred_language": "en",
        "plain_language_first": True,
    },
    "agent_limits": {
        "enabled": False,
        "status_command": [],
        "timeout_seconds": 10,
        "handoff_threshold_percent": 5.0,
        "json_paths": {
            "five_hour_remaining_pct": "",
            "weekly_remaining_pct": "",
        },
    },
    "agent_runners": {
        "default_profile": "",
        "profiles": {
            "claude-code": {
                "description": "Configure a verified local Claude Code runner command.",
                "command": [],
                "status_command": [],
                "json_paths": {},
            },
            "codex": {
                "description": "Configure a verified local Codex runner command.",
                "command": [],
                "status_command": [],
                "json_paths": {},
            },
            "gemini": {
                "description": "Configure a verified local Gemini runner command.",
                "command": [],
                "status_command": [],
                "json_paths": {},
            },
        },
    },
    "gpu": {
        "enabled": False,
        "scheduler": "slurm",
        "max_user_gpus": 1,
        "default_gpu_type": "auto",
        "auto_order": ["a100", "a6000", "a5000", "a4000"],
        "profiles": {
            "a100": {"partition": "a100", "node": "node01", "mem": "80G", "cpus": 8},
            "a4000": {"partition": "a4000", "node": "node05", "mem": "16G", "cpus": 8},
            "a5000": {"partition": "a5000", "node": "node04", "mem": "16G", "cpus": 8},
            "a6000": {"partition": "a6000", "node": "node06", "mem": "16G", "cpus": 8},
        },
        "commands": {
            "queue_status": ["squeue", "--me", "-h", "-o", "%i|%j|%T|%b|%D|%R"],
            "node_status": ["scontrol", "show", "node", "{node}", "-o"],
            "launcher": "sbatch",
        },
    },
}


class ProfileError(HarnessError):
    """Raised when the workspace profile is invalid."""


def repo_root() -> Path:
    return harness_repo_root()


def profile_paths(root: Path | None = None) -> tuple[Path, Path]:
    base = root or repo_root()
    return (
        base / "config" / "workspace_profile.example.json",
        base / "config" / "workspace_profile.local.json",
    )


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_json_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProfileError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ProfileError(f"{path} must contain a JSON object.")
    return data


def validate_profile(profile: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    display = profile.get("display", {})
    if not isinstance(display, dict):
        raise ProfileError("display must be an object.")
    language = str(display.get("summary_language") or "en").strip().lower()
    if language not in {"en", "ko"}:
        warnings.append(f"Unknown display.summary_language {language!r}; display summaries will fall back to English.")

    agent_output = profile.get("agent_output", {})
    if not isinstance(agent_output, dict):
        raise ProfileError("agent_output must be an object.")

    agent_limits = profile.get("agent_limits", {})
    if not isinstance(agent_limits, dict):
        raise ProfileError("agent_limits must be an object.")
    enabled = agent_limits.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ProfileError("agent_limits.enabled must be a boolean.")
    status_command = agent_limits.get("status_command", [])
    if not isinstance(status_command, list) or not all(isinstance(item, str) and item.strip() for item in status_command):
        raise ProfileError("agent_limits.status_command must be a list of non-empty strings.")
    if enabled and not status_command:
        raise ProfileError("agent_limits.status_command is required when agent_limits.enabled is true.")
    timeout_seconds = agent_limits.get("timeout_seconds", 10)
    if not isinstance(timeout_seconds, int) or timeout_seconds < 1 or timeout_seconds > 120:
        raise ProfileError("agent_limits.timeout_seconds must be an integer from 1 to 120.")
    threshold = agent_limits.get("handoff_threshold_percent", 5.0)
    if not isinstance(threshold, (int, float)) or threshold < 0 or threshold > 100:
        raise ProfileError("agent_limits.handoff_threshold_percent must be a number from 0 to 100.")
    json_paths = agent_limits.get("json_paths", {})
    if not isinstance(json_paths, dict):
        raise ProfileError("agent_limits.json_paths must be an object.")
    for field in ("five_hour_remaining_pct", "weekly_remaining_pct"):
        value = json_paths.get(field, "")
        if not isinstance(value, str):
            raise ProfileError(f"agent_limits.json_paths.{field} must be a string.")

    agent_runners = profile.get("agent_runners", {})
    if not isinstance(agent_runners, dict):
        raise ProfileError("agent_runners must be an object.")
    default_runner = agent_runners.get("default_profile", "")
    if not isinstance(default_runner, str):
        raise ProfileError("agent_runners.default_profile must be a string.")
    runner_profiles = agent_runners.get("profiles", {})
    if not isinstance(runner_profiles, dict):
        raise ProfileError("agent_runners.profiles must be an object.")
    for name, spec in runner_profiles.items():
        if not isinstance(spec, dict):
            raise ProfileError(f"agent_runners.profiles.{name} must be an object.")
        command = spec.get("command", [])
        if not isinstance(command, list) or not all(isinstance(item, str) and item.strip() for item in command):
            raise ProfileError(f"agent_runners.profiles.{name}.command must be a list of non-empty strings.")
        description = spec.get("description", "")
        if description is not None and not isinstance(description, str):
            raise ProfileError(f"agent_runners.profiles.{name}.description must be a string.")
        if "status_command" in spec:
            sc = spec["status_command"]
            if not isinstance(sc, list) or not all(isinstance(item, str) and item.strip() for item in sc):
                raise ProfileError(f"agent_runners.profiles.{name}.status_command must be a list of non-empty strings.")
        if "timeout_seconds" in spec:
            ts = spec["timeout_seconds"]
            if not isinstance(ts, int) or ts < 1 or ts > 120:
                raise ProfileError(f"agent_runners.profiles.{name}.timeout_seconds must be an integer from 1 to 120.")
        if "json_paths" in spec:
            jp = spec["json_paths"]
            if not isinstance(jp, dict):
                raise ProfileError(f"agent_runners.profiles.{name}.json_paths must be an object.")
    if default_runner and default_runner not in runner_profiles:
        warnings.append(f"agent_runners.default_profile {default_runner!r} is not in agent_runners.profiles.")

    gpu = profile.get("gpu", {})
    if not isinstance(gpu, dict):
        raise ProfileError("gpu must be an object.")
    max_user_gpus = gpu.get("max_user_gpus", 1)
    if not isinstance(max_user_gpus, int) or max_user_gpus < 1:
        raise ProfileError("gpu.max_user_gpus must be a positive integer.")
    profiles = gpu.get("profiles", {})
    if not isinstance(profiles, dict) or not profiles:
        raise ProfileError("gpu.profiles must be a non-empty object.")
    for name, spec in profiles.items():
        if not isinstance(spec, dict):
            raise ProfileError(f"gpu.profiles.{name} must be an object.")
        for field in ("partition", "node", "mem"):
            if not isinstance(spec.get(field), str) or not spec.get(field).strip():
                raise ProfileError(f"gpu.profiles.{name}.{field} must be a non-empty string.")
        cpus = spec.get("cpus")
        if not isinstance(cpus, int) or cpus < 1:
            raise ProfileError(f"gpu.profiles.{name}.cpus must be a positive integer.")
    auto_order = gpu.get("auto_order", [])
    if not isinstance(auto_order, list):
        raise ProfileError("gpu.auto_order must be a list.")
    if not all(isinstance(item, str) for item in auto_order):
        raise ProfileError("gpu.auto_order entries must be strings.")
    unknown = [item for item in auto_order if item not in profiles]
    if unknown:
        warnings.append(f"gpu.auto_order contains unknown profiles: {', '.join(map(str, unknown))}")
    default_gpu_type = str(gpu.get("default_gpu_type") or "auto").lower()
    if default_gpu_type != "auto" and default_gpu_type not in profiles:
        warnings.append(f"gpu.default_gpu_type {default_gpu_type!r} is not in gpu.profiles.")
    return warnings


def _read_profile_bytes(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise ProfileError(f"Cannot read workspace profile {path}: {exc}") from exc


def _parse_profile_bytes(path: Path, raw: bytes | None) -> dict[str, Any]:
    if raw is None:
        return {}
    try:
        data = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ProfileError(f"Invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ProfileError(f"{path} must contain a JSON object.")
    return data


@lru_cache(maxsize=16)
def _cached_workspace_profile(
    example_path: Path,
    example_bytes: bytes | None,
    local_path: Path,
    local_bytes: bytes | None,
) -> dict[str, Any]:
    profile = deep_merge(DEFAULT_PROFILE, _parse_profile_bytes(example_path, example_bytes))
    profile = deep_merge(profile, _parse_profile_bytes(local_path, local_bytes))
    try:
        warnings = validate_profile(profile)
    except ProfileError:
        raise
    except Exception as exc:
        raise ProfileError(f"workspace profile validation failed: {exc}") from exc
    profile["_meta"] = {
        "example_path": example_path.as_posix(),
        "local_path": local_path.as_posix(),
        "local_present": local_bytes is not None,
        "warnings": warnings,
    }
    return profile


def load_workspace_profile(root: Path | None = None) -> dict[str, Any]:
    example_path, local_path = profile_paths(root)
    profile = _cached_workspace_profile(
        example_path,
        _read_profile_bytes(example_path),
        local_path,
        _read_profile_bytes(local_path),
    )
    return copy.deepcopy(profile)


def public_workspace_profile(root: Path | None = None) -> dict[str, Any]:
    profile = load_workspace_profile(root)
    meta = profile.get("_meta", {})
    return {
        "schema_version": profile.get("schema_version", 1),
        "display": profile.get("display", {}),
        "agent_output": profile.get("agent_output", {}),
        "agent_limits": {
            "enabled": profile.get("agent_limits", {}).get("enabled", False),
            "status_command_configured": bool(profile.get("agent_limits", {}).get("status_command")),
            "timeout_seconds": profile.get("agent_limits", {}).get("timeout_seconds", 10),
            "handoff_threshold_percent": profile.get("agent_limits", {}).get("handoff_threshold_percent", 5.0),
        },
        "agent_runners": {
            "default_profile": profile.get("agent_runners", {}).get("default_profile", ""),
            "profiles": {
                str(name): {
                    "description": str(spec.get("description") or ""),
                    "command_configured": bool(spec.get("command")),
                }
                for name, spec in profile.get("agent_runners", {}).get("profiles", {}).items()
                if isinstance(spec, dict)
            },
        },
        "gpu": {
            "enabled": profile.get("gpu", {}).get("enabled", False),
            "scheduler": profile.get("gpu", {}).get("scheduler", "slurm"),
            "max_user_gpus": profile.get("gpu", {}).get("max_user_gpus", 1),
            "default_gpu_type": profile.get("gpu", {}).get("default_gpu_type", "auto"),
            "gpu_types": sorted(workspace_gpu_types() - {"auto"}),
            "auto_order": workspace_gpu_auto_order(),
        },
        "_meta": {
            "local_present": bool(meta.get("local_present")),
            "warnings": meta.get("warnings", []),
        },
    }


def workspace_gpu_profiles() -> dict[str, dict[str, Any]]:
    profile = load_workspace_profile()
    profiles = profile.get("gpu", {}).get("profiles", {})
    return {str(key).lower(): dict(value) for key, value in profiles.items()}


def workspace_gpu_types() -> set[str]:
    return {"auto", *workspace_gpu_profiles().keys()}


def workspace_gpu_auto_order() -> list[str]:
    profile = load_workspace_profile()
    profiles = workspace_gpu_profiles()
    configured = [
        str(item).lower()
        for item in profile.get("gpu", {}).get("auto_order", [])
        if str(item).lower() in profiles
    ]
    remaining = [item for item in profiles if item not in configured]
    return configured + sorted(remaining)


def workspace_gpu_max_user_gpus() -> int:
    return int(load_workspace_profile().get("gpu", {}).get("max_user_gpus") or 1)


def workspace_gpu_enabled() -> bool:
    return bool(load_workspace_profile().get("gpu", {}).get("enabled", False))


def workspace_gpu_default_type() -> str:
    value = str(load_workspace_profile().get("gpu", {}).get("default_gpu_type") or "auto").lower()
    return value if value in workspace_gpu_types() else "auto"


def workspace_agent_limits() -> dict[str, Any]:
    return dict(load_workspace_profile().get("agent_limits", {}))


def workspace_agent_limit_enabled() -> bool:
    return bool(workspace_agent_limits().get("enabled", False))


def workspace_agent_limit_status_command(profile_name: str | None = None) -> list[str]:
    if profile_name:
        profile = workspace_agent_runner_profiles().get(profile_name, {})
        if profile.get("status_command"):
            return [str(item) for item in profile["status_command"]]
    command = workspace_agent_limits().get("status_command", [])
    return [str(item) for item in command]


def workspace_agent_limit_timeout(profile_name: str | None = None) -> int:
    if profile_name:
        profile = workspace_agent_runner_profiles().get(profile_name, {})
        if profile.get("timeout_seconds"):
            return int(profile["timeout_seconds"])
    return int(workspace_agent_limits().get("timeout_seconds") or 10)


def workspace_agent_limit_threshold() -> float:
    return float(workspace_agent_limits().get("handoff_threshold_percent") or 5.0)


def workspace_agent_limit_json_paths(profile_name: str | None = None) -> dict[str, str]:
    if profile_name:
        profile = workspace_agent_runner_profiles().get(profile_name, {})
        if profile.get("json_paths"):
            paths = profile["json_paths"]
            return {str(key): str(value) for key, value in paths.items()}
    paths = workspace_agent_limits().get("json_paths", {})
    if not isinstance(paths, dict):
        return {}
    return {str(key): str(value) for key, value in paths.items()}


def workspace_agent_runner_profiles() -> dict[str, dict[str, Any]]:
    profiles = load_workspace_profile().get("agent_runners", {}).get("profiles", {})
    if not isinstance(profiles, dict):
        return {}
    return {str(name): dict(spec) for name, spec in profiles.items() if isinstance(spec, dict)}


def workspace_agent_runner_default_profile() -> str:
    value = load_workspace_profile().get("agent_runners", {}).get("default_profile", "")
    return str(value or "")


def workspace_agent_runner_command(profile_name: str | None = None) -> list[str]:
    name = str(profile_name or "").strip()
    if not name:
        raise ProfileError("agent runner profile name is required.")
    profiles = workspace_agent_runner_profiles()
    spec = profiles.get(name)
    if not isinstance(spec, dict):
        raise ProfileError(f"Unknown agent runner profile: {name}")
    command = spec.get("command", [])
    if not isinstance(command, list) or not command:
        raise ProfileError(f"agent_runners.profiles.{name}.command is not configured.")
    return [str(item) for item in command]


def workspace_gpu_command(name: str, **replacements: str) -> list[str]:
    commands = load_workspace_profile().get("gpu", {}).get("commands", {})
    value = commands.get(name)
    if not isinstance(value, list):
        raise ProfileError(f"gpu.commands.{name} must be a list.")
    rendered: list[str] = []
    for part in value:
        text = str(part)
        for key, replacement in replacements.items():
            text = text.replace("{" + key + "}", replacement)
        rendered.append(text)
    return rendered
