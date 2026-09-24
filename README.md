# Research Agent for Me

A file-based workspace for running research projects with Claude, Codex, or any
coding agent that can read and edit files.

The goal is simple: you describe the research work, the agent does the work, and
the workspace keeps durable project state in files so the next session can pick
up where the last one stopped.

You do not need to memorize the internal harness commands. Use the copy-paste
prompts below and let the agent operate the workspace.

## What This Repository Is

Research Agent Workspace is a project template plus a set of agent runbooks for
research workflows.

It helps an agent:

- turn rough ideas into concrete research questions
- review literature and baseline candidates
- import existing research code safely
- design and run experiments with smoke tests
- batch independent GPU jobs when capacity is available
- preserve experiment results, analysis, blockers, and next actions in files
- keep working results separate from final reader-facing artifacts

The workspace is intentionally file-based. A new Claude/Codex session can resume
from `HANDOFF.md` and `state/` without relying on previous chat history.

## How It Works

```text
You give a prompt
        |
        v
Claude/Codex reads project file state
        |
        v
The agent updates research folders and state files
        |
        v
The next session resumes from those files
```

The important rule is: **research progress must land in files, not only in chat.**

## Quick Start

1. Open Claude Code, Codex, or another coding agent in this repository root.
2. Paste the Initial Setup prompt.
3. Add your local preferences, including output language and GPU rules.
4. Create a new project or import an existing repo.
5. Use the Resume Work prompt for every later session.
6. Inspect changed files after each pass.

## Automated Setup And Execution

Clone the workspace, then configure portable local skills, Claude session hooks
and bounded headless execution:

```sh
git clone https://github.com/hasungjun0521/Research_Agent_for_me.git
cd Research_Agent_for_me
python -m scripts.commands.release.automation_setup --provider codex
python -m scripts.commands.research.research_autopilot init --project my_study --idea "Your research question and constraints"
python -m scripts.commands.research.research_autopilot plan --project my_study
python -m scripts.commands.research.research_autopilot run --project my_study --provider codex --max-steps 3
```

Choose `claude` instead of `codex` for Claude Code. Install and authenticate the
selected CLI first. The core needs Python 3.10+ and Git. Run setup with `--dry-run`
to preview; existing local configuration is preserved. The runtime records
prompts, logs, completion evidence and blockers, and enforces task/time limits.
A drained work queue is not a claim that scientific research is complete.

See [Automation guide](docs/automation.md) for installation, permissions,
resume, failure recovery and the exact automation boundaries.

## Initial Setup

Paste this once from the repository root:

```text
Set up this repository as a research-agent workspace.

1. If you are Claude Code, read CLAUDE.md. If you are Codex, read AGENTS.md.
2. Read README.md, project.yaml, prompts/shared/output_contracts.md, and
   prompts/shared/agent_status_protocol.md.
3. Create config/workspace_profile.local.json from the public example using the
   workspace profile setup command yourself.
4. Put my output language, GPU/SLURM, queue-status, and node-status preferences
   in the local profile.
5. Do not put private paths, credentials, or lab-specific defaults in tracked
   files.
6. Tell me which files you created or changed and what I should do next.
```

Local machine settings belong in `config/workspace_profile.local.json`. That
file is ignored by git.

## Create A New Project

Use this when starting from a research idea:

```text
Start a new research project named <project_name>.

Research idea:
<describe the idea, target problem, data, method, constraints, and goals>

Tasks:
1. Create the project folder from the template.
2. Use the project intake workflow yourself when enough detail is available.
3. Write assumptions, constraints, and open questions in 00_brief/.
4. Triage the project from the director role.
5. Update state/current_state.md, state/agent_memory.md,
   state/next_actions.md, and HANDOFF.md.
6. Tell me which files I should inspect and what prompt I should give next.
```

Use a short folder-safe project name, for example `paper_method_study` or
`dataset_metric_probe`.

## Import Existing Research Code

Use this when you already have a repo or prototype:

```text
Import an existing research repository into this workspace.

Source path: <path_to_existing_repo>
New project name: <project_name>

Requirements:
1. Run a dry run first and tell me which files will be copied or skipped.
2. If the plan is safe, perform the import.
3. Preserve the source snapshot under 04_code/imported_repo/.
4. Write the structure and risks to 02_planning/imported_repo_inventory.md.
5. Create the next action as a director triage task.
6. Do not import private files, datasets, checkpoints, or credentials.
7. Keep imported source under 04_code/; do not place imported source under
   state/ or 09_report/.
```

