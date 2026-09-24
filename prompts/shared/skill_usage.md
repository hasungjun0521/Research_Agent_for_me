# Skill Usage

Use skills and project-local runbooks to make agent passes more reliable. Skills
are workflow constraints, not decorations; apply only the skills that match the
current task.

Codex installations may have external skills from `addyosmani/agent-skills`:

- `using-agent-skills`
- `idea-refine`
- `spec-driven-development`
- `planning-and-task-breakdown`
- `incremental-implementation`
- `test-driven-development`
- `debugging-and-error-recovery`
- `code-review-and-quality`
- `code-simplification`
- `context-engineering`
- `source-driven-development`
- `doubt-driven-development`
- `frontend-ui-engineering`
- `browser-testing-with-devtools`
- `api-and-interface-design`
- `security-and-hardening`
- `performance-optimization`
- `ci-cd-and-automation`
- `git-workflow-and-versioning`
- `documentation-and-adrs`
- `deprecation-and-migration`
- `shipping-and-launch`

## Global Rules

- Start with `using-agent-skills` when it is installed, or use this mapping when it is unclear which skill applies.
- Do not use every skill at once. Pick the smallest set needed for the pass.
- For project-local speed and token discipline, read `prompts/skills/README.md` and only the specific skill file needed for the current task.
- Use `prompts/skills/context_budgeting.md` when context size is growing or repeated file reads are wasting tokens.
- Use `prompts/skills/workspace_profile.md` when adapting language, GPU, scheduler, or lab-local preferences for a user.
- Use `prompts/skills/research_repo_import.md` when importing an existing research repository into a template-backed project.
- Use `prompts/skills/privacy_publish_audit.md` before publishing, sharing, or tagging the harness.
- Use `prompts/skills/source_credibility_audit.md` before strengthening literature-backed claims or related-work text.
- Use `prompts/skills/experiment_repair.md` when experiments fail, stall, or finish without usable result artifacts.
- Use `prompts/skills/resource_ledger.md` when a pass consumes meaningful tokens, cost, wall time, GPU time, or storage.
- Use `prompts/skills/progress_checkpoint.md` during multi-step work when a
  result, blocker, direction change, failed assumption, experiment outcome,
  memory note, or next action should be saved before the final response.
- Use `prompts/skills/project_health.md` at the start of a continuation pass
  when dashboard-free status, blockers, stale state, or next-best-action
  guidance is needed.
- Use `prompts/skills/state_doctor.md` when file state is stale,
  contradictory, missing required artifacts, or hard for a fresh agent to
  resume. Preview repair before writing missing starter files unless the user
  explicitly asks to apply repair immediately.
- Use `prompts/skills/brief_intake.md` when a rough idea needs to become
  durable brief files, constraints, and open questions before routing work.
- Use `prompts/skills/experiment_planning.md` before a new experiment family,
  especially when smoke-first planning or parallel GPU main runs are possible.
- Use `prompts/skills/claim_graph.md` before strengthening paper claims from
  result rows, experiment journals, or claim-evidence tables.
- Use `prompts/skills/baseline_compare.md` after baseline source snapshots
  exist and before shaping substantial `04_code/src/` interfaces.
- Use `prompts/skills/agent_quality_audit.md` when previous agent work is hard
  to resume or done commands lack output-file evidence.
- Use `prompts/skills/skill_synthesis.md` when identifying a recurring mistake
  or receiving explicit procedural correction from the user to codify it into a
  permanent skill.
- Use `prompts/skills/phase_gate.md` before moving a project to the next research phase.
- Use `prompts/skills/run_checkpoint.md` before risky loops, major reruns, or handoffs that may need replay/fork context.
- Use `prompts/skills/gpu_parallel_execution.md` when queueing, planning, dry-running, or launching parallel GPU experiments. Check readiness diagnostics before consuming GPUs.
- Use `prompts/skills/agent_orchestration.md` when dispatching command-queue work to one or more agent passes, especially when independent commands can be prepared, run, and finished as a bounded parallel batch.
- Use `prompts/skills/experiment_smoke_first.md` before expensive full runs.
- Use `prompts/skills/experiment_completion.md` when an experiment outcome is
  known and result CSV, journal, analysis, artifacts, run state, and agent
  status should move together.
- Use `prompts/skills/literature_review.md` when scoping, decomposing, or
  resuming a literature pass: search rounds, paper notes, the related-work
  matrix, and novelty/contradiction checks before claims strengthen.
- Use `prompts/skills/weekly_deck.md` when the user wants a weekly progress
  slide deck or a glanceable status summary for a project.
- Use `prompts/skills/fast_baseline_intake.md` for baseline paper/repo ingestion.
- Use `prompts/skills/claim_and_result_evidence.md` when ingesting results or strengthening claims.
- Use `prompts/skills/dashboard_refresh.md` only when dashboard mode is explicitly
  enabled and research work changed optional dashboard support evidence before a
  human-facing handoff. Checkpoint/state updates are required regardless.
