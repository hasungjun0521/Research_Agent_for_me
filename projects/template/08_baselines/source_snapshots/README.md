# Source Snapshots

Use this folder for baseline GitHub/source repositories cloned by
`scripts/commands/baselines/baseline_intake.py`.

The standard path is:

```text
08_baselines/source_snapshots/<baseline_id>/
```

Complete external repositories may be cloned here when they are required for
baseline reproduction or source-structure comparison. Do not store large
checkpoints, datasets, generated logs, or model weights here.

For each snapshot, record:

- original repo/path
- commit hash or timestamp
- files copied
- reason for copying
- known missing files
- license or usage notes

After cloning, inspect the repo and write structure reports under
`08_baselines/structure_reports/`. Use those reports and
`08_baselines/code_structure_plan.md` before shaping project code under
`04_code/src/`.

Do not edit cloned source snapshots directly. Use wrappers/adapters in
`08_baselines/run_scripts/<baseline_id>/`, smoke scripts in
`08_baselines/run_scripts/`, and patch notes in `08_baselines/patches/`.
