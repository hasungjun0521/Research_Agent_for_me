# Research Risk And Confidence Matrix

Use this matrix before dispatching commands, launching experiments, changing
final artifacts, or using the legacy Ralph loop by explicit user request.

## Risk Levels

| Level | Meaning | Examples |
| --- | --- | --- |
| `low` | Local, reversible, no scientific claim change | Documentation wording, dashboard copy, status summaries, non-final scratch files |
| `medium` | Project artifact changes with bounded impact | Analysis scripts, claim board draft, preregistration edits, small harness utility |
| `high` | Compute, baseline, final result, or shared workflow impact | GPU launch, baseline execution, final result tables, shared scripts, claim-evidence status |
| `critical` | Irreversible, expensive, public, or conclusion-changing | Paper conclusion change, artifact packaging, destructive migration, large compute spend |

## Confidence Levels

- `HIGH`: target files, evidence, expected output, and verification command are
  known.
- `MEDIUM`: direction is clear, but one input, output, or verification detail is
  still uncertain.
- `LOW`: route, evidence, or expected outcome is unclear.

## Decision Matrix

| Confidence / Risk | low | medium | high | critical |
| --- | --- | --- | --- | --- |
| `HIGH` | Direct dispatch | Direct dispatch | Vote or director approval | Manual approval |
| `MEDIUM` | Direct dispatch with blocker path | Vote or director approval | Vote required | Manual approval |
| `LOW` | Ask/plan first | Ask/plan first | Do not execute | Do not execute |

## Command Queue Mapping

- Set `risk_level` on command queue entries when risk is `high` or `critical`.
- Set `requires_vote=true` for high-risk commands unless the user explicitly
  authorizes the exact action in the current turn.
- Use `scripts/commands/agents/agent_vote.py auto` or
  `scripts/commands/agents/agent_orchestrator.py dispatch --auto-vote` for automatic voting.
- A vote runner must return `<vote>`, `<confidence>`, and `<rationale>` tags.
- Failed or unparseable votes must be treated as abstentions.

## Done Condition

Every command should have a visible `done_when` condition. If `done_when` cannot
be stated, do not dispatch execution yet; route to planning or manual
clarification.
