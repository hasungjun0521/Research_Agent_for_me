# Agent Status Protocol

Use this protocol whenever an agent performs project work. Dashboard is not
required and should be considered off by default.

## Status File

Each project has:

`state/agent_status.json`

The loop-level summary also reads:

`state/loop_summary.json`

Agent-to-agent requests and responses live in:

`state/agent_messages.json`

The reader-facing project report lives in:

`09_report/`

`state/agent_status.json` provides the current agent visibility:

- which role agents exist,
- which agents are currently running,
- how many agents are active,
- what each agent is working on,
- recent input and output files.

`state/loop_summary.json` provides the loop recap:

- what this loop tried to do,
- what work was completed,
- what result was observed,
- what the next actions are.

## Status Values

Use these values:

- `idle`: agent is available but not currently working.
- `running`: agent is actively working.
- `waiting`: agent is waiting for user input, files, data, or another agent.
- `blocked`: agent cannot proceed because a required input or decision is missing.
- `done`: agent completed its assigned task.

`running` agents are treated as active in state summaries.

## Mandatory Status Updates

**EVERY role: set status `running` BEFORE active work starts and heartbeat at
least every 5-10 minutes. This is not optional even though the individual role
prompts cite the `agent_status` CLI only generically — this file is the shared,
canonical lifecycle reference behind that generic citation, so treat it as a
required read whenever a role prompt points at `agent_status` updates.**

`state/agent_status.json` is the file-based status source of truth. Every agent
pass must update the existing entry for that agent.

- Do not hand-edit `state/agent_status.json`; use `python -m scripts.commands.agents.agent_status ...`.
- Before active work starts, set that agent to `running`.
- During long-running work, update `updated_at` and `current_task` whenever the task meaningfully changes or at least every 5-10 minutes.
- When a meaningful result, blocker, direction change, or failed assumption
  appears, record it immediately with
  `python -m scripts.commands.review.progress_checkpoint record`. Use status
  heartbeat only for liveness updates. Do not wait until final response.
- After the pass ends, set the status to `done`, `waiting`, `blocked`, or `idle`.
- Do not append duplicate agent objects. Update the existing object whose `name` matches the agent role.
- Only add a new object when a genuinely new agent role is introduced.
- If work continues in an external terminal, tmux session, or separate process, leave the owning agent as `running` and record the execution location in `notes`.
- If a run crashes or becomes stale, the next coordinating pass should set the owner to `blocked` or `waiting` with a short note.

## Mandatory Loop Summary Updates

`state/loop_summary.json` is the file-based one-screen loop recap.

- Do not hand-edit `state/loop_summary.json`; use `python -m scripts.commands.review.loop_summary ...`.
- At the start of a loop, run `loop_summary.py start` with a concrete `--loop-id` and `--goal`.
- During an active loop, run `loop_summary.py update` when the one-line summary
  text changes.
- When a command finishes, record it with `loop_summary.py add-work` and include the command id, owner, result, and output files.
- When the loop produces a finding, record it with `loop_summary.py add-result` and cite evidence files.
- Before ending the loop, record the next concrete actions with `loop_summary.py add-next`.
- `add-next --action` must be understandable as prose. Put file paths in `--output`, and put the reason or done condition in `--note`.
- At the end of a loop, run `loop_summary.py finish` with `--summary` and `--outcome`. Use `--status blocked` or `--status waiting` when the loop did not complete.
- A loop is not complete if there is no clear statement of what changed, the
  result, and the next action.
- When work changes active code, experiment state, working analysis, or drafts,
  include the relevant working-folder outputs (`03_experiments/`, `04_code/`,
  `05_results/`, or `06_writing/`) in status. Include `09_report/` outputs only
  when final reader-facing or release-facing artifacts actually change.
- When work changes an experiment-backed claim, include the relevant preregistration, reproducibility manifest, robustness, or reviewer attack matrix file in status outputs.
- When an agent needs another agent's decision, review, or unblock action, record it with `python -m scripts.commands.agents.agent_messages send` and keep the message unresolved until the recipient responds.
- Follow `config/workspace_profile.local.json:agent_output.preferred_language` for
  loop summaries, results, and next-action notes where practical.

## Filesystem Safety Updates

- Do not delete, move, overwrite, or recursively clean any directory outside the active project folder.
- Record cleanup as status work only after confirming the cleanup target is inside the active project folder.
- If a cleanup target is outside the active project folder, stop and mark the task `blocked` or `waiting` for user direction.

## CLI Usage

Start an agent pass:

```bash
python -m scripts.commands.agents.agent_status start --project <project> --agent <agent_name> --task "<current task>" --stage "<stage>" --input <path>
```

Record a heartbeat:

```bash
python -m scripts.commands.agents.agent_status heartbeat --project <project> --agent <agent_name> --task "<current task>" --note "<progress note>" --append-note
```

Record a hook-visible activity update:

```bash
python -m scripts.commands.agents.agent_events record --project <project> --agent <agent_name> --task "<current activity>" --note "<progress note>" --sync-status
```

Record a durable research progress checkpoint:

