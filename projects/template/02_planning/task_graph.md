# Task Graph

Use this file to show dependencies between research tasks. Keep it simple and readable.

## Dependency Table

| Task ID | Task | Depends On | Owner Agent | Output | Status |
| --- | --- | --- | --- | --- | --- |
| T1 | Refine research motivation | None | motivation_planner | `00_brief/motivation.md` | not started |
| T2 | Review core prior work | T1 | literature_reviewer | `01_literature/related_work_matrix.md` | not started |
| T3 | Design minimum viable experiment | T2 | experiment_designer | `03_experiments/experiment_registry.yaml`, `03_experiments/exp_001/preregistration.md` | not started |
| T4 | Implement experiment code | T3 | code_agent | `04_code/src/`, `03_experiments/exp_001/reproducibility_manifest.json` | not started |
| T5 | Analyze results | T4 | data_analyst | `05_results/aggregate_results.md`, `05_results/statistical_robustness.md`, `05_results/tables/` | not started |
| T6 | Interpret evidence | T5 | result_interpreter | `05_results/interpretation.md`, `05_results/claim_evidence_board.md` | not started |
| T7 | Draft paper sections | T6 | writing_agent | `06_writing/draft.md` | not started |
| T8 | Export final report/release artifacts | T7 | writing_agent/code_agent | `09_report/paper/main.tex`, `09_report/results/`, `09_report/src/` | not started |
| T9 | Critique and revise | T8 | critic/director | `07_reviews/reviewer_attack_matrix.md`, `07_reviews/revision_plan.md` | not started |

## Current Critical Path

State the smallest sequence of tasks required to answer the main research question.
