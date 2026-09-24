# Current State

## Project

`{{PROJECT_NAME}}`

## Current Stage

brief

## Research Question

Not yet finalized. The first agent pass should clarify it from the user's idea
and update `00_brief/research_question.md`.

## Current Hypothesis

Not yet defined.

## Known Facts

- Project workspace has been created from the template.
- The user is expected to operate through Claude, Codex, or another coding
  agent from the repository root.
- The agent should use harness CLIs itself for structured state changes instead
  of asking the user to run Python commands.
- Active experiment/research code belongs in `04_code/`.
- Experiment design, configs, run state, logs, and run-local outputs belong in
  `03_experiments/`.
- Working analyses, robustness checks, intermediate figures, and interpretation
  belong in `05_results/`.
- `09_report/` is the final reader-facing and release-facing artifact folder.
  Export code to `09_report/src/` only after it is cleaned and stable.
- Research rigor gate files are initialized for preregistration,
  reproducibility, robustness, and reviewer-risk review.
- File-based continuity is initialized in `HANDOFF.md`, `state/agent_memory.md`,
  `state/next_actions.md`, and `state/open_questions.md`.
- Dashboard-free health and stale-state diagnostics are initialized in
  `state/project_health.md` and `state/state_doctor.md`.
- Mid-pass progress checkpoints should be recorded with
  `python -m scripts.commands.review.progress_checkpoint record` so important
  findings are saved before the final chat response.
- Structured agent status, command queue, messages, votes, GPU queue, and loop
  summary files are initialized under `state/`.
- Dataset and metric provenance registries are initialized in
  `03_experiments/dataset_registry.json` and
  `03_experiments/metric_registry.json`.
- GPU and server defaults should come from repository-level
  `config/workspace_profile.local.json`.
- Experiment data roots, running result explanations, and terminology glossary
  files are initialized at `03_experiments/data_roots.md`,
  `03_experiments/artifact_registry.csv`,
  `05_results/experiment_results.csv`, `05_results/experiment_journal.md`,
  `05_results/experiment_journal.csv`, and `06_writing/terminology.md`.
- Experiment DAG, claim graph, baseline comparison, and agent quality audit
  starter files are initialized at `03_experiments/experiment_dag.json`,
  `05_results/claim_graph.md`, `08_baselines/baseline_compare.md`, and
  `07_reviews/agent_quality_audit.md`.
- Baseline GitHub/source repositories should be cloned under
  `08_baselines/source_snapshots/<baseline_id>/`, inspected under
  `08_baselines/structure_reports/`, and summarized in
  `08_baselines/code_structure_plan.md` before shaping project code.
- No literature review has been completed yet.
- No baseline, dataset, metric, or experiment has been selected yet.
- No experiments have been run yet.

## Open Questions

- What precise research question should this project investigate?
- What is the user's target dataset, domain, or evaluation setting?
- What prior work defines the strongest baseline?
- What evidence would validate the first contribution candidate?
- What compute, time, or publication constraints should guide the project?

## Completed

- Folder structure initialized.
- Reader-facing `09_report/` folder initialized.
- File-based state and handoff files initialized.

## Next Actions

1. Ask the user for the initial idea if it is not already available.
2. Run the motivation planner role to clarify the research question,
   motivation, assumptions, constraints, and contribution candidates.
3. Run director triage after the brief is updated.
4. Refresh project health after the first meaningful state update.

## Blockers

- Research question and motivation are not yet specific.
- Required user constraints are not yet captured.

## Last Updated

YYYY-MM-DD
