---
name: literature-review
description: Run or resume a durable literature pass for a project under projects/<name>/. Use when the user asks to survey related work, check novelty of a contribution, build the related-work matrix, or before strengthening literature-backed claims. Logs search rounds, keeps per-paper notes with verbatim quotes, and validates citation credibility — all file-based in 01_literature/.
---

# Literature Review

Entrypoint for literature work in this file-based research workspace.
Source runbook: `prompts/skills/literature_review.md` (follow it for the full
protocol). Related: `prompts/skills/source_credibility_audit.md`.

## When to use

- The user asks for related work, a literature survey, or a novelty check.
- A contribution candidate needs prior-art coverage before claims strengthen.
- A previous literature pass must be resumed without re-searching.

## Workflow

1. Read `00_brief/research_question.md` and `00_brief/contribution_candidates.md`
   first; review scope comes from the brief, not from the topic alone.
2. Log every search round in `01_literature/search_log.csv`
   (`round,date,query,source_type,hits,kept,notes`), including snowball rounds
   and rounds that found nothing. Stop on saturation and say so.
3. Per-paper notes go in `01_literature/paper_notes/<bibkey>.md` with verbatim
   quotes + locators and a stance per claim (supports / contradicts /
   method-only / background). Update `related_work_matrix.md`,
   `gap_analysis.md`, and `prior_limitations.md` as papers land.
4. Novelty check: every contribution candidate names its closest prior work
   and the one-sentence delta. No closest-prior row = unreviewed.
5. Validate citations before writing depends on them:
   ```bash
   python -m scripts.commands.reports.source_credibility_audit --project <name> --write-report
   ```
6. Persist direction changes with
   `python -m scripts.commands.review.progress_checkpoint record`.

## Guardrails

- Verbatim quotes with locators only; never paraphrase into a quote.
- Independent themes may be dispatched to parallel workers, but one owner per
  `search_log.csv` round.
- `01_literature/` is working evidence — never export it to `09_report/`.
