# ADR-011: Dashboard-Free Health And Routing Surfaces

## Status

Accepted

## Date

2026-06-05

## Context

The workspace originally preserved dashboard and Ralph-loop support, but the
normal user workflow has moved toward Claude/Codex native sessions plus
file-based project state. Users should not need to open a browser dashboard or
manually inspect raw JSON to understand whether a research project is ready to
continue.

The v6 workflow also adds more required working evidence:

- dashboard-free project health and stale-state diagnostics
- rough-idea brief intake
- smoke-first experiment DAGs
- working claim graphs
- baseline source-structure comparison
- agent continuity quality audit

Without one dashboard-free routing surface, these features could become hidden
advanced commands. A fresh agent could miss them, or a closeout pass could treat
starter files as real evidence.

## Decision

Use file-based health and routing artifacts as the default project-status layer:

- `state/project_health.md` is the plain-language project health report.
- `state/state_doctor.md` is the stale/contradictory state diagnostic report.
- Health/doctor reports include recommended agent requests and suggested
  command-queue entries.
- Suggested command entries support dry-run preview before enqueueing.
- Enqueued health-derived commands use a `health_` prefix.
- Enqueued doctor-derived commands use a `doctor_` prefix.
- Empty starter files are not treated as evidence. Health and closeout checks
  distinguish file existence from useful contents, especially for
  `03_experiments/experiment_dag.json` and `05_results/claim_graph.json`.

The browser dashboard remains optional support tooling. It must not be required
for normal continuation, closeout, or release-readiness reasoning.

## Alternatives Considered

### Keep Dashboard As The Default Status Surface

Rejected. It forces a UI-first workflow even though users usually operate
through Claude/Codex sessions. It also makes headless continuation and GitHub
usage less clear.

### Only Add CLI Commands Without Health Reports

Rejected. Raw CLI output is less durable than Markdown project state and does
not give a fresh session an obvious read-first status file.

### Let Agents Hand-Edit Command Queue JSON From Health Findings

Rejected. Command routing must stay structured and traceable. The health/doctor
CLIs provide dry-run preview and enqueue paths so agents can route work without
manual JSON edits.

## Consequences

- Fresh sessions should read `state/project_health.md` and
  `state/state_doctor.md` before choosing work.
- If either file is missing or still a starter file, agents should refresh it
  before trusting it.
- Project closeout and artifact packaging treat health, state diagnostics,
  experiment DAGs, claim graphs, baseline comparisons, and agent quality audits
  as working evidence for resumability and rigor.
- Final reader-facing artifacts still belong in `09_report/`; health/doctor and
  claim graph files remain working-state evidence unless explicitly exported
  through final report workflows.

## Follow-Up Rules

- Keep dashboard references optional and legacy/support-oriented.
- Prefer preview-first routing for health/state-doctor suggestions.
- Do not mark a project ready just because starter evidence files exist.
- Keep command queue updates traceable to their diagnostic source.
