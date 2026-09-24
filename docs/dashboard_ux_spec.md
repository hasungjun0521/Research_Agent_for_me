# Dashboard UX Spec

This is a historical/parked support spec for the optional dashboard. It does
not define the default research workflow. The default workflow is Claude/Codex
native continuation from project files plus harness CLIs.

## Objective

If the dashboard is explicitly restored or maintained, keep it as a practical
research operations console. The primary user is a researcher running
multi-agent research loops who wants a browser inspection surface for what is
happening, what evidence exists, what is blocked, and what to run next without
reading JSON.

## Information Architecture

- `Overview`: decision surface for humans. Shows current instruction summary,
  active work, completed work, visible evidence, blockers, research readiness,
  phase progress, a run-readiness verdict, and next prompt.
- `Work`: command and agent operations. Shows command board, handoff timeline,
  messages/blockers, blocker triage, Ralph loops, experiments, GPU queue, and
  registries.
- `Results`: final-artifact room. Shows `09_report` snapshot, result-table
  previews, evidence map, experiment comparison, artifacts, loop results, and
  experiment outcomes.
- `Console`: safe terminal-like runbook. Shows next prompt, copy-ready workflow
  commands, Ralph loop command templates, and recent event stream. It does not
  execute shell commands from the browser.
- `Debug`: raw state and maintenance details. Shows votes, sessions, events,
  pattern memory, raw snippets, project snapshot, Data Coverage, validation
  warnings, and agent cards.

## Data Sources

- `/api/status` in server mode.
- Browser folder selection in direct-file mode.
- Existing state files under `projects/<name>/state/`.
- `09_report/README.md` and `09_report/results/*.csv` through
  `scripts/commands/reports/report_snapshot.py`.
- `scripts/commands/dashboard/dashboard_sources.py`, exposed as `/api/status.data_sources`, for a
  source manifest covering state files, events, sessions, checkpoints,
  phase gates, resource ledger entries, experiment run states, report tables,
  and final artifacts.
- `scripts/commands/dashboard/dashboard_refresh.py`, exposed as an allowlisted Console command in
  server mode, for refreshing claim/evidence, research audit, source
  credibility audit, experiment diagnosis, phase-gate audit, resource ledger,
  report-index, and source manifest inputs after research work changes.
- `scripts/commands/projects/project_closeout.py`, exposed as an allowlisted Console command in
  server mode, for writing a closeout audit that routes blockers to
  project-local skills.
- `scripts/commands/release/workspace_profile.py`, exposed through `/api/status.workspace_profile`
  in server mode, for dashboard summary language, labels, and GPU profile
  metadata.
- `scripts/commands/dashboard/dashboard_command_runner.py`, exposed through an opt-in
  `/api/run-command` server endpoint, for allowlisted validation and report
  refresh commands.

## Boundaries

- Keep the dashboard optional and parked unless a user explicitly asks for it.
- Always preserve direct file-open mode.
- Always preserve static no-build dashboard assets.
- Always escape dashboard-rendered project data.
- Never run arbitrary local commands from the dashboard browser UI.
- Never enable the command runner by default; require
  `--enable-command-runner`, keep the command list allowlisted, and execute
  argv lists rather than shell text.
- Never move raw state, events, votes, sessions, or debug details into the
  default `Overview`.
- Never show low-level harness/source health as a top-level researcher panel;
  keep it in Debug as Data Coverage.
- Never put scratch/debug outputs into `09_report/`.

## Success Criteria

- The first screen answers the five required human questions without JSON.
- Results remain visible when `loop_summary` is sparse.
- Result tables show row counts and a small preview.
- The console gives researchers the next prompt and safe copy-ready commands.
- With explicit opt-in, the console can execute allowlisted validation commands
  and show stdout/stderr in a terminal-like pane.
- Workflow audit checks critical dashboard wiring.
- Smoke tests cover summary, result, console, and view-hiding behavior.
