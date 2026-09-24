# Server Experiment Rules

Use these rules for any GPU experiment or server-side experiment run.
Machine-specific GPU caps, profile names, node names, and scheduler commands
come from `config/workspace_profile.local.json`; use
`prompts/skills/workspace_profile.md` before changing those preferences.

## GPU Allocation Workflow

1. Queue GPU experiments with `scripts/commands/experiments/gpu_scheduler.py`; do not launch long experiments by hand.
2. Let the scheduler check active allocations with `squeue --me` and free GPUs with `scontrol show node`.
3. Do not reserve more GPUs than the configured workspace/profile GPU cap across running jobs.
4. Use `scripts/commands/experiments/gpu_scheduler.py dispatch --execute` to submit every independent, currently launchable job with `sbatch --parsable`.
5. Use `gpu_scheduler list --json` when another agent needs dependency readiness for queued GPU jobs.
5. Track the experiment with `python -m scripts.commands.experiments.run_state` and the owning agent with `python -m scripts.commands.agents.agent_status`.
6. After launch, run `python -m scripts.commands.experiments.gpu_monitor --project {{PROJECT_NAME}}` to synchronize SLURM outcomes back into queue and run state files.

## Parallel GPU Scheduler

Use `scripts/commands/experiments/gpu_scheduler.py` when several experiments can run independently.

Queue a job:

```bash
python -m scripts.commands.experiments.gpu_scheduler add --project {{PROJECT_NAME}} --id <job_id> --exp-id <exp_id> --command "<run command>" --gpu-type auto --priority high --result-path <result_path> --expected-output "<expected artifact or metric>" --check-procedure "<how to verify success>"
```

If a job is not independent, record the dependency so it is held out of
parallel dispatch until the prerequisite job succeeds:

```bash
python -m scripts.commands.experiments.gpu_scheduler add --project {{PROJECT_NAME}} --id <analysis_job> --exp-id <exp_id> --command "<analysis command>" --gpu-type auto --priority medium --result-path 05_results/experiment_journal.md --expected-output "<analysis of why performance changed>" --check-procedure "<confirm the Markdown and CSV journals explain the result>" --depends-on <training_job>
```

Plan launchable jobs without starting anything:

```bash
python -m scripts.commands.experiments.gpu_scheduler plan --project {{PROJECT_NAME}}
python -m scripts.commands.experiments.gpu_scheduler plan --project {{PROJECT_NAME}} --json
```

Use JSON `plan_diagnostics` to explain excluded jobs before reducing the batch:
unfinished dependencies, no available GPU type, user cap, or per-type capacity.

Launch only after checking the plan. By default, dispatch submits all planned
jobs that fit the remaining GPU cap:

```bash
python -m scripts.commands.experiments.gpu_scheduler dispatch --project {{PROJECT_NAME}} --execute
```

Limit fanout or choose an explicit subset when needed:

```bash
python -m scripts.commands.experiments.gpu_scheduler dispatch --project {{PROJECT_NAME}} --max-parallel 2 --execute
python -m scripts.commands.experiments.gpu_scheduler dispatch --project {{PROJECT_NAME}} --ids <job_a>,<job_b> --execute
```

Explicit `dispatch --ids` requests should fail with diagnostics when any
requested job is not dispatchable; inspect the dependency or capacity reason
before reducing the batch. If `--ids` names more jobs than `--max-parallel`,
the scheduler should fail instead of silently dropping explicit jobs.

Rules:

- `dispatch` without `--execute` is a dry run and prints `sbatch` commands.
- Dry-run `dispatch` also prints diagnostics for queued jobs excluded from the
  current batch.
- Use `dispatch --json` only for dry-run machine-readable selected jobs,
  diagnostics, and launch commands; do not combine it with `--execute`.
- Prefer `dispatch` for normal work so idle GPU capacity is used for independent jobs. Use targeted `launch` only for explicit single-job or debug workflows.
- The scheduler reads the configured queue/node commands and caps launches at the workspace/profile GPU limit.
- Jobs without `depends_on` are treated as independent and may run in parallel
  if capacity is available. Jobs with `depends_on` launch only after every
  dependency is marked `succeeded`.
- Do not bypass the scheduler cap by manually launching `srun`, `sbatch`, or detached shell jobs.
- Only parallelize independent experiments. Use `--depends-on` for analysis,
  aggregation, or follow-up jobs that need a previous GPU job to succeed. Do
  not parallelize jobs that write the same output directory, checkpoint, cache,
  or result table.
- Keep `03_experiments/<exp_id>/run_state.json` current; the scheduler updates
  it when `--execute` launches a job and when
  `gpu_scheduler update --status ...` records an outcome.
- GPU scheduler launch, update, and monitor outcome syncs also update
  `state/agent_status.json` and append a GPU lifecycle event for the owning
  agent.
- Executed dispatches append a `gpu_dispatch_plan` event before launch. Use it
  to recover which independent jobs, commands, expected outputs, and check
  procedures were selected for the parallel batch.
- After launching detached jobs, run `python -m scripts.commands.experiments.gpu_monitor --project {{PROJECT_NAME}}` to synchronize finished, failed, stale, or blocked jobs back into `state/gpu_experiment_queue.json` and `run_state.json`.
- When a GPU job is marked `succeeded`, immediately follow the recorded
  `run_state.json` next action: explain why the result improved, regressed, or
  stayed flat, then update `03_experiments/<exp_id>/analysis.md`,
  `05_results/experiment_journal.md`, and `05_results/experiment_journal.csv`.

## Filesystem Safety

- Server cleanup means synchronizing SLURM job outcomes, stopping only jobs you own when needed, and updating state files.
- Never delete, move, or recursively clean directories outside the active project folder to free space or reset an experiment.
- Do not run `rm -rf`, `find ... -delete`, `git clean -fd`, `rsync --delete`, or recursive delete scripts on paths outside the active project folder.
- Do not delete external datasets, checkpoints, source repositories, or sibling project folders.

## GPU Commands

Preview scheduler-selected jobs:

```bash
python -m scripts.commands.experiments.gpu_scheduler plan --project {{PROJECT_NAME}}
```

Submit scheduler-selected jobs:

```bash
python -m scripts.commands.experiments.gpu_scheduler dispatch --project {{PROJECT_NAME}} --execute
```

Check running jobs:

```bash
squeue --me
```

Synchronize completed or failed jobs:

```bash
python -m scripts.commands.experiments.gpu_monitor --project {{PROJECT_NAME}}
```
