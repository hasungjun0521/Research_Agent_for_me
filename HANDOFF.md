# HANDOFF

Use this file as the compact cross-session continuity document for harness
maintenance. Project-local research continuity belongs in
`projects/<name>/HANDOFF.md` and `projects/<name>/state/`.

## Current Automation Pass (2026-09-24)

- Added portable `automation_setup`, official CLI `agent_runner`, and bounded
  `research_autopilot` init/plan/run. Read `docs/automation.md` for exact behavior.
- Setup installs the 13 canonical skills into repository-local Codex discovery
  and merges Claude SessionStart/Stop hooks without replacing existing settings.
- Native Windows fixes cover shared state locking, legacy runner argument parsing,
  privacy scanning, null-device verification and portable smoke fixtures.
- Serial dispatch now checks status/dependencies; parallel conflict checks include
  parent/child output paths. Autopilot requires explicit closeout and changed
  substantive evidence, records session logs, and halts on blockers/time limits.
- The user's pre-existing edits in `projects/template/09_report/README.md` and
  `prompts/agents/README.md` are intentionally preserved outside this change set.
- GitHub publication target: `hasungjun0521/Research_Agent_for_me` (new repository).
  The previous origin is retained; publish through a separate remote. No license has been added;
  an owner license choice remains pending. No live research or GPU runs were
  launched to validate scientific results.
- Validation completed on native Windows/Python 3.11: 310 unit tests passed,
  4 platform/optional tests skipped; ruff, compileall, full harness smoke and the
  complete v8.0.0 release gate passed (`--skip-paper-build --strict-template-state`).
  Actual init/plan/diagnostic CLI flow and two dependent tasks with a local fake
  agent passed. Local detailed gate log: `tmp/release_gate_full.json` (ignored).
  GitHub-hosted Linux/Windows CI and real paid-agent scientific runs have not run.

## Current Workspace Snapshot

- Repository: `research-agent-workspace`, released at v8.0.0
  (2026-06-12); see the `## v8.0.0` section in `CHANGELOG.md`.
- Primary workflow: Claude/Codex native sessions continue from file state and
  use harness CLIs directly.
- Template project: `projects/template`. Real research projects under
  `projects/` are off-limits for harness work beyond read-only scans.
- Dashboard and Ralph loop remain tracked optional legacy/support tooling, not
  the default workflow.

## Operating Rules

`AGENTS.md` is the normative rule list (imported by `CLAUDE.md`); do not
duplicate rules here. Maintenance-specific reminders:

- New commands register in `scripts/harness/commands.py`; a unit test now
  fails if a module with `main()` lands unregistered.
- New skills need all six surfaces: `prompts/skills/<name>.md`, the
  `prompts/skills/README.md` listing, a `prompts/shared/skill_usage.md`
  bullet, the registration tuple in
  `scripts/commands/release/workflow_audit.py`, `.claude/skills/<name>/
  SKILL.md`, and a row in `docs/installed_agent_skills.md`. `workflow_audit`
  now checks the `.claude/skills` surfaces too.
- Unit tests live in `scripts/tests/` only (pytest `testpaths` and CI agree).

## Recent Changes (2026-06-12 maintenance pass)

Driven by an external research-harness survey plus a full internal audit —
synthesis and the ranked adoption backlog live in
`docs/harness_survey_2026-06-12.md`. Summary:

- Weekly dev deck feature (`reports.weekly_deck`) finished and registered:
  command registry, tests moved to `scripts/tests/`, runbook + `weekly-deck`
  skill, docs. Design spec:
  `docs/superpowers/specs/2026-06-12-weekly-dev-deck-design.md`.
- New `log_digest` command for bounded SLURM/training-log digests.
- New agent skills: `literature-review` (with new runbook), `claim-evidence`,
  `baseline-intake`, `weekly-deck`.
- Registration/gate hardening: reverse-direction registry test,
  `.claude/skills` checks in `workflow_audit`, full 34-runbook tuple,
  `state_doctor --write-report` doc fix, fsync in atomic state writes,
  template/root debris removal.
- Batch 2 (commit 030d762): `seed_variance`, `env_capture`, `run_diff`,
  bib hygiene in `source_credibility_audit`, `project_resume --list`.
- Token-cost reduction: dispatched worker prompts default to the lean style
  (~2.4k tokens vs ~16.8k; `--prompt-style full` restores inlining), CLAUDE.md
  cut to Claude-specific deltas, AGENTS.md orchestrator rule compressed, and
  `context_budgeting.md` maps token sinks to cheap substitutes.

See `CHANGELOG.md` `Unreleased` for the complete list.

## Validation Status

v7.0.0 passed the full release gate on 2026-06-10. The v8.0.0 change set
(baseline decoupling, the `split` result-CSV column, CSV I/O centralization with
file locking, the `state.py` StateDoc refactor, and command consolidation) was
repaired on 2026-06-13 after an audit found it had not passed validation, and it
now passes the full gate sequence with all gates green: py_compile OK,
`ruff check scripts` clean, pytest green (226 in scripts/tests), `workflow_audit
OK`, `valid project state: template`, `project.yaml inventory OK`, `harness smoke
test OK`, `verify_harness --skip-paper-build` exit 0, and `release_check
--version v8.0.0 --strict-template-state` OK. Re-run before the next publish:

```bash
python -m py_compile $(find scripts -name '*.py' | sort)
ruff check scripts
python -m pytest -q
python -m scripts.commands.release.workflow_audit
python -m scripts.commands.projects.validate_project --project template --strict
python -m scripts.commands.projects.project_index check
python -m scripts.commands.release.smoke_test
python -m scripts.commands.release.verify_harness --project template --skip-paper-build
```

Before publishing or tagging, also run the release gate:

```bash
python -m scripts.commands.release.release_check --project template --version v8.0.0 --skip-paper-build --strict-template-state
```

## Known Risks And Follow-Up Targets

- The ranked adoption backlog (Tier 1: statement-to-evidence grounding,
  preregistration drift verification, seed-variance audit, val/test split
  lint) lives in `docs/harness_survey_2026-06-12.md` — pick from the top.
- Internal consolidation candidates (same doc): `project_doctor` single
  command, command tiering/consolidation, AGENTS.md as single rule source,
  `state.py` StateDoc refactor, orchestrator/gpu_scheduler unit tests,
  active-project listing, neutral placeholders in the workspace profile
  example.
- `project.yaml` curated `tools`/`project_skills` maps lag the actual
  command/skill set; refresh or document the curation rule.
- README.ko.md is local-only and predates v7 content; retranslate when
  convenient.

## Next Best Command

```text
Continue harness maintenance from file state. Read AGENTS.md, CHANGELOG.md
(Unreleased), and docs/harness_survey_2026-06-12.md, then pick the highest
remaining Tier-1 backlog item (statement-to-evidence grounding audit or
preregistration drift verification) or the project_doctor consolidation.
Run the full gate sequence before claiming done.
```
