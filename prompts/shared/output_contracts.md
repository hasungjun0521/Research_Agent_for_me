# Shared Output Contracts

These rules apply to all agents unless a more specific prompt says otherwise.

## Observation vs Interpretation

Always separate observations from interpretations.

- Observation: what the files, data, logs, papers, or drafts explicitly show.
- Interpretation: what those observations may mean for the research question.
- Recommendation: what should be done next.

Do not present interpretation as fact.

## Claim-Evidence-Uncertainty Format

For each important research claim, include:

- Claim: the statement being considered.
- Evidence: files, papers, results, or logs that support it.
- Uncertainty: what remains unknown or weak.
- Status: supported, partially supported, unsupported, contradicted, or untested.

## File Update Contract

Every agent response should state:

- Files read.
- Files updated.
- Files that should be updated next.
- Any unresolved questions added to `state/open_questions.md`.

## Progress Checkpoint Contract

Agents must persist important progress during the pass, not only in the final
response.

- At the start of active work, mark the owning agent as `running` with
  `python -m scripts.commands.agents.agent_status start`.
- During long-running or multi-step work, use `agent_status heartbeat` for
  liveness updates whenever the active task changes materially.
- When a meaningful result, blocker, direction change, failed assumption,
  experiment outcome, or next-action change appears, immediately run:

```bash
python -m scripts.commands.review.progress_checkpoint record --project <project> --agent <agent_name> --kind <kind> --summary "<what changed>" --evidence <path> --output <path>
```

- If five-hour or weekly remaining usage is below 5%, immediately run:

```bash
python -m scripts.commands.review.progress_checkpoint limit-handoff --project <project> --agent <agent_name> --summary "<what this session changed>" --five-hour-remaining-pct <pct> --weekly-remaining-pct <pct> --in-progress "<current work>" --next-action "<resume step>" --memory "<durable lesson>"
```

- Add `--memory`, `--next-action`, or `--open-question` when the checkpoint
  should also update `state/agent_memory.md`, `state/next_actions.md`, or
  `state/open_questions.md`.
- Add `--exp-id <exp_id>` and, when appropriate, `--run-status <status>` for
  experiment outcomes so `03_experiments/<exp_id>/run_log.md` and
  `run_state.json` history stay current.
- Use `python -m scripts.commands.agents.agent_events record --sync-status`
  only for lightweight activity timeline events that do not need memory,
  current-state, next-action, or experiment-log persistence.
- If a finding changes future routing or repeats a useful workflow lesson,
  record it through `python -m scripts.commands.review.pattern_memory`.
- Before final response, verify that the durable files tell a fresh agent what
  changed, what evidence exists, what remains blocked, and what should happen
  next without relying on chat history.

## Project Skill Contract

Agents should use project-local skills from `prompts/skills/` to reduce repeated context and speed up work.

- Load `prompts/skills/README.md` only when choosing a skill.
- Load only the one or two skill files required for the current task.
- Do not paste full skill text into status updates; state the skill name and resulting action.
- Prefer structured outputs and stable IDs over long prose summaries.

## Dashboard-Free Health Contract

Do not assume the browser dashboard is part of the default research workflow.

- Use `state/project_health.md` as the plain-language status surface when a
  fresh session needs the overall project health, blockers, and next best
  action.
- Use `state/state_doctor.md` when the project has stale, missing, or
  contradictory state.
- Treat both files as working state under `state/`, not final reader-facing
  artifacts.
- If a health or doctor report identifies a high-priority issue, route that
  issue before starting lower-priority writing or final export work.

## Working Claim Graph And Audit Contract

Use working analysis artifacts before final report exports.

- Use `05_results/claim_graph.md` and `05_results/claim_graph.json` to connect
  claims, experiment rows, baselines, and result-analysis notes before
  strengthening claims in writing.
- Use `08_baselines/baseline_compare.md` after source snapshots exist and
  before structuring substantial `04_code/src/` interfaces.
- Use `07_reviews/agent_quality_audit.md` when prior agent work is hard to
  resume or done work lacks output-file evidence.
- These files support routing and rigor. They do not replace final
  `09_report/results/` exports.

## Reader-Facing Report And Release Contract

