# Research Role Index

Authoritative index of the ten research agent roles in this directory. Each role
is a Markdown prompt the orchestrator loads at dispatch time; the lifecycle,
matrix, and ownership rules below are the single human source of truth for the
canonical role **names**.

## 1. Purpose & How To Use This Index

- The ten `prompts/agents/<role>.md` files **are** the role prompts. The
  orchestrator resolves a command's `owner_agent` to `prompts/agents/<name>.md`
  and inlines it (`scripts/commands/agents/agent_orchestrator.py:467-471`). An
  `owner_agent` with no matching file silently degrades to the literal fallback
  `Act as {agent}.` (`agent_orchestrator.py:498`), so a misspelled role loses
  its entire prompt.
- The filenames are the **canonical role names**. Never invent short-forms such
  as `reviewer`, `analyst`, or `writer`; align every routing reference, command
  queue entry, and doc to these exact names.

## 2. The Canonical Research Lifecycle (9 stages)

`Brief & Motivation` → `Literature & Baselines` → `Experiment Design` →
`Implementation & Execution` → `Analysis` → `Interpretation` → `Writing` →
`Review` → `Revision / Routing / Packaging`.

| # | Stage | Frames / produces | Primary folders |
| --- | --- | --- | --- |
| 1 | Brief & Motivation | Research question, problem, contribution candidates, assumptions | `00_brief/`, `state/open_questions.md` |
| 2 | Literature & Baselines | Prior work, gaps, baseline paper/repo inventory + intake | `01_literature/`, `08_baselines/` |
| 3 | Experiment Design | Falsifiable hypotheses, preregistration, metrics, DAG | `03_experiments/`, `02_planning/` |
| 4 | Implementation & Execution | Experiment code, GPU dispatch, run logs and manifests | `04_code/`, `03_experiments/exp_*/`, `gpu_experiment_queue.json` |
| 5 | Analysis | Raw-result observation, data trust, aggregated tables/figures | `05_results/` analysis surfaces |
| 6 | Interpretation | Claim status, caveats, next experiments | `05_results/` interpretation + claim surface |
| 7 | Writing | Motivation/lit/method/results/interpretation into modest prose | `06_writing/` |
| 8 | Review | Adversarial critique + exact venue-form review of the draft | `07_reviews/` |
| 9 | Revision / Routing / Packaging | Director prioritizes findings, routes the next loop, packages the report | `02_planning/`, `09_report/` |

This is a **routing contract, not a rigid scientific order**
(`../shared/research_handoff_graph.md:3-5`). Real research iterates with the
allowed lateral and back edges below.

## 3. Role Matrix

PRIMARY-OWNED files are written by that role; shared/append-only surfaces are
called out in §5.

