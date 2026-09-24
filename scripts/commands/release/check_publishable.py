#!/usr/bin/env python3
"""Check that the publishable harness file set is complete and safe."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.commands.release.privacy_audit import audit_privacy, git_command, git_root

REQUIRED_PUBLISHABLE_FILES = (
    "README.md",
    "ARCHITECTURE.md",
    "CHANGELOG.md",
    "HANDOFF.md",
)


def repo_root() -> Path:
    return git_root()


def publishable_paths() -> tuple[int, list[str], str]:
    # Uses git ls-files with safe.directory so release checks work in shared workspaces.
    result = subprocess.run(
        git_command(repo_root(), "ls-files", "--cached", "--others", "--exclude-standard"),
        cwd=repo_root(),
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        return result.returncode, [], result.stderr
    return 0, result.stdout.splitlines(), ""


def main() -> int:
    returncode, paths, stderr = publishable_paths()
    if returncode != 0:
        print(stderr, file=sys.stderr)
        return returncode

    path_set = set(paths)
    missing = [path for path in REQUIRED_PUBLISHABLE_FILES if path not in path_set]
    forbidden: list[str] = []
    for line in paths:
        if line.startswith("projects/") and not line.startswith("projects/template/"):
            forbidden.append(line)
        if line.startswith("config/") and line not in {
            "config/README.md",
            "config/workspace_profile.example.json",
        }:
            forbidden.append(line)
        if "__pycache__/" in line or line.endswith((".pyc", ".pyo", ".lock")):
            forbidden.append(line)

    if missing:
        print("Missing required publishable files:", file=sys.stderr)
        for path in missing:
            print(f"- {path}", file=sys.stderr)
        return 1

    if forbidden:
        print("Forbidden files are in the publishable file set:", file=sys.stderr)
        for path in forbidden:
            print(f"- {path}", file=sys.stderr)
        return 1

    private_findings = audit_privacy(repo_root(), paths).get("findings", [])
    if private_findings:
        print("Private or local markers are in publishable file contents:", file=sys.stderr)
        for finding in private_findings:
            print(f"- {finding['path']}", file=sys.stderr)
        return 1

    print("publishable file set OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
