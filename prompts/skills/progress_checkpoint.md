# Progress Checkpoint

Use this skill during any multi-step research pass when an important result,
blocker, direction change, failed assumption, experiment outcome, memory note,
or next action appears before the final response.

## Procedure

For a general research-content checkpoint:

```bash
python -m scripts.commands.review.progress_checkpoint record --project <project> --agent <agent_name> --kind result --summary "<what changed>" --evidence <path> --output <path> --memory "<durable lesson>" --next-action "<next action>"
```

For an experiment outcome:

```bash
python -m scripts.commands.review.progress_checkpoint record --project <project> --agent code_agent --kind experiment_result --exp-id <exp_id> --summary "<observed result>" --evidence 03_experiments/<exp_id>/run_log.md --output 03_experiments/<exp_id>/results/ --rationale "<why this run was needed>" --dataset "<dataset/split>" --method "<method>" --baseline-id "<baseline>" --result-analysis "<why performance improved/regressed/stayed flat>" --run-status succeeded --result-path 03_experiments/<exp_id>/results/
```

For usage-limit handoff when five-hour or weekly remaining usage is below 5%:

```bash
python -m scripts.commands.review.progress_checkpoint limit-handoff --project <project> --agent <agent_name> --summary "<what this session changed>" --five-hour-remaining-pct <pct> --weekly-remaining-pct <pct> --in-progress "<current work>" --next-action "<resume step>" --memory "<durable lesson>"
```

## What It Updates

- `state/progress_hooks.jsonl`
- `state/sessions/progress_log.md`
- `state/current_state.md`
- `state/agent_status.json`
- `state/agent_events.jsonl`
- `state/agent_memory.md` when `--memory` is provided
- `state/next_actions.md` when `--next-action` is provided
- `state/open_questions.md` when `--open-question` is provided
- `03_experiments/<exp_id>/run_log.md` and `run_state.json` when `--exp-id`
  is provided
- `03_experiments/<exp_id>/analysis.md` when `--kind experiment_result` and
  `--exp-id` are provided
- `05_results/experiment_journal.md` and `05_results/experiment_journal.csv`
  when `--kind experiment_result` and `--exp-id` are provided
- `03_experiments/artifact_registry.csv` and `03_experiments/data_roots.md`
  when the final experiment completion workflow records artifacts or data roots
- `state/limit_handoff.md` when `limit-handoff` triggers below the configured
  threshold

## Keeping Memory Bounded

`--memory` appends a `## Memory Checkpoint:` block to `state/agent_memory.md`,
which is read at every resume. When that file accumulates many old blocks,
compact it so it stops taxing context:

```bash
python -m scripts.commands.review.memory_compact --project <name>          # preview
python -m scripts.commands.review.memory_compact --project <name> --apply  # archive old blocks
```

Old checkpoints move verbatim to `state/sessions/memory_archive.md`; curated
header sections and the most recent checkpoints stay in the live file.

## Guardrails

- Use `agent_status heartbeat` for liveness-only updates.
- Use this checkpoint for durable research content that a later agent must see.
- Do not mark `--status done` while the agent owns open commands unless a
  specific `--command-id` is being completed or the exception is explicit.
- Keep evidence and output paths project-relative.