## Resume Work

Use this at the start of most sessions:

```text
Continue project <project_name> from file state.

First run the project resume summary if available, then read the source files it
lists.

Read:
- projects/<project_name>/HANDOFF.md
- projects/<project_name>/state/current_state.md
- projects/<project_name>/state/project_health.md
- projects/<project_name>/state/state_doctor.md
- projects/<project_name>/state/agent_memory.md
- projects/<project_name>/state/next_actions.md
- projects/<project_name>/state/open_questions.md
- projects/<project_name>/state/command_queue.json

If `state/project_health.md` or `state/state_doctor.md` is missing, still a
starter file, or older than recent project progress, refresh dashboard-free
diagnostics before choosing the next action. Refresh state doctor first, then
project health, so the health report can route from the latest state diagnosis.
If safe starter files need repair, ask the agent to preview the repair first,
then apply it only if the preview is safe. The repair should report which files
were created and whether any repair errors occurred. It must not invent
research content.

Pick the highest-value next action and execute it. Use harness CLIs yourself.
Save progress to files as you work.

Do not wait for me to explicitly ask for multi-agent work. If the task is deep,
broad, or naturally parallel, first identify the critical path you should handle
locally, then inspect safe sidecar work for parallelization. If several
independent command-queue entries can be handled by different owner agents
without dependency or output conflicts, prepare or run a bounded parallel agent
batch before falling back to one serial action.

If parallel prompts were already written in a previous session, inspect them,
run only the scoped ready group, and finish the group after reviewing worker
outputs. Do not launch prompts whose dependencies are unfinished.

At the end, summarize changed files, verification, remaining blockers, and the
best next prompt.
```

## Features

The most important automation surfaces are:

- Runner profiles: optional local commands in
  `config/workspace_profile.local.json` that let the orchestrator run prepared
  Claude/Codex prompts without hard-coding machine-specific runner commands in
  tracked files.
- Internal command surfaces agents use behind these requests include
  `scripts.commands.agents.agent_orchestrator status-parallel`,
  `scripts.commands.agents.agent_orchestrator run-prepared`,
  `scripts.commands.agents.agent_orchestrator finish-parallel`,
  `--all-prepared`, `scripts.commands.review.progress_checkpoint record`, and
  GPU `plan_diagnostics`.
- Parallel agent batches: independent command-queue entries can be prepared,
  launched, and finished as a bounded group when dependencies and output paths
  are safe.
- Experiment completion: finished runs should be closed through one workflow
  that updates the result CSV, experiment journal, per-experiment analysis,
  run state, artifact registry, data-root ledger, agent status, and event log
  together.
- GPU lifecycle refresh: queued/running GPU jobs can be dispatched in parallel
  within the configured GPU cap, then refreshed from scheduler-visible state so
  project run-state files do not drift.
- Dashboard-free health reports: the agent can write a plain Markdown health
  report that explains blockers, stale state, experiment gaps, GPU queue state,
  the best next action, and copy-paste-ready agent requests without opening a
  browser dashboard. The report also suggests command-queue entries when the
  next work should be routed to a specific role.
- Brief intake: rough research ideas can be turned into durable brief files,
  constraints, open questions, and director-routing context.
- Experiment planner: new experiment families can be planned as smoke-first
  DAGs with independent parallel runs, expected outputs, and check procedures.
- Claim graph: working claims, experiment rows, baseline comparisons, and
  analysis notes can be connected before claims are strengthened in writing.
- Baseline compare: cloned baseline repositories can be compared structurally
  before shaping `04_code/src/`, keeping project code more standardized.
- Agent quality audit: the workspace can check whether previous agent passes
  left enough file evidence, checkpoints, and output paths for the next session.

## Health Report vs. State Doctor

These two files are the main dashboard-free diagnostics:

| File | Meaning | Use it when |
| --- | --- | --- |
| `state/project_health.md` | Research progress health report. It explains blockers, missing analysis, stale outputs, GPU queue gaps, and the best next action. | You want to know whether the research is moving correctly and what to do next. |
| `state/state_doctor.md` | State consistency diagnosis. It checks whether queue/status/result files contradict each other or are missing required state. | A new agent cannot confidently resume, or files look stale/inconsistent. |

The health report is not a paper report and not a browser dashboard. It is a
plain Markdown working-state summary for the next Claude/Codex session.

