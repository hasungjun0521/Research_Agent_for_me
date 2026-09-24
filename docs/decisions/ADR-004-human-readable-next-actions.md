# ADR-004: Store Human-Readable Next Action Metadata

## Status
Accepted

## Date
2026-05-10

## Context
The dashboard originally rendered next actions mostly from `action`, `owner_agent`, `priority`, and `expected_outputs`. Later, file-state continuation through Claude/Codex and `scripts/commands/projects/project_resume.py` made the same problem visible outside the dashboard: when `expected_outputs` contained paths such as `03_experiments/exp_001/run_log.md`, the state was technically accurate but hard for a human or agent to understand at a glance.

## Decision
Command queue entries and loop next actions may include:

- `display_summary`: what the task means in plain language.
- `why_now`: why this is the next useful task.
- `done_when`: what completion looks like.

`expected_outputs` and `output_files` remain traceability fields, not the main explanation. User-facing summaries such as `project_resume` display the human-readable fields first and keep raw paths available through details. The optional dashboard follows the same principle when enabled.

## Consequences

- File-state continuation can answer "what should happen next?" without making
  the user decode file paths.
- Existing projects still work because support surfaces can fall back to
  path-based summaries when the new fields are missing.
- `scripts/commands/projects/migrate_project.py` can add starter metadata to old projects without overwriting research files.
- Agents and directors must write next actions for humans first and file paths second.
