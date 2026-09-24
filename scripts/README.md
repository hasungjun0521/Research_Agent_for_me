# Scripts

This folder contains lightweight helper scripts. There are no external dependencies.

## Layout

Run commands as package modules, for example
`python -m scripts.commands.projects.create_project my_new_project`. The
implementation code lives under `scripts/commands/<domain>/`, grouped by
workflow area:

- `agents/`: optional dashboard server, agent status, events, voting, and dispatch.
- `baselines/`: baseline registry, intake, repository discovery, and sandboxing.
- `dashboard/`: dashboard source manifests, refresh hooks, and command runner.
- `experiments/`: run state, GPU scheduling, diagnostics, and checkpoints.
- `projects/`: project creation, migration, intake, resume summaries, validation, and closeout.
- `reports/`: evidence boards, result ingestion support, ledgers, and packaging.
- `research/`: research loop, registry, audits, and phase gates.
- `review/`: command queue, progress checkpoints, sessions, legacy Ralph loop,
  review forms, and handoffs.
- `release/`: harness verification, privacy checks, release checks, and profile tools.

Shared harness modules live under `scripts/harness/`. The root of `scripts/`
intentionally has no Python entry-point wrappers.

## Create a New Project

From the repository root:

```bash
python -m scripts.commands.projects.create_project my_new_project
```

Project creation records a `project_created` director lifecycle event in the
new project, so the first continuation pass can see that the project was
initialized from the template.

This copies `projects/template/` to `projects/my_new_project/` and replaces `{{PROJECT_NAME}}` in text-based starter files.

After creation, `projects/my_new_project/09_report/` is initialized for final
reader-facing artifacts: LaTeX/report source, final analysis scripts, final
figures/result tables, and cleaned release code. Keep active research code in
`04_code/` and working analysis in `05_results/` until outputs are stable
enough to export.

When enough initial detail is available, apply a structured intake brief before
the first director pass:

```bash
python -m scripts.commands.projects.project_intake apply --project my_new_project --research-question "..." --motivation "..." --contribution "..."
```

## Configure A User Or Lab Environment

Workspace-specific preferences are not project state. Initialize the ignored
local profile from the public template and edit it for this machine or lab:

```bash
python -m scripts.commands.release.workspace_profile init-local
python -m scripts.commands.release.workspace_profile show --json
python -m scripts.commands.release.workspace_profile validate
```

Use `config/workspace_profile.local.json` for agent-output language, GPU caps,
GPU profile names, node defaults, partitions, queue/node scheduler commands,
optional support-surface display labels, and external agent runner profiles.
Runner profiles live under `agent_runners.profiles.<name>.command` and are used
by `agent_orchestrator dispatch`, `agent_orchestrator parallel`, and
`agent_orchestrator run-prepared` through `--runner-profile`. Use profiles for
non-interactive Codex/Claude-compatible commands; do not put interactive TUI
commands there.

To overwrite an existing project intentionally:

```bash
python -m scripts.commands.projects.create_project my_new_project --force
```

The script expects a single folder name. It refuses absolute paths, nested paths, and names containing `..` path segments.

## Import an Existing Research Repo

Use this when you already have a research codebase and want to wrap it in the
workspace template without losing the original repo structure:

```bash
python -m scripts.commands.projects.import_research_repo --source /path/to/existing/repo --project imported_project --dry-run
python -m scripts.commands.projects.import_research_repo --source /path/to/existing/repo --project imported_project
```

The import creates `projects/imported_project/` from `projects/template/`,
copies the source repo into `04_code/imported_repo/`, writes
`02_planning/imported_repo_inventory.md` and
`00_brief/imported_repo_notes.md`, then updates the command queue, loop
summary, agent lifecycle status, and event timeline with an
`imported_repo_triage` next step. Lifecycle outputs include the imported source
directory and manifest so the next agent can start triage from the snapshot
root. By default it skips VCS
folders, virtual environments, caches, datasets, checkpoints, model weights,
logs, private-looking files, symlinks, and files larger than 25 MB. Use
`--into-existing` to import into an already-created project and
`--overwrite-import` to replace a previous import folder. Custom import
directories must stay under `04_code/`; imported repositories are never allowed
under `state/`, `09_report/`, or other workflow/artifact folders. Use
`--agent <role>` when a role other than `director` should own the import
lifecycle record.

## Migrate an Existing Project

Existing projects can be upgraded without overwriting their work:

```bash
python -m scripts.commands.projects.migrate_project --project my_existing_project
```

The migration creates missing `09_report/` artifact folders/files, creates a project-local `HANDOFF.md`, creates missing research rigor gate starters, restores working artifacts such as `03_experiments/data_roots.md`, `05_results/experiment_results.csv`, `05_results/experiment_journal.md`, `05_results/experiment_journal.csv`, and `06_writing/terminology.md`, adds support state files such as pattern memory, adds human-readable `display_summary`, `why_now`, and `done_when` fields to queued next actions, and adds optional support fields to experiment run states. If `03_experiments/dataset_registry.json` already has dataset entries but `data_roots.md` is missing or still contains the starter row, migration syncs those dataset entries into `data_roots.md` without overwriting existing real rows. Use `--dry-run` first to preview changes. Use `--clean-legacy-report-md` when intentionally removing old report Markdown starter files.
Non-dry-run migration records a `project_migration` director lifecycle
status/event with the changed output paths; `--dry-run` stays read-only.

Refresh the final reader-facing report index after stable report/export work:

```bash
python -m scripts.commands.reports.report_index refresh --project my_existing_project
```

This updates only the generated final-artifact block in `09_report/README.md`,
preserving any hand-written artifact instructions outside that block. Core
workflow scripts may refresh this after final result exports or report-facing
artifact changes. Routine command queues, agent status, GPU queues, and working
analysis should be inspected through `project_resume`, `HANDOFF.md`, `state/`,
`03_experiments/`, `04_code/`, and `05_results/`, not through `09_report/`.

To start or resume an agent session from file state, print the compact resume
summary:

```bash
python -m scripts.commands.projects.project_resume --project my_existing_project
```

When it is unclear which project is active, list all projects sorted by
last-touched state (read-only; `--json` for machine-readable output):

```bash
python -m scripts.commands.projects.project_resume --list
```

This lists the files to read first, optional limit handoff state, working
artifact status for data roots, experiment journals, terminology, active
commands, open questions, workflow ownership warnings, and a continuation
prompt.

To refresh dashboard-free diagnostics, run state doctor first and project
health second:

```bash
python -m scripts.commands.projects.state_doctor --project my_existing_project --write-report
python -m scripts.commands.projects.project_health --project my_existing_project --write
```

When safe starter files are missing, preview repair before writing:

```bash
python -m scripts.commands.projects.state_doctor --project my_existing_project --dry-run-repair
python -m scripts.commands.projects.state_doctor --project my_existing_project --repair
python -m scripts.commands.projects.project_health --project my_existing_project --write
```

Repair output includes the repair mode, repaired file count, repaired paths,
and repair errors. Repairs are intentionally conservative: they create only safe
starter files or template-backed continuity files, validate template-backed JSON
before writing it, and do not infer missing research content.

Use `--dry-run-enqueue` before `--enqueue-suggestions` when routing health or
state doctor findings into `state/command_queue.json`.

To check project folder hygiene (09_report bloat, junk artifacts, stale lock
debris, unexpected top-level entries, missing or stale diagnostics), run the
read-only hygiene scan; `--clean-locks` is the only destructive action and
`--write-report` writes `state/project_hygiene.md`:

```bash
python -m scripts.commands.projects.project_hygiene --project my_existing_project
python -m scripts.commands.projects.project_hygiene --all
python -m scripts.commands.projects.project_hygiene --project my_existing_project --clean-locks
python -m scripts.commands.projects.project_hygiene --project my_existing_project --write-report --strict
```

