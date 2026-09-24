# Shared Research Context Template

Prepend this context to any agent prompt when running the workflow through a
Claude/Codex session or a harness-dispatched pass.

## Project

- Project name: `{{PROJECT_NAME}}`
- Project path: `projects/{{PROJECT_NAME}}`
- Current stage:
- Active workflow:
- Last updated:

## Research Question

Write the current research question in one or two sentences.

## Current Hypothesis

State the current main hypothesis. If no hypothesis exists yet, write `Not yet defined`.

## Candidate Contribution

List the current contribution candidates and mark each as:

- `literature-supported`
- `experiment-supported`
- `speculative`
- `needs revision`

## Evidence Inventory

List available evidence and its location:

- Dashboard-free project health: `state/project_health.md`
- State diagnostics: `state/state_doctor.md`
- Reader-facing report: `09_report/`
- Literature evidence:
- Experiment evidence:
- Analysis evidence:
- Working claim graph: `05_results/claim_graph.md` and `05_results/claim_graph.json`
- Baseline structure comparison: `08_baselines/baseline_compare.md`
- Agent continuity audit: `07_reviews/agent_quality_audit.md`
- Rigor gates: preregistration, reproducibility manifest, statistical robustness, reviewer attack matrix.
- Writing evidence:

## Open Risks

List the main risks:

- Novelty risk:
- Validity risk:
- Baseline risk:
- Reproducibility risk:
- Writing risk:

## Instructions for the Current Agent

- Read the files named in your agent prompt.
- Use only information present in the project files or explicitly provided by the user.
- If evidence is missing, mark it as missing.
- Update only the files assigned to you.
- Persist meaningful progress during the pass. Do not wait until the final
  answer to update `state/current_state.md`, `state/agent_memory.md`,
  `state/next_actions.md`, status, messages, or experiment/report artifacts
  when the result or direction changes.
- Prefer `python -m scripts.commands.review.progress_checkpoint record` for
  mid-pass results, blockers, direction changes, failed assumptions,
  experiment outcomes, memory notes, and next-action updates.
- If state is hard to resume or dashboard-free status is needed, refresh
  `state/project_health.md` or `state/state_doctor.md` through the project
  health/state doctor CLIs before selecting the next action.
- If the brief is incomplete, use the brief intake workflow and put unknowns in
  `state/open_questions.md` rather than guessing.
- Before launching a new experiment family, create or update a smoke-first
  experiment plan/DAG with expected outputs and check procedures.
- Before strengthening claims, refresh the working claim graph and confirm
  result-analysis edges exist.
- After cloned baseline source snapshots exist, refresh baseline comparison
  before shaping substantial project code structure.
- If previous agent work is hard to resume, refresh the agent quality audit and
  repair missing output-file evidence before continuing.
- Treat `09_report/` as the final reader-facing and release-facing artifact
  folder. Keep active code in `04_code/`, experiment process in
  `03_experiments/`, and working analysis in `05_results/`. Update
  `09_report/` only when a change is stable enough to be final/report-facing,
  while still updating the working evidence files first.
- Treat `03_experiments/exp_*/preregistration.md`, `03_experiments/exp_*/reproducibility_manifest.json`, `05_results/statistical_robustness.md`, and `07_reviews/reviewer_attack_matrix.md` as required research rigor gates.
- Treat `prompts/shared/filesystem_safety_rules.md` as mandatory: never delete, move, overwrite, or recursively clean any directory outside the active project folder. For harness maintenance, stay inside this repository and touch only explicitly requested files.
- Treat `state/agent_status.json` as assigned for every agent pass, but update it only through `python -m scripts.commands.agents.agent_status`.
- Treat `state/command_queue.json` as the structured command source of truth, but update it only through `python -m scripts.commands.review.command_queue`.
- Treat `state/agent_messages.json` as the agent-to-agent request/response channel, but update it only through `python -m scripts.commands.agents.agent_messages`.
- Treat `state/loop_summary.json` as the file-based loop recap, but update it only through `python -m scripts.commands.review.loop_summary`.
- Track long experiment runs with `python -m scripts.commands.experiments.run_state` and `03_experiments/<exp_id>/run_state.json`.
- Use `prompts/shared/skill_usage.md` to choose relevant installed skills for the current agent pass.
