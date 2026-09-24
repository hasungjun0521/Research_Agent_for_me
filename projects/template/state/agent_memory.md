# Agent Memory

This file stores stable project facts that future agents may rely on. Keep it
concise. Update it whenever durable project-level facts, constraints, decisions,
or lessons change.

## Stable Project Facts

- Project name: `{{PROJECT_NAME}}`
- Research domain:
- Target venue or audience:
- Primary user workflow: the user asks Claude, Codex, or another coding agent
  to continue the project from file state.

## Operating Model

- The user should not need to run harness Python commands directly.
- Agents should run required harness CLIs themselves for structured state
  changes.
- Do not hand-edit project state JSON. Use harness CLIs for agent status,
  command queue, messages, votes, experiment run state, GPU queue, registries,
  and loop summaries.
- Save meaningful progress during the pass, not only in the final chat
  response. Results, blockers, direction changes, failed assumptions,
  experiment outcomes, and next-action changes must land in project files.
- Use `python -m scripts.commands.review.progress_checkpoint record` for
  durable mid-pass updates to current state, progress logs, memory, next
  actions, open questions, and experiment run logs.
- Use project health and state doctor reports as dashboard-free status surfaces
  when choosing the next action or repairing stale state.
- Use brief intake to capture rough ideas as durable brief files and open
  questions before routing literature, baseline, or experiment work.
- A fresh agent should be able to continue by reading `HANDOFF.md`,
  `state/current_state.md`, `state/agent_memory.md`, `state/next_actions.md`,
  `state/open_questions.md`, and the relevant structured state files.

## Important Decisions

- Active experiment/research code belongs in `04_code/`.
- Experiment configs, run state, logs, and run-local outputs belong in
  `03_experiments/`.
- Working analyses, robustness checks, intermediate figures, and interpretation
  belong in `05_results/`.
- `09_report/` is the final reader-facing and release-facing artifact folder.
  Keep LaTeX, final analysis scripts, final figures, final result tables, and
  cleaned release code there only after the working files are stable.
- Raw evidence, scratch notes, generated logs, intermediate analyses, and
  temporary agent output belong in working folders or `state/sessions/`.
- Research rigor gates are required: preregistration before experiments,
  reproducibility manifests during execution, statistical robustness during
  analysis, and reviewer attack matrix before claim strengthening.

## Known Constraints

- Filesystem safety: active research work is limited to
  `projects/{{PROJECT_NAME}}/` unless the user explicitly assigns
  harness-level maintenance.
- Agents must never delete, move, overwrite, or recursively clean directories
  outside this project folder as part of project research work.
- GPU/server rules belong in repository-level
  `config/workspace_profile.local.json`; do not hard-code local cluster details
  in tracked project files.
- Expensive GPU work requires a smoke test and scheduler plan before launch.
- New experiment families should start from a smoke-first experiment DAG with
  independent main-run nodes identified before GPU dispatch.
- CPU-heavy smoke tests should be queued as bounded GPU smoke jobs after the
  local GPU profile is enabled.
- Independent GPU jobs should be queued before dispatch so available GPUs can
  run safe experiments in parallel within the configured cap.
- GPU run records should include job id/name, GPU type, node, command, expected
  outputs, check procedure, and monitor status.
- Experiment data roots and split/version identifiers live in
  `03_experiments/data_roots.md`.
- Structured working result rows live in `05_results/experiment_results.csv`.
  Export to `09_report/results/experiment_results.csv` only when reader-facing
  evidence is stable.
- Experiment outputs, metric files, logs, checkpoints, and evidence paths should
  be registered in `03_experiments/artifact_registry.csv` when an experiment is
  completed.
- Completed experiment results should update `05_results/experiment_journal.md`
  and `05_results/experiment_journal.csv` with why the experiment was run, what
  happened, and why performance moved.
- Working claim graphs belong in `05_results/claim_graph.md` and
  `05_results/claim_graph.json` before claims are strengthened in writing.
- Agent continuity quality should be reviewed in
  `07_reviews/agent_quality_audit.md` when previous passes are hard to resume.
- Paper terminology should be normalized in `06_writing/terminology.md`.
- Data: keep roots, split versions, and derived-data locations in
  `03_experiments/data_roots.md`.
- Time:
- Method:
- Writing: keep canonical terms and abbreviations in
  `06_writing/terminology.md`.

## Research Preferences

- Preferred evidence standard:
- Preferred baselines:
- Preferred ablation style:
- Reproducibility expectations:

## Workflow Preferences

- First clarify the brief before literature, baselines, experiments, or writing.
- Use `08_baselines/` for prior research code, source snapshots, reproduction
  commands, patches, and adaptation notes before treating a baseline as
  runnable or reproduced.
- Baseline GitHub/source repositories are stored under
  `08_baselines/source_snapshots/<baseline_id>/` and should not be edited
  directly.
- Use `08_baselines/structure_reports/` and
  `08_baselines/code_structure_plan.md` to compare baseline repo layouts before
  organizing substantial code in `04_code/src/`.
- Use `08_baselines/baseline_compare.md` as the generated comparison surface
  after source snapshots are available.
- Use `state/agent_messages.json` when another agent needs to answer, review,
  decide, hand off, or unblock work.
- When multiple independent command-queue entries are ready, use
  `python -m scripts.commands.agents.agent_orchestrator parallel` to plan or
  dispatch different owner agents concurrently. Mark explicit ordering with
  `depends_on` and use `parallel_group` for intentionally batched work.
- Use `prompts/skills/` as Markdown runbooks for context budgeting, GPU
  parallel execution, smoke-first experiments, baseline intake, claim
  compression, and performance measurement.
- Update `04_code/` first while code is experimental. Update
  `09_report/src/`, `09_report/paper/main.tex`, `09_report/analysis/`,
  `09_report/figures/`, `09_report/results/experiment_results.csv`, or
  `09_report/results/claim_evidence.csv` only when final/report-facing or
  release-facing artifacts change.
- Update `03_experiments/exp_*/preregistration.md`,
  `03_experiments/exp_*/reproducibility_manifest.json`,
  `05_results/statistical_robustness.md`, and
  `07_reviews/reviewer_attack_matrix.md` when experiment-backed claims change.

## Rejected Ideas

| Idea | Reason Rejected | Evidence | Date |
| --- | --- | --- | --- |
|  |  |  |  |

## Writing Preferences

- Style:
- Citation style:
- Target length:
- Target venue:
- Venue review forms: use `review_forms/form_registry.json` and
  `07_reviews/venue_review_plan.md` when a target venue/year is known. Store
  generated form reviews under `07_reviews/form_reviews/`.
