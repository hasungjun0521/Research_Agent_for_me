#!/usr/bin/env python3
"""Refresh the generated file inventory in project.yaml."""

from __future__ import annotations

import argparse
import difflib
import fnmatch
import json
import sys
from pathlib import Path
from typing import Any

from scripts.harness import repo_root as harness_repo_root

START_MARKER = "# PROJECT_INDEX:START"
END_MARKER = "# PROJECT_INDEX:END"
PUBLIC_INVENTORY_EXCLUDES = ("*.lock", "config/workspace_profile.local.json", "config/ppt_template_local.pptx", "config/*.local.pptx")

def setup_subparsers(subparsers: argparse._SubParsersAction) -> None:
    index = subparsers.add_parser("index", help="Refresh or check project.yaml generated inventory.")
    index_sub = index.add_subparsers(dest="index_command", required=True)
    index_sub.add_parser("refresh", help="Rewrite the generated project.yaml inventory.")
    index_sub.add_parser("check", help="Fail if the generated project.yaml inventory is stale.")

def repo_root() -> Path: return harness_repo_root()
def rel(p: Path) -> str: return p.relative_to(repo_root()).as_posix()

def files_under(relative_dir: str, pattern: str = "*") -> list[str]:
    root = repo_root() / relative_dir
    if not root.is_dir(): return []
    return sorted(rel(p) for p in root.rglob(pattern) if p.is_file() and "__pycache__" not in p.parts and not any(fnmatch.fnmatch(rel(p), e) for e in PUBLIC_INVENTORY_EXCLUDES))

def top_level_files() -> list[str]:
    names = ["AGENTS.md", "ARCHITECTURE.md", "CHANGELOG.md", "CLAUDE.md", "HANDOFF.md", "README.md", "project.yaml", "pyproject.toml"]
    return [n for n in names if (repo_root() / n).is_file()]

def discover_inventory() -> dict[str, Any]:
    scripts = files_under("scripts", "*.py")
    agents = files_under("prompts/agents", "*.md")
    shared = files_under("prompts/shared", "*.md")
    skills = files_under("prompts/skills", "*.md")
    docs = files_under("docs", "*.md")
    forms = files_under("review_forms")
    flows = files_under("workflows", "*.yaml")
    dash = files_under("dashboard")
    conf = files_under("config")
    return {
        "generated_by": "scripts.commands.projects.project_index",
        "root_files": top_level_files(),
        "scripts": {"count": len(scripts), "files": scripts},
        "dashboard": {"count": len(dash), "files": dash},
        "prompts": {"agents": {"count": len(agents), "files": agents}, "shared": {"count": len(shared), "files": shared}, "skills": {"count": len(skills), "files": skills}},
        "docs": {"count": len(docs), "files": docs},
        "review_forms": {"count": len(forms), "files": forms},
        "workflows": {"count": len(flows), "files": flows},
        "config": {"count": len(conf), "files": conf},
    }

def yaml_scalar(v: Any) -> str:
    if isinstance(v, bool): return "true" if v else "false"
    if isinstance(v, int): return str(v)
    if v is None: return "null"
    return json.dumps(str(v), ensure_ascii=False)

def append_yaml(lines: list[str], key: str, value: Any, indent: int) -> None:
    prefix = " " * indent
    if isinstance(value, dict):
        lines.append(f"{prefix}{key}:")
        for ck, cv in value.items(): append_yaml(lines, str(ck), cv, indent + 2)
    elif isinstance(value, list):
        if not value: lines.append(f"{prefix}{key}: []")
        else:
            lines.append(f"{prefix}{key}:")
            for item in value: lines.append(f"{prefix}  - {yaml_scalar(item)}")
    else: lines.append(f"{prefix}{key}: {yaml_scalar(value)}")

def render_inventory_block(inv: dict[str, Any]) -> str:
    lines = [START_MARKER, "generated_inventory:"]
    for k, v in inv.items(): append_yaml(lines, k, v, 2)
    lines.append(END_MARKER); return "\n".join(lines) + "\n"

def replace_block(orig: str, block: str) -> str:
    if START_MARKER not in orig: return orig + "\n\n" + block
    s = orig.find(START_MARKER); e = orig.find(END_MARKER) + len(END_MARKER)
    if e < len(orig) and orig[e] == "\n": e += 1
    return orig[:s] + block + orig[e:]

def expected_project_yaml() -> str:
    path = repo_root() / "project.yaml"
    return replace_block(path.read_text(encoding="utf-8"), render_inventory_block(discover_inventory()))

def run_refresh() -> int:
    (repo_root() / "project.yaml").write_text(expected_project_yaml(), encoding="utf-8")
    print("project.yaml refreshed"); return 0

def run_check() -> int:
    path = repo_root() / "project.yaml"; cur = path.read_text(encoding="utf-8"); exp = expected_project_yaml()
    if cur == exp: print("project.yaml inventory OK"); return 0
    diff = difflib.unified_diff(cur.splitlines(), exp.splitlines(), fromfile="project.yaml", tofile="project.yaml.expected", lineterm="")
    print("\n".join(diff), file=sys.stderr); return 1

def main() -> int:
    from scripts.commands.projects.projects import main as projects_main
    if len(sys.argv) > 1 and sys.argv[1] in {"refresh", "check"}: sys.argv.insert(1, "index")
    elif len(sys.argv) < 2 or sys.argv[1] != "index": sys.argv.insert(1, "index")
    return projects_main()

if __name__ == "__main__": raise SystemExit(main())
