"""Unit tests for the resume-time canonical-state reconciliation gate.

Covers the three contract cases plus the helpers: a pristine project (no real
activity) must stay clean so the template/smoke/verify gates stay green; a
project with results but frozen canonical surfaces must be flagged; and a
project whose canonical surfaces track real progress must stay clean.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.harness.project_diagnostics import (
    latest_activity_mtime,
    md_section_first_line,
    parse_iso_epoch,
    reconciliation_issues,
)

RESULT_HEADER = (
    "experiment_id,claim_id,dataset,split,method,baseline_id,"
    "metric,value,delta,status,evidence,caveat\n"
)


def _now_iso(delta_hours: float = 0.0) -> str:
    return (datetime.now(timezone.utc) + timedelta(hours=delta_hours)).isoformat()


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _results_csv(rows: int) -> str:
    body = "".join(
        f"exp_{i},c1,ds,test,ours,base,acc,0.{80 + i},0.01,done,ev,\n" for i in range(rows)
    )
    return RESULT_HEADER + body


def _current_state(stage: str, question: str, last_updated: str) -> str:
    return (
        "# Current State\n\n"
        f"## Current Stage\n\n{stage}\n\n"
        f"## Research Question\n\n{question}\n\n"
        "## Current Hypothesis\n\nX improves Y.\n\n"
        f"## Last Updated\n\n{last_updated}\n"
    )


def _reconcile(root: Path):
    return reconciliation_issues(root, latest_activity_mtime(root))


def _make(
    tmp_path,
    *,
    results,
    run_state_status="planned",
    loop_status="planned",
    loop_completed=None,
    loop_last_updated="YYYY-MM-DDTHH:MM:SS+09:00",
    stage="brief",
    question="Not yet finalized.",
    cs_last_updated="YYYY-MM-DD",
    phases_pending=True,
    open_commands=False,
    agents=None,
):
    root = tmp_path / "proj"
    _write(root / "05_results" / "experiment_results.csv", _results_csv(results))
    if run_state_status:
        _write(
            root / "03_experiments" / "exp_001" / "run_state.json",
            json.dumps({"status": run_state_status}),
        )
    _write(
        root / "state" / "loop_summary.json",
        json.dumps(
            {
                "status": loop_status,
                "goal": "g",
                "last_updated": loop_last_updated,
                "completed_commands": loop_completed or [],
            }
        ),
    )
    _write(root / "state" / "current_state.md", _current_state(stage, question, cs_last_updated))
    _write(
        root / "state" / "phase_gates.json",
        json.dumps(
            {
                "phases": [
                    {"id": "brief", "status": "pending" if phases_pending else "done"},
                    {"id": "experiments", "status": "pending" if phases_pending else "in_progress"},
                ]
            }
        ),
    )
    commands = [
        {
            "id": "cmd_001",
            "status": "open" if open_commands else "done",
            "updated_at": _now_iso(),
        }
    ]
    _write(root / "state" / "command_queue.json", json.dumps({"commands": commands}))
    _write(root / "state" / "agent_status.json", json.dumps({"agents": agents or []}))
    return root


def test_pristine_project_with_no_real_activity_is_clean(tmp_path):
    # Header-only results + a `planned` starter run_state == a fresh template.
    root = _make(tmp_path, results=0, run_state_status="planned")
    assert _reconcile(root) == []


def test_frozen_canonical_surfaces_with_results_are_flagged(tmp_path):
    root = _make(tmp_path, results=5, run_state_status="succeeded")
    issues = _reconcile(root)
    assert issues, "frozen canonical surfaces with results must produce findings"
    assert {item["area"] for item in issues} == {"reconciliation"}
    blob = " ".join(item["summary"] for item in issues)
    assert "loop_summary" in blob
    assert "current_state" in blob
    assert "phase gates" in blob.lower()
    assert all(item["severity"] in {"high", "medium"} for item in issues)


def test_updated_canonical_surfaces_with_results_are_clean(tmp_path):
    root = _make(
        tmp_path,
        results=5,
        run_state_status="succeeded",
        loop_status="running",
        loop_completed=["cmd_001"],
        loop_last_updated=_now_iso(),
        stage="experiments",
        question="Can X be solved with Y?",
        cs_last_updated="2026-06-14",
        phases_pending=False,
        open_commands=True,
        agents=[{"name": "code_agent", "status": "running", "updated_at": _now_iso()}],
    )
    issues = _reconcile(root)
    assert issues == [], [item["summary"] for item in issues]


def test_zombie_agent_with_results_is_flagged(tmp_path):
    root = _make(
        tmp_path,
        results=5,
        run_state_status="succeeded",
        loop_status="running",
        loop_completed=["cmd_001"],
        loop_last_updated=_now_iso(),
        stage="experiments",
        question="Real question?",
        cs_last_updated="2026-06-14",
        phases_pending=False,
        open_commands=True,
        agents=[{"name": "director", "status": "running", "updated_at": _now_iso(-72)}],
    )
    zombies = [item for item in _reconcile(root) if "zombie" in item["summary"]]
    assert len(zombies) == 1
    assert "director" in zombies[0]["summary"]


def test_parse_iso_epoch_rejects_placeholders():
    assert parse_iso_epoch("YYYY-MM-DDTHH:MM:SS+09:00") is None
    assert parse_iso_epoch("") is None
    assert parse_iso_epoch(None) is None
    assert parse_iso_epoch("2026-06-09T01:50:00+09:00") is not None


def test_md_section_first_line_extracts_header_value():
    text = "## Current Stage\n\nbrief\n\n## Last Updated\n\nYYYY-MM-DD\n"
    assert md_section_first_line(text, "Current Stage") == "brief"
    assert md_section_first_line(text, "Last Updated") == "YYYY-MM-DD"
    assert md_section_first_line(text, "Missing") == ""
