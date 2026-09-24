---
name: project-resume
description: Resume or triage a research project under projects/<name>/. Use at the START of any continuation pass, or when the user asks "what's left", "is this project healthy", "pick up where we left off", or when project state looks stale/contradictory/hard-to-resume. Runs project_resume, then state_doctor (file-state consistency) and project_health (research-progress next action) — dashboard-free.
---

# Project Resume & Triage

Entrypoint for picking up project-local work in this file-based research workspace.
Wraps the dashboard-free resume + diagnostic surfaces. Source runbooks:
`prompts/skills/state_doctor.md`, `prompts/skills/project_health.md`.

## When to use

- Starting a new continuation session on an existing `projects/<name>/`.
- User asks what is left, what to do next, or whether the project is healthy.
- State files look stale, contradictory, or hard to resume.
- Health/state-doctor reports are older than recent project progress.

## Workflow

1. Resume context first:
   ```bash
   python -m scripts.commands.projects.project_resume --project <name>
   ```
   Also read `projects/<name>/HANDOFF.md`, `state/current_state.md`,
   `state/agent_memory.md`, `state/next_actions.md` before deciding.

2. If state looks inconsistent OR the reports are stale, refresh diagnostics —
   **state doctor first, project health second** (so health routing uses the
   latest state diagnosis):
   ```bash
   python -m scripts.commands.projects.state_doctor --project <name> --write-report
   python -m scripts.commands.projects.project_health --project <name> --write
   ```
   (`--write-report` is required for state doctor to refresh
   `state/state_doctor.md`; without it the diagnosis is print-only.)

3. Treat critical/high issues as the default next action unless the user overrides.

4. If a starter/placeholder report is detected, do not trust it as evidence —
   refresh it before routing.

5. If diagnostic findings should become routed work, preview the suggested
   command entries (dry-run) first, then enqueue through the harness. Do NOT
   hand-edit `state/command_queue.json`. Doctor commands use a `doctor_` id
   prefix, health commands a `health_` prefix.

6. When state-doctor repair is needed, preview repairs before applying unless
   the user explicitly asks to write immediately. Repair must not invent
   research content (datasets, metrics, baselines, results, conclusions).

## Guardrails

- Use harness CLIs for all structured JSON state; never hand-edit status/queue JSON.
- `state/project_health.md` and `state/state_doctor.md` are working diagnostics,
  not `09_report/` artifacts — do not export them.