| Role | Stage | Mandate (one sentence) | Consumes | Produces (primary-owned) | Hands off to (trigger) |
| --- | --- | --- | --- | --- |
| [`director`](director.md) | 9. Revision / Routing / Packaging (hub for all stages) | Diagnose project state, choose the next agent or parallel batch, open vote gates, and keep state coherent across the whole loop. | `state/*` (current_state, command_queue, agent_status, agent_messages), brief/motivation, lit summaries, experiment registry + metrics, interpretation/aggregate results, draft + critic/venue review | `state/{current_state,next_actions,open_questions}.md`, `command_queue.json`, `agent_status`/`messages`, `loop_summary.json`, `02_planning/{director_plan,task_graph,decision_log}.md`, `09_report` packaging | Any role via the named "Next Agent Or Parallel Batch" block (`director.md` → `### Next Agent Or Parallel Batch`); receives back from `critic`/`venue_reviewer` |
| [`motivation_planner`](motivation_planner.md) | 1. Brief & Motivation | Refine motivation, problem statement, contribution candidates, and planning questions so the project is worth doing before any lit/experiment/writing work. | Research question, motivation notes, problem statement, assumptions/constraints, state + open_questions | `00_brief/{motivation,problem_statement,contribution_candidates,assumptions}.md` (primary author of `contribution_candidates.md`), `state/open_questions.md` + state quad | `literature_reviewer` (motivation needs sources) or `director`; surfaces Claims-to-Validate + Planning-Questions |
| [`literature_reviewer`](literature_reviewer.md) | 2. Literature & Baselines | Survey prior work, identify gaps and limitations, and inventory baseline papers/repos to prevent unsupported novelty. | Research question/motivation, bibliography, paper notes, candidate contributions, baseline candidate list | `01_literature/{related_work_matrix,gap_analysis,prior_limitations}.md`, `paper_notes/`, `08_baselines/prior_research_inventory.md` + `baseline_registry.json` (via baseline_library), `source_snapshots/`, `structure_reports/` | `experiment_designer` (gaps become tests) or `code_agent` (only after baseline intake/sandbox planning); proposes Suggested Experiments |
| [`experiment_designer`](experiment_designer.md) | 3. Experiment Design | Convert research claims into testable, preregistered hypotheses and a smoke-first experiment DAG that can validate or falsify them. | Research question/contributions, lit gaps + suggested analyses, experiment registry, metric defs, available code/datasets, constraints | `03_experiments/{experiment_registry.yaml,metrics.md,data_roots.md,experiment_dag.json}`, `exp_*/{hypothesis,config,preregistration}`, `02_planning/{experiment_plan,task_graph}.md`, `06_writing/method.md` (method-design seed only) | `code_agent` via the explicit "Required Code Changes" section (`experiment_designer.md` → `### Required Code Changes`); receives design-invalidation back-edge from `data_analyst` |
| [`code_agent`](code_agent.md) | 4. Implementation & Execution | Write, modify, run, and debug experiment code in small reviewable traceable changes, owning GPU dispatch and run-state discipline. | Experiment design + configs, preregistration, run logs/errors, existing source/tests, code review comments, baseline snapshots | `04_code/{src,tests,notebooks,implementation_notes,code_review}`, `exp_*/{run_log,run_state,reproducibility_manifest}`, `gpu_experiment_queue.json`, `08_baselines/{source_snapshots,run_scripts,patches}`, raw run rows in `05_results/` | `data_analyst` (after outputs or run logs exist); receives back from `data_analyst` on debug needs |
| [`data_analyst`](data_analyst.md) | 5. Analysis | Analyze raw results/logs/metrics to state what happened and whether the data is trustworthy, without crossing into causal interpretation. | Experiment registry, config/hypothesis, run logs, raw results/tables/figures/metrics, previous analyses, metric defs | `exp_*/analysis.md`, `05_results/{aggregate_results,failure_cases,statistical_robustness,tables/,figures/}`, working rows in `experiment_journal.md`/`.csv` | `result_interpreter` (tables ready for claims) or `experiment_designer` (results invalidate the design); surfaces Recommended-Next-Analyses |
| [`result_interpreter`](result_interpreter.md) | 6. Interpretation | Turn analyzed evidence into defensible claim status, caveats, and next experiments, naming evidence and uncertainty for each claim. | Research question/contributions, hypotheses, analyses + aggregate results, failure cases, lit gaps, current draft claims | `05_results/{interpretation.md,claim_evidence_board.md}`, narrowing of `00_brief/contribution_candidates.md`, discussion/limitations seed for `06_writing/` | `writing_agent` (claim status ready) or `experiment_designer` (next experiments); "Implications for the Paper" feeds writing |
| [`writing_agent`](writing_agent.md) | 7. Writing | Assemble brief/lit/method/results/interpretation into precise, modest, evidence-driven academic prose and own the terminology glossary. | Brief/motivation, lit review + notes + bib, experiment design/metrics, aggregate results + interpretation, existing draft, style guide + critic comments | `06_writing/{outline,abstract,introduction,related_work,method,experiments,discussion,limitations,terminology,draft}.md`, `09_report/paper/main.tex` (prose owner / draft integrator — see §5), open_questions for missing evidence | `critic` or `venue_reviewer` for review; routes Missing-Evidence back to experiment/result roles via `director` |
| [`critic`](critic.md) | 8. Review | Act as a harsh-but-constructive generic reviewer that turns rejection/overclaiming/irreproducibility risks into prioritized actionable revisions. | Draft/section, research question/contributions, lit review + gap, experiment design/metrics/results, interpretation/limitations, current revision plan | `07_reviews/{critic_comments,reviewer_attack_surface,reviewer_attack_matrix,revision_plan}.md` (does NOT write `form_reviews/` unless explicitly asked) | `director` (prioritization and risk decisions); revisions feed `writing_agent` |
| [`venue_reviewer`](venue_reviewer.md) | 8. Review | Produce a form-complete review against an exact venue/year form, gated by the form registry's LLM-use policy. | Requested form id/venue/year, target draft, venue form + rubric, brief/lit/experiments/results, baseline registry, limitations, revision plan | `07_reviews/form_reviews/<review_id>.md` (sole owner), and form-derived entries in shared `revision_plan`/`attack-surface`/`matrix` | `director`; review feeds `critic`/`writing_agent` revision; stops as `blocked` when LLM-review policy forbids |

