# Claim Graph

Use to connect paper claims to experiment evidence before strengthening claims.

## When To Use

- Experiment results or journal analysis changed.
- A writing agent wants to claim improvement, robustness, or limitation.
- You need to identify claims without analysis or evidence edges.

## Agent Workflow

1. Build the working claim graph from result CSVs, journal rows, and claim evidence.
2. Inspect claims without experiment or analysis edges.
3. Keep weak claims marked as weak until evidence and causal analysis exist.
4. Export final claim evidence only after working evidence is stable.

## Outputs

- `05_results/claim_graph.md`
- `05_results/claim_graph.json`
