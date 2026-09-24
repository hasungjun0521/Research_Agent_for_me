# Code Workspace

This folder holds the active research and experiment code for
`{{PROJECT_NAME}}`.

Use `04_code/` while methods are still being implemented, debugged, tested, or
changed for experiments. Do not use `09_report/` as the working experiment-code
area. After the code is stable and cleaned for sharing, export only the
reader-facing release subset to `09_report/src/`.

## Structure

- `src/`: reusable research source code and experiment implementation.
- `notebooks/`: exploratory notebooks or analysis notebooks used during
  development.
- `tests/`: tests and smoke checks for project code and baseline wrappers.
- `implementation_notes.md`: implementation decisions and run notes.
- `code_review.md`: review findings and technical debt.

## Code Principles

- Keep changes linked to experiment IDs.
- Prefer small, reviewable changes.
- Do not change metrics or baselines silently.
- Record commands in the relevant experiment run log.
- Keep reusable logic in `src/`; keep exploration in `notebooks/`.
- Before implementing baseline-related logic, read `08_baselines/`, especially
  `baseline_registry.json`, `structure_reports/`, and
  `code_structure_plan.md`.
- Use baseline adapters to match the project interface while preserving the
  original baseline behavior.
- When preparing a public/release artifact, copy or package only cleaned,
  documented, reviewer-facing code into `09_report/src/`; keep experimental
  scaffolding, debug scripts, raw notebooks, and failed attempts here.
