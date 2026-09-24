# Baseline Code Structure Plan

Use this file to compare cloned baseline repository structures and decide how
`04_code/src/` should be organized.

This file starts as a planning template. When
`scripts.commands.baselines.baseline_intake ingest` runs, it
may rewrite this file with generated structure rankings and adapter plans.

## Inputs

- Baseline registry: `08_baselines/baseline_registry.json`
- Cloned source repos: `08_baselines/source_snapshots/<baseline_id>/`
- Structure reports: `08_baselines/structure_reports/<baseline_id>.md`
- Project code: `04_code/src/`
- Baseline wrappers/adapters: `08_baselines/run_scripts/<baseline_id>/`

## Structure Comparison Table

| Baseline ID | Source Path | Main Entrypoints | Config Pattern | Dataset Interface | Model Interface | Evaluation Interface | Reusable Pattern | Risks |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |  |  |  |

## Project Code Layout Decision

Record the intended project-side layout before writing non-trivial code.

```text
04_code/src/
  configs/
    config loading and experiment schema helpers
  data/
    dataset loading, split handling, preprocessing, and data-root resolution
  models/
    project model definitions and architecture modules
  training/
    training loops, optimization, checkpoint orchestration, and seed handling
  evaluation/
    metrics, evaluators, result serialization, and comparison utilities
  experiments/
    wrappers that bind configs, data, model, training, and evaluation
  utils/

04_code/tests/smoke/
  smallest project-side smoke checks before full CPU/GPU runs

08_baselines/run_scripts/
  <baseline_id>/
    thin wrappers/adapters around the cloned baseline snapshot;
    baseline code never lives under 04_code/src/
```

## Adapter Rules

- Keep cloned baseline repositories unmodified under
  `08_baselines/source_snapshots/<baseline_id>/`.
- Put project-specific baseline wrappers in `08_baselines/run_scripts/<baseline_id>/`.
- Preserve baseline behavior unless `08_baselines/code_adaptation_notes.md`
  documents a compatibility change.
- Keep smoke scripts in `08_baselines/run_scripts/`.
- Keep active experiment configs, run logs, and run_state in `03_experiments/`.
- Keep working analysis, result tables, journal entries, robustness checks, and
  figures in `05_results/`.
- Keep experiment implementation in `04_code/`; export cleaned release code to
  `09_report/src/` only after the implementation is stable.

## Open Structure Questions

- Which baseline repo has the cleanest config/data/model/eval separation?
- Which baseline assumptions conflict with this project's data or metrics?
- Which interfaces should the project standardize before adding more code?
- Which code should remain an adapter rather than becoming core project logic?