## 4. Handoff Flow & Lateral / Back Edges

The preferred path and the full set of allowed lateral and blocked edges are
defined once in [`../shared/research_handoff_graph.md`](../shared/research_handoff_graph.md)
— that file is canonical; do not duplicate it here.

Preferred path (summary):

```text
director -> motivation_planner -> literature_reviewer -> experiment_designer
-> code_agent -> data_analyst -> result_interpreter -> writing_agent
-> venue_reviewer / critic -> director
```

Key constraints from [`../shared/leader_dispatch_protocol.md`](../shared/leader_dispatch_protocol.md):

- **Workers never spawn workers** and never invent a new route; a wrong route
  returns `blocked` or asks via `state/agent_messages.json`
  (`../shared/leader_dispatch_protocol.md:27-29`).
- **Three-handoff hop limit** per autonomous loop after the director selects the
  task; beyond that, stop with `manual_required` or return to the director with
  a compact plan (`../shared/research_handoff_graph.md:47-55`).

## 5. Shared Write-Surfaces & Ownership Rules (the seams)

These files are touched by more than one role. The owner authors; other roles
append or narrow only.

| Surface | Owner / write rule |
| --- | --- |
| `00_brief/contribution_candidates.md` | `motivation_planner` **authors**; `literature_reviewer` and `result_interpreter` **narrow** only (add gaps / claim status, never re-author). |
| `05_results/aggregate_results.*`, `experiment_journal.md`/`.csv` | `data_analyst` writes **observations** and working rows; `result_interpreter` writes **claims**; `code_agent` appends **raw run rows**. Keep Observation vs Interpretation split (`../shared/output_contracts.md`). |
| `06_writing/method.md`, `discussion.md`, `limitations.md` | Upstream roles seed **content** (`experiment_designer` method seed, `result_interpreter` discussion/limitations seed); `writing_agent` owns the **prose**. |
| `07_reviews/revision_plan.md`, `reviewer_attack_surface.md`, `reviewer_attack_matrix.md` | `critic` adds **generic** findings; `venue_reviewer` adds **form-grounded** entries. Append by `review_id`; do not overwrite. |
| Claim surface | `05_results/claim_evidence_board.md` is the **human** board; `claim_graph.*` is the **machine** surface (`scripts/commands/reports/claim_graph.py`, `claim_evidence_board.py`). Do not hand-edit the machine surface. |
| `09_report/paper/main.tex` | `writing_agent` owns the **prose** and integrates the draft; `experiment_designer`, `code_agent`, and `director` may export **stable method/evaluation text** only (their prompts grant `main.tex` write for that scope). Coordinate by section; never clobber prose. |
| `09_report/` exports | **Prefer one designated exporter per artifact** to avoid clobbering (`main.tex` above is the shared method/eval exception); `09_report/` stays final-artifact-facing — scratch belongs upstream. |