It also surfaces safe multi-agent batch candidates from
`state/command_queue.json`. If it prints a `Parallel Agent Batch Candidates`
section, use the shown `scripts.commands.agents.agent_orchestrator parallel`
command before falling back to one serial dispatch.
If prompts were already written for a parallel batch, the `Prepared Or
In-Progress Parallel Prompts` section shows the command id, owner, group, prompt
path, and whether the prompt file is present.
The `Parallel Batch Manifests` section lists recent
`state/orchestrator_prompts/parallel_batches/*.json` files so a fresh session
can recover which worker prompts were created together.
The `Recent Parallel Lifecycle Events` section shows the latest dispatch, run,
runner-result, and finish events from `state/agent_events.jsonl`.

When stable experiment results are ready to export, include the experiment
rationale and result explanation so the working experiment journal stays
current in both `05_results/experiment_journal.md` and
`05_results/experiment_journal.csv`, and append the same explanation to
`03_experiments/<exp_id>/analysis.md`. If `--result-analysis` is omitted, the
CLI records an analysis-pending next action in `run_state.json` instead of
silently treating the result as explained:

```bash
python -m scripts.commands.experiments.result_ingest ingest --project my_existing_project --exp-id exp_001 --input 03_experiments/exp_001/metrics.json --claim-id claim_001 --dataset dataset_id --method method_id --rationale "why this experiment was run" --result-analysis "why performance improved, regressed, or stayed flat"
python -m scripts.commands.experiments.result_ingest ingest --project my_existing_project --exp-id exp_001 --input 03_experiments/exp_001/metrics.json --claim-id claim_001 --dataset dataset_id --method method_id --rationale "stable final export" --result-analysis "evidence is stable enough for reader-facing tables" --final-export
```

Without `--final-export`, result rows stay in
`05_results/experiment_results.csv`. Use `--final-export` only for stable
reader-facing rows under `09_report/results/`. Robustness ingest follows the
same rule: without `--final-export`, it updates
`05_results/statistical_robustness.md` and the experiment analysis note; with
`--final-export`, it also writes
`09_report/results/statistical_robustness.csv`.

For stable reader-facing exports, refresh the final report index directly:

```bash
python -m scripts.commands.reports.report_index refresh --project my_existing_project
```

Use `scripts.commands.dashboard.dashboard_refresh` only when optional dashboard
mode is explicitly enabled; that command refreshes dashboard support summaries
and source coverage by default. Add `--final-export` only when it should also
refresh reader-facing `09_report/results/*.csv` files and the generated
`09_report/README.md` index.

To route handoff blockers to the right project-local skills, use:

```bash
python -m scripts.commands.projects.project_closeout --project my_existing_project --write-report
```

This writes `07_reviews/project_closeout_audit.md` and groups missing claim
rows, reviewer-risk gaps, stale command/owner state, vote-gate issues, report
hygiene problems, and the skill each next agent should load. Add
`--refresh-dashboard` only when dashboard mode is explicitly enabled and you
want the closeout hook to refresh dashboard-derived surfaces first.
`scripts/commands/reports/report_snapshot.py` is the shared source for report
table row counts and latest report files used by both `report_index.py` and the
optional dashboard API, so the README index and UI should not drift.
`scripts/commands/dashboard/dashboard_sources.py` is the optional dashboard
source manifest. It reports whether required state, event, report, session,
experiment, and artifact sources are present and when they last changed.
`scripts/commands/dashboard/dashboard_command_runner.py` is the allowlisted
command runner used by the dashboard Console when `agent_dashboard.py` starts
with `--enable-command-runner`. It accepts command ids, not shell text.

Run the static workflow wiring audit before publishing harness changes:

```bash
python -m scripts.commands.release.workflow_audit
python -m scripts.commands.release.workflow_audit --include-dashboard
```

The default audit checks core Claude/Codex file-state workflow wiring. Use
`--include-dashboard` only when intentionally maintaining optional dashboard
compatibility. That stricter mode also checks dashboard support manifests,
terminal event completion fallback, and external dashboard assets. Both modes
check that core state-changing scripts stay wired to workflow support refreshes;
final `09_report/README.md` index refresh remains opt-in for report-facing
writers.

Refresh the generated repository inventory in `project.yaml` after adding or
removing harness files:

```bash
python -m scripts.commands.projects.project_index refresh
python -m scripts.commands.projects.project_index check
```

Run the one-command release-readiness gate before tagging or publishing harness
changes:

```bash
python -m scripts.commands.release.privacy_audit
python -m scripts.commands.release.release_check --project template --version v8.0.0 --skip-paper-build --strict-template-state
```

The release check runs Python syntax checks, workflow wiring, full harness
verification, privacy/publishable-file checks, whitespace checks, and release
metadata checks. Add `--strict-template-state` for the final pre-tag pass that
must fail on generated template Ralph runs, sessions, prompt files, event
history, or lock files.

Optional dashboard compatibility checks are opt-in:

```bash
python -m scripts.commands.release.smoke_test --include-dashboard
python -m scripts.commands.release.workflow_audit --include-dashboard
python -m scripts.commands.release.verify_harness --project template --skip-paper-build --include-dashboard
python -m scripts.commands.release.release_check --project template --version v8.0.0 --skip-paper-build --strict-template-state --include-dashboard
```

Validate a lead-style agent dispatch block:

```bash
python -m scripts.commands.review.leader_dispatch validate --file state/sessions/<session_id>/leader_output.md
python -m scripts.commands.review.leader_dispatch apply --project my_new_project --file state/sessions/<session_id>/leader_output.md
python -m scripts.commands.review.leader_dispatch apply --project my_new_project --file state/sessions/<session_id>/leader_output.md --write-parallel-prompts
```

`leader_dispatch apply` converts a valid `dispatch_workers` block into
`state/command_queue.json` entries with `depends_on`, `parallel_group`, and
substantive `expected_outputs` preserved. After applying, inspect
`command_queue list --verbose` or run `agent_orchestrator parallel` to plan the
safe multi-agent batch. When the dispatch block has a `parallel_group`, `apply`
prints a `parallel hint` command for the matching `agent_orchestrator parallel`
batch.
Use `--write-parallel-prompts` when the lead dispatch should immediately write
safe parallel worker prompts and mark the selected commands `in progress`.

Validate a worker result block:

```bash
python -m scripts.commands.review.worker_result validate --file state/sessions/<session_id>/worker_output.md
```

Research routing, handoff, risk, dispatch, and reusable-pattern rules live in
`prompts/shared/research_routing_matrix.md`,
`prompts/shared/research_handoff_graph.md`,
`prompts/shared/leader_dispatch_protocol.md`,
`prompts/shared/risk_confidence_matrix.md`, and
`prompts/shared/research_brain_protocol.md`. The orchestrator includes these
contracts in generated dispatch prompts.

## Filesystem Safety

All harness work should stay inside the active project folder or, for harness maintenance, inside this repository. Do not use helper scripts, shell commands, or cleanup routines to delete, move, overwrite, or recursively clean directories outside the active folder. Avoid `rm -rf`, `find ... -delete`, `git clean -fd`, `rsync --delete`, and recursive delete scripts unless the resolved target is confirmed to be inside the active project folder.

## Optional Dashboard Support

Dashboard commands are compatibility/support tooling. They are not required for
the default Claude/Codex file-state workflow.

Optional static dashboard entry point:

```text
dashboard/index.html
```

Open the file in a browser and select a project folder.

Start the local dashboard from the repository root:

```bash
python -m scripts.commands.agents.agent_dashboard --project my_new_project
```

Share the dashboard on a trusted network with a tokenized link:

```bash
python -m scripts.commands.agents.agent_dashboard --project my_new_project --host 0.0.0.0 --port 8766 --share-token "$(python -c 'import secrets; print(secrets.token_urlsafe(18))')"
```

Binding to a non-local host without `--share-token` is refused unless `--unsafe-no-token` is passed. Use a VPN, SSH tunnel, or reverse proxy for internet sharing.

Default URL:

```text
http://127.0.0.1:8765/?project=my_new_project
```

The dashboard reads `state/loop_summary.json`, `state/command_queue.json`, `state/agent_messages.json`, `state/agent_votes.json`, `state/agent_events.jsonl`, `state/sessions/`, `state/pattern_memory.json`, `state/ralph_loop.json`, `state/agent_status.json`, and experiment `run_state.json` files. The dashboard does not start or stop agents by itself; it shows the file-based status that agents or the user record.

