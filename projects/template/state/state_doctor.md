# State Doctor

This state doctor report has not been generated yet.

## Purpose

Use this file when project state looks stale, contradictory, or hard to resume.
It should identify missing files, stale command/agent state, incomplete result
ledgers, missing experiment analysis, unresolved data roots, and baseline/code
structure gaps.

## Initial Status

- No diagnosis has been run yet.

## Recommended Agent Requests

- Refresh state doctor when command queue, agent status, experiment evidence,
  GPU queue, or baseline/code structure state looks stale or contradictory.

## Suggested Command Queue Entries

| Owner Agent | Priority | Action | Expected Outputs |
| --- | --- | --- | --- |
| director | medium | Refresh state diagnostics and route stale or contradictory state to the responsible owner. | `state/state_doctor.md, state/project_health.md, state/next_actions.md` |

## Enqueue Preview

| Command ID | Owner Agent | Priority | Action | Expected Outputs |
| --- | --- | --- | --- | --- |
| - | - | - | No enqueue entries planned yet. Refresh state doctor with a dry-run enqueue preview first. | - |
