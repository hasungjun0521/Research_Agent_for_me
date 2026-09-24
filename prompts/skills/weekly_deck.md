# Weekly Dev Deck

Use to turn a project's last week of progress into an image-first PowerPoint deck
on the lab template.

## When To Use

- The user wants a weekly progress slide deck for a project.
- A recurring status update or lab meeting needs a one-glance summary.

## Agent Workflow

1. Preview the window with `--dry-run` to confirm collected KPIs, highlights,
   trend points, delta rows, figures, and next actions.
2. Build the deck:
   `python -m scripts.commands.reports.weekly_deck build --project <name>`.
3. Adjust the window (`--since/--until/--weeks`), metric (`--metric`), or cover
   date (`--cover-date week|today`) as needed.
4. Ensure the optional deck extra is installed (`pip install -e .[deck]`).

## Design Principles (image-first / glanceable)

- Takeaway-first: each content slide leads with a one-line conclusion.
- Numbers render as KPI stat tiles; results render as charts (trend + delta bars).
- Figures generated during the week are harvested onto an "이번 주 산출물" slide.
- ≤ 5 bullets per slide; ≥ ~50% of each content slide is visual.

## Outputs

- `05_results/weekly_decks/weekly_<YYYYMMDD>.pptx`
- `05_results/weekly_decks/_build/*.png` (intermediate visuals)

## Notes

- Base template: `config/ppt_template_local.pptx` (machine-local, gitignored).
  Override with `--template` or `weekly_deck.template` in
  `config/workspace_profile.local.json`.
- Falls back to a built-in theme when no template is available.
- Data collection uses only the standard library, so `--dry-run` works without
  the optional extra installed.
