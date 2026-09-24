# ADR-005: Add Research Rigor Gates

## Status
Accepted

## Date
2026-05-10

## Context
The workspace now separates working evidence from final reader-facing artifacts. That makes outputs easier to inspect, but it does not by itself prevent weak research practice such as changing success criteria after results, omitting failed runs, losing environment details, or making claims before reviewer objections have been addressed.

## Decision
Add required research rigor gates to each template project:

- `03_experiments/exp_*/preregistration.md` records hypotheses, success criteria, failure criteria, metrics, baselines, planned analysis, confounders, and the decision rule before execution.
- `03_experiments/exp_*/reproducibility_manifest.json` records dataset, code, environment, seeds, commands, hardware, baseline links, evidence, and outputs.
- `05_results/statistical_robustness.md` records working uncertainty, sanity, data-quality, and failed-run checks.
- `07_reviews/reviewer_attack_matrix.md` maps claims to likely reviewer attacks, weakness, evidence, and response plans.
- `09_report/results/statistical_robustness.csv` stores final robustness rows for human inspection.

`scripts/commands/projects/validate_project.py --strict` checks that these files exist and have the expected structure. `--check-paper-build` optionally compiles `09_report/paper/main.tex` when a LaTeX engine is installed.

## Alternatives Considered

### Keep These As Informal Notes

Informal notes are flexible, but agents can skip them under time pressure. Required files make the checks visible in validation and migration.

### Store Everything In `09_report/`

This would make the final report folder noisy. The working gates belong in `03_experiments/`, `05_results/`, and `07_reviews/`; only final tables belong in `09_report/results/`.

### Require Full Paper Build By Default

This is useful on machines with LaTeX installed, but many environments do not have a TeX distribution. The build check is available through an explicit flag so normal validation remains lightweight.

## Consequences

- Claims are harder to strengthen without evidence.
- Experiments have a pre-result record of success and failure criteria.
- Reproducibility evidence is collected while the run is still fresh.
- Reviewer-risk work becomes visible before submission.
- Validation becomes stricter and will fail if required rigor artifacts are missing or malformed.
