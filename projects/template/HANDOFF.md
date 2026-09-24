# Project Handoff: {{PROJECT_NAME}}

Use this file as the project-local continuity document. The repository root
`HANDOFF.md` is for harness maintenance; this file is for the research project.

## Current Goal

Turn the user's initial idea into a concrete research question, motivation,
assumptions, constraints, and first next action.

## Completed Since Last Handoff

- Project folder initialized from `projects/template`.
- Reader-facing final artifact folders are initialized under `09_report/`.
- File-based agent state is initialized under `state/`.
- No literature review, baseline selection, experiment, or result analysis has
  been completed yet.

## Files To Read First

- `README.md`
- `state/current_state.md`
- `state/project_health.md`
- `state/state_doctor.md`
- `state/agent_memory.md`
- `state/next_actions.md`
- `state/open_questions.md`
- `state/command_queue.json`
- If multiple independent command-queue entries are ready, ask the agent to use
  `scripts.commands.agents.agent_orchestrator parallel` before falling back to a
  serial next command.

Read additional files only when they are needed for the current task. Read
`09_report/README.md` before final export, report hygiene, packaging, or
reader-facing review work.

## Validation Status

- Latest project-specific validation: not yet run after project creation.
- Ask the agent to validate the project after setup or a substantial pass.

## Remaining Blockers

- Research question and motivation are not yet specific.
- User constraints, target dataset, target audience, and expected contribution
  are not yet confirmed.
- No baseline, metric, dataset registry entry, or first experiment has been
  selected.
- Dashboard-free health and state doctor reports are starter files until the
  first agent pass refreshes them.

## Next Best Command

Ask Claude/Codex to continue the project from file state and execute the next
highest-value action. The user should not need to run a shell command directly;
the agent should use harness CLIs itself.

## Next Best Prompt

Paste this from the repository root into Claude Code, Codex, or another coding
agent:

```text
Continue project {{PROJECT_NAME}} from file state.

First use the project resume helper yourself, then read the source files it
lists. Do not ask the user to run it manually.

Read:
- projects/{{PROJECT_NAME}}/HANDOFF.md
- projects/{{PROJECT_NAME}}/state/current_state.md
- projects/{{PROJECT_NAME}}/state/project_health.md
- projects/{{PROJECT_NAME}}/state/state_doctor.md
- projects/{{PROJECT_NAME}}/state/agent_memory.md
- projects/{{PROJECT_NAME}}/state/next_actions.md
- projects/{{PROJECT_NAME}}/state/open_questions.md
- projects/{{PROJECT_NAME}}/state/command_queue.json

If `state/project_health.md` or `state/state_doctor.md` is missing, still a
starter file, or older than recent project progress, refresh dashboard-free
diagnostics before choosing the next action. Refresh state doctor first, then
project health, so the health report can route from the latest state diagnosis.

Choose the highest-value next work. If multiple independent command-queue
entries can be handled by different owner agents, use
`scripts.commands.agents.agent_orchestrator status-parallel` to inspect the
batch, then use `scripts.commands.agents.agent_orchestrator parallel`;
otherwise execute one serial next action. Explicit `parallel --id` requests
should fail with a concrete reason instead of silently skipping unsafe commands.
If parallel prompts were already
written and their commands are `in progress`, inspect them with
`scripts.commands.agents.agent_orchestrator run-prepared --dry-run`, then run
the scoped group with `run-prepared --group <group> --runner-command ...` only
after dependencies are done.
After reviewing worker outputs, close the scoped batch with
`scripts.commands.agents.agent_orchestrator finish-parallel --dry-run`, then
`finish-parallel --group <group> --status done --note ...` or
`--result-file <command_id>=<worker-result-path>`.

Use the harness CLIs yourself for structured state updates. Do not only tell me
which Python commands to run. Save important progress to project files during
the pass whenever there is a result, blocker, direction change, failed
assumption, experiment outcome, or next-action change. Use
`python -m scripts.commands.review.progress_checkpoint record` for those
mid-pass checkpoints.

At the end, update HANDOFF.md with what changed, validation status, remaining
blockers, and the next best prompt.
```

## First Pass Suggestion

If the user has not provided a full brief yet, start with:

```text
Use the motivation_planner role for {{PROJECT_NAME}}.

Clarify the research question, motivation, assumptions, constraints, and
candidate contribution from the user's idea. Update 00_brief/, state files, and
HANDOFF.md. Record missing information in state/open_questions.md instead of
guessing.
```

## Operating Notes

- The user operates through Claude/Codex. The agent should run required harness
  CLIs itself.
- Do not hand-edit project state JSON; use harness CLIs for structured status,
  command queue, messages, votes, experiment run state, and summaries.
- Use `scripts.commands.review.progress_checkpoint record` when mid-pass
  research content needs to land in current state, memory, next actions, open
  questions, progress logs, or experiment run logs.
- Use the project health report when deciding the next action without the
  dashboard. Use state doctor when state files look stale or contradictory.
- Use the brief intake workflow when the user's idea is rough and should be
  converted into durable brief files plus open questions.
- Keep `09_report/` final-artifact-facing. Scratch notes, raw logs,
  diagnostics, and intermediate output belong in working folders or
  `state/sessions/`.
- Keep active experiment/research code in `04_code/`. Export only cleaned,
  stable, release-facing code to `09_report/src/`.
- Keep cloned baseline GitHub/source repositories under
  `08_baselines/source_snapshots/<baseline_id>/`, inspect them through
  `08_baselines/structure_reports/`, and use
  `08_baselines/code_structure_plan.md` before shaping substantial project code.
- GPU/server rules belong in `config/workspace_profile.local.json` at the
  repository root. Expensive GPU work needs a smoke test and scheduler plan
  before launch. Queue independent experiments first and use the scheduler
  dispatch path so available GPUs can run multiple safe jobs in parallel within
  the configured cap.
- If a smoke test is CPU-heavy, queue it as a bounded GPU smoke job instead of
  saturating CPU resources.
- Keep experiment data roots and split/version identifiers in
  `03_experiments/data_roots.md`.
- Before launching a new experiment family, create a smoke-first experiment DAG
  and identify independent main-run nodes that can run in parallel on available
  GPUs.
- After each experiment finishes, analyze why performance improved, regressed,
  or stayed flat and record the result in `05_results/experiment_journal.md`
  plus `05_results/experiment_journal.csv`.
- Before strengthening claims, build or refresh the working claim graph in
  `05_results/`.
- After cloned baseline source snapshots exist, refresh the baseline comparison
  before shaping substantial `04_code/src/` structure.
- Use agent quality audit when checking whether previous agent passes left
  enough durable file evidence for a fresh session to resume.
- Keep paper terminology consistent through `06_writing/terminology.md`.
