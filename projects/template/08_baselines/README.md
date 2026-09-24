# Baselines and Prior Code

This folder is the project-local knowledge base for baseline papers, GitHub
repositories, prior research code, reproduction commands, source-structure
reports, and code-adaptation notes.

Use it before designing or implementing experiments. The goal is to make
baseline comparisons traceable and to prevent the code agent from rewriting
known methods from memory. Research code in `04_code/src/` should be structured
with reference to the baseline source maps and `code_structure_plan.md` so the
project stays consistent and reviewable.

## Files

- `baseline_registry.json`: structured list of baselines, source locations, implementation status, commands, and evidence links. Update it with `scripts/commands/baselines/baseline_library.py`.
- `prior_research_inventory.md`: human-readable notes on prior methods, papers, repos, and what each contributes.
- `implementation_recipes.md`: reusable commands for inspecting, porting, running, and validating baseline code.
- `code_adaptation_notes.md`: project-specific conventions and pitfalls when adapting prior code.
- `baseline_manifest.csv`: optional working manifest for baseline papers and
  GitHub URLs to ingest.
- `source_snapshots/README.md`: storage rules for cloned GitHub/source repos.
- `structure_reports/README.md`: generated source maps for cloned baseline repos.
- `code_structure_plan.md`: structure comparison and generated/adapted plan for
  shaping `04_code/src/` and baseline wrappers under `08_baselines/run_scripts/<id>/`.
- `patches/README.md`: notes for patches needed to make a baseline run in this project.
- `run_scripts/README.md`: wrapper scripts or command templates for baseline runs.

## Registry Commands

Initialize the registry if it is missing:

```bash
python -m scripts.commands.baselines.baseline_library init --project {{PROJECT_NAME}}
```

Register a baseline before adapting or running it:

```bash
python -m scripts.commands.baselines.baseline_library add --project {{PROJECT_NAME}} --id <baseline_id> --name "<baseline_name>" --paper "<paper_or_citation>" --repo-url <url_or_empty> --status candidate --owner code_agent
```

When you have a list of baseline papers or repo URLs, use the intake pipeline:

```bash
python -m scripts.commands.baselines.baseline_intake ingest --project {{PROJECT_NAME}} --manifest 08_baselines/baseline_manifest.csv --clone --allow-network --message-missing-repos
```

Recommended manifest columns:

```text
id,name,paper,repo_url,dataset,metric
```

This registers the baseline, clones available GitHub/source repos into
`08_baselines/source_snapshots/<baseline_id>/`, writes structure reports, ranks
the repo structures in `08_baselines/code_structure_plan.md`, and creates
smoke/wrapper scaffolds under `08_baselines/run_scripts/<baseline_id>/`.

Attach implementation and run commands as soon as they are known:

```bash
python -m scripts.commands.baselines.baseline_library update --project {{PROJECT_NAME}} --id <baseline_id> --status runnable --source-path <path> --working-dir <cwd> --dataset-path <data_path> --config <config_path> --run-command "<exact command>" --result-path <result_path>
```

Check the registry before using baseline claims:

```bash
python -m scripts.commands.baselines.baseline_library validate --project {{PROJECT_NAME}} --strict
```

## Rules

- Do not treat a baseline as valid evidence until its command, config, data path, and output path are recorded.
- Prefer linking to exact source paths, commits, or copied snapshots instead of vague method names.
- Record failed reproduction attempts. Failed runs are useful evidence about implementation risk.
- Keep large artifacts, checkpoints, datasets, and logs outside this folder unless they are small text summaries.
- When adapting code, preserve the original baseline behavior unless a documented compatibility change is required. Do not edit cloned source snapshots directly; use thin adapters, wrappers, or patch notes.
- Use `structure_reports/` and `code_structure_plan.md` before shaping
  `04_code/src/`; this is the canonical place to compare baseline repo
  structures with the project's own code layout.
- Keep experiment implementation and debugging in `04_code/`. Export cleaned,
  distribution-ready code to `09_report/src/` only after it is stable.
- Code agents must read this folder before writing baseline-related code and must update `baseline_registry.json` when baseline status, commands, source paths, or result paths change.
