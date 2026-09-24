# Statistical Robustness

Use this file for working robustness checks. Keep intermediate robustness notes,
failed-run accounting, and caveats here. Export only finalized table rows to
`09_report/results/statistical_robustness.csv` when the result is stable enough
for the reader-facing report.

## Required Checks

| Check | Purpose | Required Before Claim? | Status |
| --- | --- | --- | --- |
| Seed variance | Estimate run-to-run stability. | yes | planned |
| Confidence interval or bootstrap | Show uncertainty around the metric. | yes | planned |
| Baseline sanity check | Confirm baseline output is valid and comparable. | yes | planned |
| Data leakage check | Confirm evaluation data were not exposed to training or tuning. | yes | planned |
| Failed-run accounting | Preserve null, failed, and excluded runs. | yes | planned |

## Robustness Table

| Experiment | Check | Metric | Value | Status | Evidence | Caveat |
| --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  | planned |  |  |

## Data Quality Notes

- Missing runs:
- Excluded runs and reason:
- Suspicious logs:
- Known measurement limitations:

## Claim Impact

State how the robustness checks affect working claim interpretation. Export the
final claim status to `09_report/results/claim_evidence.csv` only after the
analysis is stable.