## Agent Status CLI

Do not edit `state/agent_status.json` by hand. Use:

```bash
python -m scripts.commands.agents.agent_status start --project my_new_project --agent code_agent --task "Run exp_001" --stage "code generation"
python -m scripts.commands.agents.agent_status heartbeat --project my_new_project --agent code_agent --note "SLURM job still running" --append-note
python -m scripts.commands.agents.agent_status finish --project my_new_project --agent code_agent --command-id cmd_003 --status done --output 03_experiments/exp_001/run_log.md
```

The CLI preserves the existing `agents` array, updates only the named agent, and writes valid JSON atomically.
It also refuses to mark an agent `done` while it still owns open or in-progress commands unless the command is completed with `--command-id` or `--allow-open-commands` is provided.
Each status update appends a lifecycle row to `state/agent_events.jsonl`.

Inspect the lifecycle log:

```bash
python -m scripts.commands.agents.agent_events record --project my_new_project --agent code_agent --task "Reading experiment logs" --note "Hook activity update" --sync-status
python -m scripts.commands.agents.agent_events list --project my_new_project
python -m scripts.commands.agents.agent_events summary --project my_new_project
python -m scripts.commands.agents.agent_events validate --project my_new_project
python -m scripts.commands.agents.agent_events reset --project template
```

Use `agent_events.py record` for lightweight hook updates. With `--sync-status`,
the command also refreshes `state/agent_status.json`; without it, the event
still appears in the project activity timeline and report-index state. Optional
dashboard views may render the same file state when dashboard mode is enabled.
When syncing `status=done`, pass `--command-id` for the command being completed,
or use `scripts/commands/agents/agent_status.py finish`; the
hook CLI applies the same open-command completion gate as the status CLI.
Use `reset` only for explicit template or release cleanup; do not erase real
project event history.

## Progress Checkpoint CLI

Use this hook when a meaningful result, blocker, direction change, failed
assumption, experiment outcome, or next-action change appears during an agent
pass. It writes a durable checkpoint to project files so later agents do not
depend on chat history.

```bash
python -m scripts.commands.review.progress_checkpoint record --project my_new_project --agent code_agent --kind result --summary "Smoke test passes on the fixture dataset" --evidence 03_experiments/exp_001/run_log.md --output 04_code/tests/test_smoke.py --memory "The fixture smoke test is now the first safety check for exp_001." --next-action "Run the configured baseline smoke check."
python -m scripts.commands.review.progress_checkpoint list --project my_new_project
python -m scripts.commands.review.progress_checkpoint validate --project my_new_project
```

The hook appends to `state/progress_hooks.jsonl`,
`state/sessions/progress_log.md`, and `state/current_state.md` by default. It
also updates `state/agent_status.json` and appends a
`progress_checkpoint` event to `state/agent_events.jsonl`.

Use these options for targeted durable updates:

- `--memory`: append durable lessons or decisions to `state/agent_memory.md`.
- `--next-action`: append human-readable next actions to `state/next_actions.md`.
- `--open-question`: append unresolved questions to `state/open_questions.md`.
- `--exp-id`: append the checkpoint to `03_experiments/<exp_id>/run_log.md` and
  update `03_experiments/<exp_id>/run_state.json` history.
- `--run-status`: set the experiment run state when an outcome is known.
- `--append-to`: append the same checkpoint to an additional project-relative
  Markdown/text file.

For experiment outcomes:

```bash
python -m scripts.commands.review.progress_checkpoint record --project my_new_project --agent code_agent --kind experiment_result --exp-id exp_001 --summary "Seed-1 smoke run completed without metric crashes" --evidence 03_experiments/exp_001/run_log.md --output 03_experiments/exp_001/results/ --rationale "Confirm the first runnable experiment path before scaling." --dataset "fixture_workflow/smoke" --method "seed_1" --baseline-id "baseline_fixture" --result-analysis "The smoke result confirms execution health; metric validity still needs data_analyst review." --run-status succeeded --result-path 03_experiments/exp_001/results/ --next-action "Ask data_analyst to inspect metric validity."
```

If an agent sees that its five-hour or weekly usage remaining is below 5%, write
a continuation handoff:

```bash
python -m scripts.commands.review.progress_checkpoint limit-handoff --project my_new_project --agent code_agent --summary "Implemented the experiment journal hook and started validation." --five-hour-remaining-pct 4.5 --weekly-remaining-pct 42 --in-progress "Release smoke is running." --next-action "Inspect smoke output and rerun release_check." --memory "The next session should resume from state/limit_handoff.md before choosing new work."
```

The hook writes `state/limit_handoff.md`, appends project memory, updates current
state, and records a progress/event row. The CLI expects observed percentages;
it does not automate an interactive Codex or Claude TUI.

If `config/workspace_profile.local.json` defines an official non-interactive
JSON status command under `agent_limits.status_command`, use `check-limits` to
query it and record the same handoff only when the configured threshold is hit:

```bash
python -m scripts.commands.review.progress_checkpoint check-limits --project my_new_project --agent code_agent --summary "Implemented the experiment journal hook and started validation." --in-progress "Release smoke is running." --next-action "Inspect smoke output and rerun release_check." --memory "The next session should resume from state/limit_handoff.md before choosing new work."
```

`progress_checkpoint.py` is for research-content persistence. Use
`agent_status.py heartbeat` when you only need to refresh liveness, and use
`experiments/run_checkpoint.py` when you need a lightweight replay/fork snapshot
before broad changes.

## Experiment Completion CLI

Use this when an experiment has a real outcome and should be closed as one
durable record instead of scattered manual edits.

```bash
python -m scripts.commands.experiments.experiment_complete --project my_new_project --exp-id exp_001 --status succeeded --summary "Primary metric improved on the configured split." --result-analysis "The gain is consistent with lower validation loss; seed variance still needs follow-up." --evidence 03_experiments/exp_001/results/metrics.json --artifact metrics:metrics=03_experiments/exp_001/results/metrics.json --data-root main_dataset=<dataset_root>
```

The command updates the working result table, human-readable experiment
journal, per-experiment analysis note, run state, artifact registry, data-root
ledger, agent status, and event log together. It requires
`--result-analysis` for succeeded or failed outcomes unless the user explicitly
allows pending analysis, so result rows do not land without an explanation of
why performance improved, regressed, or stayed flat.

Use `--final-export` only when the row is stable enough for
`09_report/results/`; ordinary research outcomes should remain in
`05_results/` and `03_experiments/`.

## Command Queue CLI

The structured command queue is stored in `state/command_queue.json`.

```bash
python -m scripts.commands.review.command_queue add --project my_new_project --id cmd_003 --action "Run exp_001" --owner code_agent --priority high --output 03_experiments/exp_001/results/ --display-summary "Run the reviewer-facing ablation." --why-now "This checks the central experimental claim before writing." --done-when "The run log, result files, and result summary are recorded."
python -m scripts.commands.review.command_queue update --project my_new_project --id cmd_003 --status "in progress"
python -m scripts.commands.review.command_queue list --project my_new_project
python -m scripts.commands.review.command_queue list --project my_new_project --verbose
python -m scripts.commands.review.command_queue list --project my_new_project --json
```

Use `--depends-on <cmd_id>` for commands that must wait for another command to
finish. Use `--parallel-group <group>` when the director intentionally groups
independent commands for a safe multi-agent batch.
Use `list --verbose` or `list --json` before parallel dispatch when you need to
inspect dependency readiness, unfinished dependency ids, parallel group, and
output metadata. JSON list output enriches each command with
`dependency_ready` and `unfinished_dependencies` without writing those computed
fields back to `state/command_queue.json`.

Keep `state/next_actions.md` as a human-readable mirror, but treat `command_queue.json` as the structured source of truth.
The generated mirror includes `Depends On` and `Parallel Group` columns so
agents can spot safe multi-agent batches without opening JSON.
Direct `command_queue add`, `update`, and `remove` operations append queue
lifecycle events without automatically changing `state/agent_status.json`; use
`agent_status.py` or the owning workflow command when agent status should move.
For high-risk commands, add `--requires-vote --vote-id <vote_id> --risk-level high`; `agent_orchestrator.py dispatch` will refuse to run the command until the linked vote is approved.

