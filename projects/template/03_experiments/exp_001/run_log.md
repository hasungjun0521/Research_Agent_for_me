# Experiment exp_001 Run Log

## Run Metadata

- Experiment ID: exp_001
- Date:
- Runner:
- Code version:
- Config path: `03_experiments/exp_001/config.yaml`
- Result path: `03_experiments/exp_001/results/`
- Baseline registry: `08_baselines/baseline_registry.json`

## Commands

```bash
# Run a cheap smoke test first. Record the exact command, expected output, and
# observed output before queueing an expensive GPU job.
<small smoke command>

# Queue and preview GPU experiment launch.
python -m scripts.commands.experiments.gpu_scheduler add --project {{PROJECT_NAME}} --id <job_id> --exp-id exp_001 --command "<exact experiment command>" --gpu-type auto --priority high --result-path 03_experiments/exp_001/results/
python -m scripts.commands.experiments.gpu_scheduler plan --project {{PROJECT_NAME}}
python -m scripts.commands.experiments.gpu_scheduler dispatch --project {{PROJECT_NAME}}

# Submit only after checking the dry-run sbatch commands. Dispatch runs all
# currently launchable independent jobs within the configured GPU cap.
python -m scripts.commands.experiments.gpu_scheduler dispatch --project {{PROJECT_NAME}} --execute

# Bound fanout or dispatch an explicit subset when needed.
python -m scripts.commands.experiments.gpu_scheduler dispatch --project {{PROJECT_NAME}} --max-parallel 2 --execute
python -m scripts.commands.experiments.gpu_scheduler dispatch --project {{PROJECT_NAME}} --ids <job_a>,<job_b> --execute

# Hold dependent jobs until prerequisites succeed.
python -m scripts.commands.experiments.gpu_scheduler add --project {{PROJECT_NAME}} --id <analysis_job> --exp-id exp_001 --command "<analysis command>" --gpu-type auto --priority medium --depends-on <training_job>

# If this run uses a baseline, register or update it:
python -m scripts.commands.baselines.baseline_library update --project {{PROJECT_NAME}} --id <baseline_id> --status runnable --working-dir <cwd> --dataset-path <data_path> --config 03_experiments/exp_001/config.yaml --run-command "<exact command>" --result-path 03_experiments/exp_001/results/ --evidence 03_experiments/exp_001/run_log.md

# Synchronize completed, failed, or stale SLURM jobs.
python -m scripts.commands.experiments.gpu_monitor --project {{PROJECT_NAME}}
```

## Environment

- Python version:
- Hardware: record GPU type, node, SLURM job id/name, and `squeue --me` status.
- Dependencies:
- Random seed:

## Outcomes

- Status: not started
- Result files:
- Errors:
- Notes:

## Reproducibility Notes

Record anything needed to rerun the experiment, including scheduler job id, `sbatch` dry-run command, GPU type, node, and monitor status.
If the run is a baseline or prior-code reproduction, also record the baseline id and update `08_baselines/baseline_registry.json`.
