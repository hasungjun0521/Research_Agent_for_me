#!/usr/bin/env python3
"""Small cross-script hooks for keeping workflow surfaces synchronized.

The harness layer must not import command modules. Command packages register
their surface refreshers here (see scripts/commands/__init__.py), and state
writers invoke whatever is registered, best-effort.
"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

SurfaceHook = Callable[[Path], None]

_report_index_hook: SurfaceHook | None = None
_dashboard_sources_hook: SurfaceHook | None = None


def register_report_index_hook(hook: SurfaceHook) -> None:
    global _report_index_hook
    _report_index_hook = hook


def register_dashboard_sources_hook(hook: SurfaceHook) -> None:
    global _dashboard_sources_hook
    _dashboard_sources_hook = hook


def refresh_workflow_surfaces(root: Path, *, include_report: bool = False) -> None:
    """Refresh derived support surfaces, and optionally the final 09_report artifact index."""
    if include_report and _report_index_hook is not None:
        try:
            _report_index_hook(root)
        except Exception as exc:  # pragma: no cover - hook must not mask the primary state write.
            print(f"warning: report index refresh skipped: {exc}", file=sys.stderr)
    if _dashboard_sources_hook is not None:
        try:
            _dashboard_sources_hook(root)
        except Exception as exc:  # pragma: no cover - hook diagnostics must not mask state writes.
            print(f"warning: dashboard source coverage skipped: {exc}", file=sys.stderr)


def refresh_report_index(root: Path, *, include_report: bool = False) -> None:
    """Compatibility wrapper for older call sites; final report refresh is opt-in."""
    refresh_workflow_surfaces(root, include_report=include_report)
