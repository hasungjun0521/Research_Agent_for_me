# Run Checkpoints

Use `python -m scripts.commands.experiments.run_checkpoint create --project {{PROJECT_NAME}} --id <checkpoint_id>`
before risky loops, major reruns, or handoffs where replay/fork context matters.

Checkpoint JSON files are lightweight snapshots for review. They do not restore
files automatically and should not contain large datasets, checkpoints, or logs.
