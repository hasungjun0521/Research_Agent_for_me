# Research Agent Workspace Architecture

> File-based multi-agent research workflow harness.
> This is the design map for humans and agents maintaining the workflow.

## 1. Design Principles

### 1.1 Files Are The Interface

The workspace is intentionally file-based. Agents do not depend on hidden chat
memory to continue a project. They read project files, update structured state
through scripts, and leave enough evidence for a future session to resume.

The durable interface is:

- `projects/<project>/state/` for workflow state.
- `projects/<project>/09_report/` for reader-facing final artifacts.
- `projects/<project>/HANDOFF.md` for project-local continuity.
- root `HANDOFF.md` for harness maintenance continuity.
- `config/workspace_profile.example.json` plus ignored
  `config/workspace_profile.local.json` for user/lab-local preferences.
- `state/project_health.md` and `state/state_doctor.md` for dashboard-free
  health and stale-state diagnostics.

### 1.2 Human-Readable First, Machine-Checkable Second

Every workflow surface should be understandable to a researcher without reading
internal JSON. `project_resume`, `09_report/README.md`, loop summaries, command
actions, and next prompts must say what happened, what result exists, and what
should happen next in plain language.

Machine-readable files still matter. They make resume summaries, orchestration,
and verification scripts deterministic. The rule is: structured state powers
tools, but prose must carry meaning.

Machine-local preferences are intentionally separate from project state. The
workspace profile controls agent/report language, GPU caps, GPU profile names,
node/partition defaults, and scheduler commands without hard-coding one user's
environment into the public harness.

### 1.3 Evidence Before Claims

The harness treats research claims as untrusted until evidence paths exist.
Experiment-backed claims must connect stable IDs across preregistration,
reproducibility manifests, result tables, robustness tables, claim-evidence
rows, paper text, and reviewer-risk notes.

Negative, failed, or blocked results are evidence. They should be recorded
instead of hidden.

### 1.4 Bounded Autonomy

Agents may run long workflows, but the workflow must have explicit boundaries:

- a project folder,
- a command or loop goal,
- a duration or stop condition,
- expected output files,
- a completion promise or result detector,
- and a clear blocked path.

GPU work is allowed only when scheduler plans, run state, job ids, expected
outputs, and check procedures make progress observable. Legacy Ralph loops are
optional support tooling and should not be used as the default workflow.

## 2. System Topology

```text
Human / Codex Session
  |
  v
Director role
  |
  +--> command queue             state/command_queue.json
  +--> loop summary              state/loop_summary.json
  +--> agent messages            state/agent_messages.json
  +--> votes                     state/agent_votes.json
  +--> sessions                  state/sessions/<session_id>/
  +--> Ralph loop                state/ralph_loop.json (legacy optional)
  +--> GPU queue                 state/gpu_experiment_queue.json
  +--> project health            state/project_health.md
  +--> state doctor              state/state_doctor.md
  |
  v
Role agents
  |
  +--> motivation_planner
  +--> literature_reviewer
  +--> experiment_designer
  +--> code_agent
  +--> data_analyst
  +--> result_interpreter
  +--> writing_agent
  +--> venue_reviewer
  +--> critic
  |
  v
Research artifacts
  |
  +--> 00_brief/ through 08_baselines/      working evidence
  +--> 09_report/                           reader-facing final artifacts
  +--> HANDOFF.md                           continuation state
```

Claude/Codex native sessions plus these files own the normal workflow. The
dashboard is optional support tooling over the same files; it does not own the
workflow and it does not start or stop agents by itself.

### 2.1 Portable Automation Entrypoints

`automation_setup` connects canonical repository skills, local Claude hooks,
CLI adapters and machine-local runner settings. `research_autopilot init` creates
a project through existing commands; `plan` inspects dispatch eligibility; `run`
refreshes diagnostics and advances ready queue entries in a bounded session.
It reuses role prompts and queue state rather than introducing another research
state machine. Every invocation keeps prompts, CLI logs and a run journal under
`state/sessions/`. Explicit task closeout plus changed evidence is required to
continue, and queue exhaustion never implies scientific or publication approval.

