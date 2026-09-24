---
name: experiment-run
description: Plan and close out research experiments under projects/<name>/. Use BEFORE launching a new experiment family (build a smoke-first DAG with expected outputs, check procedures, and a safe parallel main-run group), and AFTER an experiment outcome is known (record result + why it improved/regressed/stayed flat so CSV, journal, analysis, run_state, artifacts, and data roots move together). Wraps experiment_planner and experiment_complete.
---

# Experiment Run (Plan → Complete)

Lifecycle entrypoint for experiment families. Source runbooks:
`prompts/skills/experiment_planning.md`, `prompts/skills/experiment_completion.md`,
`prompts/skills/experiment_smoke_first.md`.

## Plan (before launching a family)

Define claim, hypothesis, dataset, metric, method, baseline, and seeds. Plan the
smallest useful **smoke node first**, then put independent main runs in one
parallel group behind the smoke dependency. Record expected output and check
procedure for every node.

```bash
python -m scripts.commands.experiments.experiment_planner --project <project>
```

Outputs: `02_planning/experiment_plan.md`, `03_experiments/experiment_dag.json`,
`03_experiments/<exp_id>/preregistration.md`.

Queue GPU jobs only after the DAG is clear and smoke-first rules are satisfied —
hand off to the `gpu-dispatch` skill for that.

## Complete (when an outcome is known)

Always analyze **why** performance improved, regressed, or stayed flat. If the
cause is uncertain, record the strongest hypothesis and what would falsify it.

```bash
python -m scripts.commands.experiments.experiment_complete \
  --project <project> --exp-id <exp_id> --status succeeded \
  --summary "<observed result>" \
  --result-analysis "<why performance improved, regressed, or stayed flat>" \
  --evidence <project-relative-evidence-path> \
  --artifact metrics:metrics=<project-relative-metrics-path> \
  --data-root <dataset_id>=<root_or_uri>
```

For failed/blocked runs, keep the same pattern with the real status and explain
the likely failure cause + what follow-up would distinguish hypotheses.

Durable outputs moved together: `05_results/experiment_results.csv`,
`05_results/experiment_journal.{md,csv}`, `03_experiments/<exp_id>/analysis.md`,
`03_experiments/<exp_id>/run_state.json`, `03_experiments/artifact_registry.csv`,
`03_experiments/data_roots.md`.

## Guardrails

- Smoke before main runs. Do not parallelize runs that write the same outputs.
- Scheduler completion ≠ research completion until this closeout records the
  result explanation and artifacts.
- Export reader-facing rows to `09_report/results/` only when the row is stable.
