# Claim And Result Evidence

Use this when experiment outputs should affect paper claims.

1. Register dataset and metric IDs before ingesting result rows, and keep the
   matching data root/split/version row in `03_experiments/data_roots.md`.
2. Ingest metric outputs:
   `python -m scripts.commands.experiments.result_ingest ingest --project <project> --exp-id <exp_id> --input <metrics.json> --claim-id <claim_id> --dataset <dataset_id> --method <method>`
   This writes working rows to `05_results/experiment_results.csv`; add
   `--final-export` only when the row is stable enough for
   `09_report/results/experiment_results.csv`.
3. Ingest robustness checks when available:
   `python -m scripts.commands.experiments.result_ingest robustness --project <project> --exp-id <exp_id> --input <robustness.json> --claim-id <claim_id>`
   This writes working robustness notes to `05_results/statistical_robustness.md`;
   add `--final-export` only when the row is stable enough for
   `09_report/results/statistical_robustness.csv`.
4. Audit provenance. This checks dataset/metric registries, result rows, and
   `03_experiments/data_roots.md`:
   `python -m scripts.commands.reports.data_metric_audit --project <project> --strict --write-report`
5. Lint paper claims:
   `python -m scripts.commands.reports.paper_claim_linter --project <project> --strict`

Do not strengthen a paper claim until the audit and linter pass or the caveat is explicitly recorded.