Every project has `09_report/` as the single final artifact folder intended for
reader-facing inspection. Routine working inspection starts from `HANDOFF.md`,
`state/current_state.md`, `state/next_actions.md`, and the working folder that
changed, such as `03_experiments/`, `04_code/`, `05_results/`, or
`08_baselines/`.

- Keep experiment design, configs, run state, logs, raw outputs, and
  experiment-local diagnostics in `03_experiments/`.
- Keep active research code, tests, notebooks, debug scripts, and implementation
  notes in `04_code/`.
- Keep working analyses, intermediate tables, robustness drafts, failure cases,
  and exploratory figures in `05_results/`.
- Use `09_report/` only for final reader-facing and release-facing artifacts
  after the working files are stable.
- Keep cleaned, distribution-ready source code in `09_report/src/` only after it
  has been curated from `04_code/`.
- Keep the current reader-facing LaTeX paper in `09_report/paper/main.tex`.
- Keep final report-level analysis scripts in `09_report/analysis/`; exploratory
  analysis stays in `05_results/` or `04_code/notebooks/`.
- Keep final image assets in `09_report/figures/`; drafts stay in
  `05_results/figures/`.
- Keep structured working result rows in `05_results/experiment_results.csv`.
  Export to `09_report/results/experiment_results.csv` only when rows are
  stable enough for reader-facing report evidence.
- Keep final robustness checks in
  `09_report/results/statistical_robustness.csv`; detailed experiment process
  stays in `03_experiments/` and `05_results/`.
- Keep final claims, evidence, caveats, and next evidence needs in
  `09_report/results/claim_evidence.csv`.
- Keep `09_report/README.md` as the final reader-facing artifact entry point.
  Workflow scripts may refresh its generated final-artifact index after stable
  report exports. Routine command, status, GPU, and working-analysis state
  belongs in `HANDOFF.md`, `state/`, `03_experiments/`, `04_code/`, and
  `05_results/`, not in the report index.
- Do not add ad hoc Markdown notes to `09_report/`; scratch notes belong in the relevant working folder from `00_brief/` through `08_baselines/`.
- When a pass materially changes method, implementation, analysis,
  interpretation, writing, figures, code, or result tables, first update the
  working source folder (`03_experiments/`, `04_code/`, `05_results/`, or
  `06_writing/`). Update `09_report/` only when the change is stable enough to
  be reader-facing or release-facing.
- When a pass changes a research claim or its status, update the working
  interpretation or claim board first. Export
  `09_report/results/claim_evidence.csv` in the same pass only when the claim
  status is stable enough to be reader-facing.
- If the report cannot be updated because evidence is missing or contradictory, record the blocker in `state/open_questions.md` and the loop summary.

## Research Rigor Gate Contract

Do not treat an experiment-backed claim as ready until the required rigor gates are current.

- Use stable `claim_id`, `experiment_id`, and `baseline_id` values across preregistration, result tables, robustness tables, and claim-evidence rows.
- Use stable dataset and metric IDs from `03_experiments/dataset_registry.json` and `03_experiments/metric_registry.json`.
- `09_report/results/claim_evidence.csv`, `09_report/results/experiment_results.csv`, and `09_report/results/statistical_robustness.csv` must cross-reference each other through those IDs.
- If `09_report/paper/main.tex` references a claim ID, that claim must not be `untested`, `unsupported`, `contradicted`, `invalid`, or `rejected`.
- Before running an experiment, update `03_experiments/exp_*/preregistration.md` with hypothesis, success criteria, failure criteria, baselines, metrics, planned analysis, confounders, and decision rule.
- While implementing or executing an experiment, update `03_experiments/exp_*/reproducibility_manifest.json` with dataset, code, environment, seeds, command, hardware, baseline links, evidence, and output paths.
- During analysis, update `05_results/statistical_robustness.md` first. Export
  final robustness rows to `09_report/results/statistical_robustness.csv` only
  when the robustness result is stable enough to be reader-facing.
- During critique or revision, update `07_reviews/reviewer_attack_matrix.md` with likely reviewer objections, current weakness, evidence, and response plan.
- Use `scripts/commands/experiments/result_ingest.py` when experiment outputs are available. Default ingest updates working result/robustness evidence first; add `--final-export` only when rows are stable enough for `09_report/results/`, then run `scripts/commands/reports/data_metric_audit.py --strict` and `scripts/commands/reports/paper_claim_linter.py --strict`.
- `scripts/commands/projects/validate_project.py --strict` must pass before calling the harness state ready for handoff.

