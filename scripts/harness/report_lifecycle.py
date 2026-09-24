"""Lifecycle helper for report/audit writer commands."""

from __future__ import annotations

from pathlib import Path

from scripts.harness.state import append_agent_event, update_agent_status
from scripts.harness.workflow_hooks import refresh_report_index


def sync_report_lifecycle(
    root: Path,
    *,
    agent: str,
    event_type: str,
    status: str,
    task: str,
    outputs: list[str],
    notes: str,
    refresh_report: bool = False,
) -> None:
    """Record lifecycle state; final report index refresh is explicit opt-in."""
    if refresh_report:
        refresh_report_index(root, include_report=True)
    update_agent_status(
        root,
        agent,
        status,
        task=task,
        stage=event_type,
        outputs=outputs,
        notes=notes,
        append_note=True,
    )
    append_agent_event(
        root,
        event_type,
        agent,
        status=status,
        task=task,
        stage=event_type,
        outputs=outputs,
        notes=notes,
    )
