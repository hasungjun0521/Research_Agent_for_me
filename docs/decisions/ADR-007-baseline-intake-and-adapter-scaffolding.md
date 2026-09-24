# ADR-007: Baseline Intake and Adapter Scaffolding

## Status

Accepted

## Context

Baseline papers often come with official or third-party repositories. If agents reimplement those baselines from memory, comparison claims become hard to trust and reviewer attacks become likely. The harness needs a repeatable path from paper list to source clone, source inspection, adapter plan, and experiment-ready registry metadata.

## Decision

Add `scripts/commands/baselines/baseline_intake.py` as the baseline intake workflow.

The workflow:

1. Reads JSON, CSV, TSV, or text manifests of baseline papers.
2. Registers every baseline in `08_baselines/baseline_registry.json`.
3. Clones available repos into `08_baselines/source_snapshots/<baseline_id>/`.
4. Inspects source structure and writes `08_baselines/structure_reports/<baseline_id>.json` and `.md`.
5. Scores repo structure and writes `08_baselines/code_structure_plan.md`.
6. Scaffolds thin project-side adapters under `04_code/src/baselines/<baseline_id>/`.
   **Superseded by v8.0.0 (Baseline Decoupling):** adapter scaffolding into
   `04_code/src/baselines/` and the `--apply-structure` flag were removed.
   Baseline wrappers, adapters, and patch notes now live only under
   `08_baselines/` (`run_scripts/<baseline_id>/` or `patches/`), keeping
   `04_code/src/` independent of external baseline code.
7. Sends agent messages for missing repo URLs when requested.

Cloned source snapshots are treated as upstream artifacts. Agents should not edit them directly. Project-specific behavior belongs in adapters, run scripts, or patch notes.

## Consequences

- Baseline comparison evidence becomes traceable from paper to repo to command to result.
- Code agents can reuse upstream structure without silently changing baseline behavior.
- Strict validation can catch source snapshots without structure reports.
- Remote cloning remains explicit through `--allow-network`, while local repo smoke tests stay deterministic.
