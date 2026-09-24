# Code Adaptation Notes

Use this file to record how prior research code is adapted into this project.

## Project Code Conventions

- Entry points:
- Config format:
- Dataset layout:
- Metric functions:
- Logging conventions:
- Checkpoint conventions:
- Baseline wrappers/adapters live under `08_baselines/run_scripts/<baseline_id>/`.
- Cloned source snapshots live under `08_baselines/source_snapshots/<baseline_id>/` and should not be edited directly.
- Before substantial project code is written, compare cloned baseline structures
  in `08_baselines/structure_reports/` and record the chosen project layout in
  `08_baselines/code_structure_plan.md`.
- Active implementation lives in `04_code/`; cleaned release-facing exports
  live in `09_report/src/` only after stabilization.

## Structure Decisions

| Decision | Baseline Evidence | Project Path | Rationale | Date |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

## Adaptation Log

| Date | Baseline | Change | Reason | Risk | Files |
| --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  |

## Compatibility Shims

List wrappers, adapters, or conversion scripts used to make prior code run without changing baseline behavior.

| Shim | Purpose | Inputs | Outputs | Owner |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

## Known Pitfalls

- 

## Do Not Change Without Recording

- Metrics:
- Dataset splits:
- Preprocessing:
- Random seeds:
- Evaluation protocol:
