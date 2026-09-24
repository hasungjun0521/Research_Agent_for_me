# Research Leader Dispatch Protocol

Use this protocol when a director or lead-style agent decomposes work for other
agents. The goal is to make handoffs parseable, resumable, and small enough for
fresh-context runs.

## Proactive Parallelization Default

Lead-style agents should look for safe worker decomposition by default when the
task is deep, broad, or naturally parallel. Do this even when the user did not
explicitly ask for multi-agent work. Keep the critical path local, then dispatch
sidecar workers only when their inputs, outputs, dependencies, and ownership are
clear enough to run independently.

Do not dispatch workers when the work has unresolved dependencies, overlapping
write paths, unapproved vote gates, missing expected outputs, or a vague done
condition. In those cases, return `manual_required` or `blocked`, or create a
single serial next action with the blocker recorded.

## Role Boundary

- The director selects the next workflow step, checks routing and risk, and keeps
  state coherent (including optional support summaries when dashboard mode is enabled).
- Lead-style agents plan, route, and synthesize. They may write plans,
  summaries, or review notes, but should not silently perform broad execution
  work that belongs to a worker command.
- Worker agents execute one concrete task from a plan or command. They should
  not spawn other agents or invent a new route. If the route is wrong, they
  return `blocked` or ask through `state/agent_messages.json`.

## Required Lead Output

Every lead-style pass that routes follow-up work should end with exactly one
dispatch block:

```text
=== LEADER DISPATCH ===
type: dispatch_workers

workers:
  - name: code_agent
    command_id: cmd_003
    depends_on: cmd_001
    parallel_group: 1
    expected_outputs: 03_experiments/exp_001/run_log.md, 05_results/experiment_journal.md
    prompt: |
      Run the preregistered smoke experiment and record the result.
next_turn_expects: Worker result blocks with evidence paths and blockers.
plan_file: state/sessions/session_id/plans/experiment_plan.md
risk_level: high
confidence: MEDIUM
=== END LEADER DISPATCH ===
```

Supported `type` values:

- `dispatch_workers`: request one or more worker commands.
- `complete`: finish the lead pass and optionally name the next lead or owner.
- `manual_required`: stop automation because a human decision is needed.
- `blocked`: stop because a required file, result, permission, or dependency is
  missing.

## Dispatch Fields

For `dispatch_workers`, include:

- `workers`: one or more worker entries.
- `workers[].name`: an existing research agent role such as `literature_reviewer`,
  `experiment_designer`, `code_agent`, `data_analyst`, `result_interpreter`,
  `writing_agent`, `venue_reviewer`, or `critic`.
- `workers[].command_id`: the command queue id when one exists.
- `workers[].depends_on`: command ids that must be `done` before this worker is
  dispatchable. Use `none` only when there is no dependency.
- `workers[].parallel_group`: workers with the same group may run in parallel if
  their write sets do not overlap.
- `workers[].expected_outputs`: substantive working artifacts the worker should
  produce. Do not use only generic checkpoint files such as
  `state/current_state.md` or `state/next_actions.md`.
- `workers[].prompt`: the self-contained worker instruction.
- `next_turn_expects`: what the lead expects when results are returned.
- `plan_file`: the project-relative plan or session file the worker must read.
- `risk_level`: `low`, `medium`, `high`, or `critical`.
- `confidence`: `HIGH`, `MEDIUM`, or `LOW`.

For `complete`, include:

```text
=== LEADER DISPATCH ===
type: complete

result_file: 07_reviews/research_audit.md
handoff_to: writing_agent
handoff_context: |
  Use the audit findings to revise the paper claims.
status: resolved
=== END LEADER DISPATCH ===
```

For `manual_required`, include `reason` and the best available
`partial_result_file`. For `blocked`, include `blocked_by` and
`retry_suggestion`.

## Worker Result Contract

Workers that were dispatched from a leader should return a compact result block:

```text
=== WORKER RESULT ===
status: OK
confidence: HIGH
summary: Smoke run completed and produced a final result table.
files_read: state/command_queue.json, 03_experiments/exp_001/preregistration.md
files_updated: 03_experiments/exp_001/run_log.md, 05_results/tables/exp_001_results.csv
evidence: 05_results/tables/exp_001_results.csv
blockers: none
next: Ask result_interpreter to update working claim evidence and export final report rows only when stable.
=== END WORKER RESULT ===
```

Use `status: BLOCKED` when evidence or permissions are missing, and use
`status: FAIL` when verification ran but failed.

## Resume Rule

If a worker result is short, pass it inline to the lead on the next turn. If the
combined result text is large, write it under `state/sessions/<id>/` and pass a
three-line summary plus the file path. State must persist through files, not
chat memory.