| Area | What the agent can do | Where it writes |
| --- | --- | --- |
| Brief | Research question, motivation, assumptions, constraints | `00_brief/` |
| Literature | Paper notes, citation gaps, related work matrix | `01_literature/` |
| Planning | Director plan, milestones, decisions, task graph | `02_planning/` |
| Experiments | Preregistration, configs, run state, logs, data roots | `03_experiments/` |
| Code | Active implementation, tests, notebooks, adapters | `04_code/` |
| Results | Working result CSV, analysis, robustness, journals | `05_results/` |
| Writing | Draft sections and terminology glossary | `06_writing/` |
| Review | Critic comments, reviewer risks, rebuttal planning | `07_reviews/` |
| Baselines | Cloned source snapshots, structure reports, adapters | `08_baselines/` |
| Final report | Reader-facing exports and packaged artifacts | `09_report/` |
| State | Memory, handoff, command queue, agent status, health report | `state/` |

## What You Can Ask The Agent To Do

You do not need to know the internal command names. Use requests like these:

| If you want to... | Ask the agent to... | Main files updated |
| --- | --- | --- |
| See whether a project is healthy | "Check project health and tell me the next blocker." | `state/project_health.md`, `state/state_doctor.md` |
| Repair missing starter files | "Preview state doctor repair for safe missing project surfaces. If safe, apply it, then refresh health." | `state/`, `03_experiments/`, `05_results/`, `06_writing/`, `08_baselines/` |
| Route health findings | "Preview the health report's suggested queue entries, then enqueue the safe ones." | `state/command_queue.json`, `state/next_actions.md` |
| Start from a rough idea | "Run brief intake and turn this idea into project state." | `00_brief/`, `02_planning/intake_summary.md`, `state/open_questions.md` |
| Plan experiments safely | "Create a smoke-first experiment plan and identify parallel runs." | `02_planning/experiment_plan.md`, `03_experiments/experiment_dag.json` |
| Use idle GPUs efficiently | "Queue independent jobs first, show the scheduler plan, then dispatch safe parallel jobs." | `state/gpu_experiment_queue.json`, `03_experiments/<exp_id>/run_state.json` |
| Finish an experiment | "Close out this experiment and explain why the result improved or regressed." | `05_results/experiment_results.csv`, `05_results/experiment_journal.md`, `03_experiments/<exp_id>/analysis.md` |
| Compare baseline repos | "Compare cloned baseline repo structures before shaping project code." | `08_baselines/baseline_compare.md`, `08_baselines/code_structure_plan.md` |
| Strengthen paper claims | "Refresh the claim graph and check which claims are actually supported." | `05_results/claim_graph.md`, `05_results/claim_graph.json` |
| Check agent handoff quality | "Audit whether prior agent work is resumable from files." | `07_reviews/agent_quality_audit.md` |
| Prepare final artifacts | "Package only stable reader-facing outputs." | `09_report/`, artifact manifests |

## Common Prompts

### Check project health

```text
Check project health for <project_name>.

Use the dashboard-free health report and state doctor yourself. Tell me the
overall status, highest-priority blocker, stale state if any, and the next
action you recommend. If safe starter surfaces are missing, run state doctor
repair preview first. If the preview is safe, apply repair, then refresh state
doctor and project health in that order. Save the refreshed health report in
project state. Do not infer missing research content during repair.
```

### Capture a rough idea

```text
Use brief intake for <project_name>.

Turn the rough idea below into durable brief files, constraints, open questions,
and director-routing context. Do not guess missing dataset, metric, baseline, or
compute constraints.

Idea:
<paste rough idea>
```

### Clarify an idea

```text
Use the motivation_planner role for <project_name>. Clarify the research
question, problem statement, candidate contributions, weak assumptions, and
questions the literature_reviewer should answer next.
```

### Review literature and baselines

```text
Use the literature_reviewer role for <project_name>. Separate papers that
support the claim, baseline candidates, and claims that still need citations.
Mark unsupported claims as unsupported.
```

### Design experiments

```text
Use the experiment_designer role for <project_name>. Design experiments for the
core claims, including success criteria, failure criteria, metrics, baselines,
confounders, preregistration updates, and smoke-test requirements.
Create a smoke-first experiment DAG and identify independent runs that can be
queued in parallel after the smoke test passes.
```

### Implement or run experiments

```text
Use the code_agent role for <project_name>. Read the preregistration and
reproducibility manifest first. Start with the smallest smoke test. Before
expensive GPU execution, show the scheduler plan and update project state.
```

### Analyze results

