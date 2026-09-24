---
name: weekly-deck
description: Build an image-first weekly development deck (PowerPoint) for a project — KPI tiles, result trend/delta charts, and harvested figures from the last week of progress. Use when the user wants a weekly progress deck, lab-meeting slides, or a glanceable status summary. Wraps reports.weekly_deck.
---

# Weekly Dev Deck

Entrypoint for weekly progress decks.
Source runbook: `prompts/skills/weekly_deck.md`.

## When to use

- The user wants a weekly progress slide deck for a project.
- A recurring status update or lab meeting needs a one-glance summary.

## Workflow

1. Preview what the week's data supports (stdlib-only, no extra deps):
   ```bash
   python -m scripts.commands.reports.weekly_deck build --project <name> --dry-run
   ```
   Confirm KPIs, highlights, trend points, delta rows, figures, next actions.
2. Build the deck (needs the optional `deck` extra —
   `pip install -e .[deck]` for python-pptx + matplotlib):
   ```bash
   python -m scripts.commands.reports.weekly_deck build --project <name>
   ```
3. Adjust as needed: window `--since/--until/--weeks`, metric `--metric`,
   cover `--cover-date week|today`, figures `--max-figures`, title `--title`.

## Outputs

- `projects/<name>/05_results/weekly_decks/weekly_<YYYYMMDD>.pptx`
- `05_results/weekly_decks/_build/*.png` (intermediate visuals)

## Guardrails

- Decks are working artifacts in `05_results/`, never `09_report/`.
- The base template `config/ppt_template_local.pptx` is machine-local and
  gitignored; override via `--template` or `weekly_deck.template` in
  `config/workspace_profile.local.json`. Without a template the built-in
  fallback theme is used.
- Do not generate test decks inside `projects/template/`; use a scratch
  project copy instead.
