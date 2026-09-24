---
name: gpu-dispatch
description: Queue and dispatch independent experiments to the GPU/SLURM cluster in a bounded parallel batch instead of launching one at a time. Use when multiple experiments share no write paths and GPU capacity is available, or when a CPU-heavy/long smoke test should run as a bounded GPU job. Wraps scripts.commands.experiments.gpu_scheduler (plan/dispatch/update/refresh) and respects the configured GPU cap.
---

# GPU Parallel Dispatch

Queue independent jobs first, then let the scheduler dispatch a bounded parallel
batch within the configured cap. Source: `prompts/skills/gpu_parallel_execution.md`.
Read `prompts/skills/workspace_profile.md` first if the cluster, GPU cap,
scheduler commands, or GPU ordering differ from the public template.

## Preconditions

- Confirm jobs are independent and share no write targets.
- Confirm `config/workspace_profile.local.json` has `gpu.enabled=true` and real
  scheduler/cap values before any `--execute`.
- Run `squeue --me` before launch; keep total usage ≤ `gpu.max_user_gpus`.

## Workflow

1. Queue each job (record command, exp-id, expected output, check procedure):
   ```bash
   python -m scripts.commands.experiments.gpu_scheduler add --project <project> \
     --id exp001 --exp-id exp_001 --command "python -m ..." --gpu-type auto \
     --priority high --result-path 03_experiments/exp_001/results/ \
     --expected-output "primary metrics and checkpoint" \
     --check-procedure "Inspect log and metrics before marking succeeded."
   ```

2. Check capacity and plan:
   ```bash
   python -m scripts.commands.experiments.gpu_scheduler status --project <project>
   python -m scripts.commands.experiments.gpu_scheduler plan --project <project>
   ```
   Use `plan --json` / `dispatch --json` (omit `--execute`) for machine-readable
   `plan_diagnostics` explaining selected/excluded jobs before reducing a batch.

3. Dispatch the bounded batch:
   ```bash
   python -m scripts.commands.experiments.gpu_scheduler dispatch --project <project> --execute
   ```
   Use `--max-parallel N` to limit fanout, `--ids` for explicit subsets (don't
   pass more `--ids` than `--max-parallel`).

4. Heartbeat long jobs:
   ```bash
   python -m scripts.commands.experiments.run_state heartbeat --project <project> --exp-id <exp_id> --note "..."
   ```

5. After each job, sync queue + state:
   ```bash
   python -m scripts.commands.experiments.gpu_scheduler update --project <project> \
     --id <job_id> --status succeeded --note "..." --result-path <path>
   ```
   Use `gpu_scheduler refresh --json` to inspect scheduler-visible lifecycle;
   `refresh --write` to sync terminal states back.

6. When a job is terminal, close the experiment via the `experiment-run` skill
   so metrics, artifacts, data roots, and analysis move together.

## Hard limits

- Never bypass the scheduler cap with manual `srun`/`sbatch`/detached jobs.
- Do not parallelize experiments that write the same outputs.
- Scheduler completion ≠ research completion.
