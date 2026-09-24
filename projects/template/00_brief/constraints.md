# Constraints

## Resource Constraints

- Compute:
  - GPU experiments must be queued, planned, and launched with `scripts/commands/experiments/gpu_scheduler.py`.
  - Expensive runs require a small smoke test first, with the smoke command and output recorded in the experiment run log.
  - The scheduler checks `squeue --me` and configured node availability before submitting with `sbatch`.
  - Queue independent experiments first; when GPUs are available, use `dispatch` so launchable jobs run in parallel within the configured cap.
  - Active GPU usage must not exceed the configured workspace/project GPU cap.
  - Do not bypass the scheduler with manual `srun`, `sbatch`, or detached shell jobs.
  - Synchronize finished or failed jobs with `scripts/commands/experiments/gpu_monitor.py`.
- Time:
- Data access:
- Annotation budget:
- External dependencies:

## Filesystem Safety Constraints

- Active research work is limited to this project folder: `projects/{{PROJECT_NAME}}/`.
- Agents must not delete, move, overwrite, or recursively clean any directory outside this project folder.
- Destructive commands such as `rm -rf`, `find ... -delete`, `git clean -fd`, `rsync --delete`, and recursive delete scripts are forbidden outside this project folder.
- External datasets, checkpoints, cloned repositories, parent directories, sibling projects, and home-directory folders must never be deleted as part of project cleanup.

## Method Constraints

- Required baselines:
- Baseline source discipline: prior-code and baseline candidates must be registered in `08_baselines/baseline_registry.json` before they are used as comparison evidence.
- Required datasets:
- Evaluation limits:
- Reproducibility requirements:

## Scope Constraints

- Domains excluded:
- Claims excluded:
- User groups excluded:

## Risk Constraints

List risks that should prevent the project from expanding beyond its evidence.
