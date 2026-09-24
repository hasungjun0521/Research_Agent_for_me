# ADR-008: GPU Parallel Scheduler and Project Skills

## Status

Accepted

## Context

Expensive experiments should run in parallel when GPUs are available, but the workflow must not exceed the user's GPU cap or start jobs without traceable state. Agents also repeat common procedures, which wastes tokens and makes handoffs inconsistent.

## Decision

Add `scripts/commands/experiments/gpu_scheduler.py` and `state/gpu_experiment_queue.json`.

The scheduler:

1. Queues independent GPU jobs.
2. Reads `squeue --me` to estimate current user GPU usage.
3. Reads node availability through `scontrol show node`.
4. Plans launchable jobs under `max_user_gpus`, default 8.
5. Prints dry-run `sbatch` commands unless `dispatch --execute` is used.
6. Updates `run_state.json` when jobs are executed and when scheduler status
   updates reconcile queued jobs with running or completed experiment state.

Add project-local skills under `prompts/skills/` for compact repeated workflows:

- context budgeting
- GPU parallel execution
- smoke-first experiments
- fast baseline intake
- paper claim compression
- performance measurement

## Consequences

- Parallel experiment launch becomes bounded and auditable.
- Agents can reduce context and token cost by loading only the relevant skill file.
- The harness can validate the GPU queue shape before handoff.
- Actual SLURM launch remains opt-in through `--execute`; normal batches use
  `dispatch` so all independent jobs that fit available GPU capacity can run in
  parallel.
