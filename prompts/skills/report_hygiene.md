# Report Hygiene

Use this skill when validation says `09_report/` contains Markdown scratch
files or legacy report notes.

## Rule

`09_report/` is final-artifact-only. Keep final paper, cleaned release source,
final analysis scripts, final figures, and final result tables there. Move
working notes and experimental artifacts to the relevant folder:

- `04_code/` for active experiment code, tests, debug scripts, notebooks, and
  implementation notes.
- `05_results/` for analysis notes and result interpretation drafts.
- `07_reviews/` for reviewer risks, critiques, rebuttal notes, and audits.
- `08_baselines/` for baseline source notes and reproduction notes.
- `03_experiments/exp_*/` for experiment-local logs or diagnostics.

## Procedure

1. Run `python -m scripts.commands.projects.project_closeout --project <project>` and copy the
   `report_hygiene` issue paths.
2. Move each scratch Markdown file to the correct working folder. Preserve
   evidence; do not delete files unless the human explicitly asks.
3. Leave `09_report/README.md` as the only Markdown file at report root unless a
   specific final artifact contract says otherwise.
4. Refresh:

```bash
python -m scripts.commands.projects.validate_project --project <project> --strict
```

Dashboard refresh is not part of this default skill. Use
`prompts/skills/dashboard_refresh.md` only when dashboard mode is explicitly
enabled.
