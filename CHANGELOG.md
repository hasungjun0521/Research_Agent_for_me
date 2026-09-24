# Changelog

## Unreleased

### Portable research automation

- Add repository-local setup for Codex skills, Claude session/checkpoint hooks,
  and official CLI runner adapters with stdin prompts, logs and timeouts.
- Add bounded research autopilot initialization, queue planning and execution
  with dependency/vote gates and evidence-aware closeout.
- Fix native Windows state locking and retain permanent coordination sidecars.
- Check serial dispatch dependencies and nested output-path conflicts.
- Add explicit editable packaging and Windows/Linux setup CI; remove fictitious
  default runner/status commands and detect Windows private home paths.


### Added

- Added a resume-time **state reconciliation gate** to the shared project
  diagnostics (`scripts/harness/project_diagnostics.reconciliation_issues`).
  `state_doctor`, `project_health`, and `project_resume` now flag when the
  canonical machine-readable surfaces a fresh session reads first
  (`loop_summary.json`, the `current_state.md` structured header,
  `phase_gates.json`, `command_queue.json`, `agent_status.json`) are frozen at
  the intake default or stale relative to real experiment activity — the
  "shadow workflow" failure where progress only lands in append-only freeform
  surfaces while the resume state silently lies. The check is a hard no-op until
  an experiment has actually run (result rows or a non-`planned` run_state), so
  a pristine template/new project stays green and the template/smoke/verify
  gates are unaffected. Unit tests: `scripts/tests/test_reconciliation.py`.

### Changed

- Completed the `agents`/`baselines` consolidation dispatchers (full subcommand
  routing via delegation), added the central multi-agent role index
  `prompts/agents/README.md`, and finished the v8.0.0 version bump so the default
  `verify_harness`/`release_check` path re-validates the current release.

## v8.0.0 - 2026-06-12

Major architectural release focusing on baseline decoupling, rigorous data-split provenance, and multi-agent concurrency safety.

### Added

