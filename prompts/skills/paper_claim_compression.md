# Paper Claim Compression Skill

Use this when writing, interpreting, or reviewing claims.

## Procedure

1. Assign or reuse stable `claim_id` values.
2. Compress each claim to one sentence.
3. Link each claim to experiment IDs, baseline IDs, robustness checks, caveats, and next evidence needs.
4. If evidence is weak, reduce the claim strength instead of adding prose.
5. Update the working interpretation or claim board first. Export
   `09_report/results/claim_evidence.csv` only when the compressed claim is
   stable enough to be reader-facing.

## Output

Use this compact format:

| Claim ID | Claim | Evidence | Caveat | Next Needed |
| --- | --- | --- | --- | --- |
