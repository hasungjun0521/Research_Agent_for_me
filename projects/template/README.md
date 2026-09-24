# {{PROJECT_NAME}}

This project was created from `projects/template/`. It is meant to be operated
through Claude, Codex, or another coding agent from the repository root.

The user should not need to run harness Python commands directly. Ask the agent
to read the project state, choose the next action, and use the harness CLIs
itself while keeping progress saved in project files.

## Start Here

From the repository root, open Claude Code or Codex and paste:

```text
Continue project {{PROJECT_NAME}} from file state.

First use the project resume helper yourself, then read the source files it
lists. Do not ask the user to run it manually.

Read:
- projects/{{PROJECT_NAME}}/HANDOFF.md
- projects/{{PROJECT_NAME}}/state/current_state.md
- projects/{{PROJECT_NAME}}/state/project_health.md
- projects/{{PROJECT_NAME}}/state/state_doctor.md
- projects/{{PROJECT_NAME}}/state/agent_memory.md
- projects/{{PROJECT_NAME}}/state/next_actions.md
- projects/{{PROJECT_NAME}}/state/open_questions.md
- projects/{{PROJECT_NAME}}/state/command_queue.json

If `state/project_health.md` or `state/state_doctor.md` is missing, still a
starter file, or older than recent project progress, refresh dashboard-free
diagnostics before choosing the next action. Refresh state doctor first, then
project health, so the health report can route from the latest state diagnosis.
If safe starter files need repair, ask the agent to preview the repair first,
then apply it only if the preview is safe. The repair should report which files
were created and whether any repair errors occurred. It must not invent
research content.

Choose the highest-value next work. If multiple independent command-queue
entries can be handled by different owner agents, use
scripts.commands.agents.agent_orchestrator status-parallel, then use
scripts.commands.agents.agent_orchestrator parallel; otherwise execute one
serial next action. Explicit parallel --id requests should fail with a concrete
reason instead of silently skipping unsafe commands. If parallel prompts were
already written and their commands
are in progress, inspect them with
scripts.commands.agents.agent_orchestrator run-prepared --dry-run, run the
scoped group with run-prepared --group <group> --runner-command ... only after
dependencies are done, and close
reviewed batches with scripts.commands.agents.agent_orchestrator
finish-parallel --dry-run, then finish-parallel --group <group> --status done
--note ... or --result-file <command_id>=<worker-result-path>.

Use the harness CLIs yourself for structured state updates. Do not only tell me
which commands to run. Save important progress to files during the pass whenever
there is a result, blocker, direction change, failed assumption, experiment
outcome, or next-action change. Use
`python -m scripts.commands.review.progress_checkpoint record` for those
mid-pass checkpoints.

At the end, summarize changed files, verification, remaining blockers, and the
best next prompt.
```

## First Project Pass

The template starts before a research question is defined. The first useful pass
is usually:

```text
Use the motivation_planner role for {{PROJECT_NAME}}.

Clarify the research question, motivation, assumptions, constraints, and
candidate contribution from the user's idea. If enough detail is available,
use the brief intake workflow yourself before editing additional brief files.
Update 00_brief/, state files, and HANDOFF.md. If information is missing,
record it in state/open_questions.md instead of guessing.
```

After the brief is clear, ask for director triage:

```text
Use the director role for {{PROJECT_NAME}}.

Read the updated brief, current state, agent memory, next actions, open
questions, and command queue. Choose the next research step and update the
project state so a fresh agent can continue without chat history.
```

## GPU And Experiment Rules

GPU and server rules belong in the repository-level
`config/workspace_profile.local.json`, not inside this project folder.

For expensive experiments, tell the agent:

```text
Before running any expensive GPU job, design and run the smallest useful smoke
test. Queue independent experiments first. Show the scheduler plan, then launch
through the harness GPU scheduler so all launchable jobs that fit the configured
GPU cap can run in parallel. Record each job's command, scheduler job id,
expected output, and check procedure. Update run_state, agent status, and
HANDOFF.md while the jobs are running.
```

Jobs without `--depends-on` are treated as independent and may run in parallel.
Use `--depends-on <job_id>` for analysis, aggregation, or follow-up jobs that
must wait for a prerequisite job to succeed.

## Files To Inspect

Most users should inspect:

- `state/project_health.md`: dashboard-free health report and next best action.
- `state/state_doctor.md`: stale or contradictory state diagnostics.
- `09_report/README.md`: entry point for reader-facing outputs.
- `HANDOFF.md`: latest continuity note and next prompt.
- `state/current_state.md`: current project status.
- `state/next_actions.md`: human-readable next work.
- `state/open_questions.md`: missing inputs and decisions.

For experiment-heavy work, also inspect:

