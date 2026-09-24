# Experiment Planning

Use before launching a new experiment family.

## When To Use

- A claim needs experimental evidence.
- Several seeds, ablations, or methods can run independently after a smoke test.
- GPU capacity should be used in parallel without ad hoc launch commands.

## Agent Workflow

1. Define claim, hypothesis, dataset, metric, method, baseline, and seeds.
2. Plan the smallest useful smoke node first.
3. Put independent main runs in one parallel group after the smoke dependency.
4. Record expected output and check procedure for every node.
5. Queue GPU jobs only after the DAG is clear and smoke-first rules are satisfied.

## Outputs

- `02_planning/experiment_plan.md`
- `03_experiments/experiment_dag.json`
- `03_experiments/<exp_id>/preregistration.md`
