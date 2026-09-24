# Experiment Journal

Append one row whenever experiment results are recorded. Keep this Markdown file
as the human-readable ledger and `experiment_journal.csv` as the structured
ledger for filtering, packaging, and later analysis.

| Updated At | Experiment | Rationale | Dataset | Method | Baseline | Result Summary | Result Analysis | Evidence | Caveat |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
|  | exp_001 |  |  |  |  | planned | analysis pending | 03_experiments/exp_001/analysis.md |  |

## Analysis Discipline

- After every completed experiment, explain why performance improved,
  regressed, or stayed flat.
- Separate confirmed causes from plausible hypotheses.
- Link to `03_experiments/<exp_id>/analysis.md`, run logs, data roots,
  baseline registry entries, and failure-case evidence.
- Keep `experiment_journal.md` and `experiment_journal.csv` synchronized through
  harness CLIs such as `result_ingest` and `progress_checkpoint`.
- Do not strengthen claims until the analysis explains the observed movement or
  records why the cause is still unknown.