## Research Loop Contract

The director can use `scripts/commands/research/research_loop.py` to turn evidence gaps into concrete work.

- `python -m scripts.commands.research.research_loop plan --project <project>` prints suggested next actions without editing state.
- `python -m scripts.commands.research.research_loop enqueue --project <project>` adds missing command-queue entries and handoff messages.
- Research-loop enqueue must preserve `depends_on` and `parallel_group`
  metadata so `agent_orchestrator parallel` can batch independent generated
  commands without guessing dependency order.
- Before dispatching one serial command from the queue, check whether multiple
  independent `open` commands can be handled by different owner agents. If so,
  use `python -m scripts.commands.agents.agent_orchestrator parallel --project
  <project> --max-agents <n>` to plan or write the batch.
- Research-loop planning may use working result rows from
  `05_results/experiment_results.csv` to route robustness/data-quality work,
  but paper-claim linting and final report gates should rely on stable
  `09_report/results/` exports.
- The loop engine must write visible state only: `state/command_queue.json` and `state/agent_messages.json`.
- Agents should still update status, loop summary, and evidence files when they actually perform the work.

## Leader Dispatch And Routing Contract

When a director or lead-style pass needs to route work, use the compact shared
protocols instead of ad hoc prose:

- `prompts/shared/research_routing_matrix.md` maps user requests and project
  symptoms to the first responsible role.
- `prompts/shared/research_handoff_graph.md` bounds allowed role handoffs and
  prevents infinite agent ping-pong.
- `prompts/shared/leader_dispatch_protocol.md` defines the required
  `LEADER DISPATCH` and `WORKER RESULT` blocks.
- `prompts/shared/risk_confidence_matrix.md` decides whether a command can be
  dispatched directly, needs a vote, or needs manual approval.
- `prompts/shared/research_brain_protocol.md` explains how to retrieve reusable
  project-local lessons from `state/pattern_memory.json`.
- Use `scripts.commands.agents.agent_orchestrator parallel` when the queue has
  independent commands with approved vote gates, completed dependencies,
  distinct owner agents, and no required-input or expected-output path
  conflicts. Use `parallel --json` when another agent needs
  `open_parallel_diagnostics` beside the planned commands. Use `dispatch` or
  `next` only when no safe batch exists. Use `next --json` when another agent
  needs the serial fallback and `open_parallel_diagnostics` in one payload.
  Explicit `parallel --id <cmd>` requests must fail with a concrete reason when
  a requested command is unsafe; do not silently skip explicit ids.
- Use `scripts.commands.agents.agent_orchestrator status-parallel` to inspect
  prepared prompts before running them; prepared prompts with unfinished
  dependencies must stay waiting until their `depends_on` commands are done.
  Use `open_parallel_diagnostics` when no safe open batch appears; common
  reasons include missing expected outputs, unfinished dependencies, duplicate
  owner selection, and path conflicts.
- Use `scripts.commands.review.command_queue list --verbose` or `--json` when
  you need command-level dependency readiness; JSON output includes computed
  `dependency_ready` and `unfinished_dependencies` fields.

Validate leader dispatch blocks with:

```bash
python -m scripts.commands.review.leader_dispatch validate --file <dispatch-output.md>
```

Apply a valid `dispatch_workers` block to the command queue with:

```bash
python -m scripts.commands.review.leader_dispatch apply --project <project> --file <dispatch-output.md>
```

If the lead pass should immediately materialize safe parallel worker prompts,
use:

```bash
python -m scripts.commands.review.leader_dispatch apply --project <project> --file <dispatch-output.md> --write-parallel-prompts
```

If prompts were written in an earlier session and commands are already
`in progress`, inspect them first with:

```bash
python -m scripts.commands.agents.agent_orchestrator run-prepared --project <project> --group <group> --dry-run
```

Then run them with:

```bash
python -m scripts.commands.agents.agent_orchestrator run-prepared --project <project> --group <group> --runner-command "<agent-cli> --prompt-file {prompt_file}"
```

