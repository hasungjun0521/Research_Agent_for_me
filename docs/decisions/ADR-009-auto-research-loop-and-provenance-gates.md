# ADR-009: Auto Research Loop and Provenance Gates

## Status

Accepted

## Context

The harness had strong state files and validation, but agents still needed a director to manually decide the next step from missing evidence. Results also used dataset and metric strings that were not guaranteed to map to stable provenance.

## Decision

Add three mechanisms:

1. `03_experiments/dataset_registry.json` and `03_experiments/metric_registry.json` for stable dataset/metric IDs.
2. `scripts/commands/research/research_registry.py` to update those registries without hand-editing JSON.
3. `scripts/commands/research/research_loop.py` to inspect current gaps and enqueue visible next actions in `state/command_queue.json` plus handoff messages in `state/agent_messages.json`.

Validation now checks:

- dataset and metric registry shape,
- result rows against registered dataset/metric IDs when rows exist,
- weak claim IDs referenced in `09_report/paper/main.tex`,
- baseline smoke scripts for adapter-backed runnable baselines.

## Consequences

- The director can bootstrap the next research loop from state instead of hidden memory.
- Result tables have stronger dataset/metric provenance.
- The paper cannot quietly reference unsupported claim IDs without a strict validation warning.
- Baseline adapters get a cheap smoke check before expensive reproduction.
