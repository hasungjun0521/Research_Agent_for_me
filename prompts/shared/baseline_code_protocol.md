# Baseline Code Protocol

Use this protocol whenever a task touches prior research code, baseline implementation, baseline reproduction, or comparison claims.

## Baseline Folder

Each project owns a baseline library at:

`08_baselines/`

Core files:

- `baseline_registry.json`: structured source of truth for baseline status, source paths, commands, configs, results, and evidence.
- `prior_research_inventory.md`: human-readable map from papers and repos to methods, reviewer expectations, and relevance.
- `implementation_recipes.md`: command templates for inspection, setup, runs, and failure recording.
- `code_adaptation_notes.md`: compatibility changes, shims, and risks introduced while porting code.
- `baseline_manifest.csv`: optional working manifest for baseline papers and
  GitHub/source URLs.
- `source_snapshots/`: cloned GitHub/source repositories under
  `source_snapshots/<baseline_id>/`.
- `structure_reports/`: generated source maps for cloned repos.
- `code_structure_plan.md`: ranking of cloned repos by structure quality and the project-side adapter layout to apply.
- `patches/`: patches or patch notes needed to reproduce/adapt a baseline.
- `run_scripts/`: thin wrappers for baseline runs.

## Required Workflow

Before writing baseline-related code:

1. Read `08_baselines/baseline_registry.json`.
2. Read `08_baselines/prior_research_inventory.md`.
3. Read `08_baselines/implementation_recipes.md`.
4. Read `08_baselines/code_adaptation_notes.md`.
5. Check whether the method already has a source path, command, known difference, or failed reproduction note.

When a baseline is identified:

```bash
python -m scripts.commands.baselines.baseline_library add --project <project> --id <baseline_id> --name "<baseline_name>" --paper "<paper_or_citation>" --repo-url <repo_url> --status source_found --owner <agent_name>
```

When the user provides baseline papers or repo URLs, prefer the intake workflow:

```bash
python -m scripts.commands.baselines.baseline_intake ingest --project <project> --manifest 08_baselines/baseline_manifest.csv --clone --allow-network --message-missing-repos
```

If repo URLs are missing or uncertain, resolve candidates before implementation:

```bash
python -m scripts.commands.baselines.repo_discovery --project <project> --candidate-file 08_baselines/repo_candidates.csv --apply
python -m scripts.commands.baselines.baseline_sandbox --project <project> --strict --write-policy
```

The manifest may be JSON, CSV, TSV, or plain text. Recommended CSV columns:

```text
id,name,paper,repo_url,dataset,metric
```

The intake workflow must:

1. Register every paper in `08_baselines/baseline_registry.json`.
2. Clone available GitHub/source repos into `08_baselines/source_snapshots/<baseline_id>/`.
3. Inspect source structure and write `08_baselines/structure_reports/<baseline_id>.json` and `.md`.
4. Creates run-script scaffolds under `08_baselines/run_scripts/<baseline_id>_smoke.py`.
5. Write `08_baselines/code_structure_plan.md` ranking the most reusable repo
   structures and defining how `04_code/src/` should be organized.
6. Create dry smoke scripts under `08_baselines/run_scripts/<baseline_id>_smoke.py`.
7. Create agent messages for missing repo URLs when `--message-missing-repos` is used.

When repo URLs are missing for registered baselines:

```bash
python -m scripts.commands.baselines.baseline_intake discover --project <project> --message-missing-repos
```

When implementation details become known:

```bash
python -m scripts.commands.baselines.baseline_library update --project <project> --id <baseline_id> --status runnable --source-path <source_path> --working-dir <cwd> --dataset-path <data_path> --config <config_path> --run-command "<exact run command>" --result-path <result_path> --evidence <evidence_file>
```

When reproduction succeeds:

```bash
python -m scripts.commands.baselines.baseline_library update --project <project> --id <baseline_id> --status reproduced --result-path <result_path> --evidence 03_experiments/<exp_id>/analysis.md
```

When reproduction fails:

```bash
python -m scripts.commands.baselines.baseline_library update --project <project> --id <baseline_id> --status failed --note "<short failure reason>" --evidence 03_experiments/<exp_id>/run_log.md
```

Validate before using baseline evidence:

```bash
python -m scripts.commands.baselines.baseline_library validate --project <project> --strict
python -m scripts.commands.projects.validate_project --project <project>
```

## Evidence Rules

- Do not claim a baseline is reproduced unless its registry entry has status `reproduced`, at least one run command, result path, and evidence file.
- Do not compare against a baseline whose dataset, metric, or preprocessing differs from the current experiment unless `code_adaptation_notes.md` documents the difference.
- Do not silently rewrite a baseline from memory when source code, paper pseudocode, or a prior implementation is available.
- Do not edit cloned source snapshots directly; create adapters, wrappers, or patch notes instead.
- Before structuring substantial project code, compare cloned baselines through
  `08_baselines/structure_reports/` and document the chosen layout in
  `08_baselines/code_structure_plan.md`.
- Keep active project implementation in `04_code/`. Export cleaned,
  distribution-ready code to `09_report/src/` only after the implementation is
  stable.
- Record failed reproduction attempts; they are valid implementation-risk evidence.
- Keep checkpoints, datasets, external repositories, and large logs out of `08_baselines/` unless the project explicitly decides otherwise.