```bash
python -m scripts.commands.review.progress_checkpoint record --project <project> --agent <agent_name> --kind result --summary "<what changed>" --evidence <path> --output <path> --memory "<durable lesson>" --next-action "<next action>"
```

Record an experiment outcome checkpoint:

```bash
python -m scripts.commands.review.progress_checkpoint record --project <project> --agent code_agent --kind experiment_result --exp-id <exp_id> --summary "<observed result>" --evidence 03_experiments/<exp_id>/run_log.md --output 03_experiments/<exp_id>/results/ --rationale "<why this run was needed>" --dataset "<dataset/split>" --method "<method>" --baseline-id "<baseline>" --result-analysis "<why performance improved/regressed/stayed flat>" --run-status succeeded --result-path 03_experiments/<exp_id>/results/
```

Record a usage-limit continuation handoff when the five-hour or weekly remaining
usage is below 5%:

```bash
python -m scripts.commands.review.progress_checkpoint limit-handoff --project <project> --agent <agent_name> --summary "<what this session changed>" --five-hour-remaining-pct <pct> --weekly-remaining-pct <pct> --in-progress "<current work>" --next-action "<resume step>" --memory "<durable lesson>"
```

Finish an agent pass:

```bash
python -m scripts.commands.agents.agent_status finish --project <project> --agent <agent_name> --command-id <command_id> --status done --output <path> --note "<result>"
```

The CLI refuses to mark an agent `done` when it still owns open or in-progress commands unless the pass explicitly completes a command with `--command-id` or uses `--allow-open-commands`.

Validate the state files:

```bash
python -m scripts.commands.projects.validate_project --project <project>
```

Start and finish a loop:

```bash
python -m scripts.commands.review.loop_summary start --project <project> --loop-id <loop_id> --goal "<goal>"
python -m scripts.commands.review.loop_summary update --project <project> --summary "<current loop summary>"
python -m scripts.commands.review.loop_summary add-work --project <project> --id <command_id> --action "<completed action>" --owner <agent_name> --result "<result>" --output <path>
python -m scripts.commands.review.loop_summary add-result --project <project> --title "<result title>" --status done --summary "<result summary>" --evidence <path>
python -m scripts.commands.review.loop_summary add-next --project <project> --action "<next action>" --owner <agent_name> --priority high --output <path>
python -m scripts.commands.review.loop_summary finish --project <project> --status done --summary "<what changed>" --outcome "<result>"
```

## Optional Dashboard Visibility Behavior

- If using dashboard, directly opening `dashboard/index.html` and selecting a
  folder is snapshot mode; browser file selection does not automatically watch
  file changes.
- If using dashboard, `python -m scripts.commands.agents.agent_dashboard --project <name>`
  is live server mode; the browser refreshes from `/api/status` every 5 seconds.
- In both modes, dashboard visibility reflects the same file state used by
  Claude/Codex continuation. Work is not visible in optional status surfaces
  until the owning agent entry is marked `running`.
- Durable research-content updates should use
  `scripts/commands/review/progress_checkpoint.py record`. It updates current
  state, optional memory/next-action/open-question files, optional experiment
  run logs, agent status, and the event timeline.
- Lightweight activity-only updates may use
  `scripts/commands/agents/agent_events.py record`. Pass `--sync-status` when
  the update should also refresh `state/agent_status.json`. Optional dashboard
  views may render that same file state when dashboard mode is enabled, but the
  file state is the source of truth. Finish events should be recorded as
  `status=done` instead of left as running activity. If a hook syncs
  `status=done`, pass the completed `--command-id` or use
  `scripts/commands/agents/agent_status.py finish`; hook CLIs must not bypass
  the open-command completion gate.
- Completed work and loop outcomes only show when `state/loop_summary.json` is updated. `state/command_queue.json` is still used for active command ownership.
- Agent-to-agent coordination only shows when `state/agent_messages.json` is updated.

## Update Rules

Before starting an agent task:

1. Set that agent's `status` to `running`.
2. Set `current_task` to the concrete task.
3. Set `stage` to the workflow stage.
4. Set `started_at` and `updated_at`.
5. List the files being read in `last_input_files`.
6. Record execution context in `notes` when relevant, such as tmux session, SLURM job, notebook, or external process.

After completing an agent task:

1. Set `status` to `done`, `waiting`, `blocked`, or `idle`.
2. Update `current_task` with the result or next expected task.
3. Set `updated_at`.
4. List the changed files in `last_output_files`.
5. Add short notes when the status is `waiting` or `blocked`.

## Timestamp Format

Use ISO-like timestamps:

`YYYY-MM-DDTHH:MM:SS+09:00`

Adjust the timezone if your local workflow uses another timezone.

## Manual Example

```json
{
  "name": "literature_reviewer",
  "status": "running",
  "current_task": "Review core baseline papers for the first contribution claim.",
  "stage": "literature",
  "started_at": "2026-05-09T13:30:00+09:00",
  "updated_at": "2026-05-09T13:30:00+09:00",
  "last_input_files": [
    "00_brief/contribution_candidates.md",
    "01_literature/papers.bib"
  ],
  "last_output_files": [
    "01_literature/related_work_matrix.md",
    "01_literature/gap_analysis.md"
  ],
  "notes": ""
}
```
