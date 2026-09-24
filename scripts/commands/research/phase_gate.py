#!/usr/bin/env python3
"""Manage research phase gates and completion conditions."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any

from scripts.harness.state import (
    HarnessError,
    append_agent_event,
    atomic_write_json,
    load_json,
    now_iso,
    project_root,
    update_agent_status,
)
from scripts.harness.workflow_hooks import refresh_report_index

PHASES = [
    ("brief", "Research brief", "Research question and scope are concrete."),
    ("literature", "Literature grounding", "Bibliography and paper notes are populated."),
    ("planning", "Experiment planning", "Claim graph and preregistration are ready."),
    ("experiments", "Experiment execution", "Runs have produced auditable evidence."),
    ("results", "Result evidence", "Stable claim/result evidence and robustness checks are populated."),
    ("writing", "Paper writing", "Draft sections are tied to evidence."),
    ("review", "Reviewer risk", "Reviewer risks and rebuttal plan are documented."),
    ("report", "Final artifacts", "09_report contains only final artifacts and result tables."),
]
STATUS_VALUES = {"blocked", "pending", "in_progress", "done", "waived"}
CSV_HEADER = ["phase", "status", "condition", "evidence", "warning"]


def gate_path(root: Path) -> Path:
    return root / "state" / "phase_gates.json"


def default_gates(project_name: str) -> dict[str, Any]:
    return {
        "project": project_name,
        "schema_version": 1,
        "last_updated": now_iso(),
        "status_values": sorted(STATUS_VALUES),
        "phases": [
            {
                "id": phase_id,
                "label": label,
                "status": "pending",
                "condition": condition,
                "evidence": [],
                "notes": "",
                "updated_at": "",
            }
            for phase_id, label, condition in PHASES
        ],
    }


def validate_gates(data: dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise HarnessError("phase_gates.json must be a JSON object.")
    phases = data.get("phases")
    if not isinstance(phases, list):
        raise HarnessError("phase_gates.json must contain a phases array.")
    seen: set[str] = set()
    for index, phase in enumerate(phases):
        if not isinstance(phase, dict):
            raise HarnessError(f"phase_gates phases[{index}] must be an object.")
        phase_id = str(phase.get("id") or "").strip()
        if not phase_id:
            raise HarnessError(f"phase_gates phases[{index}] is missing id.")
        if phase_id in seen:
            raise HarnessError(f"Duplicate phase gate id: {phase_id}")
        seen.add(phase_id)
        status = str(phase.get("status") or "").strip()
        if status not in STATUS_VALUES:
            raise HarnessError(f"Phase {phase_id} has invalid status: {status!r}")
        if not isinstance(phase.get("evidence", []), list):
            raise HarnessError(f"Phase {phase_id} evidence must be a list.")


def load_gates(root: Path) -> dict[str, Any]:
    data = load_json(gate_path(root), fallback=default_gates(root.name))
    validate_gates(data)
    return data


def write_gates(root: Path, data: dict[str, Any]) -> None:
    data["last_updated"] = now_iso()
    validate_gates(data)
    atomic_write_json(gate_path(root), data)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage research phase gates.")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="Create state/phase_gates.json if missing.")
    init.add_argument("--project", required=True)

    set_cmd = sub.add_parser("set", help="Set a phase gate status.")
    set_cmd.add_argument("--project", required=True)
    set_cmd.add_argument("--phase", required=True)
    set_cmd.add_argument("--status", required=True, choices=sorted(STATUS_VALUES))
    set_cmd.add_argument("--evidence", action="append", default=[])
    set_cmd.add_argument("--note", default="")

    audit = sub.add_parser("audit", help="Audit phase gate state against project evidence.")
    audit.add_argument("--project", required=True)
    audit.add_argument("--write-report", action="store_true")
    audit.add_argument("--strict", action="store_true")
    audit.add_argument("--json", action="store_true")
    return parser.parse_args()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""


def csv_has_rows(path: Path) -> bool:
    if not path.is_file():
        return False
    with path.open("r", encoding="utf-8", newline="") as handle:
        return any(any(str(value or "").strip() for value in row.values()) for row in csv.DictReader(handle))


def evidence_checks(root: Path) -> dict[str, tuple[bool, str]]:
    return {
        "brief": (len(read_text(root / "00_brief" / "research_question.md").strip()) >= 80, "00_brief/research_question.md"),
        "literature": ((root / "01_literature" / "papers.bib").stat().st_size > 0 if (root / "01_literature" / "papers.bib").is_file() else False, "01_literature/papers.bib"),
        "planning": ((root / "03_experiments" / "exp_001" / "preregistration.md").is_file(), "03_experiments/exp_001/preregistration.md"),
        "experiments": (any((root / "03_experiments").glob("exp_*/run_state.json")), "03_experiments/exp_*/run_state.json"),
        "results": (csv_has_rows(root / "09_report" / "results" / "claim_evidence.csv"), "09_report/results/claim_evidence.csv"),
        "writing": (len(read_text(root / "06_writing" / "draft.md").strip()) >= 80, "06_writing/draft.md"),
        "review": ((root / "07_reviews" / "reviewer_attack_matrix.md").is_file(), "07_reviews/reviewer_attack_matrix.md"),
        "report": ((root / "09_report" / "README.md").is_file(), "09_report/README.md"),
    }


def audit_gates(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    checks = evidence_checks(root)
    rows: list[dict[str, str]] = []
    warnings: list[str] = []
    blockers: list[str] = []
    for phase in data.get("phases", []):
        phase_id = str(phase.get("id") or "")
        passed, evidence = checks.get(phase_id, (False, ""))
        status = str(phase.get("status") or "pending")
        warning = ""
        if status == "done" and not passed:
            warning = "marked done but expected evidence is missing"
            blockers.append(f"{phase_id}: {warning}")
        elif status in {"pending", "blocked"} and passed:
            warning = "evidence exists but gate is not marked done"
            warnings.append(f"{phase_id}: {warning}")
        rows.append({
            "phase": phase_id,
            "status": status,
            "condition": str(phase.get("condition") or ""),
            "evidence": evidence,
            "warning": warning,
        })
    return {
        "project": root.name,
        "status": "blocked" if blockers else "warning" if warnings else "ready",
        "blockers": blockers,
        "warnings": warnings,
        "phases": rows,
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Phase Gate Audit",
        "",
        f"- Project: `{report['project']}`",
        f"- Status: `{report['status']}`",
        "",
        "| Phase | Status | Evidence | Warning |",
        "| --- | --- | --- | --- |",
    ]
    for row in report["phases"]:
        lines.append(f"| {row['phase']} | {row['status']} | {row['evidence']} | {row['warning'] or '-'} |")
    return "\n".join(lines) + "\n"


def write_report(root: Path, report: dict[str, Any]) -> Path:
    md_path = root / "07_reviews" / "phase_gate_audit.md"
    md_path.write_text(render_markdown(report), encoding="utf-8")
    csv_path = root / "09_report" / "results" / "phase_gate_audit.csv"
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_HEADER, lineterminator="\n")
        writer.writeheader()
        writer.writerows(report["phases"])
    refresh_report_index(root, include_report=True)
    return csv_path


def sync_phase_lifecycle(root: Path, event: str, status: str, task: str, outputs: list[str], note: str) -> None:
    agent_status = "blocked" if status == "blocked" else "waiting"
    update_agent_status(
        root,
        "director",
        agent_status,
        task=task,
        stage="phase_gate",
        outputs=outputs,
        notes=note,
        append_note=True,
    )
    append_agent_event(
        root,
        event,
        "director",
        status=agent_status,
        task=task,
        stage="phase_gate",
        outputs=outputs,
        notes=note,
    )


def main() -> int:
    args = parse_args()
    try:
        root = project_root(args.project)
        if args.command == "init":
            if not gate_path(root).exists():
                write_gates(root, default_gates(root.name))
            print(gate_path(root).relative_to(root).as_posix())
            return 0

        data = load_gates(root)
        if args.command == "set":
            for phase in data["phases"]:
                if phase.get("id") == args.phase:
                    phase["status"] = args.status
                    phase["evidence"] = args.evidence
                    phase["notes"] = args.note
                    phase["updated_at"] = now_iso()
                    write_gates(root, data)
                    sync_phase_lifecycle(
                        root,
                        "phase_gate_set",
                        args.status,
                        f"Set phase gate {args.phase} to {args.status}.",
                        ["state/phase_gates.json"],
                        args.note or "Phase gate state updated.",
                    )
                    print(f"{args.phase} -> {args.status}")
                    return 0
            raise HarnessError(f"Unknown phase gate: {args.phase}")

        report = audit_gates(root, data)
        if args.write_report:
            csv_path = write_report(root, report)
            report["written"] = ["07_reviews/phase_gate_audit.md", csv_path.relative_to(root).as_posix()]
            sync_phase_lifecycle(
                root,
                "phase_gate_audit",
                report["status"],
                "Audit phase gate readiness.",
                report["written"],
                f"Phase gate audit status: {report['status']}.",
            )
        if args.json:
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print(render_markdown(report).rstrip())
        return 1 if args.strict and report["blockers"] else 0
    except (HarnessError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
