---
name: baseline-intake
description: Register, clone, inspect, and adapt baseline papers/repos for a project, then align project code structure with the inspected baselines. Use when the user provides baseline papers or repo URLs, asks to set up baselines, or before shaping substantial 04_code/src/ interfaces. Wraps baselines.baseline_library, baseline_intake, repo_discovery, baseline_sandbox, and baseline_compare.
---

# Baseline Intake & Structure

Entrypoint for baseline work in this file-based research workspace.
Source runbooks: `prompts/skills/fast_baseline_intake.md`,
`prompts/skills/baseline_compare.md`.

## When to use

- The user provides baseline papers or repository URLs.
- A project needs runnable baselines before main experiments.
- Baseline snapshots exist and `04_code/src/` interfaces are about to be
  shaped.

## Workflow

1. Register baselines in the library
   (`08_baselines/baseline_registry.json`):
   ```bash
   python -m scripts.commands.baselines.baseline_library add --project <name> --id <baseline_id> --name "..." --paper "..." --repo-url "..." --status source_found --owner code_agent
   ```
2. Ingest from a manifest (clone + inspect + scaffold adapters and smoke
   scripts):
   ```bash
   python -m scripts.commands.baselines.baseline_intake ingest --project <name> --manifest baselines.csv --clone --allow-network --message-missing-repos
   ```
   Or inspect one registered baseline:
   `baseline_intake inspect --project <name> --id <baseline_id>`.
3. Resolve missing repos and audit command safety:
   ```bash
   python -m scripts.commands.baselines.repo_discovery --project <name> --candidate-file 08_baselines/repo_candidates.csv --apply
   python -m scripts.commands.baselines.baseline_sandbox --project <name> --strict --write-policy
   ```
4. After snapshots exist and before shaping `04_code/src/`:
   ```bash
   python -m scripts.commands.baselines.baseline_compare --project <name> --write
   ```
   Record the chosen layout in `08_baselines/code_structure_plan.md`.

## Guardrails

- Cloned sources stay read-only under `08_baselines/source_snapshots/<id>/`;
  adapters and wrappers go in `08_baselines/run_scripts/<id>/`.
- Run baseline smoke scripts before claiming a baseline is runnable; route
  heavy smoke runs through the GPU scheduler, not the login node.
- Never import baseline source into `state/` or `09_report/`.
