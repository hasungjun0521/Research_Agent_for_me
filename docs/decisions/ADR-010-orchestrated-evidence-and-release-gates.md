# ADR-010: Orchestrated Evidence And Release Gates

## Status
Accepted

## Date
2026-05-10

## Context
The workspace had a strong folder structure, a dashboard, baseline intake, GPU queue planning, and research-loop suggestions. The remaining gap was that important research actions still depended on manual glue: copying prompts into agents, checking detached GPU jobs, converting raw outputs into final result tables, turning reviews into revision tasks, and packaging final artifacts.

## Decision
Add scriptable gates for the remaining workflow gaps:

- `scripts/commands/agents/agent_orchestrator.py` renders dispatch prompts, updates command/agent state, and optionally calls an explicit external runner.
- `scripts/commands/experiments/gpu_monitor.py` reconciles running GPU jobs with scheduler, tmux, logs, result paths, and `run_state.json`.
- `scripts/commands/baselines/repo_discovery.py` scores baseline repo candidates from local notes, candidate files, and optional GitHub search.
- `scripts/commands/baselines/baseline_sandbox.py` audits cloned-code commands before execution.
- `scripts/commands/experiments/result_ingest.py`, `scripts/commands/reports/data_metric_audit.py`, and `scripts/commands/reports/paper_claim_linter.py` connect raw outputs, registry provenance, and paper claims.
- `scripts/commands/review/review_to_revision.py` converts reviewer risks into revision tasks.
- `scripts/commands/reports/artifact_packager.py` creates a reproducibility manifest and optional archive.

## Consequences
- Agent handoffs can be reproduced from prompt files rather than only dashboard copy/paste.
- Detached experiments have an explicit monitor path instead of relying on manual `squeue` checks.
- Final paper claims get checked against structured evidence before being strengthened.
- Baseline execution has a lightweight security gate before third-party code runs.
- Submission artifacts can be assembled consistently without mixing final files with scratch notes.

## Alternatives Considered

### Keep the workflow manual
- Pros: fewer scripts.
- Cons: high chance of stale state, unsupported paper claims, and missed failed jobs.
- Rejected because the user wants the harness to keep thinking and verifying until evidence is solid.

### Put all automation into the dashboard
- Pros: one visible UI.
- Cons: harder to test and unsafe for command execution.
- Rejected in favor of testable CLI gates with dashboard visibility.
