"""Centralized agent usage limit sensing and runner selection."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from scripts.harness.workspace_profile import (
    workspace_agent_limit_json_paths,
    workspace_agent_limit_status_command,
    workspace_agent_limit_timeout,
    workspace_agent_runner_profiles,
)


def run_status_command(command: list[str], timeout_seconds: int) -> dict[str, Any]:
    if not command:
        return {}
    try:
        completed = subprocess.run(
            command,
            cwd=Path.cwd(),
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        if completed.returncode != 0:
            return {}
        payload = json.loads(completed.stdout)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def json_path_value(payload: dict[str, Any], path: str) -> Any:
    value: Any = payload
    for part in path.split("."):
        if not part:
            continue
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def pct_value(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().removesuffix("%")
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def extract_limit_pct(
    payload: dict[str, Any], configured_path: str, fallback_paths: list[str]
) -> float | None:
    paths = [configured_path] if configured_path else []
    paths.extend(path for path in fallback_paths if path not in paths)
    for path in paths:
        value = pct_value(json_path_value(payload, path))
        if value is not None:
            return value
    return None


def fetch_runner_limits(profile_name: str) -> dict[str, float | None]:
    cmd = workspace_agent_limit_status_command(profile_name)
    timeout = workspace_agent_limit_timeout(profile_name)
    paths = workspace_agent_limit_json_paths(profile_name)
    payload = run_status_command(cmd, timeout)
    if not payload:
        return {"five_hour": None, "weekly": None}

    five_hour = extract_limit_pct(
        payload,
        paths.get("five_hour_remaining_pct", ""),
        ["five_hour_remaining_pct", "five_hour.remaining_pct", "limits.five_hour.remaining_pct"],
    )
    weekly = extract_limit_pct(
        payload,
        paths.get("weekly_remaining_pct", ""),
        ["weekly_remaining_pct", "weekly.remaining_pct", "limits.weekly.remaining_pct"],
    )
    return {"five_hour": five_hour, "weekly": weekly}


def select_best_runner() -> str:
    profiles = workspace_agent_runner_profiles()
    candidates: list[tuple[str, float]] = []
    for name in profiles:
        # Skip runners without a status command configured
        if not workspace_agent_limit_status_command(name):
            continue
        limits = fetch_runner_limits(name)
        # Use the minimum of the two periods as the bottleneck score
        vals = [v for v in (limits["five_hour"], limits["weekly"]) if v is not None]
        score = min(vals) if vals else -1.0
        if score >= 0:
            candidates.append((name, score))

    if not candidates:
        # Fallback to the default profile if no dynamic info is available
        from scripts.harness.workspace_profile import workspace_agent_runner_default_profile

        return workspace_agent_runner_default_profile()
    return sorted(candidates, key=lambda x: x[1], reverse=True)[0][0]