The native session remains a supported entrypoint. Claude hooks provide context
and a one-time save reminder; they never launch experiments. Codex discovers the
same skills in generated `.agents/skills`. See `docs/automation.md` for setup,
limits and recovery. Private profiles and installed hook settings stay ignored.

## 3. Project Filesystem Contract

Each project under `projects/<project>/` follows the same shape:

- `00_brief/`: research question, motivation, assumptions, constraints, and
  contribution candidates.
- `01_literature/`: papers, paper notes, related-work matrix, gap analysis, and
  prior limitations.
- `02_planning/`: director plans, milestones, task graph, and decision log.
- `02_planning/experiment_plan.md`: smoke-first experiment family plans.
- `03_experiments/`: experiment registry, dataset and metric registries,
  experiment DAGs, preregistration, run state, config, analysis notes, and
  reproducibility manifests.
- `04_code/`: project code, notebooks, tests, implementation notes, and code
  review notes. Existing repositories imported with
  `scripts/commands/projects/import_research_repo.py` are copied under
  `04_code/imported_repo/` so their runnable structure is preserved while the
  surrounding project template organizes research state.
- `05_results/`: working result interpretation, claim graphs, failure cases,
  robustness notes, generated figures, and non-final tables.
- `06_writing/`: draft sections and outline.
- `07_reviews/`: critic comments, venue-form reviews, agent quality audits,
  reviewer attack matrix, rebuttal notes, and revision plans.
- `08_baselines/`: baseline registry, source snapshots, structure reports,
  baseline comparison, run scripts, adaptation notes, and patches.
- `09_report/`: final reader-facing entry point.
- `state/`: workflow state used by scripts, agents, and optional support tools.

`09_report/` is intentionally narrow. It should contain only final/report-facing
source code, paper files, analysis scripts, figures, and result tables. Scratch
notes belong in `00_brief/` through `08_baselines/` or `state/sessions/`.

## 4. Agent Workflow

### 4.1 Director

The director chooses the next concrete task, checks risk/confidence, updates
file-visible state, and routes work. It should not silently convert broad goals
into untracked work. Use command queue entries, loop summaries, handoff files,
and progress checkpoints.

### 4.2 Lead-Style Routing

When a task needs decomposition, the director or lead-style pass uses the shared
dispatch contract:

- `prompts/shared/research_routing_matrix.md`
- `prompts/shared/research_handoff_graph.md`
- `prompts/shared/leader_dispatch_protocol.md`
- `prompts/shared/risk_confidence_matrix.md`
- `prompts/shared/research_brain_protocol.md`

`LEADER DISPATCH` blocks are validated with:

```bash
python -m scripts.commands.review.leader_dispatch validate --file <leader-output.md>
```

Worker outputs are validated with:

```bash
python -m scripts.commands.review.worker_result validate --file <worker-output.md>
```

### 4.3 Worker Agents

A worker owns one concrete task. It should read only the files needed for that
task, update only the expected artifacts, and return a compact result block with
status, confidence, files read, files updated, evidence, blockers, and next
action.

Workers do not invent new routing. If a task is wrong or missing inputs, they
return `BLOCKED` or use `state/agent_messages.json`.

## 5. State Model

State files are modified through scripts, not by hand:

- `scripts/commands/agents/agent_status.py`: current role status and lifecycle events.
- `scripts/commands/review/command_queue.py`: user-visible work ownership and completion.
- `scripts/commands/review/loop_summary.py`: one-screen summary, completed work, results,
  and next actions.
- `scripts/commands/agents/agent_messages.py`: agent-to-agent questions, handoffs, blockers,
  reviews, and decisions.
- `scripts/commands/agents/agent_vote.py`: independent votes for important or high-risk work.
- `scripts/commands/agents/agent_events.py`: append-only activity and hook-visible events.
- `scripts/commands/review/progress_checkpoint.py`: durable mid-pass progress,
  memory, blockers, next actions, and experiment outcome checkpoints.
- `scripts/commands/projects/project_resume.py`: compact file-state summary for
  fresh Claude/Codex continuation sessions.
- `scripts/commands/projects/project_health.py`: dashboard-free status report
  with blockers, next best action, and copy-paste-ready agent requests.