## Agent Vote CLI

Important commands can be gated by multi-agent votes in `state/agent_votes.json`.
Vote open/cast/cancel/auto actions record lifecycle status/events so high-risk
decisions stay visible in file-state handoffs.

```bash
python -m scripts.commands.agents.agent_vote open --project my_new_project --id vote_001 --title "Approve baseline reproduction" --rationale "This changes experiment scope and compute spend." --risk-level high --command-id cmd_003 --required-voter director --required-voter critic --min-approvals 2
python -m scripts.commands.agents.agent_vote vote --project my_new_project --id vote_001 --agent director --vote approve --confidence high --rationale "Inputs and rollback path are clear."
python -m scripts.commands.agents.agent_vote vote --project my_new_project --id vote_001 --agent critic --vote approve --confidence medium --rationale "Risk is acceptable with the recorded checks."
python -m scripts.commands.agents.agent_vote status --project my_new_project --id vote_001
```

Generate voter prompts and optionally run voter agents automatically:

```bash
python -m scripts.commands.agents.agent_vote auto --project my_new_project --id vote_001 --voter director --voter critic --execute --runner-command "<your-agent-cli> --prompt-file {prompt_file}"
python -m scripts.commands.agents.agent_orchestrator dispatch --project my_new_project --id cmd_003 --auto-vote --vote-voter director --vote-voter critic --vote-runner-command "<your-agent-cli> --prompt-file {prompt_file}"
```

The runner output is parsed from `<vote>approve|reject|abstain</vote>`, `<confidence>low|medium|high</confidence>`, and `<rationale>...</rationale>` tags. Unparseable or failed runner output records an `abstain`, not an approval. Automatic voting through either `agent_vote.py auto` or `agent_orchestrator.py dispatch --auto-vote` appends an `agent_vote_auto` lifecycle event.

## Session Workspace CLI

Use `state/sessions/<session_id>/` for loop-local scratchpads, plans, results, and non-final artifacts.
Session start, update, finish, and prune commands append `session_state_*`
events while keeping the session folder as the source of truth.

```bash
python -m scripts.commands.review.session_state start --project my_new_project --goal "Run baseline intake and smoke checks before full reproduction."
python -m scripts.commands.review.session_state update --project my_new_project --id session_ab12cd34 --command-id cmd_003 --note "Smoke checks queued."
python -m scripts.commands.review.session_state finish --project my_new_project --id session_ab12cd34 --status done --note "Session outputs are summarized in loop_summary.json."
python -m scripts.commands.review.session_state validate --project my_new_project
```

## Pattern Memory CLI

Use `state/pattern_memory.json` for project-local reusable lessons. This is for patterns that should guide later agents, such as when to smoke-test, when to require a vote, or which evidence format avoided a previous failure.
Pattern additions and updates append `pattern_memory_*` events while keeping
`state/pattern_memory.json` as the reusable lesson source of truth.

```bash
python -m scripts.commands.review.pattern_memory add --project my_new_project --id baseline_smoke_first --title "Smoke baseline before full runs" --summary "Run the smallest baseline check before spending full GPU time." --tag baseline --trigger "Before reproducing a cloned baseline" --recommendation "Use baseline_sandbox.py and a smoke command before scheduler launch." --evidence state/pattern_memory.json
python -m scripts.commands.review.pattern_memory search --project my_new_project --query "baseline smoke"
python -m scripts.commands.review.pattern_memory validate --project my_new_project
```

## Memory Compact CLI

`state/agent_memory.md` is read at every resume, and `progress_checkpoint`
appends a `## Memory Checkpoint:` block per durable note, so the file grows
monotonically and taxes context. `memory_compact` archives old checkpoint
blocks verbatim to `state/sessions/memory_archive.md` and rewrites the live
file with the curated header sections (Stable Project Facts, Operating Model,
…) plus the recent checkpoints. Curated sections and undated checkpoints are
never archived. Preview by default; pass `--apply` to write.

```bash
python -m scripts.commands.review.memory_compact --project my_new_project
python -m scripts.commands.review.memory_compact --project my_new_project --older-than-days 30 --keep-recent 5 --apply
```

`--older-than-days` sets the staleness cutoff and `--keep-recent` pins the N
newest checkpoints even when they are older than the cutoff. History is never
lost — retired blocks move to the archive, which stays out of `09_report/`.

## Legacy Ralph Loop CLI

The Ralph loop CLI is kept for compatibility, but it is no longer the default
automation path. Prefer Claude/Codex native session controls plus the harness
command queue, agent status, messages, session workspaces, and loop summary.

Use `state/ralph_loop.json` only when a human explicitly wants the legacy
bounded autonomous pass: run until the result is detected or until the requested
time budget expires. A result can be an explicit completion promise from the
runner, a linked command reaching `done`, or a configured result file appearing.

```bash
python -m scripts.commands.review.ralph_loop run --project my_new_project --goal "Finish the next dispatchable command or record a blocker." --duration-hours 3 --completion-promise RALPH_COMPLETE --result-file state/progress_hooks.jsonl --codex-runner
python -m scripts.commands.review.ralph_loop run --project my_new_project --goal "Finish the next dispatchable command or record a blocker." --duration-hours 3 --completion-promise RALPH_COMPLETE --result-file state/progress_hooks.jsonl --execute --runner-command "<your-agent-cli> --prompt-file {prompt_file}"
python -m scripts.commands.review.ralph_loop status --project my_new_project
python -m scripts.commands.review.ralph_loop validate --project my_new_project
python -m scripts.commands.review.ralph_loop compact --project my_new_project --id <run_id> --keep 5 --delete-prompts
```

For experiment loops, prefer a progress checkpoint or working result artifact as
the result detector. Do not use `09_report/results/experiment_results.csv` as a
default loop target; that file is reserved for stable final exports.

Without `--codex-runner` or `--execute`, the CLI writes one fresh-context prompt under `state/ralph_prompts/` and leaves the run recorded as `running` so an operator can execute or cancel it. With `--codex-runner`, each iteration calls `codex -a never exec -C <repo> -s workspace-write -` and sends the fresh prompt on stdin. With `--execute --runner-command`, each runner invocation receives only the prompt file path, so state must persist through project files rather than chat history. For Claude, use the generic `--execute --runner-command` path instead of `--codex-runner`.
If a loop is interrupted, rerun `ralph_loop.py run` with the same `--id`; running loops resume from their existing deadline, result files, and iteration history instead of starting over or failing as duplicates.
Use `compact` only for terminal runs when an iteration history became too large;
it edits `state/ralph_loop.json` through the Ralph CLI and can remove obsolete
prompt files from `state/ralph_prompts/`.

## Agent Message CLI

The agent-to-agent request channel is stored in `state/agent_messages.json`.

```bash
python -m scripts.commands.agents.agent_messages send --project my_new_project --id msg_001 --from-agent director --to-agent data_analyst --kind question --priority high --subject "Check exp_001 robustness" --body "Can the current result support claim_001?" --related-exp-id exp_001 --related-claim-id claim_001 --required-response "Return supported/partial/unsupported with evidence."
python -m scripts.commands.agents.agent_messages respond --project my_new_project --id msg_001 --from-agent data_analyst --response "Partial only; seed variance is still missing."
python -m scripts.commands.agents.agent_messages list --project my_new_project --agent data_analyst
```

Use command queue entries for user-visible work ownership. Use agent messages for questions, handoffs, review requests, blockers, and decisions between agents.
`agent_messages send`, `update`, and `respond` append coordination events while
keeping `state/agent_messages.json` as the source of truth for message content.

## Loop Summary CLI

Project loop summaries are stored in `state/loop_summary.json`. They are useful
for fresh Claude/Codex continuation, report summaries, and optional dashboard
inspection.
Loop summary mutations append `loop_summary_*` events while keeping
`state/loop_summary.json` as the recap source of truth.

