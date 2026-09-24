---
name: project-hygiene
description: Tidy the folder structure of projects under projects/<name>/. Use when 09_report/ is bloated with non-final artifacts (caches, checkpoints, raw eval dumps, copied source trees), stale .lock debris accumulates, unexpected top-level entries appear (e.g. accidental nested projects/), diagnostics were never generated for an idle project, or the user asks to "clean up / tidy / organize" project folders. Read-only by default; wraps scripts.commands.projects.project_hygiene.
---

# Project Hygiene

Folder-structure diagnosis and cleanup routing for this file-based research
workspace. Source runbook: `prompts/skills/project_hygiene.md` (see also
`prompts/skills/report_hygiene.md` for the 09_report move rules).

## When to use

- `09_report/` exceeds the reader-facing ceiling (default 200 files / 200 MB)
  or contains `__pycache__`, `.pyc`, checkpoints (`.pt/.pth/.ckpt/.safetensors`),
  or raw logs.
- An idle project never generated `state/state_doctor.md` /
  `state/project_health.md`.
- Stale zero-byte `.lock` files (flock debris) litter the project tree.
- Unexpected top-level entries exist outside the numbered template folders.
- Result rows exist in `05_results/experiment_results.csv` but no claim graph.

## Workflow

1. Scan read-only first (single project or the whole workspace):
   ```bash
   python -m scripts.commands.projects.project_hygiene --project <name>
   python -m scripts.commands.projects.project_hygiene --all
   ```
   Nothing is written or deleted by default.

2. Resolve high findings first, using the suggested commands in the output:
   - missing diagnostics → `state_doctor --write-report`, then
     `project_health --write` (doctor first, health second);
   - report bloat/junk → follow `prompts/skills/report_hygiene.md`: move active
     code to `04_code/`, raw eval output to `05_results/` or
     `03_experiments/`, snapshots to `08_baselines/`. Move deliberately;
     never bulk-delete research artifacts.

3. Lock debris is the only thing the command itself may delete, and only when
   explicitly asked. Locks are probed with a non-blocking flock first so a
   lock held by a live process is never removed, and `template` is always
   scan-only (`--clean-locks`/`--write-report` are skipped for it):
   ```bash
   python -m scripts.commands.projects.project_hygiene --project <name> --clean-locks
   ```

4. Persist the diagnosis so the next session can find it from file state:
   ```bash
   python -m scripts.commands.projects.project_hygiene --project <name> --write-report
   ```
   This writes `state/project_hygiene.md` (a working diagnostic — never export
   it to `09_report/`).

5. After moves, re-run with `--strict` (exits non-zero while high findings
   remain), then refresh `validate_project --strict` and the diagnostics.

## Guardrails

- Do not move or delete research artifacts without reporting what moves where;
  the command intentionally only reports them.
- Do not run `--clean-locks` or `--write-report` against projects the user
  asked you not to touch; the plain scan is always safe.
- Use harness CLIs for any state JSON the findings route into; never hand-edit
  `state/command_queue.json`.
