# ADR-003: Add A Reader-Facing Report Folder

## Status
Accepted

## Date
2026-05-10

## Context
The workspace separates research work across folders for brief, literature, planning, experiments, code, results, writing, reviews, and baselines. That structure is useful for agents and reproducibility, but it makes the human-visible output feel fragmented. A user should not need to inspect every working folder to understand the current method, writing state, and analysis results.

## Decision
Each project includes `09_report/` as the single reader-facing artifact folder. It contains typed artifact subfolders:

- `src/` for source code intended to accompany the report.
- `paper/` for LaTeX paper files, starting with `main.tex`.
- `analysis/` for report-level analysis code.
- `figures/` for final images.
- `results/` for final experiment result tables.

Working folders remain the source of evidence:

- `03_experiments/` stores per-experiment configs, logs, raw outputs, and analyses.
- `05_results/` stores aggregate result work products, tables, figures, failures, and interpretation.
- `06_writing/` stores section drafts and writing scratch space.

Agents that materially change working evidence should first update the relevant
working folders. They update `09_report/` only when the code, paper text,
analysis code, figures, or result tables are stable enough to be
reader-facing. Ad hoc markdown notes and scratch outputs stay in the working
folders.

## Alternatives Considered

### Put All Human Output In `05_results/`

This would centralize analysis, but it would mix method and writing with result-specific artifacts. It also does not solve the problem of paper text living separately in `06_writing/`.

### Replace `05_results/` And `06_writing/` With One Folder

This reduces visible folders, but it removes useful working separation for agents. Raw evidence, scratch analysis, and polished reader-facing text have different lifecycles.

### Use Only The Dashboard

The dashboard is good for loop status and next prompts, but it is not a durable report surface for method, writing, and analysis.

## Consequences

- Humans can start in `09_report/` and find only final/report artifacts.
- Existing folders remain useful for traceability and agent specialization.
- Agents must keep working evidence synchronized immediately and export to the
  report layer when conclusions are stable enough for readers.
- Some duplication is intentional; `09_report/` is the final artifact layer, while the other folders are source evidence and work history.