- `03_experiments/`: experiment plans, configs, run state, logs.
- `03_experiments/experiment_dag.json`: smoke-first and parallel-run DAGs.
- `03_experiments/data_roots.md`: dataset roots, split/version identifiers,
  and derived-data locations.
- `04_code/`: active experiment and research code.
- `05_results/`: working analysis, robustness, and intermediate result
  interpretation.
- `05_results/claim_graph.md` and `05_results/claim_graph.json`: working
  claim/evidence graph before final export.
- `05_results/experiment_results.csv`: structured working result rows before
  final export.
- `05_results/experiment_journal.md` and `05_results/experiment_journal.csv`:
  running ledgers of why each experiment was run, what happened, and why the
  result likely moved.
- `06_writing/terminology.md`: paper-wide glossary for consistent terms.
- `08_baselines/source_snapshots/`: cloned baseline GitHub/source repositories.
- `08_baselines/code_structure_plan.md`: structure comparison between baseline
  repos and the project's code layout.
- `08_baselines/baseline_compare.md`: generated comparison of cloned baseline
  repo structures.
- `07_reviews/agent_quality_audit.md`: continuity audit for agent output
  quality and resumability.
- `09_report/results/`: final exported result tables and claim evidence.

## Health Report vs. State Doctor

Use these two files before choosing the next action:

| File | Meaning | Use it when |
| --- | --- | --- |
| `state/project_health.md` | Research progress health report. It explains blockers, missing analysis, stale outputs, GPU queue gaps, and the best next action. | You want to know whether the research is moving correctly and what to do next. |
| `state/state_doctor.md` | State consistency diagnosis. It checks whether queue/status/result files contradict each other or are missing required state. | A new agent cannot confidently resume, or files look stale/inconsistent. |

The health report is not a paper report and not a browser dashboard. It is a
plain Markdown working-state summary for the next Claude/Codex session.

## What To Ask The Agent

Use these requests instead of manually running internal commands:

| If you want to... | Ask the agent to... | Main files updated |
| --- | --- | --- |
| Check project status | "Refresh project health and tell me the next blocker." | `state/project_health.md`, `state/state_doctor.md` |
| Repair missing starter files | "Preview state doctor repair for safe missing project surfaces. If safe, apply it, then refresh health." | `state/`, `03_experiments/`, `05_results/`, `06_writing/`, `08_baselines/` |
| Route health findings | "Preview the health report's suggested queue entries, then enqueue the safe ones." | `state/command_queue.json`, `state/next_actions.md` |
| Capture a rough idea | "Run brief intake and turn this idea into durable project files." | `00_brief/`, `02_planning/intake_summary.md`, `state/open_questions.md` |
| Plan experiments | "Create a smoke-first experiment DAG and mark independent parallel runs." | `02_planning/experiment_plan.md`, `03_experiments/experiment_dag.json` |
| Use GPUs efficiently | "Queue independent jobs, show the scheduler plan, then dispatch safe parallel jobs." | `state/gpu_experiment_queue.json`, `03_experiments/<exp_id>/run_state.json` |
| Finish an experiment | "Close out the experiment and explain why performance improved, regressed, or stayed flat." | `05_results/experiment_results.csv`, `05_results/experiment_journal.md`, `03_experiments/<exp_id>/analysis.md` |
| Compare baseline repos | "Compare cloned baseline source structures before shaping project code." | `08_baselines/baseline_compare.md`, `08_baselines/code_structure_plan.md` |
| Strengthen claims | "Refresh the claim graph and identify unsupported or weak claims." | `05_results/claim_graph.md`, `05_results/claim_graph.json` |
| Check handoff quality | "Audit whether previous agent work is resumable from files." | `07_reviews/agent_quality_audit.md` |

State doctor repair creates only safe starter files or template-backed
continuity files. It must not invent research content, datasets, metrics,
baselines, results, or conclusions.

## Project Folders

- `00_brief/`: research question, motivation, problem statement, assumptions,
  constraints, and contribution candidates.
- `01_literature/`: bibliography, paper notes, related work matrix, gap
  analysis, and prior limitations.
- `02_planning/`: director plan, milestones, task graph, and decision log.
- `03_experiments/`: experiment registry, data roots, preregistration,
  experiment DAGs, reproducibility manifests, metrics, configs, logs, results,
  and analyses.
- `04_code/`: active research/experiment code, notebooks, tests,
  implementation notes, and code review.
- `05_results/`: aggregate results, experiment journal, claim graph,
  robustness checks, figures, tables, failure cases, and interpretation.
- `06_writing/`: terminology glossary, outline, section drafts, and working
  paper/report drafts.
- `07_reviews/`: critiques, reviewer risks, venue-form reviews, agent quality
  audits, rebuttal notes, and revision planning.