## 6. owner_agent & Routing Contracts

- `owner_agent` resolves two different ways. For **dispatch**, the orchestrator
  takes the first `/`- or `,`-segment as the target
  (`scripts/commands/agents/agent_orchestrator.py:166-168`). For **claim/finish
  authorization**, `owner_matches` accepts **any** listed segment
  (`scripts/harness/state.py:708-709`, tested by
  `test_owner_matches_supports_multi_owner_strings` in
  `scripts/tests/test_state_logic.py`; `validate_project.py:1146-1147` validates
  every segment). Multi-owner strings such as `code_agent/critic` are therefore
  supported — but for clarity prefer a single explicit owner and route the next
  role explicitly rather than stuffing several owners into one field.
- Auto-routed vs not:
  - `scripts/harness/project_diagnostics.py:415-472` emits suggested commands
    owned by `director`, `motivation_planner`, `experiment_designer`,
    `data_analyst`, `result_interpreter`, `code_agent`, and `critic`.
  - `scripts/commands/research/research_loop.py:104-188` emits
    `motivation_planner`, `literature_reviewer`, `experiment_designer`,
    `code_agent`, and `data_analyst`.
  - `writing_agent` and `venue_reviewer` are **never auto-routed**; they require
    an explicit `owner_agent` chosen by a human or the director.
- Request → first role mapping lives in
  [`../shared/research_routing_matrix.md`](../shared/research_routing_matrix.md).

## 7. Cross-Cutting Obligations Every Role Must Honor

All defined in [`../shared/output_contracts.md`](../shared/output_contracts.md)
unless noted:

- **Status discipline** — set `running` before work and heartbeat every 5-10
  min; end with `done`/`waiting`/`blocked`/`idle`
  (`../shared/agent_status_protocol.md`).
- **Observation vs Interpretation** split and **Claim-Evidence-Uncertainty-Status**
  format for every result claim.
- **File Update Contract** and the **Completion Gate** (no `done` without
  verification or a recorded blocker).
- **Loop Summary Contract** is scoped to the `director`; the **Vote Contract**
  gates high-risk/expensive/claim-status/packaging commands.
- **Filesystem safety** (`../shared/filesystem_safety_rules.md`) and, when usage
  runs low, `progress_checkpoint` / `limit-handoff`.
- Refresh visible handoff state (`HANDOFF.md`, the `state/` quad) before ending a
  substantial pass.

## 8. Maintenance Note

When adding or renaming a role, update prompts ↔ routing ↔ code **together** —
the role names are hardcoded in more than one place and do **not** auto-derive
from these filenames:

- `scripts/commands/review/leader_dispatch.py` `KNOWN_AGENT_ROLES` is a hardcoded
  allowlist of these 10 names; a leader-dispatched command whose `owner_agent` is
  outside it errors `unknown worker role` (`leader_dispatch.py:151-152`, exercised
  by the smoke gate). Renaming a role prompt without updating this set silently
  breaks every leader-dispatch of that role.
- `scripts/commands/projects/validate_project.py:1135-1147` validates `owner_agent`
  only against the live `agent_status` agent names, **not** against the role prompt
  files — so a typo that never reaches `leader_dispatch` is not caught there.

No single check ties `owner_agent` to the `prompts/agents/<role>.md` filenames, so
drift across prompts ↔ routing ↔ `KNOWN_AGENT_ROLES` is easy to introduce. Keep
this index as the single human source of truth for the canonical role names, and
update `KNOWN_AGENT_ROLES` whenever a role is renamed.