`run-prepared` must re-check `depends_on` immediately before launch and fail
instead of running a scoped prepared command whose dependencies are not done.
Use `--all-prepared` only when intentionally running prepared prompts across
all groups; it must not bypass dependency readiness. Otherwise scope prepared
execution with `--group` or explicit `--id` values.
Explicit `--id` values must refer to prepared `in progress` commands with
`orchestrator_prompt`; invalid explicit ids should fail instead of being
silently skipped.

After reviewing worker outputs, finish the scoped prepared batch with:

```bash
python -m scripts.commands.agents.agent_orchestrator finish-parallel --project <project> --group <group> --status done --dry-run
python -m scripts.commands.agents.agent_orchestrator finish-parallel --project <project> --group <group> --status done --note "<verification>"
python -m scripts.commands.agents.agent_orchestrator finish-parallel --project <project> --group <group> --status done --result-file <command_id>=<worker-result-path>
```

Do not use non-dry-run `finish-parallel --status done` without a verification
`--note` or evidence `--output` or `--result-file`.
Do not use non-dry-run `finish-parallel --status blocked` or `deferred` without
a `--note` explaining the reason.
Per-command `--result-file` paths should preserve existing expected outputs and
add worker-result evidence, not replace the original output contract.

After applying, use `command_queue list --verbose` or
`agent_orchestrator status-parallel` to inspect the safe multi-agent batch.

Validate worker result blocks with:

```bash
python -m scripts.commands.review.worker_result validate --file <worker-output.md>
```

Do not let a lead-style pass keep routing in free text when downstream agents
need to parse or resume the work.

## Baseline Intake Contract

When baseline papers or repo URLs are provided, agents should turn them into traceable source artifacts before implementing from memory.

- Use `python -m scripts.commands.baselines.baseline_intake ingest --project <project> --manifest <manifest> --clone --allow-network --message-missing-repos` when repo URLs are available or need discovery follow-up.
- Keep cloned source under `08_baselines/source_snapshots/<baseline_id>/`.
- Keep source maps under `08_baselines/structure_reports/<baseline_id>.json` and `.md`.
- Keep the structure ranking and adapter layout in `08_baselines/code_structure_plan.md`.
- Keep project-side wrappers under `08_baselines/run_scripts/`.
- Keep dry smoke scripts under `08_baselines/run_scripts/<baseline_id>_smoke.py`.
- Use `scripts/commands/baselines/repo_discovery.py` to resolve candidate repos and `scripts/commands/baselines/baseline_sandbox.py --strict` before running cloned code.
- Do not edit cloned source snapshots directly. Use adapters, run scripts, or patch notes.
- Missing repo URLs should become `agent_messages.py` requests to `literature_reviewer`, not silent assumptions.

## Agent Message Contract

Agents may ask each other questions, request reviews, hand off blockers, or request decisions through `state/agent_messages.json`.

- Use `python -m scripts.commands.agents.agent_messages`; do not hand-edit or replace `state/agent_messages.json`.
- Use `state/command_queue.json` for user-visible work ownership and `state/agent_messages.json` for agent-to-agent requests and responses.
- Every message needs `from_agent`, `to_agent`, `kind`, `priority`, `subject`, and `body`.
- Link messages to `related_command_id`, `related_claim_id`, or `related_exp_id` whenever the request affects a tracked command, claim, or experiment.
- The recipient should respond with `agent_messages.py respond`; do not resolve a message from the sender side unless it was cancelled or superseded.
- Unresolved high-priority blocker messages make strict validation fail.

## Human-Readable Next Action Contract

Next actions must be understandable without reading file paths. This applies to
`state/next_actions.md`, `state/command_queue.json`, project resume summaries,
and any optional dashboard view.

- Write `action` as the actual work in plain language, for example `Run the official baseline smoke check`, not `Update outputs`.
- Use `notes` for why the task matters or what decision it unlocks.
- Use `expected_outputs` only for traceability files and folders.
- Do not rely on `expected_outputs` to explain the task to the user.
- For parallel-ready commands, include at least one substantive working
  artifact in `expected_outputs`, such as a file under `00_brief/`,
  `01_literature/`, `02_planning/`, `03_experiments/`, `04_code/`,
  `05_results/`, `06_writing/`, `07_reviews/`, or `08_baselines/`.
