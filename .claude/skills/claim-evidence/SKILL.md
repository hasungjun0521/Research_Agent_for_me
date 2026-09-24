---
name: claim-evidence
description: Refresh and audit the claim/evidence surfaces before strengthening paper claims from experiment results. Use when the user wants to update the claim graph, build the claim-evidence board, lint paper claims against result rows, or asks "is this claim supported". Wraps reports.claim_graph, reports.claim_evidence_board, reports.paper_claim_linter, and reports.data_metric_audit.
---

# Claim & Result Evidence

Entrypoint for connecting paper claims to experiment evidence.
Source runbooks: `prompts/skills/claim_graph.md`,
`prompts/skills/claim_and_result_evidence.md`,
`prompts/skills/claim_table_backfill.md`.

## When to use

- Before strengthening any paper claim from experiment results.
- After result ingest, when the working claim graph or board is stale.
- When claim rows are missing, disconnected, or contradicted by results.
- Before submission-style writing or reviewer-response work.

## Workflow

1. Refresh the working claim graph first:
   ```bash
   python -m scripts.commands.reports.claim_graph --project <name> --write
   ```
2. Build the working claim-evidence board (working view; final export is
   opt-in):
   ```bash
   python -m scripts.commands.reports.claim_evidence_board build --project <name> --write
   ```
   Add `--final-export` only when the board is stable enough for
   `09_report/results/claim_evidence_board.csv`.
3. Lint paper text against result evidence:
   ```bash
   python -m scripts.commands.reports.paper_claim_linter --project <name> --strict
   ```
4. For dataset/metric provenance behind the claims:
   ```bash
   python -m scripts.commands.reports.data_metric_audit --project <name> --strict --write-report
   ```
5. Route gaps (missing claim rows, unsupported claims) back into the queue or
   `claim_table_backfill` runbook work instead of editing claims to fit.

## Guardrails

- Claims are untrusted until evidence paths exist; negative/failed results are
  evidence and must stay recorded.
- Working surfaces live in `05_results/`; `09_report/results/` updates only
  through explicit `--final-export`.
- Never hand-edit generated boards/graphs — rerun the commands.
