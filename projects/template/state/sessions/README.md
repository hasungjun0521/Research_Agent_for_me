# Session Workspaces

Use `python -m scripts.commands.review.session_state start --project {{PROJECT_NAME}} --goal "..."`
to create isolated loop/session folders under this directory.

Each session folder contains:

- `session.json` for structured lifecycle metadata.
- `scratchpad.md` for loop-local notes that can be rewritten safely.
- `plans/` for plan files.
- `results/` for session-local result summaries.
- `artifacts/` for non-final supporting files.

The shared `state/sessions/progress_log.md` file is written by
`python -m scripts.commands.review.progress_checkpoint record` as an append-only
timeline of meaningful mid-pass updates.

Do not put final human-facing artifacts here. Final artifacts belong in
`09_report/`.