- `scripts/commands/projects/state_doctor.py`: stale or contradictory project
  state diagnostics.
- `scripts/commands/projects/brief_intake.py`: rough-idea intake into durable
  brief files, constraints, intake summaries, and open questions.
- `scripts/commands/review/session_state.py`: isolated per-loop scratchpads, plans, results, and
  artifacts.
- `scripts/commands/review/ralph_loop.py`: bounded fresh-context loops.
- `scripts/commands/experiments/gpu_scheduler.py` and `scripts/commands/experiments/gpu_monitor.py`: queued and running
  GPU experiments. The scheduler reads GPU caps, profile names, nodes,
  partitions, and status commands from the workspace profile.
- `scripts/commands/experiments/experiment_planner.py`: smoke-first experiment
  DAGs with dependency-aware parallel main-run nodes, expected outputs, and
  check procedures.
- `scripts/commands/reports/claim_graph.py`: working claim/evidence graph that
  connects claims, experiment rows, baselines, and analysis notes.
- `scripts/commands/baselines/baseline_compare.py`: bounded source snapshot
  comparison before shaping `04_code/src/`.
- `scripts/commands/review/agent_quality_audit.py`: continuity audit for
  output-file evidence, progress checkpoints, and experiment-result analysis.
- `scripts/commands/review/pattern_memory.py`: reusable project-local workflow lessons.

The state model is append-friendly where history matters and overwrite-friendly
where a single source of truth matters. For example, `agent_events.jsonl` is
append-only, while `loop_summary.json` is the current one-screen recap.

## 6. Report And Artifact Flow

Final artifacts flow into `09_report/`:

```text
03_experiments/exp_*/run_state.json
03_experiments/exp_*/reproducibility_manifest.json
05_results/statistical_robustness.md
05_results/claim_graph.md
05_results/claim_graph.json
07_reviews/reviewer_attack_matrix.md
07_reviews/agent_quality_audit.md
08_baselines/baseline_compare.md
state/project_health.md
        |
        v
09_report/results/*.csv
09_report/analysis/
09_report/figures/
09_report/paper/main.tex
09_report/src/
        |
        v
09_report/README.md
```

`scripts/commands/reports/report_snapshot.py` is the shared source for report-table counts and
latest result files. `scripts/commands/reports/report_index.py refresh` writes the generated
`09_report/README.md` index. State-changing scripts call the report-index hook
when their changes affect reader-facing outputs.

`scripts/commands/dashboard/dashboard_refresh.py` is an optional support hook
for dashboard mode. It regenerates dashboard-derived surfaces without
hand-editing raw JSON state files. Agents should not run it as the default
handoff path; use `project_resume`, `progress_checkpoint`, `loop_summary`, and
`project_closeout` first.

`scripts/commands/projects/project_closeout.py` is the handoff blocker-routing hook. It checks
research readiness, command/owner state, vote gates, and `09_report/` hygiene.
When explicitly requested with `--refresh-dashboard`, it also refreshes and
checks dashboard support surfaces. It writes
`07_reviews/project_closeout_audit.md` with the project-local skill each next
agent should load.

Dashboard-free health, state diagnostics, experiment DAGs, claim graphs,
baseline comparisons, and agent quality audits are working evidence. They are
not final paper artifacts, but closeout and artifact packaging use them to
prove that the project is resumable and that claims/results/code structure were
handled deliberately. See
`docs/decisions/ADR-011-dashboard-free-health-and-routing.md` for the design
rationale.

`scripts/commands/projects/import_research_repo.py` is the non-destructive intake path for an
existing research repository. It creates a template-backed project, copies the
source snapshot into `04_code/imported_repo/`, skips private/generated/large
artifacts by default, writes import inventory notes, and makes the next
file-state action a director triage pass over the imported repo.

`scripts/commands/dashboard/dashboard_sources.py` is the optional dashboard source manifest. It records
which state, event, session, checkpoint, phase-gate, resource-ledger,
experiment, result-table, and final-artifact inputs are present and when they
last changed. `/api/status` includes this as `data_sources`, and the static
dashboard renders it only in Debug as Data Coverage so operational source
issues do not clutter the researcher overview.

