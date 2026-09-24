"""Fast, read-only Claude session context; never launches agents or experiments."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def response(payload: dict, root: Path) -> dict:
    if os.environ.get("RESEARCH_AGENT_CHILD") == "1":
        return {}
    event = payload.get("hook_event_name", "")
    if event == "SessionStart":
        projects = sorted(path.name for path in (root / "projects").iterdir()
                          if path.is_dir() and path.name != "template") if (root / "projects").is_dir() else []
        context = (
            "Research Agent Workspace: read AGENTS.md (and CLAUDE.md). "
            "For harness maintenance read root HANDOFF.md. For project work run "
            "python -m scripts.commands.projects.project_resume --project <name>, then read "
            "its HANDOFF and state files. Refresh state doctor before project health. "
            "Use harness CLIs for state changes. Save evidence and a progress checkpoint before stopping. "
            "Projects: " + (", ".join(projects[:30]) or "none; create one from template")
        )
        return {"hookSpecificOutput": {"hookEventName": event, "additionalContext": context}}
    # One continuation reminder, not a recursive stop loop. The agent must decide
    # whether a checkpoint applies; the hook never invents research progress.
    if event == "Stop" and not payload.get("stop_hook_active"):
        return {"decision": "block", "reason": (
            "Before finishing substantial research work, save a progress_checkpoint and update "
            "the project handoff with status, evidence, blockers and next action. For harness work "
            "update root HANDOFF.md when needed. If already saved or this was only conversation, "
            "finish without changing files. Do not start new work just for this reminder."
        )}
    return {}


if __name__ == "__main__":
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict):
            data = {}
        print(json.dumps(response(data, Path(__file__).resolve().parents[1])))
    except (OSError, ValueError, TypeError):
        print("{}")
