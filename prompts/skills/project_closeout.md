# Project Closeout

Use this skill before handing a research project to another agent or to a human
reviewer, without requiring dashboard visibility.

## Required Hook

Run the closeout audit:

```bash
python -m scripts.commands.projects.project_closeout --project <project> --write-report
```

## Read The Output As Routing

- `project_health` means refresh `state/project_health.md` before handoff.
- `state_doctor` means refresh stale-state diagnostics before trusting the queue.
- `claim_evidence` means use `prompts/skills/claim_table_backfill.md`.
- `claim_graph` means use `prompts/skills/claim_graph.md`.
- `artifact_registry` means record metric files, logs, checkpoints, result
  directories, and evidence paths through the experiment completion workflow.
- `experiment_dag` means use `prompts/skills/experiment_planning.md`.
- `baseline_compare` means use `prompts/skills/baseline_compare.md`.
- `agent_quality` means use `prompts/skills/agent_quality_audit.md`.
- `reviewer_risk` means use `prompts/skills/reviewer_risk_matrix.md`.
- `workflow_state` or `vote_gate` means use `prompts/skills/workflow_state_reconcile.md`.
- `report_hygiene` means use `prompts/skills/report_hygiene.md`.
- Dashboard refresh is optional. Use `prompts/skills/dashboard_refresh.md` only
  when dashboard mode is explicitly enabled.

## Exit Criteria

Do not call a project ready for handoff until these pass:

```bash
python -m scripts.commands.projects.project_closeout --project <project> --write-report
python -m scripts.commands.projects.validate_project --project <project> --strict
```

Dashboard refresh is not part of the default closeout. Use
`prompts/skills/dashboard_refresh.md` only when dashboard mode is explicitly
enabled.
