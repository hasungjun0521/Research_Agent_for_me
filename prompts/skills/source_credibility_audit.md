# Source Credibility Audit

Use this skill before strengthening literature-backed claims, writing related
work, or publishing a report.

## Procedure

```bash
python -m scripts.commands.reports.source_credibility_audit --project <project> --write-report
python -m scripts.commands.reports.paper_claim_linter --project <project> --strict
```

## Required Surfaces

- `01_literature/papers.bib`
- `01_literature/paper_notes/`
- Writing and result files that cite sources.
- `09_report/results/claim_evidence.csv`

## Guardrails

- Do not invent citations.
- Do not claim source support unless the citation key resolves and the claim row
  points to evidence.
- If a citation is missing, block claim strengthening until the source is
  registered or the claim is softened.
