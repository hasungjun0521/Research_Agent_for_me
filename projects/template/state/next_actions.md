<!-- BEGIN GENERATED COMMAND QUEUE MIRROR -->
# Next Actions

This file is the human-readable mirror of the next work. The structured command
queue lives in `state/command_queue.json` and should be updated by agents
through harness CLIs.

Actions should be understandable without opening file paths. Use file paths for
traceability, not as the explanation of the task.

## Immediate Next Actions

| Command | Action | Owner Agent | Depends On | Parallel Group | Required Inputs | Expected Outputs | Priority | Status | Done When |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| cmd_001 | Turn the user's initial idea into a concrete research brief. | motivation_planner | - | - | User-provided research idea, `00_brief/research_question.md`, `00_brief/motivation.md` | `00_brief/research_question.md`, `00_brief/motivation.md`, `00_brief/problem_statement.md`, `00_brief/assumptions.md`, `00_brief/constraints.md`, `00_brief/contribution_candidates.md`, `state/current_state.md`, `state/agent_memory.md`, `state/next_actions.md`, `state/open_questions.md` | high | open | The brief states the research question, motivation, assumptions, constraints, candidate contribution, and missing information in project files. |
| cmd_002 | Choose the next research step after the brief is concrete. | director | cmd_001 | - | `00_brief/`, `state/current_state.md`, `state/agent_memory.md`, `state/next_actions.md`, `state/open_questions.md`, `state/command_queue.json` | `02_planning/director_plan.md`, `02_planning/decision_log.md`, `state/current_state.md`, `state/next_actions.md`, `state/command_queue.json`, `HANDOFF.md` | high | open | The plan, next actions, command queue, and HANDOFF name the next owner, purpose, and completion condition in plain language. |

## Suggested Prompt

```text
Continue project {{PROJECT_NAME}} from file state.

First use the project resume helper yourself
(`python -m scripts.commands.projects.project_resume --project {{PROJECT_NAME}}`)
and read the source files it lists. Do not ask the user to run it manually.

Read HANDOFF.md, state/current_state.md, state/project_health.md,
state/state_doctor.md, state/agent_memory.md, state/next_actions.md,
state/open_questions.md, and state/command_queue.json.

If state/project_health.md or state/state_doctor.md is still a starter file,
refresh dashboard-free health/state diagnostics before choosing the next action.

Pick the highest-value next work. If multiple independent command-queue entries
can be handled by different owner agents, use
`scripts.commands.agents.agent_orchestrator status-parallel`, then use
`scripts.commands.agents.agent_orchestrator parallel`; otherwise execute one
serial next action. Explicit `parallel --id` requests should fail with a
concrete reason instead of silently skipping unsafe commands. If parallel
prompts were already written and their commands
are `in progress`, inspect them with
`scripts.commands.agents.agent_orchestrator run-prepared --dry-run`, run the
scoped group with `run-prepared --group <group> --runner-command ...` only
after dependencies are done, and close
reviewed batches with `scripts.commands.agents.agent_orchestrator
finish-parallel --dry-run`, then `finish-parallel --group <group> --status done
--note ...` or `--result-file <command_id>=<worker-result-path>`. Use harness
CLIs yourself for structured state updates. Save
meaningful progress to files during the pass with
`python -m scripts.commands.review.progress_checkpoint record` when results,
blockers, direction changes, failed assumptions, experiment outcomes, memory
notes, or next-action changes appear.
```

## Status Values

Use `open`, `blocked`, `in progress`, `done`, or `deferred`.

## Update Rule

Update this mirror through `python -m scripts.commands.review.command_queue`;
do not hand-edit it as the source of truth.

<!-- END GENERATED COMMAND QUEUE MIRROR -->