```bash
python -m scripts.commands.review.loop_summary start --project my_new_project --loop-id loop_003 --goal "Run the reviewer-facing ablation"
python -m scripts.commands.review.loop_summary update --project my_new_project --summary "The loop is running; initial logs are healthy."
python -m scripts.commands.review.loop_summary add-work --project my_new_project --id cmd_003 --action "Run exp_001" --owner code_agent --result "Experiment completed" --output 03_experiments/exp_001/run_log.md
python -m scripts.commands.review.loop_summary add-result --project my_new_project --title "Ablation result" --status done --summary "The ablation supports the target claim." --evidence 03_experiments/exp_001/results/
python -m scripts.commands.review.loop_summary add-next --project my_new_project --action "Turn the ablation result into rebuttal text" --owner writing_agent --priority high --output 07_reviews/rebuttal_notes.md --note "Done when the rebuttal note states the claim, evidence, and caveat in reader-facing prose."
python -m scripts.commands.review.loop_summary finish --project my_new_project --status done --summary "Loop completed with result and follow-up." --outcome "Use the ablation in the next writing pass."
```

Use this file at the start and end of each research loop so completed work is
separated from active commands in file-state continuation and optional status
surfaces.
For `add-next`, make `--action` readable on its own. Put paths in `--output`; do not use paths as the main explanation.

## Experiment Run State CLI

Long GPU/server experiments should be tracked in `03_experiments/<exp_id>/run_state.json`.

```bash
python -m scripts.commands.experiments.run_state init --project my_new_project --exp-id exp_001
python -m scripts.commands.experiments.run_state start --project my_new_project --exp-id exp_001 --slurm-job-name exp_001 --slurm-job-id 12345 --gpu-type A4000 --node node05 --log-path 03_experiments/exp_001/run.log --result-path 03_experiments/exp_001/results/ --expected-output "ablation metrics and logs" --check-procedure "Inspect run.log and metrics before marking succeeded." --display-summary "Run exp_001 ablation on the configured dataset."
python -m scripts.commands.experiments.run_state heartbeat --project my_new_project --exp-id exp_001 --note "epoch 20/100"
python -m scripts.commands.experiments.run_state finish --project my_new_project --exp-id exp_001 --status succeeded --judgement "Run completed; analysis still needs to explain the metric movement." --next-action "Ask data_analyst to update 03_experiments/exp_001/analysis.md, 05_results/experiment_journal.md, and 05_results/experiment_journal.csv."
```

`run_state.py` also updates the owning agent's `state/agent_status.json` row and
appends a lifecycle event. A succeeded run sets the owner to `waiting`, not
`done`, because analysis and experiment journal updates usually remain.

## Research Registry CLI

Datasets and metrics used in final result tables should be registered with stable IDs.

```bash
python -m scripts.commands.research.research_registry add-dataset --project my_new_project --id cnn_dm --name "CNN/DailyMail" --status validated --source "hf://cnn_dailymail" --split test --checksum "<split-or-manifest-checksum>"
python -m scripts.commands.research.research_registry add-metric --project my_new_project --id rouge_l --name "ROUGE-L" --status validated --direction higher
python -m scripts.commands.research.research_registry validate --project my_new_project
```

`05_results/experiment_results.csv` and final exports under
`09_report/results/` should use these IDs in their `dataset` and `metric`
columns.
Registry changes record the generic `research_registry` event plus
`research_registry_dataset` or `research_registry_metric` for easier event-log
filtering.

## Researcher Workflow CLIs

Use these commands when a real researcher is starting or auditing a project.
They make the required research state explicit before expensive experiments or
submission-style writing.

Create the initial brief, first claim row, dataset/metric candidates, and an
intake summary. This also marks the starter brief command done and routes the
next command toward director triage:

```bash
python -m scripts.commands.projects.project_intake apply --project my_new_project --research-question "..." --motivation "..." --contribution "..." --claim-id claim_001 --dataset-id my_dataset --dataset-name "My Dataset" --metric-id main_metric --metric-name "Main Metric" --metric-direction higher --force
```

Complete and audit an experiment preregistration before execution. The write
command records `experiment_designer` lifecycle status/events by default; use
`--agent <role>` when another role owns the preregistration. Success evidence
points to the working result table in `05_results/experiment_results.csv`;
export to `09_report/results/` only after the result is stable enough for
reader-facing review.

```bash
python -m scripts.commands.experiments.preregistration_helper write --project my_new_project --exp-id exp_001 --claim-id claim_001 --claim "..." --expectation "..." --support "..." --falsify "..." --success "..." --failure "..." --metric main_metric --dataset my_dataset --split test --smoke-command "python -m ..." --smoke-expected-output "small metrics file" --smoke-check-procedure "inspect log and output path" --analysis "..." --decision-rule "..."
python -m scripts.commands.experiments.preregistration_helper audit --project my_new_project --exp-id exp_001 --strict
```

Generate the working claim/evidence board and a broader research-readiness
audit:

```bash
python -m scripts.commands.reports.claim_evidence_board build --project my_new_project --write
python -m scripts.commands.research.research_audit --project my_new_project --write-report
python -m scripts.commands.reports.report_index refresh --project my_new_project
```

Export a stable reader-facing claim board only when the board is no longer just
working interpretation:

```bash
python -m scripts.commands.reports.claim_evidence_board build --project my_new_project --write --final-export
```

The generated board lives in `05_results/claim_evidence_board.md`, and the
readiness audit lives in `07_reviews/research_audit.md`. Add `--final-export`
to `claim_evidence_board build --write` only when the board is stable enough for
`09_report/results/claim_evidence_board.csv`. `research_audit --write-report`
writes the review audit and reader-facing audit table, then surfaces it in the
generated `09_report/README.md` index. `research_audit --write-report` records
director lifecycle status/events by default; use `--agent <role>` when another
role owns the readiness audit. `claim_evidence_board build --write` records
`result_interpreter` lifecycle status/events by default; use `--agent <role>`
when another role owns the claim-board update.

## Research Loop CLI

Use this to turn current evidence gaps into visible command-queue work.

```bash
python -m scripts.commands.research.research_loop plan --project my_new_project
python -m scripts.commands.research.research_loop enqueue --project my_new_project --max-actions 3
```

`plan` is read-only. `enqueue` records a `director` lifecycle status/event when
it adds command-queue entries and handoff messages.

The loop CLI writes `state/command_queue.json` and `state/agent_messages.json`.
Generated command-queue entries include `depends_on` and `parallel_group`
metadata so `agent_orchestrator parallel` can safely batch independent follow-up
work. If the loop also enqueues research-question refinement, other generated
tasks depend on that brief-refinement command before they become parallel-ready.
It treats `05_results/experiment_results.csv` as working evidence for planning
robustness checks, while final claim/paper gates still rely on stable
`09_report/results/` exports.

## Research Quality Hooks

Use these before claiming a result is publication-ready.
`source_credibility_audit` also runs bib-entry hygiene checks over
`01_literature/papers.bib`: duplicate keys, placeholder entries, near-duplicate
titles, missing essential fields (title/year/author), and an informational
arXiv-preprint count. Duplicates, placeholders, and near-duplicates gate
`--strict`; missing fields warn only. A freshly created project starts
`blocked` on this audit until the template's starter `placeholder2026` bib
entry is replaced with real literature — that is the intended signal.

```bash
python -m scripts.commands.reports.source_credibility_audit --project my_new_project --write-report
python -m scripts.commands.experiments.experiment_diagnosis --project my_new_project --write-report
python -m scripts.commands.research.phase_gate init --project my_new_project
python -m scripts.commands.research.phase_gate audit --project my_new_project --write-report
python -m scripts.commands.reports.resource_ledger init --project my_new_project
python -m scripts.commands.reports.resource_ledger summary --project my_new_project --write-report
python -m scripts.commands.experiments.run_checkpoint create --project my_new_project --id before_major_loop --label "Before major loop"
```

`run_checkpoint create` records director lifecycle status/events by default;
use `--agent <role>` when another role owns the checkpoint.

### Result-integrity checks

Before strengthening claims, two checks catch the most common ways agent-driven
results become untrustworthy:

