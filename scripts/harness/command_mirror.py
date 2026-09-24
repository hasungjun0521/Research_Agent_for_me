#!/usr/bin/env python3
"""Render human-readable mirrors for structured command state."""

from __future__ import annotations

from pathlib import Path

GENERATED_START = "<!-- BEGIN GENERATED COMMAND QUEUE MIRROR -->"
GENERATED_END = "<!-- END GENERATED COMMAND QUEUE MIRROR -->"
LEGACY_PRESERVE_HEADINGS = (
    "\n## Hooked Next Actions:",
    "\n## Manual Next Actions",
    "\n## Manual Notes",
    "\n## Preserved Previous Next Action Notes",
)


def markdown_cell(value: object) -> str:
    text = str(value or "").replace("\n", " ").strip()
    return text.replace("|", "\\|") or "-"


def markdown_list(values: object) -> str:
    if not isinstance(values, list) or not values:
        return "-"
    return ", ".join(f"`{value}`" if "/" in str(value) else str(value) for value in values)


def render_next_actions(project: str, queue: dict) -> str:
    active_statuses = {"open", "in progress", "blocked", "deferred"}
    commands = [
        command for command in queue.get("commands", [])
        if str(command.get("status") or "").strip().lower() in active_statuses
    ]
    lines = [
        GENERATED_START,
        "# Next Actions",
        "",
        "This file is the human-readable mirror of the next work. The structured command",
        "queue lives in `state/command_queue.json` and should be updated by agents",
        "through harness CLIs.",
        "",
        "Actions should be understandable without opening file paths. Use file paths for",
        "traceability, not as the explanation of the task.",
        "",
        "## Immediate Next Actions",
        "",
        "| Command | Action | Owner Agent | Depends On | Parallel Group | Required Inputs | Expected Outputs | Priority | Status | Done When |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    if commands:
        for command in commands:
            action = command.get("display_summary") or command.get("action") or ""
            lines.append(
                f"| {markdown_cell(command.get('id'))} | "
                f"{markdown_cell(action)} | "
                f"{markdown_cell(command.get('owner_agent'))} | "
                f"{markdown_cell(markdown_list(command.get('depends_on')))} | "
                f"{markdown_cell(command.get('parallel_group'))} | "
                f"{markdown_cell(markdown_list(command.get('required_inputs')))} | "
                f"{markdown_cell(markdown_list(command.get('expected_outputs')))} | "
                f"{markdown_cell(command.get('priority'))} | "
                f"{markdown_cell(command.get('status'))} | "
                f"{markdown_cell(command.get('done_when'))} |"
            )
    else:
        lines.append("| - | No active queued work. | - | - | - | - | - | - | - | - |")
    lines.extend([
        "",
        "## Suggested Prompt",
        "",
        "```text",
        f"Continue project {project} from file state.",
        "",
        f"First run `python -m scripts.commands.projects.project_resume --project {project}`",
        "and read the source files it lists.",
        "",
        "Read HANDOFF.md, state/current_state.md, state/project_health.md,",
        "state/state_doctor.md, state/agent_memory.md, state/next_actions.md,",
        "state/open_questions.md, and state/command_queue.json.",
        "",
        "If project_health.md or state_doctor.md is missing, still starter-level,",
        "or older than recent project progress, refresh dashboard-free diagnostics",
        "before choosing the next action. Refresh state doctor first, then project",
        "health, so health routing uses the latest state diagnosis.",
        "If safe starter repair is needed, preview with `state_doctor --dry-run-repair`",
        "before applying `state_doctor --repair`.",
        "",
        "First inspect parallel work with",
        "`python -m scripts.commands.agents.agent_orchestrator status-parallel --project " + project + "`.",
        "If several independent open commands can be handled by different owner agents,",
        "use `python -m scripts.commands.agents.agent_orchestrator parallel --project " + project + " --max-agents <n> --write`.",
        "Explicit `parallel --id` requests should fail with a concrete reason instead of silently skipping unsafe commands.",
        "If prompts were already written and commands are `in progress`, inspect them",
        "with `run-prepared --dry-run`, run only a ready scoped group with `run-prepared --group <group> --runner-command ...`,",
        "then close reviewed batches with `finish-parallel --dry-run` and `finish-parallel --group <group> --status done --note ...`.",
        "Otherwise pick the single most important serial action and execute it. Use",
        "harness CLIs yourself for structured state updates. Save meaningful progress",
        "to files during the pass with",
        "`python -m scripts.commands.review.progress_checkpoint record` when results,",
        "blockers, direction changes, failed assumptions, experiment outcomes, memory",
        "notes, or next-action changes appear.",
        "```",
        "",
        "## Status Values",
        "",
        "Use `open`, `blocked`, `in progress`, `done`, or `deferred`.",
        "",
        "## Update Rule",
        "",
        "Update this mirror through `python -m scripts.commands.review.command_queue`;",
        "do not hand-edit it as the source of truth.",
        "",
        GENERATED_END,
    ])
    return "\n".join(lines)


def generated_block(text: str) -> str | None:
    if GENERATED_START not in text or GENERATED_END not in text:
        return None
    before_end = text.split(GENERATED_START, 1)[1]
    generated = before_end.split(GENERATED_END, 1)[0]
    return f"{GENERATED_START}{generated}{GENERATED_END}"


def preserve_existing_notes(existing: str) -> str:
    if not existing.strip():
        return ""
    if GENERATED_START in existing and GENERATED_END in existing:
        before, rest = existing.split(GENERATED_START, 1)
        _, after = rest.split(GENERATED_END, 1)
        preserved = "\n\n".join(part.strip() for part in (before, after) if part.strip())
        return f"\n\n{preserved}\n" if preserved else ""
    if existing.lstrip().startswith("# Next Actions") and "## Immediate Next Actions" in existing:
        indexes = [existing.find(heading) for heading in LEGACY_PRESERVE_HEADINGS if existing.find(heading) >= 0]
        if not indexes:
            return ""
        return "\n\n" + existing[min(indexes):].strip() + "\n"
    return "\n\n## Preserved Previous Next Action Notes\n\n" + existing.strip() + "\n"


def generated_mirror_matches(existing: str, project: str, queue: dict) -> bool:
    rendered = render_next_actions(project, queue)
    return (generated_block(existing) or existing.strip()) == rendered.strip()


def sync_next_actions(root: Path, queue: dict) -> None:
    path = root / "state" / "next_actions.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    path.write_text(render_next_actions(root.name, queue) + preserve_existing_notes(existing), encoding="utf-8")
