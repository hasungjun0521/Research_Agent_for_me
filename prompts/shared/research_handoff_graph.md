# Research Handoff Graph

Use this graph to keep multi-agent research loops bounded. It is a routing
contract, not a scientific workflow requirement; real research can iterate, but
one autonomous pass should not bounce indefinitely between roles.

## Preferred Paths

```text
director
  -> motivation_planner
  -> literature_reviewer
  -> experiment_designer
  -> code_agent
  -> data_analyst
  -> result_interpreter
  -> writing_agent
  -> venue_reviewer / critic
  -> director
```

Allowed lateral handoffs:

- `motivation_planner -> literature_reviewer` when motivation needs sources.
- `literature_reviewer -> experiment_designer` when evidence gaps become tests.
- `literature_reviewer -> code_agent` only after baseline intake/sandbox planning.
- `experiment_designer -> code_agent` after preregistration and success criteria.
- `code_agent -> data_analyst` after outputs or run logs exist.
- `data_analyst -> experiment_designer` when results invalidate the design.
- `data_analyst -> result_interpreter` when tables are ready for claims.
- `result_interpreter -> writing_agent` when claim status is ready.
- `writing_agent -> critic` or `venue_reviewer` for review.
- `critic -> director` for prioritization and risk decisions.

## Blocked Paths

Avoid these paths unless the director explicitly re-routes:

- Worker directly spawning another worker.
- `writing_agent -> code_agent` without a director command.
- `code_agent -> writing_agent` before data/claim interpretation.
- Any role changing final claim status without `result_interpreter` or critic
  review.
- Any role launching expensive compute without scheduler/monitor state and the
  relevant risk gate.

## Hop Limit

For one autonomous loop, use a maximum of three role handoffs after the director
selects the task. If more handoffs are required, stop with `manual_required` or
return control to the director with a compact plan.

Parallel branches count hops independently. A branch that reaches its hop limit
must stop without blocking independent branches that already have enough
evidence to complete.

## Handoff Payload

Each handoff should include:

- Current claim, experiment, baseline, or command id.
- Files read and files updated.
- Evidence that justifies the handoff.
- Uncertainty and known blockers.
- Proposed next role and done condition.
