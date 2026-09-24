# Research Agent Workspace

Claude Code compatibility lives in `CLAUDE.md`, which imports this file and adds
Claude-specific operating rules.

## Scope

This repository is a file-based harness for research workflows. Root-level work
maintains the harness itself. Project-local research work belongs under
`projects/<name>/`.

## Core Commands

- Compile scripts: `python -m compileall -q scripts`
- Workflow audit: `python -m scripts.commands.release.workflow_audit`
- Smoke test: `python -m scripts.commands.release.smoke_test`
- Template validation: `python -m scripts.commands.projects.validate_project --project template --strict`
- Full harness check: `python -m scripts.commands.release.verify_harness --project template --skip-paper-build`
- Release gate: `python -m scripts.commands.release.release_check --project template --version v8.0.0 --skip-paper-build --strict-template-state`

## Operating Rules

- Use harness CLIs instead of hand-editing project state JSON.
- At the start of a project-local continuation pass, prefer
  `python -m scripts.commands.projects.project_resume --project <name>` before
  selecting the next action.
- If project state looks stale, contradictory, hard to resume, or health/state
  doctor reports are older than recent project progress, use
  `python -m scripts.commands.projects.state_doctor --project <name> --write-report`
  and
  `python -m scripts.commands.projects.project_health --project <name> --write`
  instead of relying on the dashboard. Without `--write-report`, state doctor
  only prints findings and `state/state_doctor.md` stays stale.
- Treat `state/project_health.md` as the research progress health report and
  `state/state_doctor.md` as the file-state consistency diagnosis. They are
  working-state diagnostics, not final report artifacts or browser dashboard
  outputs.
- When both diagnostics need refresh, run state doctor first and project health
  second so health routing is based on the latest state diagnosis.
- When health/state doctor findings should become routed work, use their
  suggested-command dry-run preview first, then enqueue through the harness
  instead of hand-editing `state/command_queue.json`.
- When state doctor repair is needed, preview repairs before applying them
  unless the user explicitly asks to write immediately.
- When the user's idea is still rough, use
  `python -m scripts.commands.projects.brief_intake` to turn known fields into
  durable brief files and open questions.
- Keep machine-local settings in `config/workspace_profile.local.json`; do not
  put private paths, credentials, or lab-specific defaults in tracked files.
- Keep `projects/<name>/09_report/` final-artifact-facing. Scratch notes,
  intermediate diagnostics, and raw working logs belong in `00_brief/` through
  `08_baselines/`, `05_results/`, or `state/sessions/`.
- When project folder structure drifts (09_report bloat or junk, unexpected temporary
  files, unexpected top-level entries, never-generated diagnostics on idle
  projects), run
  `python -m scripts.commands.projects.project_hygiene --project <name>`
  (read-only by default) and resolve high findings before lower-priority work.
- State-file `.lock` sidecars are permanent coordination files. Do not delete
  them as debris; `project_hygiene --clean-locks` is a compatibility no-op.
- Keep active experiment and research code in `projects/<name>/04_code/`.
  Export cleaned, distribution-ready code to `09_report/src/` only after it is
  stable enough to share.
- Keep structured working result rows in
  `projects/<name>/05_results/experiment_results.csv`; export stable
  reader-facing rows to `projects/<name>/09_report/results/` only when final
  report evidence is ready.
- Ralph loop and dashboard are optional legacy/support tools. Do not use them as
  the default workflow unless the user explicitly asks.
- For GPU work, read the local rules from
  `config/workspace_profile.local.json`. Queue independent experiments first and
  use `python -m scripts.commands.experiments.gpu_scheduler dispatch` so
  available GPUs can run parallel jobs within the configured cap. Use
  `gpu_scheduler plan --json` and `plan_diagnostics` to explain excluded jobs
  before reducing a parallel batch.
- For multi-agent work, prefer
  `python -m scripts.commands.agents.agent_orchestrator parallel` when
  independent commands can go to different owner agents; never batch commands
  with unresolved dependencies, shared output paths, or unapproved vote gates.
  `python -m scripts.commands.agents.agent_orchestrator status-parallel` gives
  a read-only view of open/prepared work with exclusion diagnostics; explicit
  `parallel --id` requests fail with a concrete reason instead of silently
  skipping unsafe commands. For prompts already written in an earlier session
  whose commands are still `in progress`, use
  `python -m scripts.commands.agents.agent_orchestrator run-prepared`
  (`--dry-run` first, then `--group` or `--id` with the configured runner)
  instead of re-planning from `open` commands; it must fail rather than launch
  prompts with unresolved `depends_on`, and `--all-prepared` is only for
  intentionally running every prepared group. After reviewing worker outputs,
  close the scoped batch with
  `python -m scripts.commands.agents.agent_orchestrator finish-parallel`.
  Dispatched prompts default to the lean style (shared contracts referenced as
  read-on-demand pointers); pass `--prompt-style full` only when a runner
  cannot read repository files.