- Treat generic checkpoint files such as `state/current_state.md`,
  `state/agent_memory.md`, `state/next_actions.md`, `state/open_questions.md`,
  `state/agent_status.json`, and `state/agent_events.jsonl` as coordination
  state, not as the substantive output that makes a command parallel-ready.
- If the task is an experiment or validation run, name the method, dataset or split, check type, and done condition in the action or notes.

## Filesystem Safety Contract

- Stay inside the active project folder for research work.
- Do not delete, move, overwrite, or recursively clean any directory outside the active project folder.
- For harness maintenance, stay inside this repository and touch only files explicitly required by the user request.
- Do not run destructive cleanup commands such as `rm -rf`, `find ... -delete`, `git clean -fd`, `rsync --delete`, or recursive delete scripts on parent directories, sibling projects, datasets, checkpoints, external repositories, home-directory folders, or system paths.

## Unsupported Claims

Avoid unsupported claims. If a claim is plausible but not yet supported, label it as one of:

- `hypothesis`
- `speculation`
- `requires literature support`
- `requires experiment`
- `requires analysis`
- `requires citation`

## Evidence Discipline

- Do not invent citations.
- Do not invent experiment results.
- Do not ignore negative results.
- Do not hide uncertainty in vague wording.
- Do not turn a convenience baseline into a scientific comparison unless justified.

## State Updates

When a task changes project direction, update:

- `state/current_state.md`
- `state/next_actions.md`
- `state/open_questions.md`
- `state/agent_status.json` through `python -m scripts.commands.agents.agent_status ...` for every agent pass.
- `state/command_queue.json` through `python -m scripts.commands.review.command_queue ...` when command ownership, priority, or status changes.
- `state/agent_messages.json` through `python -m scripts.commands.agents.agent_messages ...` when an agent asks, answers, blocks, reviews, or hands off work to another agent.
- `state/agent_votes.json` through `python -m scripts.commands.agents.agent_vote ...` when important commands need independent approval before dispatch.
- `state/agent_events.jsonl` through harness CLIs; do not manually edit or truncate the event log.
- `state/sessions/<session_id>/` through `python -m scripts.commands.review.session_state ...` for loop-local scratchpads, plans, results, and artifacts.
- `state/pattern_memory.json` through `python -m scripts.commands.review.pattern_memory ...` when a reusable workflow lesson should guide later agents.
- `state/ralph_loop.json` only when the user explicitly asks for the legacy Ralph loop.
- `state/loop_summary.json` through `python -m scripts.commands.review.loop_summary ...` when a loop starts, finishes work, records a result, or selects next actions.
- `HANDOFF.md` in the project root when a long session ends, a major task pivots, or validation/blockers changed.
- `02_planning/decision_log.md` for major decisions.

## Agent Status Contract

Each agent must update its existing entry in `state/agent_status.json` during project work.

- Use `python -m scripts.commands.agents.agent_status`; do not hand-edit or replace the JSON file.
- Set `status` to `running` before active work starts.
- Set `status` to `done`, `waiting`, `blocked`, or `idle` when the pass ends.
- Keep `current_task`, `stage`, `updated_at`, `last_input_files`, and `last_output_files` current.
- During long work, update `updated_at` and `current_task` as a heartbeat at least every 5-10 minutes.
- Do not append duplicate agent entries; update the object whose `name` matches the agent role.
- Do not mark an agent as `running` unless it is actively working.
- Agent lifecycle changes append to `state/agent_events.jsonl`; inspect them with `python -m scripts.commands.agents.agent_events`.

## Command Queue Contract

The structured command queue lives in `state/command_queue.json`.

- Use `python -m scripts.commands.review.command_queue`; do not hand-edit the JSON file.
- Keep `state/next_actions.md` as the human-readable mirror, but treat `command_queue.json` as the structured command source of truth.
- Set command status to `in progress` before execution, then `done`, `blocked`, `open`, or `deferred`.
- Every command should name an `owner_agent`, expected outputs, priority, and status.
- Every command created for possible multi-agent dispatch should also set
  `depends_on` and `parallel_group`. Use an empty dependency list only when the
  command is genuinely independent.
