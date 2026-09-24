# Baseline Compare

Use after baseline GitHub/source repositories have been cloned into the project.

## When To Use

- You need to standardize `04_code/src/` structure.
- Baseline repos have different config/data/model/eval layouts.
- You need thin adapters without modifying cloned snapshots.

## Agent Workflow

1. Scan `08_baselines/source_snapshots/<baseline_id>/` with bounded file limits.
2. Compare entrypoints, config files, packages, data/model/train/eval patterns.
3. Update `08_baselines/baseline_compare.md`.
4. Reflect the chosen project-side structure in `08_baselines/code_structure_plan.md`.
5. Keep cloned snapshots read-only; put wrappers under `08_baselines/run_scripts/`.

## Outputs

- `08_baselines/baseline_compare.md`
- `08_baselines/code_structure_plan.md`
