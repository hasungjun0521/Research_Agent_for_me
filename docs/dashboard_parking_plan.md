# Dashboard Parking Plan

The dashboard is preserved as optional support tooling, but it is no longer the
primary workflow for this workspace.

## Current Status

- Primary workflow: ask Claude, Codex, or another coding agent to work from
  project files and use the harness CLIs.
- Dashboard workflow: optional inspection surface for state files.
- Command runner: optional and disabled unless the dashboard server starts with
  `--enable-command-runner`.

## Why It Is Parked

In normal use, the researcher asks an agent to continue a project, run an
experiment, update evidence, or perform closeout. The agent runs Python harness
commands and updates files. Opening a browser UI added extra ceremony without
being the main control path.

The dashboard remains useful for later inspection, demos, or status monitoring,
so the files should be kept intact unless a future cleanup explicitly removes
them.

## Preserved Files

Dashboard assets:

- `dashboard/README.md`
- `dashboard/index.html`
- `dashboard/styles.css`
- `dashboard/app.js`
- `dashboard/core.js`

Dashboard server and helpers:

- `scripts/commands/agents/agent_dashboard.py`
- `scripts/commands/dashboard/dashboard_refresh.py`
- `scripts/commands/dashboard/dashboard_sources.py`
- `scripts/commands/dashboard/dashboard_command_runner.py`

Design and documentation:

- `docs/dashboard_ux_spec.md`
- Dashboard sections in `ARCHITECTURE.md`
- Dashboard commands in `scripts/README.md`

Project state still read by the dashboard:

- `state/agent_status.json`
- `state/agent_events.jsonl`
- `state/command_queue.json`
- `state/loop_summary.json`
- `state/agent_messages.json`
- `state/agent_votes.json`
- `state/pattern_memory.json`
- `state/sessions/`
- Experiment `run_state.json` files

## Restore Procedure

From the repository root:

```bash
python -m scripts.commands.dashboard.dashboard_refresh --project <project>
python -m scripts.commands.agents.agent_dashboard --project <project>
```

Open the printed URL, usually:

```text
http://127.0.0.1:8765/?project=<project>
```

If dashboard buttons need to run allowlisted commands:

```bash
python -m scripts.commands.agents.agent_dashboard --project <project> --enable-command-runner
```

For network sharing, use a token and a trusted network boundary:

```bash
python -m scripts.commands.agents.agent_dashboard --project <project> --host 0.0.0.0 --port 8766 --share-token "$(python -c 'import secrets; print(secrets.token_urlsafe(18))')"
```

Do not expose the dashboard directly to the public internet.

## Future Removal Checklist

If the dashboard is removed later, first preserve:

- A file inventory of the removed dashboard assets.
- The last known `/api/status` response shape.
- A migration note for any state fields that existed only for dashboard
  rendering.
- A replacement user workflow in `README.md`.
- Any release-check changes needed after removing dashboard files from
  `project.yaml`.

Until that cleanup happens, keep dashboard files tracked and treat them as
parked optional tooling.
