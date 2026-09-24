# Experiment Repair

Use this skill when an experiment fails, stalls, succeeds without result
artifacts, or has unclear next steps.

## Procedure

```bash
python -m scripts.commands.experiments.experiment_diagnosis --project <project> --write-report
python -m scripts.commands.experiments.run_state set --project <project> --exp-id <exp_id> --status blocked --note "<diagnosis>"
```

Then either:

- repair and retry with the smallest reproducible command,
- mark the run as failed with a clear cause, or
- abandon the run and record why it should not support a claim.

## Guardrails

- Never hide failed runs.
- Do not rerun expensive GPU jobs before a smoke reproduction.
- Attach the diagnosis to `03_experiments/<exp_id>/run_log.md` or
  `run_state.json` through scripts.
