#!/usr/bin/env python3
"""Audit baseline commands before executing cloned third-party code."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from scripts.harness.report_lifecycle import sync_report_lifecycle
from scripts.harness.state import HarnessError, load_baseline_registry, project_root

BLOCK_PATTERNS = [
    (re.compile(r"\brm\s+-rf\s+[/~]"), "destructive rm -rf against absolute/home path"),
    (re.compile(r"\bsudo\b"), "sudo is not allowed in baseline commands"),
    (re.compile(r"\bchmod\s+777\b"), "world-writable chmod is not allowed"),
    (re.compile(r"\bcurl\b.*\|\s*(?:sh|bash)"), "curl pipe to shell is not allowed"),
    (re.compile(r"\bwget\b.*\|\s*(?:sh|bash)"), "wget pipe to shell is not allowed"),
]
WARN_PATTERNS = [
    (re.compile(r"\bpip\s+install\b"), "dependency install must be reviewed and pinned"),
    (re.compile(r"\bconda\s+install\b"), "dependency install must be reviewed and pinned"),
    (re.compile(r"\bgit\s+clone\b"), "nested clone should be registered in baseline metadata"),
    (re.compile(r"https?://"), "network access must be explicitly justified"),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check baseline command safety policy.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--agent", default="code_agent")
    parser.add_argument("--baseline-id")
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--write-policy", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def iter_commands(baseline: dict[str, Any]) -> list[tuple[str, str]]:
    commands = baseline.get("commands", {})
    if not isinstance(commands, dict):
        return []
    result: list[tuple[str, str]] = []
    for kind, values in commands.items():
        if isinstance(values, list):
            for value in values:
                if str(value).strip():
                    result.append((str(kind), str(value)))
        elif str(values or "").strip():
            result.append((str(kind), str(values)))
    return result


def audit_command(command: str) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    for pattern, message in BLOCK_PATTERNS:
        if pattern.search(command):
            errors.append(message)
    for pattern, message in WARN_PATTERNS:
        if pattern.search(command):
            warnings.append(message)
    return errors, warnings


def audit_baselines(root: Path, baseline_id: str | None = None) -> dict[str, Any]:
    registry = load_baseline_registry(root)
    findings: list[dict[str, str]] = []
    for baseline in registry.get("baselines", []):
        if not isinstance(baseline, dict):
            continue
        current_id = str(baseline.get("id") or "")
        if baseline_id and current_id != baseline_id:
            continue
        source_path = str(baseline.get("source_path") or baseline.get("local_snapshot") or "")
        if source_path and (Path(source_path).is_absolute() or ".." in Path(source_path).parts):
            findings.append({"baseline_id": current_id, "severity": "error", "field": "source_path", "message": "source_path must be project-relative"})
        for kind, command in iter_commands(baseline):
            errors, warnings = audit_command(command)
            for message in errors:
                findings.append({"baseline_id": current_id, "severity": "error", "field": kind, "message": message, "command": command})
            for message in warnings:
                findings.append({"baseline_id": current_id, "severity": "warning", "field": kind, "message": message, "command": command})
    return {"project": root.name, "findings": findings}


def write_policy(root: Path) -> Path:
    path = root / "08_baselines" / "sandbox_policy.md"
    lines = [
        "# Baseline Sandbox Policy",
        "",
        "Use this policy before executing cloned baseline code.",
        "",
        "## Required Controls",
        "",
        "- Keep cloned source under `08_baselines/source_snapshots/` and do not edit it directly.",
        "- Run generated smoke scripts before full GPU reproduction.",
        "- Review dependency installs before execution; prefer pinned requirements or isolated environments.",
        "- Do not allow commands with `sudo`, destructive absolute-path deletes, or pipe-to-shell installers.",
        "- Record network access, license notes, commit hash, command, dataset path, and result path in `baseline_registry.json`.",
        "",
        "Validate commands with:",
        "",
        "```bash",
        "python -m scripts.commands.baselines.baseline_sandbox --project <project> --strict",
        "```",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def sync_sandbox_agent(root: Path, agent: str, result: dict[str, Any]) -> None:
    findings = result.get("findings", [])
    errors = [finding for finding in findings if finding.get("severity") == "error"]
    warnings = [finding for finding in findings if finding.get("severity") == "warning"]
    status = "blocked" if errors else "waiting"
    task = "Wrote baseline sandbox safety policy."
    notes = f"Baseline sandbox audit found {len(errors)} error(s) and {len(warnings)} warning(s)."
    sync_report_lifecycle(
        root,
        agent=agent,
        event_type="baseline_sandbox",
        status=status,
        task=task,
        outputs=["08_baselines/sandbox_policy.md"],
        notes=notes,
        refresh_report=False,
    )


def main() -> int:
    args = parse_args()
    try:
        root = project_root(args.project)
        result = audit_baselines(root, args.baseline_id)
        policy_path = write_policy(root) if args.write_policy else None
        if args.write_policy:
            sync_sandbox_agent(root, args.agent, result)
        errors = [finding for finding in result["findings"] if finding["severity"] == "error"]
        if args.json:
            if policy_path:
                result["policy_path"] = policy_path.relative_to(root).as_posix()
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            if not result["findings"]:
                print(f"baseline sandbox OK: {args.project}")
            for finding in result["findings"]:
                print(f"{finding['severity']}\t{finding['baseline_id']}\t{finding['field']}\t{finding['message']}")
            if policy_path:
                print(policy_path.relative_to(root).as_posix())
        if args.strict and errors:
            return 1
        return 0
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
