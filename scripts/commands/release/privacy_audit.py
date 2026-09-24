#!/usr/bin/env python3
"""Scan publishable files for local/private markers."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

# Match POSIX data/home roots, Windows drive paths, and UNC shares. The
# boundary avoids treating URL route components or relative paths as local.
LOCAL_ABSOLUTE_PATH_RE = re.compile(
    r"(^|[\s:=('\"`])(?:"
    r"/(?:home|Users|data|mnt|scratch|gpfs|lustre|nfs|tmp|var/tmp)/"
    r"|[A-Za-z]:[\\/]"
    r"|\\\\[A-Za-z0-9][A-Za-z0-9._-]*[\\/](?=[A-Za-z0-9_$-])"
    r")[^\s)'\"`]+",
    re.IGNORECASE,
)


def git_command(root: Path, *args: str) -> list[str]:
    return ["git", "-c", f"safe.directory={root.resolve()}", *args]


def git_root(cwd: Path | None = None) -> Path:
    base = cwd or Path.cwd()
    result = subprocess.run(
        git_command(base, "rev-parse", "--show-toplevel"),
        cwd=base,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).resolve()
    return base.resolve()


def publishable_paths(root: Path) -> list[str]:
    # Uses git ls-files with safe.directory so release checks work in shared workspaces.
    result = subprocess.run(
        git_command(root, "ls-files", "--cached", "--others", "--exclude-standard"),
        cwd=root,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git ls-files failed")
    return [line for line in result.stdout.splitlines() if line]


def private_project_markers(root: Path) -> list[str]:
    markers: list[str] = []
    projects_dir = root / "projects"
    if not projects_dir.is_dir():
        return markers
    for path in projects_dir.iterdir():
        if not path.is_dir() or path.name == "template":
            continue
        markers.append(path.name)
        underscore_parts = path.name.split("_")
        if len(underscore_parts) >= 3:
            markers.append("_".join(underscore_parts[:3]))
    return markers


def default_private_markers(root: Path) -> list[str]:
    markers = private_project_markers(root)
    user = (os.environ.get("USER") or os.environ.get("USERNAME") or "").strip()
    if user:
        markers.extend([
            "/" + f"home/{user}",
            "/" + f"data/projects/{user}",
            f"{user}'s",
        ])

    markers.extend(
        [
            "toolcall" + "-maint-workspace",
            "Gen" + "Lab",
            "Re" + "Summ",
            "Triple" + "Summ",
        ]
    )
    return sorted({marker for marker in markers if marker})


def scan_file(path: Path, markers: list[str]) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return any(marker in text for marker in markers) or bool(LOCAL_ABSOLUTE_PATH_RE.search(text))


def audit_privacy(root: Path, paths: list[str] | None = None, markers: list[str] | None = None) -> dict[str, Any]:
    publishable = paths if paths is not None else publishable_paths(root)
    marker_list = markers if markers is not None else default_private_markers(root)
    findings: list[dict[str, str]] = []
    for relative in publishable:
        path = root / relative
        if not path.is_file():
            continue
        if scan_file(path, marker_list):
            findings.append({"path": relative, "issue": "private_or_local_marker"})
    return {
        "ok": not findings,
        "root": root.as_posix(),
        "files_scanned": len(publishable),
        "findings": findings,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scan publishable files for local/private markers.")
    parser.add_argument("--root", default="", help="Repository root to scan. Defaults to the current git root.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable output.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve() if args.root else git_root()
    try:
        result = audit_privacy(root)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, indent=2))
    elif result["ok"]:
        print("privacy audit OK")
    else:
        print("Private or local markers are in publishable file contents:", file=sys.stderr)
        for finding in result["findings"]:
            print(f"- {finding['path']}", file=sys.stderr)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
