# Claim Table Backfill

Use this skill when stable reader-facing claim rows are ready to export, or
when project review shows `09_report/results/claim_evidence.csv` has no claim
rows or weak claim linkage.

## Procedure

1. Read only the files needed to identify the claim:
   `00_brief/research_question.md`, `02_planning/intake_summary.md`,
   `03_experiments/exp_*/preregistration.md`, and the relevant result tables.
2. Reuse stable `claim_id` values when they already exist in preregistration,
   result rows, paper text, or planning notes.
3. If the claim status is still unstable, update `05_results/interpretation.md`
   or `05_results/claim_evidence_board.md` and record the export blocker in
   `state/open_questions.md`.
4. When the claim status is stable enough for readers, update
   `09_report/results/claim_evidence.csv` with one row per claim:
   `claim_id`, `claim`, `status`, `evidence`, `experiments`, `robustness`,
   `caveat`, and `next_needed`.
5. If a result file exists, ingest it through `scripts/commands/experiments/result_ingest.py` rather
   than hand-copying experiment result rows.
6. Close out and validate:

```bash
python -m scripts.commands.projects.project_closeout --project <project> --write-report
python -m scripts.commands.projects.validate_project --project <project> --strict
```

Dashboard refresh is not part of this default skill. Use
`prompts/skills/dashboard_refresh.md` only when dashboard mode is explicitly
enabled.

## Guardrails

- Do not strengthen a claim because a metric looks good; status must match the
  evidence and caveat.
- If the evidence is incomplete, use `untested`, `partial`, or `unsupported`
  and fill `next_needed`.
- Do not move scratch notes into `09_report/`; only final tables and artifacts
  belong there.
