# Research Routing Matrix

Use this matrix before dispatching a command or choosing the next agent pass. It
maps common research requests to the first responsible role and the expected
handoff path. Use the legacy Ralph loop only when the user explicitly asks for
it.

| Request or Symptom | First Role | Typical Next Role | Notes |
| --- | --- | --- | --- |
| Need overall project status without dashboard | `director` | `state_doctor` workflow if stale | Refresh project health and choose the next highest-priority blocker. |
| Stale, contradictory, or hard-to-resume state | `director` | `critic` | Run state doctor, repair safe missing starters, and checkpoint unresolved blockers. |
| Vague idea, unclear contribution, weak motivation | `motivation_planner` | `director` | Produce a reader-readable problem, claim candidate, and open questions. |
| Rough idea needs durable setup files | `motivation_planner` | `director` | Use brief intake; put unknown dataset/metric/baseline/compute details in open questions. |
| Need papers, related work, or baseline candidates | `literature_reviewer` | `experiment_designer` or `baseline_intake` workflow | Use source-grounded notes and avoid unsupported claims. |
| Need baseline code or repo reproduction | `literature_reviewer` | `code_agent` | Use repo discovery, intake, sandbox audit, then smoke execution. |
| Cloned baseline repos exist and project code structure is unclear | `code_agent` | `director` | Compare baseline structures before shaping `04_code/src/`; do not edit cloned snapshots. |
| Need experiment design, hypotheses, metrics, or preregistration | `experiment_designer` | `code_agent` | Update preregistration before execution. |
| Need a new experiment family with parallel seeds/ablations | `experiment_designer` | `code_agent` | Create a smoke-first experiment DAG before GPU queueing. |
| Need implementation, experiment execution, or GPU run | `code_agent` | `data_analyst` | Use scheduler/monitor for GPU jobs and keep run manifests current. |
| Need result tables, statistical checks, or null-result handling | `data_analyst` | `result_interpreter` | Preserve negative or failed results; do not hide uncertainty. |
| Need claim status or reviewer-safe interpretation | `result_interpreter` | `writing_agent` or `critic` | Update claim-evidence artifacts before paper claims. |
| Need to strengthen claims after results changed | `result_interpreter` | `writing_agent` | Refresh the working claim graph and check analysis edges first. |
| Need paper, rebuttal, or report writing | `writing_agent` | `venue_reviewer` or `critic` | Cite evidence paths and keep unsupported claims labeled. |
| Need venue-form review or adversarial critique | `venue_reviewer` or `critic` | `director` | Convert findings into concrete next actions. |
| Previous agent pass is hard to trust or resume | `critic` | `director` | Audit agent quality and repair missing output evidence or checkpoints. |
| Need final package or public artifact | `director` | `critic` | Run artifact packaging and publishable checks. |
| High-risk command, expensive compute, claim-status change, or final packaging | `director` | vote gate | Use `agent_vote.py` before dispatch. |

## Harness Owner-Generator Note

Two harness commands auto-generate `owner_agent` suggestions, and they do not
always agree, so read this note before trusting a single suggestion's owner:

- `research_loop.py` assigns `motivation_planner`, `literature_reviewer`,
  `experiment_designer`, `code_agent`, and `data_analyst`. It is the generator
  that routes baseline candidate/repo work to `literature_reviewer`.
- `project_diagnostics.py` (the state-doctor / project-health suggestion ladder)
  assigns `director`, `motivation_planner`, `experiment_designer`,
  `data_analyst`, `result_interpreter`, `code_agent`, and `critic`. It does not
  assign `literature_reviewer`; conversely `research_loop.py` does not assign
  `result_interpreter` or `critic`.

Canonical first-owner per stage stays as in the table above. The one place the
two generators visibly diverge is the baselines area:

- Baseline candidate / repo discovery (finding papers and repos to reproduce) is
  owned first by `literature_reviewer` (matrix rows above), matching
  `research_loop.py`.
- Baseline structure-comparison (diffing already-cloned source trees and shaping
  `04_code/src/` to follow them) is owned by `code_agent`. This is exactly the
  step the diagnostics ladder emits as its `baselines -> code_agent` suggestion
  (producing `08_baselines/baseline_compare.md` and
  `08_baselines/code_structure_plan.md`), so that mapping is the
  structure-comparison step, not candidate discovery.

When the two generators suggest different owners for similar-looking baseline
work, route discovery to `literature_reviewer` and structure-comparison to
`code_agent`.

## Routing-Coverage Gaps

The auto-suggestion engine does not currently emit any `writing_agent` or
`venue_reviewer` owner. The `writing` issue area produces a recommended-request
bullet but no `suggested_command`, so writing/terminology and venue-review work
has no machine-assigned owner and falls back to `director` via the orchestrator's
default owner resolution. For paper-writing and venue-review work, a human or
`director` must set `owner_agent` explicitly (`writing_agent` or
`venue_reviewer`) rather than relying on an auto-generated suggestion.

## Fast Path

A command may skip a lead-style planning turn only when all conditions hold:

- The target files or output artifacts are known.
- The requested change is specific enough to verify.
- Risk is `low` or `medium`.
- Confidence is `HIGH`.
- The write set does not overlap an active command.

Otherwise, route through the responsible lead role and require a dispatch block.

## Parallel Path

Parallel dispatch is allowed when work items are independent and have disjoint
write sets. Common safe examples:

- Literature search and implementation smoke planning.
- Claim-evidence board generation and optional support-surface inspection.
- Multiple read-only reviews of the same draft.

Parallel dispatch is not allowed when one task consumes another task's output,
when both tasks edit the same report artifact, or when both tasks mutate the
same command/status state.