- Use `prompts/skills/project_closeout.md` before handing a project to another agent or human.
- Use `prompts/skills/claim_table_backfill.md` when claim rows are missing or disconnected from results.
- Use `prompts/skills/reviewer_risk_matrix.md` when reviewer objections need concrete risks and response plans.
- Use `prompts/skills/workflow_state_reconcile.md` when commands, owners, experiments, or vote gates are out of sync.
- Use `prompts/skills/report_hygiene.md` when `09_report/` contains scratch Markdown or non-final artifacts.
- Use `prompts/skills/project_hygiene.md` when project folder structure drifts: `09_report/` bloat or junk, stale `.lock` debris, quarantined `.corrupt-*` state files, unexpected top-level entries, or missing diagnostics on idle projects.
- Use `prompts/skills/paper_claim_compression.md` when writing or reviewing claims.
- Use `prompts/skills/artifact_packaging.md` before sharing or archiving a project.
- Use `prompts/skills/performance_measurement.md` when optimizing runtime, token usage, or analysis throughput.
- For non-trivial code changes, use `incremental-implementation` and `test-driven-development`.
- For failures, use `debugging-and-error-recovery` before adding new features.
- For CI, automation, status tooling, or dashboard harness changes, use `ci-cd-and-automation`.
- For high-risk or uncertain decisions, use `doubt-driven-development` before finalizing.
- For framework/library-specific code, use `source-driven-development` and verify primary sources.
- For prior research code or baselines, use `source-driven-development`, `context-engineering`, and `documentation-and-adrs`; record source paths and commands in `08_baselines/`.
- For venue/year review forms, use `context-engineering` and `doubt-driven-development`; select the exact form from `review_forms/form_registry.json` and fill every required field.
- For final review before committing or shipping, use `code-review-and-quality` and `git-workflow-and-versioning`.

## Agent Mapping

| Agent | Primary Skills | Use For |
| --- | --- | --- |
| `director` | `context-engineering`, `planning-and-task-breakdown`, `documentation-and-adrs`, `doubt-driven-development`, `project_health`, `state_doctor` | Routing work, keeping state coherent, decomposing tasks, recording decisions |
| `motivation_planner` | `idea-refine`, `spec-driven-development`, `doubt-driven-development`, `brief_intake` | Turning vague ideas into research questions, clarifying claims and boundaries |
| `literature_reviewer` | `source-driven-development`, `context-engineering`, `documentation-and-adrs` | Grounding claims in sources, keeping citation context reliable |
| `experiment_designer` | `spec-driven-development`, `planning-and-task-breakdown`, `doubt-driven-development`, `experiment_planning` | Turning claims into falsifiable experiments with acceptance criteria |
| `code_agent` | `incremental-implementation`, `test-driven-development`, `debugging-and-error-recovery`, `source-driven-development` | Implementing, running, and debugging experiments in small verified increments |
| `data_analyst` | `debugging-and-error-recovery`, `doubt-driven-development`, `documentation-and-adrs` | Verifying result quality, preserving null/failed runs, documenting uncertainty |
| `result_interpreter` | `doubt-driven-development`, `code-review-and-quality`, `documentation-and-adrs`, `claim_graph` | Separating evidence from claims and reviewer-safe interpretation |
| `writing_agent` | `documentation-and-adrs`, `code-review-and-quality`, `doubt-driven-development` | Revising paper/rebuttal text while avoiding unsupported claims |
| `venue_reviewer` | `context-engineering`, `doubt-driven-development`, `code-review-and-quality` | Filling venue/year review forms, scoring drafts with evidence, and producing review-form revision targets |
| `critic` | `code-review-and-quality`, `security-and-hardening`, `performance-optimization`, `doubt-driven-development`, `agent_quality_audit` | Reviewer-style risk finding and quality gates |

## Frontend And Dashboard Work

When modifying `dashboard/index.html` or browser-facing UI:

- Use `frontend-ui-engineering` for layout, interaction states, accessibility, and responsive design.
- Use `browser-testing-with-devtools` when a real browser runtime is available.
- Use `performance-optimization` if rendering, polling, or large state payloads become slow.

## Harness And Release Work

When modifying scripts, CI, publication flow, or repo hygiene:

- Use `ci-cd-and-automation` for quality gates.
- Use `git-workflow-and-versioning` for atomic commits and publishable state.
- Use `security-and-hardening` for secrets, private project exclusion, and untrusted inputs.
- Use `prompts/skills/privacy_publish_audit.md` when checking GitHub-visible files for local paths, private project names, or reference workspace names.
- Use `shipping-and-launch` before publishing the harness.
- Use `deprecation-and-migration` when replacing old state formats or CLI behavior.