- Important or high-risk commands may set `requires_vote=true`, `vote_id`, and `risk_level`; `scripts/commands/agents/agent_orchestrator.py dispatch` must not run them until the linked vote is approved.
- Do not mark an agent pass `done` while it owns an `open` or `in progress` command. Finish as `waiting` or `blocked`, or pass `--command-id` to `scripts/commands/agents/agent_status.py finish` so the specific command is completed.

## Multi-Agent Vote Contract

Use votes when a command changes experiment scope, spends substantial compute,
alters shared harness behavior, changes claim status, or packages final
artifacts. The director opens the vote, at least two independent agents should
vote when possible, and dissent should remain visible instead of being edited
away. A command that requires a vote is dispatchable only after the vote status
is `approved`.

For automatic voting, use `python -m scripts.commands.agents.agent_vote auto` or
`python -m scripts.commands.agents.agent_orchestrator dispatch --auto-vote`. The auto runner
must return explicit vote, confidence, and rationale tags. Unparseable or failed
runner output must never become an approval; it is recorded as an abstention.

## Session Workspace Contract

Use `state/sessions/<session_id>/` for loop-local scratchpads, plan files,
intermediate result summaries, and non-final artifacts. These folders isolate
parallel or long-running loops. They do not replace `state/loop_summary.json`
for handoff-visible status and they do not replace `09_report/` for final
human-facing artifacts.

## Pattern Memory Contract

Use `state/pattern_memory.json` for reusable project-local lessons that should
influence later agents. Record patterns with `python -m scripts.commands.review.pattern_memory`
instead of hand-editing JSON. A pattern should include the trigger, the
recommendation, and evidence files when available. Deprecate a pattern instead
of deleting it when later evidence shows it is no longer reliable.

## Legacy Ralph Loop Contract

The Ralph loop CLI remains for compatibility, but it is not the default
automation path. Prefer Claude/Codex native session controls plus the harness
command queue, status, messages, session workspaces, and loop summary.

Use `python -m scripts.commands.review.ralph_loop` only when a human explicitly
authorizes that legacy bounded-loop behavior. The loop must stop when a
configured result is detected or when the deadline is reached. Result detection
can use a completion promise marker, a linked command reaching `done`, or
configured project-relative result files. Each iteration must persist progress
through project files, not chat memory. External agent execution is opt-in
through `--execute --runner-command`; Codex-specific `--codex-runner` is legacy
and should not be used for Claude runs.

## Loop Summary Contract

The one-screen handoff summary is driven by `state/loop_summary.json`.

- The director owns `loop_summary` start/finish; worker passes do NOT update `loop_summary` directly — they record progress via `progress_checkpoint` and the director folds it into `loop_summary` on the next routing turn.
- Use `python -m scripts.commands.review.loop_summary`; do not hand-edit the JSON file.
- Start each research loop with a clear `loop_id`, `goal`, and `status=running`.
- Use `update` during an active loop when the summary should change without resetting recorded work.
- Record completed work with `add-work`, including command id, owner, result, and output files.
- Record loop-level findings with `add-result`, including evidence files.
- Record the next concrete actions with `add-next`; do not leave the project without a next action unless it is intentionally stopped.
- Finish each loop with `finish --summary ... --outcome ...` and use `done`, `blocked`, or `waiting` honestly.
- An agent should not claim the loop is complete unless the loop summary tells a future reader what changed, what the result was, and what should happen next.

## Completion Gate

Agents must not decide that the broader workflow is complete just because their local pass is complete.

- A pass is `done` only when the assigned command's expected outputs exist or were explicitly judged unnecessary.
- If expected outputs are missing, finish as `blocked` with the missing input/output in `notes`.
- If another agent or user decision is needed, finish as `waiting`.
- If long-running external work continues, keep the owning agent `running` and update heartbeat.
- Use `python -m scripts.commands.projects.validate_project --project <project>` before claiming the harness state is healthy.

## Experiment Run State Contract

Long-running experiments must have `03_experiments/<exp_id>/run_state.json`.

- Use `python -m scripts.commands.experiments.run_state`; do not hand-edit the JSON file.
- Record SLURM job name/id, GPU type, node, log path, result path, status, and heartbeat.
- Keep run state as `running` while the external process is active.
- Finish as `succeeded`, `failed`, `blocked`, or `cancelled`.
