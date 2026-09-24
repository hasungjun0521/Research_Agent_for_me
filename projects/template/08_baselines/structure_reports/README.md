# Baseline Structure Reports

Store generated source-structure summaries from `scripts/commands/baselines/baseline_intake.py`.

Each baseline with cloned source should have:

- `<baseline_id>.json`: machine-readable detected structure, entry points, configs, and score.
- `<baseline_id>.md`: human-readable source map and adapter plan.

Use these reports before creating adapters or copying ideas into project code.

Use the reports to update `08_baselines/code_structure_plan.md` before
structuring substantial code in `04_code/src/`. The plan should explain which
baseline repo conventions are copied, adapted, or rejected.
