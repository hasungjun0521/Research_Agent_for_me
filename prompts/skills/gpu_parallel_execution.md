# GPU Parallel Execution Skill

Use this when multiple independent experiments can run on the SLURM GPU cluster.
Queue independent experiments first, then dispatch a bounded parallel batch when
GPU capacity is available instead of launching experiments one at a time.
Load `prompts/skills/workspace_profile.md` first when the user's GPU cluster,
GPU cap, scheduler commands, or preferred GPU ordering differs from the public
template.

## Procedure

1. Confirm jobs are independent and do not share write targets.
2. Queue jobs with `python -m scripts.commands.experiments.gpu_scheduler add`.
3. Run `python -m scripts.commands.experiments.gpu_scheduler status --project <project>` and confirm remaining user GPU capacity from `config/workspace_profile.local.json` and active jobs.
4. Use `python -m scripts.commands.experiments.gpu_scheduler list --project <project> --json` when you need dependency readiness for queued GPU jobs.
5. Run `python -m scripts.commands.experiments.gpu_scheduler plan --project <project>` and review planned launches.
   Use `--json` when another agent needs machine-readable `plan_diagnostics`
   explaining selected and excluded jobs.
6. Before any `--execute` call, confirm `config/workspace_profile.local.json`
   has `gpu.enabled=true` and the real scheduler/cap values for this machine.
7. For one-shot bounded execution, run:
   `python -m scripts.commands.experiments.gpu_scheduler dispatch --project <project> --execute`.
   This combines planning and launch for all currently dispatchable jobs.
8. To limit fanout, use `--max-parallel N` with `dispatch`.
9. For explicit subsets, use `--ids` with `dispatch`; if a requested job is not
   dispatchable, use the reported diagnostics before reducing or rerouting the
   batch. Do not combine more explicit `--ids` than `--max-parallel`; the
   scheduler should fail instead of silently dropping requested jobs.
10. If you need command preview only (no submission), omit `--execute`; the
   dry-run dispatch prints selected launch commands plus diagnostics for queued
   jobs excluded from that batch.
   Use `dispatch --json` when another agent needs machine-readable
   `selected_jobs`, `plan_diagnostics`, and `launch_commands`.
11. Heartbeat long jobs with `python -m scripts.commands.experiments.run_state heartbeat --project <project> --exp-id <exp_id> --note "..."`.
12. After each job completes, synchronize the GPU queue and experiment state
    with `python -m scripts.commands.experiments.gpu_scheduler update --project
    <project> --id <job_id> --status succeeded --note "..." --result-path
    <path>`. Use `failed`, `blocked`, or `cancelled` when that is the real
    outcome.
13. Use `python -m scripts.commands.experiments.gpu_scheduler refresh --project
    <project> --json` to inspect scheduler-visible lifecycle state. Use
    `refresh --write` to sync visible terminal states back into the GPU queue
    and run_state. Only use `--mark-missing <status>` after deciding how this
    cluster should treat running jobs that disappeared from scheduler output.
14. When refresh marks a job terminal or a human confirms the real outcome,
    close the experiment with `prompts/skills/experiment_completion.md` so
    metrics, artifacts, data roots, analysis, and state files move together.

## Parallel Launch Rule

- If multiple experiments are independent and share no output paths, queue them all first.
- Then let the scheduler choose max parallelism according to remaining capacity.
- Default to `dispatch` for normal GPU batches. It submits every queued,
  launchable independent job that fits the current GPU cap instead of running
  experiments one at a time.

```bash
python -m scripts.commands.experiments.gpu_scheduler add --project <project> --id exp001 --exp-id exp_001 --command "python -m ..." --gpu-type auto --priority high --result-path 03_experiments/exp_001/results/ --expected-output "primary metrics and checkpoint" --check-procedure "Inspect log and metrics before marking succeeded."
python -m scripts.commands.experiments.gpu_scheduler add --project <project> --id exp002 --exp-id exp_002 --command "python -m ..." --gpu-type auto --priority high --result-path 03_experiments/exp_002/results/ --expected-output "primary metrics and checkpoint" --check-procedure "Inspect log and metrics before marking succeeded."
python -m scripts.commands.experiments.gpu_scheduler add --project <project> --id exp003 --exp-id exp_003 --command "python -m ..." --gpu-type auto --priority high --result-path 03_experiments/exp_003/results/ --expected-output "primary metrics and checkpoint" --check-procedure "Inspect log and metrics before marking succeeded."

python -m scripts.commands.experiments.gpu_scheduler status --project <project>
python -m scripts.commands.experiments.gpu_scheduler dispatch --project <project> --execute
```

- Do not override the planner for “run all immediately” unless the job queue and
  node policy explicitly allow it.

## Hard Limits

- Use `squeue --me` before launch.
- Do not use `--execute` until the local profile has `gpu.enabled=true`.
- Keep total user GPU usage at or below the configured
  `config/workspace_profile.local.json:gpu.max_user_gpus` value.
- Never bypass the scheduler cap with manual `srun`, `sbatch`, or detached shell jobs.
- Do not parallelize experiments that write the same outputs.
- Do not treat scheduler completion as research completion until the experiment
  completion workflow records the result explanation and artifacts.
