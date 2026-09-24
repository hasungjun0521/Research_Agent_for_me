# Literature Review

Use when scoping, running, or resuming a literature pass for a project:
search rounds, paper notes, the related-work matrix, and novelty checks
before research claims strengthen.

## Goal

Leave literature evidence durable and machine-checkable in `01_literature/`
so a fresh session can resume the review without re-searching, and so claims
never outrun what the curated literature supports.

## Workflow

1. Scope from the brief first. Read `00_brief/research_question.md`,
   `00_brief/contribution_candidates.md`, and open questions before searching.
   Each contribution candidate needs prior-art coverage, not just topically
   similar papers.
2. Log search rounds durably. Record each round (date, query, source, hits
   kept) in `01_literature/search_log.csv` with columns
   `round,date,query,source_type,hits,kept,notes`. Include snowball rounds
   (references and citers of confirmed-relevant seeds) as
   `source_type=snowball_refs` / `snowball_citers`. Stop expanding when a
   round adds no new relevant papers (saturation), and say so in `notes`.
3. Keep one note file per paper under `01_literature/paper_notes/` with the
   bib key as the filename, verbatim quotes with locators (section/page) for
   anything a claim may later rest on, and an explicit stance per project
   claim: supports / contradicts / method-only / background.
4. Update `01_literature/related_work_matrix.md` (and its thematic clusters)
   and `01_literature/gap_analysis.md` / `prior_limitations.md` as papers
   land. The matrix row is the contract: problem, method, strength,
   limitation, relevance.
5. Cross-check novelty before strengthening claims. For each entry in
   `00_brief/contribution_candidates.md`, name the closest prior work from
   the matrix and state the delta in one sentence. A contribution with no
   closest-prior-work row is unreviewed, not novel.
6. Validate citation credibility before claims move into writing:
   ```bash
   python -m scripts.commands.reports.source_credibility_audit --project <name> --write-report
   ```
   Resolve placeholder bib entries and unmatched citations before
   `06_writing/` work depends on them.
7. Checkpoint findings with
   `python -m scripts.commands.review.progress_checkpoint record` when a
   round changes direction (gap closed, contribution scooped, new baseline
   found) so the result survives the session.

## Parallelization

Literature work splits cleanly: independent themes, baselines, or
contribution candidates can be dispatched as separate worker passes through
the command queue / orchestrator, each owning disjoint matrix rows and note
files. Keep `search_log.csv` updates in one owner per round to avoid
conflicting appends.

## Guardrails

- Quotes must be verbatim with locators; paraphrase drifts into fabrication.
- Negative search results are evidence — log rounds that found nothing.
- Do not edit cloned baseline sources while reading them; notes go in
  `01_literature/`, adapters in `08_baselines/`.
- `01_literature/` is working evidence, never a `09_report/` artifact.
