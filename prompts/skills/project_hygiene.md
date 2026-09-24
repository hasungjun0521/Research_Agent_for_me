# Project Hygiene

Use when a project folder has drifted from the template contract: `09_report/`
is bloated with non-final artifacts, stale `.lock` debris accumulates, top-level
entries appear outside the numbered folders, or diagnostics were never
generated for an idle project.

Project hygiene is a folder-structure diagnosis. It answers: "Does this project
still follow the workspace filesystem contract, and what should move where?"
Use state doctor for state-file consistency and project health for research
routing; use this skill for folder shape, bloat, and debris.

## When To Use

- `09_report/` exceeds a sane reader-facing size (default 200 files / 200 MB)
  or contains caches, checkpoints, or raw logs.
- A project was idle for a while and `state/state_doctor.md` or
  `state/project_health.md` was never generated.
- Stale zero-byte `.lock` files (flock debris) litter the project.
- Quarantined `.corrupt-*` state backups (from `state_doctor --repair`) are
  waiting for inspection.
- Unexpected top-level entries exist (for example an accidental nested
  `projects/` directory).
- Result rows exist but no working claim graph was written.

## Agent Workflow

1. Scan read-only first; nothing is written or deleted by default:

```bash
python -m scripts.commands.projects.project_hygiene --project <project>
python -m scripts.commands.projects.project_hygiene --all
```

2. Resolve high findings first. Missing diagnostics route to
   `state_doctor.md` / `project_health.md` skills; report bloat routes to
   `report_hygiene.md`. Move files deliberately — active code to `04_code/`,
   raw eval output to `05_results/` or `03_experiments/`, snapshots to
   `08_baselines/`. Never bulk-delete research artifacts.
3. Lock debris is the only thing the command may delete, and only when
   explicitly asked. Each lock is probed with a non-blocking flock first, so
   locks held by a live process are skipped, and `template` is always
   scan-only (`--clean-locks`/`--write-report` are not applied to it):

```bash
python -m scripts.commands.projects.project_hygiene --project <project> --clean-locks
```

4. Persist the diagnosis when it should be findable from file state:

```bash
python -m scripts.commands.projects.project_hygiene --project <project> --write-report
```

5. After moves, re-run with `--strict` (non-zero exit while high findings
   remain), then refresh `validate_project --strict` and the diagnostics so
   routing uses the cleaned structure.

## Output

- `state/project_hygiene.md` (with `--write-report`; working diagnostic, never
  exported to `09_report/`)