- Added `--metric-regex` to `experiment_planner`: allows the experiment DAG to define extraction patterns (the "metric contract") upfront (survey backlog #5, Weco-inspired).
- Added `result_ingest parse-log`: memory-efficient command to extract metrics directly from massive run logs using `collections.deque` and the planned `metric_regex`, preventing OOM on GB-scale SLURM outputs.
- Added data `split` provenance tracking to `experiment_results.csv` (defaults to 'test').
- Added `paper_claim_linter` validation to block reader-facing claims that are backed only by 'val' split results, enforcing rigorous held-out test evaluation (survey backlog #4).
- Added `project_doctor` (`projects.project_doctor`): a consolidated high-performance command that runs `state_doctor`, `project_health`, and `project_hygiene` sequentially in a single memory context, eliminating redundant disk I/O.
- Added preregistration drift verification
  (`preregistration_helper drift`): compares the preregistration (dataset,
  primary metric, claim id) against `experiment_results.csv` rows and
  `run_state.json`, flagging dataset/metric/claim drift and a `succeeded` run
  with no result rows (survey backlog #2, Curie-inspired).
- Added a statement-to-evidence grounding check to `paper_claim_linter`:
  strong/comparative claim sentences (outperforms, state-of-the-art, …) that
  cite no matching result number, `claim_id`, or citation are flagged as
  ungrounded (survey backlog #1, Kosmos-inspired).
- Added `memory_compact` (`review.memory_compact`): archives old
  `## Memory Checkpoint:` blocks from the always-loaded `state/agent_memory.md`
  to `state/sessions/memory_archive.md`, keeping curated header sections and
  recent checkpoints. Preview by default, `--apply` to write; bounds the
  per-resume context cost of monotonically-growing memory (survey backlog #23,
  beads-inspired).
- Added Gemini CLI support: `GEMINI.md` entrypoint (imports `AGENTS.md`) and
  `tools/install_gemini_skills.sh` to link `.claude/skills/` into
  `~/.gemini/skills/`. README and `docs/installed_agent_skills.md` now document
  the Codex and Gemini installers side by side.
- Added the `skill-synthesis` skill (self-evolution protocol) plus its runbook;
  the runbook now lists all 7 registration surfaces and the
  `project_index refresh` + `verify_harness` validation steps so synthesized
  skills pass the release gate.

### Changed

- **[Breaking]** Baseline Decoupling: `04_code/src/baselines/` has been entirely eliminated. The `baseline_intake` tool no longer supports `--apply-structure`. All baseline wrappers, adapters, and patch notes must now reside strictly within `08_baselines/` (`run_scripts/` or `patches/`), guaranteeing that the project's `04_code/src` remains pristine and logically independent of external baseline code.
- **[Breaking]** Result CSV schemas (`experiment_results.csv`) now require a `split` column.
- Centralized all CSV I/O (`read_csv`, `write_csv`, `upsert_rows`) into `scripts/harness/state_io.py`.
- Applied atomic `fcntl`/directory-based file locking to all `write_csv` operations across the harness, preventing data corruption during concurrent multi-agent writes to shared result tables.
- Token discipline: `memory_compact` added to the `context_budgeting` token-sink
  map and the CLAUDE.md/GEMINI.md token-discipline rules; the
  `progress_checkpoint` runbook now points at it for bounding memory growth.

## v7.1.0 - 2026-06-12

Maintenance pass driven by an external research-harness survey (AI-Scientist
v2, Agent Laboratory, AIDE/RD-Agent, CodeScientist, Kosmos, PaperQA2, spec-kit,
LangGraph/AutoGen patterns, Hydra/DVC/W&B conventions) plus a full internal
audit. Survey synthesis and adoption roadmap: `docs/harness_survey_2026-06-12.md`.

### Added

- Added `seed_variance` (`experiments.seed_variance`): cross-seed stability
  audit over `experiment_results.csv` seed families (`_seed_<n>` suffix);
  warns on single-seed claims and unstable families, `--strict` gates,
  `--write-report` writes `05_results/seed_variance.md`.
- Added `env_capture` (`experiments.env_capture`): fills empty observable
  fields of `reproducibility_manifest.json` (git commit + dirty flag, Python
  version, pip freeze snapshot, node, GPU type/count); never overwrites
  non-empty values.
- Added `run_diff` (`experiments.run_diff`): read-only side-by-side of two
  experiments — config unified diff, dotted manifest key differences, result
  rows with per-metric value deltas.
- Added `project_resume --list`: read-only listing of all projects sorted by
  last-touched state with current-state headline and first open next action,
  so a fresh session can find the active project without scanning state files.
- Extended `source_credibility_audit` with bib-entry hygiene: duplicate keys,
  placeholder entries, near-duplicate titles, missing essential fields, and an
  informational arXiv-preprint count (duplicates/placeholders/near-duplicates
  gate `--strict`).
- Added the `weekly_deck` command family (`reports.weekly_deck` +
  `weekly_deck_builder`/`weekly_deck_charts` helpers): an image-first weekly
  development deck (KPI tiles, trend/delta charts, harvested figures) rendered
  on the machine-local PowerPoint template, with stdlib-only data collection,
  a `--dry-run` preview, and the optional `deck` extra
  (`pip install -e .[deck]`). Design spec:
  `docs/superpowers/specs/2026-06-12-weekly-dev-deck-design.md`.
- Added `log_digest` (`experiments.log_digest`): condenses huge training/SLURM
  logs into a bounded digest (head, tail, capped failure-pattern matches with
  explicit truncation notes) so agents never read multi-MB logs end to end.
- Added agent skills `literature-review`, `claim-evidence`, `baseline-intake`,
  and `weekly-deck` under `.claude/skills/`, plus the
  `prompts/skills/literature_review.md` runbook (search-round log, per-paper
  stance notes, novelty cross-check, citation credibility audit).
- Added a reverse-direction registry test: any module under
  `scripts/commands/*/` that defines `main()` must be registered in
  `COMMAND_MODULES`, so new CLIs can no longer land unregistered.
- `workflow_audit` now checks every `.claude/skills/*/SKILL.md` (front-matter
  name matches the directory, row in `docs/installed_agent_skills.md`, mention
  in `README.md`) and extends the runbook registration tuple from 15 to all 34
  non-dashboard `prompts/skills/` runbooks (`dashboard_refresh.md` keeps its
  separate check).

### Changed

- Token-cost reduction: dispatched worker prompts now default to a lean style
  that inlines only the role prompt, filesystem safety rules, and the dispatch
  payload, listing the other shared contracts as read-on-demand pointers
  (~2k tokens per prompt instead of ~17k; `--prompt-style full` restores
  inlining). `CLAUDE.md` was reduced to Claude-specific deltas (~60% smaller;
  it imports `AGENTS.md`, so shared rules load once, not twice), the AGENTS.md
  orchestrator rule was compressed, and `context_budgeting.md` now lists known
  token sinks with their cheap substitutes (log_digest, project_resume --list,
  run_diff, --help over full README reads).
- `pytest` `testpaths` narrowed to `scripts/tests` so bare `pytest` matches
  the CI step; the weekly-deck tests moved to `scripts/tests/`.
- `project_index` public inventory now excludes machine-local
  `config/*.local.pptx` artifacts via fnmatch patterns.
- `AGENTS.md` and the `project-resume` skill now show
  `state_doctor --write-report` in the diagnostics ritual; without the flag
  the report file was silently left stale.
- `prompts/shared/skill_usage.md` gained the missing `experiment_completion`
  mapping bullet plus bullets for the new runbooks.

### Fixed

- `atomic_write_json_unlocked` now fsyncs the temp file before `os.replace`,
  closing a power-loss window that could leave truncated state files.
- Removed the unreferenced `python_module_display()` registry helper.
- Removed template/root debris: empty `projects/template/state/ralph_prompts/`
  and root `.codex/` directories; template
  `gpu_experiment_queue.json` `last_updated` placeholder now matches the other
  starter files.

## v7.0.0 - 2026-06-10

V7 hardens the harness foundation: corrupt-state recovery through state doctor
repair, import-safe workspace profiles, project folder hygiene tooling, a real
unit-test suite with lint enforcement in CI, clean harness/commands layering,
and one canonical data-roots table schema.

### Added

- Added `project_hygiene.py` and the `project-hygiene` skill: a read-only
  project folder-structure diagnosis covering `09_report/` bloat and junk,
  stale zero-byte lock debris, quarantined `.corrupt-*` state backups,
  unexpected top-level entries, missing or stale diagnostics, and missing
  claim graphs. `--clean-locks` (flock-probed, template excluded) and
  `--write-report` are the only mutations; `--strict` gates on high findings
  in `verify_harness` and the smoke test.
- Added a harness unit-test suite under `scripts/tests/` covering state I/O
  atomicity and corrupt-JSON handling, workspace profile validation and
  content-keyed caching, command-queue dependency cycles and ownership,
  vote-gate evaluation, unified data-root writers, project hygiene scanning,
  and command-registry importability (including a guard that the harness
  layer never imports command modules).
- Added `ruff` lint and `pytest` unit-test steps to CI alongside compile,
  project index, and `verify_harness` checks.
- Added corrupt state JSON recovery to state doctor repair: `--dry-run-repair`
  previews and `--repair` quarantines unreadable state files to `.corrupt-*`
  backups under the state lock, then restores template-backed starters.

### Changed

- Moved the workspace profile core (loading, validation, caching, accessors)
  to `scripts/harness/workspace_profile.py`; the release command keeps the CLI
  and re-exports for compatibility. Profile loading is now cached keyed on
  config file contents and returns isolated copies.
- Inverted workflow-surface hooks: `scripts/commands/__init__.py` registers
  report-index and dashboard-source refreshers with
  `scripts/harness/workflow_hooks.py`, so the harness layer no longer imports
  command modules anywhere.
- Unified the two `03_experiments/data_roots.md` writers on the canonical
  seven-column table: `experiment_registry.append_data_root_rows` now upserts
  through `scripts/harness/data_roots.py`, folds timestamps into Notes, and
  rows are never appended under a foreign table header.
- `ProfileError` now subclasses `HarnessError`, and a malformed local
  workspace profile degrades imports with a stderr warning instead of
  crashing every harness command; `gpu_scheduler` fails with a clear message
  instead of an import-time traceback.
- `load_json` keeps raising on corrupt state files but now points at the
  state doctor repair recovery path; read paths never rename or mutate state.
- Restored the template baseline adapter location
  `projects/template/04_code/src/baselines/` and removed the abandoned
  duplicate `04_code/baselines/` move that broke migration and the smoke test.

### Fixed

- Fixed a missing `sys` import in the dashboard command runner error path.
- Fixed loop-variable closure binding in the GPU scheduler refresh mutator.
- Fixed misleading multi-character `rstrip` suffix handling in the paper
  claim linter quantitative check.
- Fixed lint findings across `scripts/` (unused imports and variables,
  unsorted imports, deprecated typing imports, percent-formatting) and
  enforced the configured `ruff` ruleset in CI.

## v6.0.0 - 2026-06-05

V6 candidate work for dashboard-free project health, rough-idea intake,
smoke-first experiment planning, claim graphs, baseline structure comparison,
and agent continuity quality audits.

### Added

- Added dashboard-free project state diagnostics through `state_doctor.py` and
  project health summaries through `project_health.py`.
- Added `brief_intake.py` so rough research ideas can become durable brief
  files, constraints, intake summaries, and open questions.
- Added `experiment_planner.py` to create smoke-first experiment DAGs with
  dependency-aware parallel main-run nodes, expected outputs, and check
  procedures.
- Added `claim_graph.py` to connect working claims, experiment result rows,
  baseline references, and result-analysis notes before paper claims are
  strengthened.
- Added `baseline_compare.py` to compare cloned baseline repository structure
  before shaping substantial project code under `04_code/src/`.
- Added `agent_quality_audit.py` to check whether previous agent passes left
  enough output-file evidence, progress checkpoints, and experiment analysis
  for a fresh session to resume.
- Added template starter files for project health, state doctor, brief intake,
  experiment DAGs, claim graphs, baseline comparison, and agent quality audit.
- Added health/state-doctor suggested-command dry-run preview and enqueue
  support so diagnostics can become structured command-queue work without
  manual JSON edits, with source-specific command id prefixes for traceability.
- Added state doctor repair preview with `--dry-run-repair`, including smoke
  and verification coverage that checks the preview path does not write planned
  repair files.
- Added template-backed state doctor repair for missing core continuation
  files and safe starter ledgers, with repaired-file reporting in
  `state/state_doctor.md` and agent lifecycle outputs.
- Added repair mode/count reporting and command-queue mirror sync when state
  doctor repair restores `state/command_queue.json` or `state/next_actions.md`.
- Added template-backed JSON repair validation and repair-error reporting so
  malformed starter state files are not written during state doctor repair.

### Changed

- Updated project resume, README prompts, HANDOFF prompts, shared skill usage,
  routing matrix, research context, output contracts, workflows, and project
  metadata so the new features are part of the default Claude/Codex file-state
  workflow rather than hidden optional commands.
- Kept the new diagnostic commands read-only by default; they write state only
  when explicitly asked to write or repair.
- Changed dashboard-free diagnostics to refresh state doctor before project
  health, detect stale diagnostic reports from working project activity, and
  show generated timestamps in diagnostic reports.
- Changed diagnostic suggested-command tables and enqueue previews to show
  required inputs as well as expected outputs, so repair commands do not depend
  on files they are meant to recreate.
- Clarified README, template README, scripts README, and project metadata that
  state doctor repair must be previewed before writing, reports repaired files
  and repair errors, and never invents missing research content.
- Updated project closeout and artifact packaging so dashboard-free health,
  state diagnostics, experiment DAGs, claim graphs, baseline comparison, and
  agent quality audits are treated as handoff/reproducibility evidence.
- Added ADR-011 to record the dashboard-free health/routing decision and keep
  dashboard/Ralph support optional rather than default.

## v5.0.0 - 2026-06-05

V5 release for Claude/Codex-native research operation, bounded multi-agent
parallel dispatch, GPU batch scheduling, and stronger experiment-result
persistence.

### Added

- Added dependency-aware multi-agent command batching with `status-parallel`,
  `parallel`, `run-prepared`, and `finish-parallel` lifecycle commands.
- Added prepared parallel batch manifests and diagnostics for unresolved
  dependencies, duplicate owners, vote gates, and substantive output-path
  conflicts.
- Added GPU scheduler JSON diagnostics for `list`, `plan`, dry-run `dispatch`,
  explicit `dispatch --ids`, max-parallel cap mismatches, and dependency-gated
  jobs.
- Added durable experiment-result checkpoint behavior so progress checkpoints
  update the experiment journal, analysis notes, run state, and working result
  CSV.
- Added project resume and command mirror support for parallel command groups,
  dependency readiness, prepared prompts, and continuation prompts.
- Added baseline code-structure planning and adapter scaffolding outputs so
  cloned baseline repositories can guide standardized project code layout.

### Changed

- Reworked the default template and user docs toward Claude/Codex file-state
  continuation instead of dashboard/manual-first workflows.
- Kept Ralph loop and dashboard assets as optional legacy/support tools rather
  than default research flow dependencies.
- Clarified `04_code/`, `08_baselines/`, `05_results/`, and `09_report/`
  boundaries so active experiment work, baseline snapshots, working analysis,
  and final release artifacts do not get mixed.
- Strengthened migration/import repair paths so strict validation can recover
  data roots, terminology, experiment journals, and working result rows from
  existing project state.
- Updated release, smoke, workflow-audit, and template validation coverage for
  multi-agent parallel dispatch and GPU parallel experiment scheduling.

## v4.0.0 - 2026-05-17

V4 core workflow upgrade for release-ready autonomous research loops.

### Added

- Added `scripts/commands/release/release_check.py` as the one-command release-readiness gate for
  syntax checks, workflow wiring, full harness verification, publishable-file
  checks, whitespace checks, release metadata, and optional strict template
  state hygiene.
- Added `scripts/commands/release/privacy_audit.py` and `prompts/skills/privacy_publish_audit.md`
  so publication checks catch local paths, private project names, and reference
  workspace names before release.
- Added research-quality hooks inspired by public research-agent workflows:
  `scripts/commands/reports/source_credibility_audit.py`, `scripts/commands/experiments/experiment_diagnosis.py`,
  `scripts/commands/reports/resource_ledger.py`, `scripts/commands/research/phase_gate.py`, and
  `scripts/commands/experiments/run_checkpoint.py`, plus matching project-local skills.
- Added Ralph stale-active-run hardening so a later run can settle an expired
  active run before starting instead of staying blocked on stale state.
- Added dashboard overview auto-summary fallback logic so the overview can
  summarize completed work, loop results, or `09_report` result tables when the
  loop summary is sparse.
- Added smoke coverage for the fixture researcher workflow, dashboard overview
  summary fallback, Ralph resume/stale-settlement behavior, and `smoke_test.py
  --help`.
- Added a dashboard Overview operations console that summarizes current work,
  completed work, visible `09_report` results/artifacts, blockers, and the next
  command/prompt without exposing raw state by default.
- Added a research-readiness panel, phase map, command board, result-table CSV
  previews, and a safe terminal-like command console with next prompt, recent
  events, validation commands, orchestrator prompt commands, report refresh,
  and Ralph loop templates.
- Added `scripts/commands/dashboard/dashboard_sources.py` and `/api/status.data_sources` so the
  dashboard can prove which state/report/event sources were loaded in server
  and direct-file modes.
- Added a dashboard `Run Readiness Gate`, `Evidence Map`, `Experiment
  Comparison`, and `Blocker Triage` so researchers can decide what to run,
  which claims have evidence, how experiment rows compare, and which blockers
  need action without reading raw state files.
- Added `scripts/commands/dashboard/dashboard_command_runner.py` plus an opt-in
  `scripts/commands/agents/agent_dashboard.py --enable-command-runner` mode for allowlisted
  validation/report-refresh commands from the Console view.
- Added `scripts/commands/dashboard/dashboard_refresh.py` and `prompts/skills/dashboard_refresh.md`
  as the researcher handoff hook for regenerating all dashboard-visible derived
  inputs after a research pass.
- Added `scripts/commands/projects/project_closeout.py` plus project-local closeout skills for
  routing missing claim rows, reviewer-risk gaps, stale workflow state,
  vote-gate issues, and `09_report/` hygiene problems before handoff.
- Added `config/workspace_profile.example.json`, ignored
  `config/workspace_profile.local.json`, and `scripts/commands/release/workspace_profile.py` so
  language, GPU caps, GPU profiles, node defaults, and scheduler commands can
  be configured per user or lab without changing public harness files.
- Added `scripts/commands/projects/import_research_repo.py` and
  `prompts/skills/research_repo_import.md` so an existing research repository
  can be wrapped in a template-backed project, copied under
  `04_code/imported_repo/`, inventoried, and surfaced as a dashboard triage
  task without importing private/generated/large artifacts by default.
- Added bounded multi-agent parallel orchestration through
  `scripts/commands/agents/agent_orchestrator.py` with `status-parallel`,
  `parallel`, `run-prepared`, and `finish-parallel`, including dependency,
  owner, vote, output-path, prepared-prompt, and manifest diagnostics.
- Added machine-readable parallel diagnostics for `next --json`,
  `parallel --json`, command-queue JSON listing, prepared prompt readiness,
  and `state/orchestrator_prompts/parallel_batches/*.json` validation.
- Added GPU scheduler parallel-dispatch diagnostics for `list --json`,
  `plan --json`, dry-run `dispatch`, dry-run `dispatch --json`, explicit
  `dispatch --ids`, and max-parallel mismatch handling so independent
  experiments can fill available GPUs without silently dropping jobs.

### Changed

- Kept publishable template cleanliness in `validate_project.py --strict` and
  mirrored it in the dedicated release check with a
  `--strict-template-state` final-release option.
- Updated `scripts/commands/release/verify_harness.py` to include the release-check metadata gate
  without recursively invoking the full verification suite.
- Reworked dashboard navigation into `Overview`, `Work`, `Results`, and
  `Console`, and `Debug`, moving votes, sessions, events, raw snippets, and
  agent cards out of the default researcher view.
- Removed the visible dashboard health panel from the researcher flow and moved
  low-level source coverage and validation details to Debug as Data Coverage.
- Reworked project template and shared prompts so Claude/Codex agents prefer
  file-state continuation, safe parallel command batches, and GPU scheduler
  dispatch over manual dashboard/Ralph-loop workflows.

## v3.0.0 - 2026-05-16

V3 release of the file-based research-agent workflow harness.
(There is no v2.0.0 entry; that version number was skipped, not lost.)

### Added

- Added `ARCHITECTURE.md` as the system design map for the V3 workflow.
- Added reader-facing research workflow tools:
  - `scripts/commands/projects/project_intake.py`
  - `scripts/commands/experiments/preregistration_helper.py`
  - `scripts/commands/reports/claim_evidence_board.py`
  - `scripts/commands/research/research_audit.py`
- Added shared report snapshot/index infrastructure:
  - `scripts/commands/reports/report_snapshot.py`
  - `scripts/commands/reports/report_index.py`
  - `scripts/harness/workflow_hooks.py`
- Added workflow wiring audit with `scripts/commands/release/workflow_audit.py`.
- Added parseable orchestration contracts:
  - `prompts/shared/research_routing_matrix.md`
  - `prompts/shared/research_handoff_graph.md`
  - `prompts/shared/leader_dispatch_protocol.md`
  - `prompts/shared/risk_confidence_matrix.md`
  - `prompts/shared/research_brain_protocol.md`
- Added `scripts/commands/review/leader_dispatch.py` and `scripts/commands/review/worker_result.py` to validate
  `LEADER DISPATCH` and `WORKER RESULT` blocks.
- Added Ralph loop Codex-runner support, run compaction, and reset cleanup.
- Added session pruning and agent-event reset commands for explicit template or
  release hygiene.
- Added generated `09_report/README.md` indexing for final/report-facing
  artifacts and result tables.

### Changed

- Reworked the dashboard into a cleaner three-view UI:
  - `Overview`
  - `Work Details`
  - `Raw`
- Split dashboard implementation into `dashboard/index.html`,
  `dashboard/styles.css`, and `dashboard/app.js`.
- Made dashboard report results use the same shared report snapshot logic as the
  report index.
- Tightened dashboard live-state behavior so terminal hook events do not linger
  as active work.
- Updated orchestration prompts so generated agent prompts include routing,
  handoff, dispatch, risk/confidence, and reusable-pattern contracts.
- Generalized useful ideas from an external reference dashboard into research-safe
  routing and result contracts without copying reference-specific agents or paths.
- Made GPU instructions use the configured workspace/project GPU cap instead
  of a user-specific hardcoded cap.

### Fixed

- Fixed cases where completed work could fail to surface in the dashboard by
  deriving completed activity from terminal agent events when loop summaries are
  sparse.
- Fixed report-result visibility by refreshing `09_report/README.md` through
  workflow hooks after material state or result changes.
- Fixed template hygiene so generated Ralph runs, generated prompt files,
  generated session directories, event history, lock files, and lost
  `{{PROJECT_NAME}}` placeholders are caught by strict validation.
- Fixed publishable-file checks to require `ARCHITECTURE.md` and `CHANGELOG.md`
  and reject lock/cache artifacts.

### Verification

- `python -m py_compile scripts/*.py`
- `python -m scripts.commands.release.workflow_audit`
- `python -m scripts.commands.release.check_publishable`
- `python -m scripts.commands.projects.validate_project --project template --strict`
- `python -m scripts.commands.release.smoke_test`
- `python -m scripts.commands.release.verify_harness --project template --skip-paper-build`
- `git diff --check`

## v1.0.0 - 2026-05-10

Initial V1 release of the research-agent workspace harness.

- Added root and project-local handoff files for cross-session continuity.
- Added dashboard-visible agent event timelines, session workspaces, pattern memory, vote gates, and bounded Ralph loops.
- Added automatic multi-agent voting for important commands through `scripts/commands/agents/agent_vote.py auto` and `scripts/commands/agents/agent_orchestrator.py dispatch --auto-vote`.
- Added share-token protection for dashboard servers bound to non-local hosts.
- Extended project validation, smoke tests, and harness verification to cover handoffs, events, votes, sessions, pattern memory, Ralph loop state, dashboard JavaScript, and publishable file safety.
