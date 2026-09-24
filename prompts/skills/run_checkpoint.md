# Run Checkpoint

Use this skill before a risky refactor, a long autonomous loop, a major
experiment rerun, or a handoff where replay/fork context matters.

## Procedure

```bash
python -m scripts.commands.experiments.run_checkpoint create --project <project> --id <checkpoint_id> --label "<short label>" --note "<why now>"
python -m scripts.commands.experiments.run_checkpoint list --project <project>
python -m scripts.commands.experiments.run_checkpoint audit --project <project>
```

`create` records director lifecycle status/events by default. Add
`--agent <role>` when another role owns the checkpoint.

## Guardrails

- Checkpoints are lightweight snapshots for review and fork planning; they do
  not restore files automatically.
- Do not store large datasets, checkpoints, or logs in checkpoint files.
- Create a checkpoint before using the legacy Ralph loop, and only use that
  loop when the user explicitly requests it.
