# ADR-001: Add Per-Project Baseline Library

## Status
Accepted

## Date
2026-05-09

## Context
Research agents need to compare against prior work without relying on memory, vague method names, or undocumented local code changes. The existing workspace already tracks project state, experiment runs, and command queues, but it did not have a first-class place for baseline code, reproduction commands, source snapshots, and adaptation notes.

## Decision
Each project includes `08_baselines/` as the local baseline and prior-code library. The structured source of truth is `08_baselines/baseline_registry.json`, managed by `scripts/commands/baselines/baseline_library.py`. Human-readable context lives beside it in `prior_research_inventory.md`, `implementation_recipes.md`, and `code_adaptation_notes.md`.

## Alternatives Considered

### Put Baselines Under `04_code/`

This keeps code-related files together, but it mixes project implementation code with external prior-work evidence and makes it harder for literature, experiment, and critic agents to find baseline rationale.

### Use Only Literature Notes

Literature notes are good for claims and citations, but they are not enough for reproducible commands, source paths, patches, and run results.

## Consequences

- Code agents must inspect `08_baselines/` before implementing baseline-related code.
- Experiment designers can distinguish required, optional, rejected, and unavailable baselines.
- Validation can catch broken registry structure before agents rely on comparison evidence.
- Large external repositories, checkpoints, datasets, and logs remain outside the publishable harness by default.