## 7. Legacy Ralph Loop Model

Ralph loops are legacy optional bounded autonomous runs. They persist prompts
and progress in files so a fresh agent can continue without chat memory.

Use Ralph only with:

- explicit duration,
- explicit result condition,
- explicit completion promise,
- and a clear statement of what output proves completion.

Prompt-only Ralph runs write prompts and state. They do not execute an external
agent. Executing until result requires `--execute --runner-command` or
`--codex-runner`.

Template projects must not ship with historical Ralph prompt files or completed
Ralph run history. `validate_project.py --project template --strict` enforces
this hygiene.

## 8. Optional Dashboard Support Model

The dashboard is preserved as optional support tooling. It has two modes:

- Direct file mode: open `dashboard/index.html`, select a project folder, and
  inspect a snapshot.
- Server mode: run `python -m scripts.commands.agents.agent_dashboard --project <project>` and
  fetch live state from `/api/status`.

The dashboard is split into:

- `dashboard/index.html`: markup and stable DOM ids.
- `dashboard/styles.css`: visual layout and responsive rules.
- `dashboard/app.js`: parsing, rendering, API loading, and interactions.

The default UI keeps high-signal information in `Overview`: current work,
completed work, visible results/artifacts, blockers, and the next
command/prompt, plus research-readiness and phase-map summaries. Expanded
workflow operations live in `Work`, final report artifacts and result-table
previews live in `Results`, a safe copy-ready runbook lives in `Console`, and
raw state/event/debug surfaces live in `Debug`. The dashboard intentionally does
not expose arbitrary browser-triggered shell execution; command execution stays
in the local terminal or agent session.

Low-level validation warnings and source-coverage details stay out of the main
researcher flow. They are available in Debug through the Data Coverage panel
for operators who need to inspect missing or stale inputs.

The advanced research UI surfaces are:

- `Run Readiness Gate`: a run/no-run verdict built from next command, blockers,
  evidence rows, and required dashboard sources.
- `Evidence Map`: claim rows connected to experiment/result rows.
- `Experiment Comparison`: a compact comparison table from
  `09_report/results/experiment_results.csv`.
- `Blocker Triage`: grouped workflow/research/data/experiment/writing blockers
  with next-resolution guidance.

The dashboard can optionally run a small allowlist of local harness commands in
server mode only. `scripts/commands/dashboard/dashboard_command_runner.py` defines the allowlist
and uses `subprocess.run` with argv lists, never arbitrary shell text. The
feature is disabled unless `scripts/commands/agents/agent_dashboard.py` starts with
`--enable-command-runner`.

## 9. Safety And Release Gates

Before calling the harness healthy:

```bash
python -m scripts.commands.release.workflow_audit
python -m scripts.commands.release.smoke_test
python -m scripts.commands.release.privacy_audit
python -m scripts.commands.release.verify_harness --project template --skip-paper-build
git diff --check
```

Before calling a project research-ready:

```bash
python -m scripts.commands.projects.validate_project --project <project> --strict
python -m scripts.commands.reports.data_metric_audit --project <project> --strict
python -m scripts.commands.reports.paper_claim_linter --project <project> --strict
python -m scripts.commands.research.research_audit --project <project> --write-report
python -m scripts.commands.projects.project_closeout --project <project> --write-report
```

If dashboard mode is explicitly enabled for a project, additionally check:

```bash
python -m scripts.commands.dashboard.dashboard_refresh --project <project> --check
```

High-risk commands should use votes. Experiment execution should use the GPU
scheduler/monitor path rather than ad hoc detached jobs. Baseline execution
should go through repo discovery, intake, and sandbox checks before execution.

## 10. Non-Goals

This workspace is not:

- a replacement for a lab notebook or data warehouse,
- a hidden autonomous system that can safely run without file-state evidence,
- a generic task manager,
- a place to store raw private datasets or credentials,
- or a guarantee that an unsupported research claim is true.

The harness makes research work easier to resume, audit, and verify. Scientific
validity still comes from evidence, experiment design, analysis, and review.
