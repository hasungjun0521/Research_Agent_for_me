"""Repository and project path helpers."""

from __future__ import annotations

from pathlib import Path

from .errors import HarnessError


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def project_root(project_name: str) -> Path:
    if not project_name:
        raise HarnessError("Project name is required.")
    candidate = Path(project_name)
    if candidate.is_absolute() or len(candidate.parts) != 1 or ".." in candidate.parts:
        raise HarnessError("Project name must be a single folder name under projects/.")
    root = repo_root() / "projects" / candidate
    if not root.is_dir():
        raise HarnessError(f"Project not found: {project_name}")
    return root