- `08_baselines/`: baseline registry, prior research inventory, cloned
  GitHub/source repositories, baseline comparison, structure reports,
  code-structure plans, patches, and run scripts.
- `09_report/`: final reader-facing and release-facing artifacts only.
- `state/`: current state, project health, state doctor, agent memory, next
  actions, open questions, progress checkpoints, structured queues, status,
  messages, and handoff state.

## Filesystem Safety

This project folder is the active folder for research work. Agents must not
delete, move, overwrite, or recursively clean any directory outside
`projects/{{PROJECT_NAME}}/` unless the user explicitly assigns harness-level
maintenance.

Cleanup commands must not target parent directories, sibling projects,
datasets, checkpoints, external source trees, home-directory folders, or system
paths.

## Progress Checkpoint Hook

During multi-step work, ask the agent to save meaningful progress before the
final response:

```text
When a result, blocker, direction change, failed assumption, experiment outcome,
memory note, or next-action change appears, run the progress checkpoint hook and
cite the project files it updated.
```

The agent-facing command is:

```bash
python -m scripts.commands.review.progress_checkpoint record --project {{PROJECT_NAME}} --agent <agent_name> --kind result --summary "<what changed>" --evidence <path> --output <path> --memory "<durable lesson>" --next-action "<next action>"
```

For experiments, include `--exp-id <exp_id>`, `--rationale`, `--dataset`,
`--method`, `--baseline-id`, and `--result-analysis`. When the outcome is known,
include `--run-status <status>` so `03_experiments/<exp_id>/run_log.md`,
`03_experiments/<exp_id>/analysis.md`, `run_state.json`,
`05_results/experiment_journal.md`, and `05_results/experiment_journal.csv`
are updated together.

For final experiment outcomes, prefer the experiment completion workflow. It
keeps `05_results/experiment_results.csv`,
`05_results/experiment_journal.md`, `05_results/experiment_journal.csv`,
`03_experiments/<exp_id>/analysis.md`,
`03_experiments/<exp_id>/run_state.json`,
`03_experiments/artifact_registry.csv`, and
`03_experiments/data_roots.md` synchronized.

Also keep `05_results/experiment_journal.md` and
`05_results/experiment_journal.csv` current. Each completed experiment should
record why it was run, the result, and the evidence-backed analysis of why
performance improved, regressed, or stayed flat.

Register completed experiment outputs, metric files, checkpoints, logs, and
evidence paths in `03_experiments/artifact_registry.csv`. Register dataset
roots, splits, and versions in `03_experiments/data_roots.md`.

By default, result ingest writes working rows to
`05_results/experiment_results.csv`. Add `--final-export` only when rows are
stable enough for `09_report/results/experiment_results.csv`.

```bash
python -m scripts.commands.review.progress_checkpoint record --project {{PROJECT_NAME}} --agent <agent_name> --kind experiment_result --exp-id <exp_id> --summary "<observed result>" --evidence 03_experiments/<exp_id>/run_log.md --output 03_experiments/<exp_id>/results/ --rationale "<why this run was needed>" --dataset "<dataset/split>" --method "<method>" --baseline-id "<baseline>" --result-analysis "<why performance improved/regressed/stayed flat>" --run-status succeeded
```

If the agent sees that its five-hour or weekly usage remaining is below 5%, run:

```bash
python -m scripts.commands.review.progress_checkpoint limit-handoff --project {{PROJECT_NAME}} --agent <agent_name> --summary "<what this session changed>" --five-hour-remaining-pct <pct> --weekly-remaining-pct <pct> --in-progress "<current work>" --next-action "<resume step>" --memory "<durable lesson>"
```

This writes `state/limit_handoff.md` and appends `state/agent_memory.md` so the
next session can resume cleanly.

If `config/workspace_profile.local.json` defines an official non-interactive
JSON status command under `agent_limits.status_command`, prefer:

```bash
python -m scripts.commands.review.progress_checkpoint check-limits --project {{PROJECT_NAME}} --agent <agent_name> --summary "<what this session changed>" --in-progress "<current work>" --next-action "<resume step>" --memory "<durable lesson>"
```

Do not open a nested interactive Codex/Claude TUI just to type `status`.

## Code And Report Boundary

- Use `04_code/` for active experiment implementation, debugging, tests,
  notebooks, and research code organization.
- Use `03_experiments/` for experiment configs, preregistration, run state,
  logs, and run-local outputs.
- Use `05_results/` for working analysis, robustness checks, intermediate
  figures, and interpretation.
- Use `08_baselines/source_snapshots/<baseline_id>/` for cloned baseline
  GitHub/source repositories and `08_baselines/code_structure_plan.md` to decide
  how project code should be structured relative to those baselines.
- Use `09_report/src/` only after code is cleaned and stable enough for
  release/reviewer-facing distribution.
