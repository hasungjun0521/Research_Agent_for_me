# Optional Agent Status Dashboard

This folder contains a parked, optional browser dashboard for checking project
state files. It is not the default research workflow. Normal use is to ask
Claude, Codex, or another coding agent to continue from file state and use the
harness CLIs directly.

Use the dashboard only when you explicitly want a browser inspection surface or
demo console. See `docs/dashboard_parking_plan.md` for the current support
policy.

Open:

`dashboard/index.html`

Then select a project folder such as:

`projects/my_new_project/`

This direct-file mode is a snapshot. Browser file selection does not watch local files, so reload the folder to see later changes.

The dashboard is split into:

- `index.html`: markup and stable DOM ids.
- `styles.css`: visual layout and responsive rules.
- `core.js`: shared dashboard constants and pure helper functions.
- `app.js`: file parsing, API polling, filtering, rendering, copy actions, and
  detail drawer behavior.

The dashboard reads these files from the selected folder:

- `state/agent_status.json`
- `state/agent_events.jsonl`
- `state/agent_messages.json`
- `state/command_queue.json`
- `state/gpu_experiment_queue.json`
- `state/current_state.md`
- `state/next_actions.md`
- `09_report/README.md`
- `09_report/results/*.csv`
- `03_experiments/dataset_registry.json`
- `03_experiments/metric_registry.json`
- `03_experiments/*/run_state.json`
- `state/resource_ledger.json`
- `state/phase_gates.json`
- `state/checkpoints/*.json`

It calculates active agents from agents whose status is `running`.

The dashboard-generated `Next Prompt` includes the filesystem boundary: the next agent must stay inside the active project folder and must not delete, move, overwrite, or recursively clean directories outside it.

When served through `scripts/commands/agents/agent_dashboard.py`, dashboard
summary language and top-card labels come from
`config/workspace_profile.local.json`. Direct file-open mode falls back to the
public workspace profile defaults.

The UI is intentionally split into five views:

- `Overview`: the default, human-facing operations console. It shows only what
  is happening now, what completed, which results/artifacts exist, what is
  blocked, what command/prompt should run next, research readiness, and the
  current phase in the research workflow. It also includes a decision-grade
  `Run Readiness Gate` that summarizes whether the next run is ready, blocked,
  missing sources, or waiting for a selected command.
- `Work`: the operator view for active and completed commands, blockers, Ralph
  runs, command-board lanes, pipeline/handoff state, experiments, GPU queue,
  registries, and blocker triage by workflow/research/data/experiment/writing
  category.
- `Results`: the artifact view for the loop result summary, `09_report`
  snapshot, result table previews, evidence map, experiment comparison table,
  final report files, and experiment outcomes.
- `Console`: a terminal-like but safe runbook for the next prompt, recent event
  stream, validation commands, report refresh, orchestrator prompt generation,
  and Ralph loop command templates. It is copy-ready and does not execute shell
  commands from the browser unless the local server is explicitly started with
  `--enable-command-runner`, in which case only allowlisted harness commands can
  be run.
- `Debug`: source snippets, votes, sessions, event history, pattern memory,
  agent cards, dashboard data coverage, state validation warnings, and
  copy-ready CLI helpers.

`Pipeline & Handoff` now lives in `Work`, not the default overview. It is a
compact timeline rather than a full graph and surfaces the selected next action,
open/running commands, recent terminal events, Ralph runs, owner routing, and
open vote count so the user can inspect workflow movement when needed.

Reader-facing artifacts live under `09_report/`:

- `src/`: report source code.
- `paper/`: LaTeX files.
- `analysis/`: report analysis code.
- `figures/`: final images.
- `results/`: final result tables.

The dashboard now treats `09_report/README.md` and `09_report/results/*.csv`
as first-class UI inputs. Even when `state/loop_summary.json` has not yet
recorded a result entry, the `Report Results` panel and the Korean result
summary show final result tables, row counts, and recent report files from
`09_report/`. Server mode also includes a small CSV preview for each result
table so researchers can inspect columns and the first rows without opening raw
files.

Research rigor gates live in the working folders:

- `03_experiments/exp_*/preregistration.md`
- `03_experiments/exp_*/reproducibility_manifest.json`
- `05_results/statistical_robustness.md`
- `07_reviews/reviewer_attack_matrix.md`

Next-action cards prefer human-readable fields from `state/command_queue.json` and `state/loop_summary.json`:

- `display_summary`: what the task means.
- `why_now`: why it is next.
- `done_when`: what completion looks like.

File paths remain available through Inspect, but they should not be the only explanation shown to the user.
Agent Messages shows open agent-to-agent requests from `state/agent_messages.json`; unresolved high-priority blockers appear in the Work blockers view, while low-level state validation details stay in Debug.

For automatic file reading through a local server, use:

```bash
python -m scripts.commands.agents.agent_dashboard --project my_new_project
```

Server mode reads the latest project files through `/api/status` and the browser refreshes the view every 5 seconds. The API includes a `data_sources` manifest from `scripts/commands/dashboard/dashboard_sources.py`, so Debug can show which state/report/event/checkpoint/phase/resource sources were loaded, which required sources are missing, and when each source last changed. The dashboard still only reflects what is written to the project state files; running an agent does not appear as running unless that agent updates `state/agent_status.json` through `scripts/commands/agents/agent_status.py` or records hook activity with status sync. When no agent is marked `running`, the live panel falls back only to non-terminal hook activity from the last 15 minutes; `done`, `finish`, and other terminal events stay in the event timeline instead of lingering as live work. Hook-driven `status=done` syncs should include `--command-id` or use `scripts/commands/agents/agent_status.py finish` so completion stays tied to command ownership. After research work changes evidence, blockers, costs, phase status, or final result tables, run `python -m scripts.commands.dashboard.dashboard_refresh --project my_new_project` to refresh every derived dashboard input in one command.
To enable the safe web runner for validation/report-refresh commands:

```bash
python -m scripts.commands.agents.agent_dashboard --project my_new_project --enable-command-runner
```

The runner is allowlist-only through `scripts/commands/dashboard/dashboard_command_runner.py`; it
does not run arbitrary shell text and does not use `shell=True`. When enabled,
the Console can run the allowlisted `Refresh Dashboard Inputs` hook, which maps
to `scripts/commands/dashboard/dashboard_refresh.py`, and the `Project Closeout Audit` hook, which
maps to `scripts/commands/projects/project_closeout.py --refresh-dashboard --write-report`.
The top Korean work summary also reads terminal `agent_events.jsonl` entries as
a fallback. This means a recent `finish`/`done` event can still explain what
just completed even if `loop_summary.completed_commands` has not been filled
yet.

Use the harness CLIs instead of hand-editing JSON:

```bash
python -m scripts.commands.agents.agent_status start --project my_new_project --agent code_agent --task "Run exp_001"
python -m scripts.commands.agents.agent_events record --project my_new_project --agent code_agent --task "Inspecting run logs" --note "Hook activity update" --sync-status
python -m scripts.commands.review.command_queue update --project my_new_project --id cmd_001 --status "in progress"
python -m scripts.commands.experiments.run_state heartbeat --project my_new_project --exp-id exp_001 --note "still running"
python -m scripts.commands.experiments.gpu_monitor --project my_new_project
python -m scripts.commands.agents.agent_orchestrator dispatch --project my_new_project --id cmd_001
python -m scripts.commands.projects.validate_project --project my_new_project
```
