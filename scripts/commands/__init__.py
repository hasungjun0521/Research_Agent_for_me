"""Grouped command implementations for the research-agent harness.

Importing any command module runs this package init, which registers the
command-layer workflow-surface hooks with the harness. The harness layer
itself never imports command modules; it only invokes what is registered.
"""

from pathlib import Path

from scripts.harness import workflow_hooks


def _refresh_report_index(root: Path) -> None:
    from scripts.commands.reports.report_index import refresh_project_index

    refresh_project_index(root)


def _refresh_dashboard_sources(root: Path) -> None:
    from scripts.commands.dashboard.dashboard_sources import build_dashboard_sources

    build_dashboard_sources(root)


workflow_hooks.register_report_index_hook(_refresh_report_index)
workflow_hooks.register_dashboard_sources_hook(_refresh_dashboard_sources)
