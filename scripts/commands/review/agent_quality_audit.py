#!/usr/bin/env python3
"""Audit whether agent passes left enough durable evidence to resume."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scripts.harness.project_diagnostics import jsonl_rows
from scripts.harness.state import (
    HarnessError,
    append_agent_event,
    project_root,
    update_agent_status,
)
from scripts.harness.workflow_hooks import refresh_report_index


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit agent event/progress quality for project continuity.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--agent", default="critic")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def read_json(path: Path, fallback: Any) -> Any:
    if not path.is_file():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return fallback


def build_audit(root: Path) -> dict[str, Any]:
    events = jsonl_rows(root / "state" / "agent_events.jsonl")
    progress = jsonl_rows(root / "state" / "progress_hooks.jsonl")
    queue = read_json(root / "state" / "command_queue.json", {"commands": []})
    commands = queue.get("commands") if isinstance(queue, dict) else []
    commands = commands if isinstance(commands, list) else []
    done_commands = [cmd for cmd in commands if str(cmd.get("status") or "").lower() == "done"]
    active_commands = [cmd for cmd in commands if str(cmd.get("status") or "").lower() in {"open", "in progress", "blocked"}]

    findings: list[dict[str, str]] = []
    if done_commands and not progress:
        findings.append({"severity": "high", "finding": "Commands are done but no progress checkpoint log exists.", "recommendation": "Use progress_checkpoint during long or multi-step passes."})
    for event in events:
        if str(event.get("status") or "").lower() == "done" and not event.get("outputs"):
            findings.append({"severity": "medium", "finding": f"Done event `{event.get('event')}` has no output files.", "recommendation": "Record output paths so future agents can inspect evidence instead of relying on chat."})
    for cmd in done_commands:
        if not str(cmd.get("notes") or "").strip() and not cmd.get("expected_outputs"):
            findings.append({"severity": "medium", "finding": f"Done command `{cmd.get('id')}` lacks notes and expected outputs.", "recommendation": "Close commands with evidence, outputs, and done condition."})
    for row in progress:
        if str(row.get("kind") or "") == "experiment_result" and not str(row.get("result_analysis") or row.get("rationale") or "").strip():
            findings.append({"severity": "high", "finding": f"Experiment checkpoint `{row.get('exp_id')}` lacks analysis/rationale.", "recommendation": "Explain why performance improved, regressed, or stayed flat."})

    score = max(0, 100 - 15 * len([item for item in findings if item["severity"] == "high"]) - 7 * len([item for item in findings if item["severity"] == "medium"]) - 2 * len([item for item in findings if item["severity"] == "low"]))
    return {
        "schema_version": 1,
        "project": root.name,
        "score": score,
        "findings": findings,
        "counts": {
            "events": len(events),
            "progress_checkpoints": len(progress),
            "done_commands": len(done_commands),
            "active_commands": len(active_commands),
        },
    }


def render_markdown(audit: dict[str, Any]) -> str:
    lines = [
        "# Agent Quality Audit",
        "",
        f"- Project: `{audit['project']}`",
        f"- Continuity score: {audit['score']}/100",
        f"- Agent events: {audit['counts']['events']}",
        f"- Progress checkpoints: {audit['counts']['progress_checkpoints']}",
        f"- Done commands: {audit['counts']['done_commands']}",
        f"- Active commands: {audit['counts']['active_commands']}",
        "",
        "## Findings",
        "",
        "| Severity | Finding | Recommendation |",
        "| --- | --- | --- |",
    ]
    if not audit["findings"]:
        lines.append("| info | No continuity findings. | Continue using progress checkpoints and output-file evidence. |")
    for item in audit["findings"]:
        finding = item["finding"].replace("|", "\\|")
        recommendation = item["recommendation"].replace("|", "\\|")
        lines.append(f"| {item['severity']} | {finding} | {recommendation} |")
    lines.extend([
        "",
        "## Quality Bar",
        "",
        "- Done work should cite output files, not only chat summaries.",
        "- Long passes should include progress checkpoints before the final response.",
        "- Experiment results should include the reason for the run, result, evidence, and why performance moved.",
        "- Fresh agents should be able to continue from HANDOFF.md plus state files without chat history.",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    try:
        root = project_root(args.project)
        audit = build_audit(root)
        content = render_markdown(audit)
        outputs: list[str] = []
        if args.write:
            path = root / "07_reviews" / "agent_quality_audit.md"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
            outputs = ["07_reviews/agent_quality_audit.md"]
            try:
                update_agent_status(root, args.agent, "done", task="Audit agent continuity quality.", stage="agent quality", outputs=outputs, notes=f"Agent quality score {audit['score']}/100.")
            except HarnessError:
                pass
            append_agent_event(root, "agent_quality_audit", args.agent, status="done", task="Audit agent continuity quality.", stage="agent quality", outputs=outputs, notes=f"Agent quality score {audit['score']}/100.")
            refresh_report_index(root)
        if args.json:
            print(json.dumps({"written": bool(args.write), "outputs": outputs, "audit": audit}, indent=2, ensure_ascii=False))
        else:
            print(content, end="")
        return 0
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
