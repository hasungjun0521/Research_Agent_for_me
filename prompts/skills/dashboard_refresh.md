# Dashboard Refresh

Use this skill only when dashboard workflow is explicitly enabled for the
current project session.

## Goal

Keep the optional dashboard view grounded in the actual project files without
hand-editing JSON state.

## Required Command

From the repository root, refresh dashboard-derived inputs:

```bash
python -m scripts.commands.dashboard.dashboard_refresh --project <project>
```

This writes working/support summaries only. Add `--final-export` only when the
dashboard refresh should also update stable reader-facing `09_report` tables and
the final report index:

```bash
python -m scripts.commands.dashboard.dashboard_refresh --project <project> --final-export
```

Use check mode when diagnosing source coverage without writing generated files:

```bash
python -m scripts.commands.dashboard.dashboard_refresh --project <project> --check
```

## What The Hook Refreshes

- `05_results/claim_evidence_board.md`
- `07_reviews/research_audit.md`
- `09_report/results/claim_evidence_board.csv` only with `--final-export`
- `09_report/results/research_audit.csv` only with `--final-export`
- the generated block in `09_report/README.md` only with `--final-export`
- dashboard data-source coverage, matching `/api/status.data_sources`

## Operating Rules

- Do not hand-edit files under `state/*.json`; use the harness scripts that own
  those contracts.
- Keep `09_report/` for final reader-facing artifacts only.
- If results changed, run the refresh after the result-ingest or audit command,
  not before it.
- If the dashboard Console is running with `--enable-command-runner`, use the
  allowlisted `Refresh Dashboard Inputs` command instead of typing arbitrary
  shell text into the browser.
- After a substantial research pass, run project validation:

```bash
python -m scripts.commands.projects.validate_project --project <project> --strict
```
