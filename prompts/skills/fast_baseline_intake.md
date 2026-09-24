# Fast Baseline Intake Skill

Use this when baseline papers or repo URLs are provided.

## Procedure

1. Create or update a manifest with `id,name,paper,repo_url,dataset,metric`.
2. Run `scripts/commands/baselines/baseline_intake.py ingest --project <project> --manifest 08_baselines/baseline_manifest.csv --clone --allow-network --message-missing-repos`, or pass another repo-relative, project-relative, or absolute manifest path.
3. Read `08_baselines/code_structure_plan.md`.
4. Use wrappers under `08_baselines/run_scripts/`; do not edit source snapshots directly.
5. Record exact run commands before marking a baseline runnable.

## Token Discipline

Read structure reports before reading full repo files. Open only entry points, config files, data loaders, metric code, and adapters needed for the current task.
