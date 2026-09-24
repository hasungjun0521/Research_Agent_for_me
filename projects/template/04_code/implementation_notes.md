# Implementation Notes

## Current Code State

Describe what code exists and what is missing.

## Experiment Links

| Experiment ID | Code Path | Config Path | Run Command | Status |
| --- | --- | --- | --- | --- |
| exp_001 |  | `03_experiments/exp_001/config.yaml` |  | planned |

## Baseline Code Links

Track baseline and prior-code sources through `08_baselines/baseline_registry.json`; do not rely on method names alone.

| Baseline ID | Source Path | Wrapper / Patch | Run Command | Status |
| --- | --- | --- | --- | --- |
|  |  |  |  |  |

## Assumptions

- 

## Filesystem Safety Notes

- Code and experiment work must stay inside `projects/{{PROJECT_NAME}}/` unless the user explicitly assigns harness-level maintenance.
- Do not delete, move, overwrite, or recursively clean directories outside this project folder.
- Before any cleanup command, resolve the target path and confirm it is inside this project folder.
- Do not use `rm -rf`, `find ... -delete`, `git clean -fd`, `rsync --delete`, or recursive delete scripts on parent directories, sibling projects, datasets, checkpoints, external repositories, or system paths.

## Server Execution Notes

- Queue GPU experiments with `scripts/commands/experiments/gpu_scheduler.py add`.
- Run and record a cheap smoke test before queueing an expensive run.
- Inspect launchability with `scripts/commands/experiments/gpu_scheduler.py plan`.
- Submit normal GPU batches with `scripts/commands/experiments/gpu_scheduler.py dispatch --execute`; the scheduler uses `sbatch` and fills available GPU capacity with independent queued jobs.
- Use `dispatch --max-parallel N` or `dispatch --ids <id_a>,<id_b>` when fanout must be bounded. Use targeted `launch` only for explicit single-job or debug workflows.
- Check allocations with `squeue --me`.
- Keep active GPU usage at or below the configured workspace/project GPU cap.
- Synchronize completed, failed, or stale jobs with `scripts/commands/experiments/gpu_monitor.py`.

## Known Issues

- 

## Reproducibility Notes

- Record SLURM job id/name, GPU type, node, `squeue --me` check, and monitor status for GPU runs.
