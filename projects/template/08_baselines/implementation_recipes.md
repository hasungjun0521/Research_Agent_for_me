# Baseline Implementation Recipes

Use these command templates before writing new experiment code. Replace placeholders with project-specific values.

## Inspect Baseline Source

```bash
python -m scripts.commands.agents.agent_status start --project {{PROJECT_NAME}} --agent code_agent --task "Inspect baseline source" --stage "baseline implementation" --input 08_baselines/baseline_registry.json
```

```bash
find <baseline_source_path> -maxdepth 3 -type f | sort
```

```bash
rg -n "class |def |argparse|config|dataset|metric|train|test|eval" <baseline_source_path>
```

## Register A Baseline

Create or update `08_baselines/baseline_registry.json` with the helper CLI:

```bash
python -m scripts.commands.baselines.baseline_library add --project {{PROJECT_NAME}} --id <baseline_id> --name "<baseline_name>" --paper "<paper_or_citation>" --repo-url <repo_url> --status source_found --owner code_agent --dataset <dataset> --metric <metric>
```

## Ingest Baseline Papers And Repos

Use this when the user provides baseline papers or repo URLs:

```bash
python -m scripts.commands.baselines.baseline_intake ingest --project {{PROJECT_NAME}} --manifest 08_baselines/baseline_manifest.csv --clone --allow-network --message-missing-repos
```

Recommended manifest:

```text
id,name,paper,repo_url,dataset,metric
```

Expected outputs:

- `08_baselines/source_snapshots/<baseline_id>/`
- `08_baselines/structure_reports/<baseline_id>.json`
- `08_baselines/structure_reports/<baseline_id>.md`
- `08_baselines/code_structure_plan.md`
- `08_baselines/run_scripts/<baseline_id>/`

If a repo URL is missing, the intake command records repo search queries and can send a message to `literature_reviewer` with `--message-missing-repos`.

Record exact commands as soon as they are known:

```bash
python -m scripts.commands.baselines.baseline_library update --project {{PROJECT_NAME}} --id <baseline_id> --status runnable --source-path <baseline_source_path> --working-dir <cwd> --dataset-path <data_path> --config <config_path> --run-command "<exact run command>" --result-path <result_path> --evidence 03_experiments/<exp_id>/run_log.md
```

Every runnable baseline entry must include:

- exact working directory
- full command
- config path
- dataset path
- output path
- expected metric files
- known differences from the original paper/repo

## Create Experiment State

```bash
python -m scripts.commands.experiments.run_state init --project {{PROJECT_NAME}} --exp-id <exp_id> --owner code_agent --step "Prepare baseline run"
```

## Start A GPU Baseline Run

```bash
# Run a cheap smoke command first and record the observed output before
# queueing the expensive baseline job.
<small baseline smoke command>

python -m scripts.commands.experiments.gpu_scheduler add --project {{PROJECT_NAME}} --id <job_id> --exp-id <exp_id> --command "<exact baseline command>" --gpu-type auto --priority high --result-path 03_experiments/<exp_id>/results/
python -m scripts.commands.experiments.gpu_scheduler plan --project {{PROJECT_NAME}}
python -m scripts.commands.experiments.gpu_scheduler dispatch --project {{PROJECT_NAME}}
python -m scripts.commands.experiments.gpu_scheduler dispatch --project {{PROJECT_NAME}} --execute
```

Use `dispatch --max-parallel N` or `dispatch --ids <job_a>,<job_b>` when a
baseline batch needs bounded fanout. Dispatch submits all launchable
independent jobs that fit the configured GPU cap.

Then record run state:

```bash
python -m scripts.commands.experiments.run_state heartbeat --project {{PROJECT_NAME}} --exp-id <exp_id> --note "Baseline job submitted through gpu_scheduler."
```

## Heartbeat During Long Runs

```bash
python -m scripts.commands.agents.agent_status heartbeat --project {{PROJECT_NAME}} --agent code_agent --task "Running <baseline_name>" --note "Progress: <short status>" --append-note
```

```bash
python -m scripts.commands.experiments.run_state heartbeat --project {{PROJECT_NAME}} --exp-id <exp_id> --note "Progress: <short status>"
```

## Finish A Baseline Run

```bash
python -m scripts.commands.experiments.gpu_scheduler update --project {{PROJECT_NAME}} --id <job_id> --status succeeded --result-path <result_path> --note "Results saved to <result_path>"
```

```bash
python -m scripts.commands.agents.agent_status finish --project {{PROJECT_NAME}} --agent code_agent --command-id <command_id> --status done --output 08_baselines/baseline_registry.json --output 03_experiments/<exp_id>/run_log.md
```

## Failure Recording

If a baseline fails, keep the command and log path:

```bash
python -m scripts.commands.experiments.gpu_scheduler update --project {{PROJECT_NAME}} --id <job_id> --status failed --note "<short failure reason>"
```

Then update:

- `08_baselines/baseline_registry.json`
- `08_baselines/code_adaptation_notes.md`
- `03_experiments/<exp_id>/run_log.md`