- Proactively look for multi-agent parallelization even when the user does not
  explicitly ask for it. Use this default for deep research, broad codebase
  analysis, multi-file implementation, independent experiment batches,
  baseline/code/result review splits, or any task where separate agents can
  work on disjoint files or questions. First identify the local critical-path
  work to do yourself, then delegate or dispatch only sidecar work that is
  independent. Do not parallelize tasks with unresolved dependencies, shared
  write paths, unapproved vote gates, or unclear ownership.
- If `config/workspace_profile.local.json` defines
  `agent_runners.default_profile` or a named runner profile, use
  `agent_orchestrator dispatch/parallel/run-prepared --runner-profile <name>`
  for non-interactive external agent execution instead of embedding ad hoc
  runner commands in chat.
- When queueing GPU jobs, record the command, scheduler job id after launch,
  expected output, and check procedure through `gpu_scheduler` metadata and
  `run_state.json`; do not leave those details only in chat.
- If a smoke test is CPU-heavy or long-running, queue it as a bounded GPU smoke
  job instead of saturating CPU resources.
- After an experiment completes, analyze why performance improved, regressed,
  or stayed flat. Keep the running ledger in
  `projects/<name>/05_results/experiment_journal.md` and
  `projects/<name>/05_results/experiment_journal.csv`. Prefer
  `python -m scripts.commands.experiments.experiment_complete` when the final
  outcome is known so result CSV, analysis notes, artifact registry, data roots,
  run_state, and agent status move together.
- Before launching a new experiment family, use
  `python -m scripts.commands.experiments.experiment_planner` to create a
  smoke-first DAG, identify independent parallel main runs, and record expected
  outputs/check procedures.
- Use `python -m scripts.commands.reports.claim_graph --project <name> --write`
  before strengthening paper claims from experiment results.
- Use `python -m scripts.commands.baselines.baseline_compare --project <name> --write`
  after baseline source snapshots are cloned so project code structure can
  follow inspected baseline patterns without modifying cloned repos.
- Use `python -m scripts.commands.review.agent_quality_audit --project <name> --write`
  when checking whether agent work left enough durable evidence for a fresh
  session to resume.
- Use `python -m scripts.commands.reports.weekly_deck build --project <name>` to
  render an image-first weekly development deck (KPI tiles, result charts,
  harvested figures) on the local PowerPoint template. Data collection is
  standard-library; preview with `--dry-run`. Rendering needs the optional `deck`
  extra (`pip install -e .[deck]`). Output goes to `05_results/weekly_decks/`,
  never `09_report/`. The base template is the gitignored
  `config/ppt_template_local.pptx` (override with `--template` or
  `weekly_deck.template` in `config/workspace_profile.local.json`).
- Keep experiment data roots and split/version identifiers in
  `projects/<name>/03_experiments/data_roots.md`.
- Keep paper terminology consistent through
  `projects/<name>/06_writing/terminology.md`.
- During long or multi-step research work, use
  `python -m scripts.commands.review.progress_checkpoint record` when a result,
  blocker, direction change, failed assumption, experiment outcome, memory note,
  or next action should be saved before the final response.
- Keep durable project lessons in `state/agent_memory.md` or the appropriate
  project report/planning file; keep transient run details in `state/sessions/`
  or experiment folders.
- Before ending a substantial project pass, refresh the visible handoff state:
  current status, next action, blockers, and evidence files should be findable
  from project state without chat history.
- If the current agent's five-hour or weekly usage remaining is below 5%, run
  `python -m scripts.commands.review.progress_checkpoint limit-handoff` with the
  observed remaining percentages. Summarize the current session, in-progress
  work, next actions, and durable memory before the session ends.
- If `config/workspace_profile.local.json` defines an official non-interactive
  JSON status command under `agent_limits.status_command`, prefer
  `python -m scripts.commands.review.progress_checkpoint check-limits` over
  interactive status probing. Never drive a nested interactive Codex/Claude TUI
  just to type `status`.
- For dashboard work, keep `dashboard/index.html` as markup, `dashboard/styles.css`
  as styling, and JavaScript in external dashboard scripts.
- For harness maintenance, stay inside this repository and touch only files
  required by the task. Do not delete or recursively clean directories outside
  the active scope.

## Structure

- `scripts/commands/`: grouped command implementations by workflow domain.
  Public commands run as modules, for example
  `python -m scripts.commands.projects.create_project`.
- `scripts/harness/`: shared harness code used by command implementations.
- `dashboard/`: static/server-backed dashboard assets.
- `prompts/`: agent, shared protocol, and project-skill prompt files.
- `docs/decisions/`: ADRs for durable design decisions.
- `review_forms/`: venue/year review forms and registry.
- `workflows/`: workflow definitions used by agents and humans.
- `config/`: public workspace profile template plus ignored local override.
