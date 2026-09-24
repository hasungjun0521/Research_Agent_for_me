#!/usr/bin/env python3
"""Capture a researcher-friendly brief intake without requiring manual JSON edits."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.harness.state import HarnessError, append_agent_event, now_iso, project_root, update_agent_status
from scripts.harness.workflow_hooks import refresh_report_index


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Draft or apply a research brief intake wizard.")
    sub = parser.add_subparsers(dest="command", required=True)

    draft = sub.add_parser("draft", help="Print or write the brief intake questionnaire.")
    draft.add_argument("--project", required=True)
    draft.add_argument("--write", action="store_true")

    apply = sub.add_parser("apply", help="Apply any supplied brief fields to project files.")
    apply.add_argument("--project", required=True)
    apply.add_argument("--agent", default="motivation_planner")
    apply.add_argument("--research-question", default="")
    apply.add_argument("--motivation", default="")
    apply.add_argument("--contribution", action="append", dest="contributions")
    apply.add_argument("--target-venue", default="")
    apply.add_argument("--dataset", action="append", dest="datasets")
    apply.add_argument("--metric", action="append", dest="metrics")
    apply.add_argument("--baseline", action="append", dest="baselines")
    apply.add_argument("--constraint", action="append", dest="constraints")
    apply.add_argument("--risk", action="append", dest="risks")
    apply.add_argument("--open-question", action="append", dest="open_questions")
    apply.add_argument("--compute-budget", default="")
    apply.add_argument("--deadline", default="")
    apply.add_argument("--write", action="store_true", help="Write files. Without this, print the planned intake summary.")
    apply.add_argument("--json", action="store_true")
    return parser.parse_args()


def compact_list(values: list[str] | None) -> list[str]:
    return [str(value).strip() for value in values or [] if str(value).strip()]


def append_section(path: Path, title: str, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    separator = "\n" if existing and not existing.endswith("\n") else ""
    block = "\n".join(["", f"## {title}", "", *lines]).rstrip() + "\n"
    path.write_text(existing + separator + block, encoding="utf-8")


def render_questionnaire(project: str) -> str:
    return "\n".join([
        "# Research Brief Intake",
        "",
        f"Project: `{project}`",
        "",
        "Answer only what is known. Unknowns should become open questions, not guesses.",
        "",
        "## Core Brief",
        "",
        "- Research question:",
        "- Motivation / why this matters:",
        "- Candidate contribution:",
        "- Target venue or audience:",
        "",
        "## Evaluation",
        "",
        "- Dataset / split / version:",
        "- Primary metric and direction:",
        "- Strongest baseline candidates:",
        "- Success criterion:",
        "- Failure criterion:",
        "",
        "## Constraints",
        "",
        "- Compute budget:",
        "- Deadline:",
        "- Data access or privacy constraints:",
        "- Known risks:",
        "",
        "## Open Questions",
        "",
        "- What must be clarified before literature review?",
        "- What must be clarified before experiments?",
    ]) + "\n"


def intake_payload(args: argparse.Namespace) -> dict[str, object]:
    return {
        "research_question": args.research_question.strip(),
        "motivation": args.motivation.strip(),
        "contributions": compact_list(args.contributions),
        "target_venue": args.target_venue.strip(),
        "datasets": compact_list(args.datasets),
        "metrics": compact_list(args.metrics),
        "baselines": compact_list(args.baselines),
        "constraints": compact_list(args.constraints),
        "risks": compact_list(args.risks),
        "open_questions": compact_list(args.open_questions),
        "compute_budget": args.compute_budget.strip(),
        "deadline": args.deadline.strip(),
    }


def render_summary(project: str, payload: dict[str, object]) -> str:
    def items(key: str) -> list[str]:
        values = payload.get(key)
        return values if isinstance(values, list) else []

    lines = [
        "# Intake Summary",
        "",
        f"Project: `{project}`",
        "",
        "## Brief",
        "",
        f"- Research question: {payload.get('research_question') or 'missing'}",
        f"- Motivation: {payload.get('motivation') or 'missing'}",
        f"- Target venue/audience: {payload.get('target_venue') or 'missing'}",
        f"- Compute budget: {payload.get('compute_budget') or 'missing'}",
        f"- Deadline: {payload.get('deadline') or 'missing'}",
        "",
        "## Contributions",
        "",
    ]
    lines.extend(f"- {value}" for value in items("contributions")) if items("contributions") else lines.append("- missing")
    lines.extend(["", "## Evaluation", ""])
    for label, key in (("Datasets", "datasets"), ("Metrics", "metrics"), ("Baselines", "baselines")):
        values = items(key)
        lines.append(f"- {label}: {', '.join(values) if values else 'missing'}")
    lines.extend(["", "## Constraints And Risks", ""])
    for value in items("constraints"):
        lines.append(f"- Constraint: {value}")
    for value in items("risks"):
        lines.append(f"- Risk: {value}")
    if not items("constraints") and not items("risks"):
        lines.append("- missing")
    lines.extend(["", "## Open Questions", ""])
    lines.extend(f"- {value}" for value in items("open_questions")) if items("open_questions") else lines.append("- none supplied")
    lines.extend([
        "",
        "## Next Routing",
        "",
        "- If the brief has enough detail, run director triage.",
        "- If dataset, metric, or baseline is missing, route those as explicit open questions before expensive experiments.",
    ])
    return "\n".join(lines) + "\n"


def has_any_payload(payload: dict[str, object]) -> bool:
    for value in payload.values():
        if isinstance(value, list) and value:
            return True
        if isinstance(value, str) and value.strip():
            return True
    return False


def apply_payload(root: Path, args: argparse.Namespace, payload: dict[str, object], summary: str) -> list[str]:
    timestamp = now_iso()
    outputs = ["02_planning/intake_summary.md"]
    append_section(root / "02_planning" / "intake_summary.md", f"Brief Intake: {timestamp}", summary.splitlines()[2:])
    if payload.get("research_question"):
        append_section(root / "00_brief" / "research_question.md", f"Intake: {timestamp}", [str(payload["research_question"])])
        outputs.append("00_brief/research_question.md")
    if payload.get("motivation"):
        append_section(root / "00_brief" / "motivation.md", f"Intake: {timestamp}", [str(payload["motivation"])])
        outputs.append("00_brief/motivation.md")
    if payload.get("contributions"):
        append_section(root / "00_brief" / "contribution_candidates.md", f"Intake: {timestamp}", [f"- {item}" for item in payload["contributions"]])
        outputs.append("00_brief/contribution_candidates.md")
    constraint_lines: list[str] = []
    for label in ("compute_budget", "deadline", "target_venue"):
        if payload.get(label):
            constraint_lines.append(f"- {label.replace('_', ' ').title()}: {payload[label]}")
    constraint_lines.extend(f"- Constraint: {item}" for item in payload.get("constraints", []))
    constraint_lines.extend(f"- Risk: {item}" for item in payload.get("risks", []))
    if constraint_lines:
        append_section(root / "00_brief" / "constraints.md", f"Intake: {timestamp}", constraint_lines)
        outputs.append("00_brief/constraints.md")
    if payload.get("open_questions"):
        append_section(root / "state" / "open_questions.md", f"Brief Intake Questions: {timestamp}", [f"- {item}" for item in payload["open_questions"]])
        outputs.append("state/open_questions.md")
    append_section(root / "state" / "current_state.md", f"Brief Intake Applied: {timestamp}", [
        f"- Research question supplied: {'yes' if payload.get('research_question') else 'no'}",
        f"- Motivation supplied: {'yes' if payload.get('motivation') else 'no'}",
        f"- Dataset candidates: {', '.join(payload.get('datasets', [])) if payload.get('datasets') else 'missing'}",
        f"- Metric candidates: {', '.join(payload.get('metrics', [])) if payload.get('metrics') else 'missing'}",
        "- Next: director triage or resolve missing brief fields.",
    ])
    outputs.append("state/current_state.md")
    return outputs


def main() -> int:
    args = parse_args()
    try:
        root = project_root(args.project)
        if args.command == "draft":
            content = render_questionnaire(root.name)
            if args.write:
                path = root / "00_brief" / "intake_wizard.md"
                path.write_text(content, encoding="utf-8")
            print(content, end="")
            return 0

        payload = intake_payload(args)
        if not has_any_payload(payload):
            raise HarnessError("No intake fields supplied.")
        summary = render_summary(root.name, payload)
        outputs: list[str] = []
        if args.write:
            outputs = apply_payload(root, args, payload, summary)
            try:
                update_agent_status(root, args.agent, "done", task="Apply research brief intake.", stage="brief intake", outputs=outputs, notes="Brief intake applied to project files.")
            except HarnessError:
                pass
            append_agent_event(root, "brief_intake", args.agent, status="done", task="Apply research brief intake.", stage="brief intake", outputs=outputs, notes="Brief intake applied.")
            refresh_report_index(root)
        if args.json:
            print(json.dumps({"project": root.name, "written": bool(args.write), "outputs": outputs, "intake": payload}, indent=2, ensure_ascii=False))
        else:
            print(summary, end="")
        return 0
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