```bash
# Preregistration drift: did the executed run match what was registered?
python -m scripts.commands.experiments.preregistration_helper drift --project my_new_project --exp-id exp_001 --strict
# Statement-to-evidence grounding is part of the paper claim linter:
python -m scripts.commands.reports.paper_claim_linter --project my_new_project --strict
```

`preregistration_helper drift` compares the preregistration (dataset, primary
metric, claim id) against `05_results/experiment_results.csv` rows (including
`_seed_<n>` children) and `run_state.json`, flagging dataset/metric/claim drift
and a `succeeded` run with no matching result rows. Split drift is covered once
result rows carry a `split` column. `paper_claim_linter` now also flags
**ungrounded claim statements** — sentences asserting a strong/comparative
result (outperforms, state-of-the-art, significantly, …) that cite no matching
result number, no `claim_id`, and no citation.

The source audit checks bibliography/citation integrity and claim-source links.
The experiment diagnosis hook turns failed, stale, or result-missing runs into
repair actions in `state/command_queue.json`. Phase gates track whether the project is ready to move between
brief, literature, planning, experiment, result, writing, review, and final
report phases. The resource ledger records token, cost, GPU, wall-time, API, or
storage usage. Resource ledger records append `resource_ledger_record` events;
summary reports keep the existing director lifecycle status/event. Checkpoints are lightweight replay/fork snapshots and do not
restore files automatically.

## GPU Scheduler CLI

Use this for bounded parallel GPU experiments. Planning is safe; launch only starts jobs with `--execute`.

```bash
python -m scripts.commands.experiments.gpu_scheduler init --project my_new_project
python -m scripts.commands.experiments.gpu_scheduler add --project my_new_project --id exp_001_seed_1 --exp-id exp_001 --command "python train.py --config 03_experiments/exp_001/config.yaml --seed 1" --gpu-type auto --priority high --result-path 03_experiments/exp_001/results/seed_1/ --expected-output "seed_1 metrics and checkpoint" --check-procedure "Inspect the log and verify metrics exist before marking succeeded."
python -m scripts.commands.experiments.gpu_scheduler add --project my_new_project --id exp_001_seed_2 --exp-id exp_001 --command "python train.py --config 03_experiments/exp_001/config.yaml --seed 2" --gpu-type auto --priority high --result-path 03_experiments/exp_001/results/seed_2/ --expected-output "seed_2 metrics and checkpoint" --check-procedure "Inspect the log and verify metrics exist before marking succeeded."
python -m scripts.commands.experiments.gpu_scheduler add --project my_new_project --id exp_001_analysis --exp-id exp_001 --command "python analyze.py --input 03_experiments/exp_001/results/" --gpu-type auto --priority medium --result-path 05_results/experiment_journal.md --expected-output "analysis explaining metric movement" --check-procedure "Confirm experiment_journal.md explains why the result changed." --depends-on exp_001_seed_1 --depends-on exp_001_seed_2
python -m scripts.commands.experiments.gpu_scheduler plan --project my_new_project
python -m scripts.commands.experiments.gpu_scheduler list --project my_new_project --json
python -m scripts.commands.experiments.gpu_scheduler dispatch --project my_new_project
python -m scripts.commands.experiments.gpu_scheduler dispatch --project my_new_project --json
python -m scripts.commands.experiments.gpu_scheduler dispatch --project my_new_project --execute
```

The scheduler reads the configured queue command, checks available configured
nodes, caps launches at the workspace/profile GPU limit, submits launchable
independent jobs with `sbatch --parsable`, and updates `run_state.json` after
executed dispatches. Queue additions, launches, and outcome updates also append
agent events and update `state/agent_status.json` for the owning agent. Jobs without
`depends_on` are treated as independent; jobs with `depends_on` are held until
every dependency has status `succeeded`.
`plan --json` includes `plan_diagnostics` so agents can see which queued jobs
were selected and which were excluded for unfinished dependencies, unavailable
GPU type, user GPU cap, or per-type capacity.
`list --json` enriches queued/running/completed jobs with `dependency_ready` and
`unfinished_dependencies` without writing those computed fields back to
`state/gpu_experiment_queue.json`.
`dispatch` without `--execute` prints the launch commands for selected jobs and
diagnostic lines for queued jobs that were excluded from that dry-run batch.
Use `dispatch --json` for a machine-readable dry-run payload containing
`selected_jobs`, `plan_diagnostics`, and `launch_commands`; it is intentionally
blocked with `--execute`.
Executed dispatches also append a `gpu_dispatch_plan` event before launch. That
event records the selected job IDs, commands, expected outputs, and check
procedures for the parallel batch.

Use `dispatch` for normal parallel batches. `launch` is single-job by default:
use `launch --id <job_id>` for a debug/manual launch, or `launch --all-planned`
only when intentionally preserving the older all-planned launch behavior.
Explicit `dispatch --ids <job_id>` requests fail with the same diagnostic
reasons when a requested job is not currently dispatchable. If `--ids` names
more jobs than `--max-parallel`, the scheduler fails instead of silently
dropping explicit jobs.

Monitor detached launches and update outcomes:

```bash
python -m scripts.commands.experiments.gpu_monitor --project my_new_project
python -m scripts.commands.experiments.gpu_monitor --project my_new_project --squeue-output state/squeue_mock.txt --json
```

When `gpu_scheduler update --status succeeded` records a completed GPU job, the
experiment `run_state.json` receives a follow-up `next_action` asking the agent
to explain why the result improved, regressed, or stayed flat and to update the
experiment analysis/journal files.
Use `gpu_scheduler refresh --json` to inspect scheduler-visible lifecycle state
for queued and running jobs. Use `refresh --write` to sync visible terminal
states into `state/gpu_experiment_queue.json` and experiment `run_state.json`.
If a running job is missing from scheduler output, pass `--mark-missing blocked`
or another explicit terminal status only after deciding how missing jobs should
be handled in that environment.

## Log Digest CLI

Condense a huge training/SLURM log into a bounded, deterministic digest instead
of reading the whole file in an agent session. The digest keeps the head, the
tail, and every line matching failure patterns (error/exception/traceback/
NaN/OOM/CUDA/slurmstepd/killed/assert), capped with explicit truncation notes.

```bash
python -m scripts.commands.experiments.log_digest --log 03_experiments/exp_001/results/train.log
python -m scripts.commands.experiments.log_digest --log slurm-12345.out --out 03_experiments/exp_001/results/log_digest.md
python -m scripts.commands.experiments.log_digest --log train.log --pattern "val_acc" --max-matches 400
```

Digests are working diagnostics: keep them under `03_experiments/<exp_id>/` or
`state/sessions/`, never `09_report/`. Add `--pattern <regex>` for run-specific
metric lines, or `--no-default-patterns` to match only your own patterns.

## Run Diff CLI

Mechanically answer "what changed between these two runs" instead of eyeballing
experiment folders. Read-only; compares `config.yaml` (unified diff),
`reproducibility_manifest.json` (dotted-key differences), and the runs' result
rows from `05_results/experiment_results.csv`:

```bash
python -m scripts.commands.experiments.run_diff --project my_new_project --exp-a exp_001 --exp-b exp_002
python -m scripts.commands.experiments.run_diff --project my_new_project --exp-a exp_001 --exp-b exp_002 --out 05_results/run_diff_exp001_exp002.md
```

## Environment Capture CLI

Fill the empty observable fields of an experiment's
`reproducibility_manifest.json` automatically (git commit with dirty flag,
Python version, `pip freeze` snapshot to `environment_freeze.txt`, node, GPU
type/count when `nvidia-smi` is available). Existing non-empty values are never
overwritten:

```bash
python -m scripts.commands.experiments.env_capture --project my_new_project --exp-id exp_001 --dry-run
python -m scripts.commands.experiments.env_capture --project my_new_project --exp-id exp_001
```

## Seed Variance CLI

Audit multi-seed result stability before claims strengthen. Groups
`05_results/experiment_results.csv` rows by stripping the planner's
`_seed_<n>` suffix and warns on single-seed claims and unstable families:

