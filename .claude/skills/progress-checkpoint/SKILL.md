---
name: progress-checkpoint
description: Persist durable mid-pass research progress before the final response. Use during any long/multi-step pass as soon as there is a meaningful result, blocker, direction change, failed assumption, experiment outcome, memory note, or next action — don't wait until the end. Also use limit-handoff when five-hour or weekly usage remaining drops below 5%. Wraps scripts.commands.review.progress_checkpoint.
---

# Progress Checkpoint

Durable mid-pass persistence so a later agent (or a fresh session) sees results,
blockers, and next actions without chat history. Source: `prompts/skills/progress_checkpoint.md`.

## When to use

- A result, blocker, direction change, failed assumption, experiment outcome,
  durable lesson, or next action appears mid-pass.
- Five-hour or weekly usage remaining is below 5% → `limit-handoff`.
- NOT for liveness-only updates — use `agent_status heartbeat` for those.

## Commands

General research checkpoint:
```bash
python -m scripts.commands.review.progress_checkpoint record \
  --project <project> --agent <agent_name> --kind result \
  --summary "<what changed>" --evidence <path> --output <path> \
  --memory "<durable lesson>" --next-action "<next action>"
```

Experiment outcome:
```bash
python -m scripts.commands.review.progress_checkpoint record \
  --project <project> --agent code_agent --kind experiment_result \
  --exp-id <exp_id> --summary "<observed result>" \
  --evidence 03_experiments/<exp_id>/run_log.md \
  --output 03_experiments/<exp_id>/results/ \
  --rationale "<why this run was needed>" --dataset "<dataset/split>" \
  --method "<method>" --baseline-id "<baseline>" \
  --result-analysis "<why performance improved/regressed/stayed flat>" \
  --run-status succeeded --result-path 03_experiments/<exp_id>/results/
```

Usage-limit handoff (below 5% remaining):
```bash
python -m scripts.commands.review.progress_checkpoint limit-handoff \
  --project <project> --agent <agent_name> --summary "<what this session changed>" \
  --five-hour-remaining-pct <pct> --weekly-remaining-pct <pct> \
  --in-progress "<current work>" --next-action "<resume step>" --memory "<durable lesson>"
```

If `config/workspace_profile.local.json` defines `agent_limits.status_command`,
prefer `progress_checkpoint check-limits` over interactive status probing.

## Guardrails

- Keep evidence/output paths project-relative.
- Do not mark `--status done` while the agent owns open commands unless a
  specific `--command-id` is being completed.