```text
Use the data_analyst and result_interpreter roles for <project_name>. Update the
working result CSV, experiment journal, run analysis, and claim evidence board.
Explain why performance improved, regressed, or stayed flat. Separate confirmed
causes from plausible hypotheses.
Refresh the working claim graph before strengthening claims.
```

### Write or critique

```text
Use the writing_agent or critic role for <project_name>. Review
06_writing/draft.md, 05_results/interpretation.md, and
05_results/claim_evidence_board.md first. Check stable 09_report exports only
when they already exist. Flag overclaiming, missing evidence, weak
reviewer-facing arguments, and required revisions.
```

### Build a weekly progress deck

```text
Build the weekly development deck for <project_name>. Collect the last week of
progress (progress log, experiment results, next actions, commits, figures) and
render an image-first PowerPoint on the lab template. Show me the --dry-run
summary first, then save the deck.
```

The agent runs `python -m scripts.commands.reports.weekly_deck build --project
<project_name>` and writes `05_results/weekly_decks/weekly_<date>.pptx`. The deck
is image-first (KPI tiles, result charts, harvested figures). Rendering needs the
optional extra: `pip install -e .[deck]` (python-pptx + matplotlib). The base look
comes from `config/ppt_template_local.pptx` (machine-local, gitignored).

## GPU Workflow

Give the agent your GPU rules in plain language:

```text
Update the workspace profile with my GPU rules.

- scheduler: SLURM
- max GPUs I should occupy at once: 4
- default GPU preference order: a100, a6000, a5000, a4000
- a100 profile: partition=a100, node=node01, mem=80G, cpus=8
- a6000 profile: partition=a6000, node=node06, mem=48G, cpus=8
- queue status should use squeue --me
- node status should use scontrol show node {node} -o
- GPU experiments must not be launched with ad hoc sbatch/srun commands.
- Use the smoke-first rule before expensive runs.
- If several independent experiments are queued and GPUs are available, use the
  internal scripts.commands.experiments.gpu_scheduler dispatch workflow so
  launchable jobs run in parallel within my GPU cap.
- After jobs start or finish, use the GPU scheduler refresh workflow to sync
  scheduler-visible state back into the project queue and run_state files.
- Explain scheduler plan diagnostics before reducing a parallel batch.
- If a smoke test is CPU-heavy or long-running, queue it as a bounded GPU smoke
  job instead of saturating CPU resources.
```

For expensive experiments:

```text
Before running this experiment, design a smoke test and show me the scheduler
plan. Record the success criteria, failure criteria, expected outputs, check
procedure, and stop condition in project files before execution.

If several independent jobs are ready and GPUs are free, queue them together and
use the GPU scheduler dispatch workflow instead of launching them one by one.

During execution, update agent status, run_state, command/job id, expected
output, and check procedure. After each completed experiment, analyze why
performance improved, regressed, or stayed flat and update the experiment
journal, artifact registry, and data-root ledger.
```

## Result Tracking

The workspace expects every meaningful result to be saved while work is
happening.

Ask the agent to record experiment outcomes like this:

```text
Record this as an experiment-result checkpoint for <project_name>.

Include:
- experiment id
- observed result
- evidence path
- output path
- why the run was needed
- dataset and split
- method
- baseline
- whether the run succeeded, failed, or is blocked
- why performance improved, regressed, or stayed flat
- the next concrete follow-up
```

The most important result files are:

| File | Purpose |
| --- | --- |
| `05_results/experiment_results.csv` | Structured working result rows |
| `05_results/experiment_journal.md` | Human-readable explanation of why each experiment was run and why the result moved |
| `03_experiments/artifact_registry.csv` | Output, metrics, evidence, and result artifact ledger |
| `03_experiments/data_roots.md` | Dataset root, split, and version ledger |
| `03_experiments/<exp_id>/analysis.md` | Per-experiment analysis and uncertainty |
| `03_experiments/<exp_id>/run_state.json` | Current run status, expected output, and check procedure |
| `05_results/claim_evidence_board.md` | Working claim-to-evidence board |
| `06_writing/terminology.md` | Shared glossary for consistent paper wording |

## Project Structure