```bash
python -m scripts.commands.experiments.seed_variance --project my_new_project
python -m scripts.commands.experiments.seed_variance --project my_new_project --write-report --strict
```

`--write-report` writes the working diagnostic `05_results/seed_variance.md`;
`--strict` exits 1 when any single-seed-claim or instability warning exists.

## Agent Orchestrator CLI

Use this when you want command queue entries to become reproducible prompts or an opt-in external runner invocation.

Rendered prompts default to the lean style: the role prompt, filesystem safety
rules, and the dispatch payload are inlined, while the other shared contracts
(`prompts/shared/output_contracts.md`, routing matrix, handoff graph, dispatch
protocol, risk matrix, brain protocol, research context, skill usage) are
listed as read-on-demand pointers. This keeps each worker prompt at roughly 2k
tokens instead of ~17k. Pass `--prompt-style full` on `prompt`, `dispatch`, or
`parallel` only when a runner cannot read repository files.

```bash
python -m scripts.commands.agents.agent_orchestrator next --project my_new_project
python -m scripts.commands.agents.agent_orchestrator status-parallel --project my_new_project
python -m scripts.commands.agents.agent_orchestrator prompt --project my_new_project --id cmd_001 --write
python -m scripts.commands.agents.agent_orchestrator dispatch --project my_new_project --id cmd_001
python -m scripts.commands.agents.agent_orchestrator finish --project my_new_project --id cmd_001 --status done --note "Verified."
```

`next` keeps the serial fallback visible for compatibility, but also prints a
parallel batch hint when several independent commands are ready. In JSON mode,
the same hint is returned as `parallel_commands` alongside
`open_parallel_diagnostics`.
`status-parallel` is read-only and shows both safe open parallel candidates and
already-written prepared parallel commands, including whether each prepared
prompt is `ready` or still waiting on unfinished dependencies. It also reports
open command diagnostics such as `missing_expected_outputs`,
`unfinished_dependencies:<ids>`, `owner_already_selected:<agent>`, and
`path_conflict` so agents can fix the queue instead of guessing why no safe
batch appeared.
JSON output from `parallel`, `status-parallel`, `run-prepared`, and
`finish-parallel` includes `scope` or `read_only`/`dry_run` metadata so a fresh
agent can tell whether a command changed state or only inspected a batch.
`parallel --json` also includes `open_parallel_diagnostics`, so automation can
explain excluded open commands without running a separate status command.
`run-prepared` re-checks `depends_on` immediately before launching prepared
prompts; explicit `--id` or `--group` runs fail instead of silently launching
work whose dependencies are not done.

When multiple independent agent tasks are ready, plan or write a parallel batch:

```bash
python -m scripts.commands.agents.agent_orchestrator parallel --project my_new_project --max-agents 4
python -m scripts.commands.agents.agent_orchestrator parallel --project my_new_project --max-agents 4 --write
python -m scripts.commands.agents.agent_orchestrator parallel --project my_new_project --max-agents 4 --write --execute --runner-command "<your-agent-cli> --prompt-file {prompt_file}"
python -m scripts.commands.agents.agent_orchestrator run-prepared --project my_new_project --group research_loop_auto --dry-run
python -m scripts.commands.agents.agent_orchestrator run-prepared --project my_new_project --group research_loop_auto --runner-command "<your-agent-cli> --prompt-file {prompt_file}"
python -m scripts.commands.agents.agent_orchestrator finish-parallel --project my_new_project --group research_loop_auto --status done --dry-run
python -m scripts.commands.agents.agent_orchestrator finish-parallel --project my_new_project --group research_loop_auto --status done --note "Verified worker outputs."
python -m scripts.commands.agents.agent_orchestrator finish-parallel --project my_new_project --group research_loop_auto --status done --result-file cmd_003=05_results/worker_results/cmd_003.md
```

The parallel planner selects `open` commands whose votes are approved, whose
`depends_on` commands are `done`, whose expected output paths do not conflict,
and whose owner agents are distinct unless `--allow-same-agent` is passed. Use
`command_queue add --depends-on <cmd_id> --parallel-group <group>` to make
dependencies and safe batches explicit.
Automatic planning excludes unsafe open commands. Explicit `parallel --id
<cmd>` requests are stricter: every requested command must be open, have
expected outputs, pass vote/dependency gates, avoid owner/path conflicts with
other explicit ids, and fit within `--max-agents`; otherwise the command fails
with a concrete reason instead of being silently skipped.

`parallel --write` records a batch manifest under
`state/orchestrator_prompts/parallel_batches/` in addition to individual worker
prompts and a `parallel_dispatch_plan` event.
Use `run-prepared --dry-run` to inspect prompts written in an earlier session
without starting external runners. Use `run-prepared --runner-command ...` when
the prepared commands are already `in progress`; `parallel --execute` only
selects still-open commands. `run-prepared` requires `--group`, one or more
`--id` values, or the explicit `--all-prepared` override so separate prepared
batches are not mixed accidentally. `--all-prepared` still respects dependency
readiness and fails rather than launching prompts whose `depends_on` entries are
not done.
Use `finish-parallel --dry-run` after reviewing worker results to inspect which
commands would close. Then use `finish-parallel` to mark a scoped prepared batch
`done`, `blocked`, or `deferred` without finishing unrelated groups. `--status
done` requires a verification `--note`, evidence `--output`, or per-command
`--result-file <command_id>=<path>` when not using `--dry-run`. `blocked` and
`deferred` finishes require a reason in `--note`. Per-command result files are
merged with existing `expected_outputs` rather than replacing them.
When `run-prepared` or `finish-parallel` receives explicit `--id` values, each
id must already be an `in progress` prepared command with an
`orchestrator_prompt`; invalid explicit ids fail instead of being skipped.

Generic checkpoint paths such as `state/current_state.md`,
`state/agent_memory.md`, `state/next_actions.md`,
`state/open_questions.md`, `state/agent_status.json`, and
`state/agent_events.jsonl` are treated as managed coordination state for
parallel conflict checks. Each parallel-ready command should still list at
least one substantive working artifact in `expected_outputs`.

`dispatch --execute`, `parallel --execute`, and `run-prepared` can use either
an explicit `--runner-command` template or a local
`--runner-profile <name>` from `config/workspace_profile.local.json`.
If `agent_runners.default_profile` is configured, `--execute` falls back to that
profile when no inline runner command is supplied. Runner profile commands are
arrays and can use `{prompt_file}`, `{project}`, `{command_id}`, and `{agent}`
placeholders.

## Baseline Library CLI

Baseline and prior-code metadata should be tracked in `08_baselines/baseline_registry.json`.

```bash
python -m scripts.commands.baselines.baseline_library init --project my_new_project
python -m scripts.commands.baselines.baseline_library add --project my_new_project --id baseline_lstm --name "Baseline-LSTM" --paper "..." --repo-url "..." --status source_found --owner code_agent
python -m scripts.commands.baselines.baseline_library update --project my_new_project --id baseline_lstm --status runnable --source-path 08_baselines/source_snapshots/baseline_lstm --working-dir 04_code --dataset-path data/processed --config 03_experiments/exp_001/config.yaml --run-command "python train.py --config configs/baseline_lstm.yaml" --result-path 03_experiments/exp_001/results/
python -m scripts.commands.baselines.baseline_library list --project my_new_project
python -m scripts.commands.baselines.baseline_library validate --project my_new_project --strict
```

`baseline_library add` and `baseline_library update` record lifecycle
status/events for the baseline owner, defaulting to `code_agent` when no owner
is set. The recorded output paths include the registry and any known source,
adapter, smoke, result, or evidence paths.

Use `08_baselines/prior_research_inventory.md` for human-readable method mapping and `08_baselines/code_adaptation_notes.md` for compatibility changes.

## Baseline Intake CLI

When the user provides baseline papers or repo URLs, use `baseline_intake.py` to register, clone, and inspect baseline source.
Intake also records the owning agent's lifecycle status and an event log entry
so later agents can see that baseline source mapping is ready.
`ingest` and `inspect` clone/inspect the repos, write a dry smoke scaffold under
`08_baselines/run_scripts/`, and update `08_baselines/code_structure_plan.md`
with the inspected repo structure. Baseline wrappers/adapters live only under
`08_baselines/` (`run_scripts/<id>/` or `patches/`); intake never writes into
`04_code/src/`, which stays independent of baseline code.
Project validation warns if generated baseline structure reports are not
reflected in `08_baselines/code_structure_plan.md`.

```bash
python -m scripts.commands.baselines.baseline_intake ingest --project my_new_project --manifest baselines.csv --clone --allow-network --message-missing-repos
python -m scripts.commands.baselines.baseline_intake discover --project my_new_project --message-missing-repos
python -m scripts.commands.baselines.baseline_intake inspect --project my_new_project --id dpp_lstm
```

Recommended manifest columns:

```text
id,name,paper,repo_url,dataset,metric
```

Outputs include `08_baselines/source_snapshots/<baseline_id>/`, `08_baselines/structure_reports/<baseline_id>.json`, `08_baselines/code_structure_plan.md`, and `08_baselines/run_scripts/<baseline_id>_smoke.py`.

Resolve repo candidates and audit command safety:

```bash
python -m scripts.commands.baselines.repo_discovery --project my_new_project --candidate-file 08_baselines/repo_candidates.csv --apply
python -m scripts.commands.baselines.baseline_sandbox --project my_new_project --strict --write-policy
```

`repo_discovery.py` records `literature_reviewer` lifecycle status/events by
default; use `--agent <role>` when another role owns the repo-candidate pass.
`baseline_sandbox.py --write-policy` records `code_agent` lifecycle
status/events by default; use `--agent <role>` when another role owns the
sandbox-policy pass.

## Result Evidence CLI

Normalize experiment outputs and check result provenance before strengthening paper claims.
The ingest commands append lifecycle status for the recording agent. Result
ingest keeps the experiment journal and experiment-local analysis current;
robustness ingest also appends working robustness notes before final exports are
treated as reader-facing evidence.

```bash
python -m scripts.commands.experiments.result_ingest ingest --project my_new_project --exp-id exp_001 --input 03_experiments/exp_001/metrics.json --claim-id claim_001 --dataset cnn_dm --method our_method --rationale "why this experiment was run" --result-analysis "why performance improved, regressed, or stayed flat"
python -m scripts.commands.experiments.result_ingest robustness --project my_new_project --exp-id exp_001 --input 03_experiments/exp_001/robustness.json --claim-id claim_001 --next-needed "interpret robustness before strengthening the claim"
python -m scripts.commands.experiments.result_ingest robustness --project my_new_project --exp-id exp_001 --input 03_experiments/exp_001/robustness.json --claim-id claim_001 --next-needed "stable reader-facing robustness export" --final-export
python -m scripts.commands.reports.data_metric_audit --project my_new_project --strict --write-report
python -m scripts.commands.reports.paper_claim_linter --project my_new_project --strict
```

Add `--final-export` to `result_ingest ingest` only when the result row should
also update `09_report/results/experiment_results.csv`. Add `--final-export` to
`result_ingest robustness` only when the robustness row should also update
`09_report/results/statistical_robustness.csv`.

`research_audit.py` also checks that non-template projects have moved beyond
starter working artifacts for `03_experiments/data_roots.md`,
`05_results/experiment_journal.md`, `05_results/experiment_journal.csv`, and
`06_writing/terminology.md`.
`claim_evidence_board.py` uses final claim/result CSVs for stable claim counts,
but its Markdown report also previews non-starter working rows from
`05_results/experiment_journal.csv` so early projects can see evidence before
final export. Add `--final-export` only when the board should also update
`09_report/results/claim_evidence_board.csv`.
`data_metric_audit.py` checks final exported result rows, pre-export working
rows in `05_results/experiment_results.csv`, and journal rows in
`05_results/experiment_journal.csv` for dataset registry and data-root coverage.
`--write-report` writes working audit outputs under `05_results/` and records
`data_analyst` lifecycle status/events by default. It does not refresh the final
report index unless a separate report-facing export step is run. Use
`--agent <role>` when another role owns the provenance audit.

## Revision And Artifact CLI

Convert reviewer risks into commands and package reproducibility artifacts.

```bash
python -m scripts.commands.review.review_to_revision --project my_new_project --enqueue
python -m scripts.commands.reports.artifact_packager --project my_new_project --tar
```

`artifact_packager` includes report artifacts, experiment provenance, the
working result table, the running experiment journal, data-root documentation,
and the terminology glossary. It fails by default if those required working
evidence files are missing; use `--allow-incomplete` only for explicit
draft/internal packages. It also fails by default if packaged text files contain
local absolute paths; use `--allow-local-paths` only for private/internal
archives. Non-dry-run packaging records `writing_agent` lifecycle status/events
by default; pass `--agent <role>` if another role owns the release artifact.

Before packaging or sharing final artifacts, run `project_closeout`. It checks
final claim export readiness, workflow/vote blockers, report hygiene, data-root
documentation, experiment-journal explanations, and terminology glossary
readiness.

## Review Form CLI

Venue/year review forms are registered in `review_forms/form_registry.json`.

```bash
python -m scripts.commands.review.review_forms list
python -m scripts.commands.review.review_forms scaffold --id iclr_2026_main --venue iclr --year 2026 --track main
python -m scripts.commands.review.review_forms add --id acl_2026_main --venue acl --year 2026 --track main --form-path review_forms/venues/acl/2026/main/review_form.md --rubric-path review_forms/venues/acl/2026/main/rubric.md
python -m scripts.commands.review.review_forms create-review --project my_new_project --form-id iclr_2026_main --review-id iclr_2026_draft_review --paper 06_writing/draft.md --use-case internal_mock_review
python -m scripts.commands.review.review_forms validate --strict
```

Generated project reviews go under `07_reviews/form_reviews/`.
`create-review` records the selected `--reviewer` lifecycle status/events; the
default reviewer is `venue_reviewer`.

## Weekly Dev Deck CLI

Render an image-first weekly progress deck (KPI tiles, result trend/delta
charts, harvested figures) for a project on top of the machine-local PowerPoint
template. Data collection is standard-library; rendering needs the optional
`deck` extra (`pip install -e .[deck]` for python-pptx + matplotlib).

```bash
python -m scripts.commands.reports.weekly_deck build --project my_new_project --dry-run
python -m scripts.commands.reports.weekly_deck build --project my_new_project
python -m scripts.commands.reports.weekly_deck build --project my_new_project --weeks 2 --metric acc --cover-date today
```

Output goes to `05_results/weekly_decks/weekly_<YYYYMMDD>.pptx` (never
`09_report/`). The base template resolves `--template` >
`weekly_deck.template` in `config/workspace_profile.local.json` > the
gitignored `config/ppt_template_local.pptx` > a built-in fallback theme.

## Validation

Before sharing or committing a project harness, run:

```bash
python -m scripts.commands.projects.validate_project --project my_new_project
```

Validation checks that required working artifacts exist, including data roots,
working result rows, experiment journal files, and terminology. For non-template
projects it also warns when succeeded experiment runs have no working result rows,
when working result rows have no journal explanation rows, or when data
roots/terminology still contain starter placeholders. It also checks that
`09_report/` artifact folders exist and, once a project reaches later stages,
warns when final report artifacts appear older than the working result,
interpretation, or writing files.
It also checks preregistration, reproducibility manifests, statistical
robustness files, reviewer attack matrix, final report CSV headers,
claim/experiment/baseline cross-references, baseline source structure reports,
agent-to-agent messages, and parallel agent batch manifests under
`state/orchestrator_prompts/parallel_batches/`. Command queue validation also
checks that `depends_on` references known command ids and that the dependency
graph has no duplicate dependencies, self-dependencies, or cycles before agents
are parallelized.

Optionally compile the LaTeX paper when `xelatex`, `latexmk`, or `pdflatex` is installed:

```bash
python -m scripts.commands.projects.validate_project --project my_new_project --check-paper-build
```

For the full harness verification suite:

```bash
python -m scripts.commands.release.verify_harness --project template
```