```text
projects/<project_name>/
  00_brief/        Research question, motivation, assumptions, constraints
  01_literature/   Paper notes, related work, gap analysis
  02_planning/     Plans, milestones, decision log
  03_experiments/  Experiment design, configs, run state, logs
  04_code/         Active research/experiment code, tests, implementation notes
  05_results/      Working analysis, robustness, result tables, journals
  06_writing/      Paper or report drafts and terminology
  07_reviews/      Critique, reviewer risks, rebuttal planning
  08_baselines/    Baseline papers, cloned source repos, structure plans
  09_report/       Final reader-facing and release-facing artifacts
  state/           Agent memory, current state, next actions, queues, messages
```

Keep active experiment code in `04_code/`. Keep experiment process, configs,
logs, and run state in `03_experiments/`. Keep working analysis in
`05_results/`. Keep cloned baseline repos in
`08_baselines/source_snapshots/<baseline_id>/`.

Use `09_report/` only for final reader-facing artifacts and cleaned release
exports. Export code to `09_report/src/` only after it has been cleaned and
stabilized from `04_code/`.

## What To Inspect After A Pass

Most users should inspect:

| File or folder | Why it matters |
| --- | --- |
| `HANDOFF.md` | Latest handoff and next prompt |
| `state/current_state.md` | Current project state |
| `state/next_actions.md` | Next work |
| `state/open_questions.md` | Blockers and unknowns |
| `03_experiments/` | Experiment plans, run state, logs |
| `04_code/` | Active research and experiment code |
| `05_results/` | Working results and analysis |
| `08_baselines/` | Baseline source snapshots and structure plans |
| `09_report/README.md` | Final artifact index after stable export |

## Session Handoff

If an agent session is close to its usage limit, ask it to write a handoff before
ending:

```text
My remaining agent limit is below 5%.

Before ending this session, write a limit handoff for <project_name>.
Summarize what changed, what is currently in progress, the exact resume step,
durable memory, unresolved questions, and the prompt the next Claude/Codex
session should use.
```

This creates `state/limit_handoff.md` and gives the next session a concrete
continuation prompt. The harness does not drive the Codex interactive TUI to
type `status`; use percentages shown by the agent UI or an official
non-interactive status command when one is available.

## Recovery Prompts

### State looks inconsistent

```text
Reconcile workflow state for project <project_name>. Compare command queue,
agent status, open questions, loop summary, and HANDOFF.md. Fix what can be
fixed through harness CLIs and record uncertain items as blockers.
```

### An experiment failed

```text
Diagnose the failed experiment in project <project_name>. Read run logs,
run_state, reproducibility manifest, and recent code changes. Start with the
smallest reproducible repair step. Preserve failed results and uncertainty.
```

### Results were not saved

```text
Audit whether the last pass saved its results to files. Find results, blockers,
and next actions that exist only in chat or transient notes, then recover them
into state files and HANDOFF.md. Mark uncertain reconstructions as uncertain.
```

## Agent Compatibility

- Claude Code reads `CLAUDE.md`.
- Codex reads `AGENTS.md`. Gemini CLI reads `GEMINI.md`.
- `CLAUDE.md` and `GEMINI.md` both import `AGENTS.md`, so every agent shares the
  same base rules.
- `prompts/agents/` contains role prompts.
- `prompts/skills/` contains task runbooks.
- `.claude/skills/` contains auto-discoverable agent skills (SKILL.md) that wrap
  the harness CLIs across the project lifecycle (brief-intake, project-resume,
  literature-review, experiment-run, gpu-dispatch, agent-orchestration,
  baseline-intake, claim-evidence, progress-checkpoint, weekly-deck,
  project-hygiene, skill-synthesis, release-closeout). Claude Code loads these
  automatically. Codex and Gemini CLI use the same SKILL.md format — run
  `tools/install_codex_skills.sh` (`~/.codex/skills/`) or
  `tools/install_gemini_skills.sh` (`~/.gemini/skills/`) to link them there. See
  `docs/installed_agent_skills.md`.

Claude should not assume the upstream Codex skills are installed. It should read
`prompts/skills/*.md` as plain Markdown runbooks.

## Maintainer Notes

Normal users do not need this section.

Before publishing or tagging harness changes, ask the agent to run the
`scripts.commands.release.release_check` release gate for `v8.0.0`, skipping the
paper build only when LaTeX is not available and keeping strict template-state
checks enabled.

Optional dashboard compatibility checks are opt-in. Add dashboard checks only
when intentionally maintaining the parked dashboard.

## Reference

Agents and maintainers can use:

- `scripts/README.md`: harness CLI details
- `ARCHITECTURE.md`: internal design
- `project.yaml`: inventory and operating rules
- `docs/private_github_publish.md`: publishability checklist
