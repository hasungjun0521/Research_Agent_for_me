---
name: release-closeout
description: Finalize a research project for handoff, sharing, publication, or harness release. Use when the user says "wrap up / finalize / package / publish / share / release / submit" a project or the harness. Bundles the closeout audit, 09_report hygiene, privacy/publishable audit, and artifact packaging so nothing private leaks and the final-artifact folder stays clean. Wraps project_closeout, validate_project, privacy_audit, check_publishable, verify_harness, and artifact_packager.
---

# Release & Closeout

Entrypoint for the END of a project: handoff, sharing, publication, or harness
release. Bundles four runbooks: `prompts/skills/project_closeout.md`,
`prompts/skills/report_hygiene.md`, `prompts/skills/privacy_publish_audit.md`,
`prompts/skills/artifact_packaging.md`.

## 1. Closeout audit (routing)

```bash
python -m scripts.commands.projects.project_closeout --project <name> --write-report
```
Read the audit output as routing — each issue maps to a follow-up skill/runbook
(e.g. `project_health`, `state_doctor`, `claim_graph`, `artifact_registry`,
`report_hygiene`). Resolve before declaring handoff-ready.

## 2. Report hygiene (09_report is final-artifact-only)

Move scratch Markdown / working notes out of `09_report/` into the right folder
(`04_code/`, `05_results/`, `07_reviews/`, `08_baselines/`, `03_experiments/exp_*/`).
Leave `09_report/README.md` as the only Markdown at report root. Preserve
evidence — do not delete unless the user explicitly asks.

## 3. Validate

```bash
python -m scripts.commands.projects.validate_project --project <name> --strict
```

## 4. Privacy / publishable audit (before any sharing or tagging)

```bash
python -m scripts.commands.release.privacy_audit
python -m scripts.commands.release.check_publishable
```
Look for: private project names leaking into root docs/prompts/scripts, local
absolute paths (home/lab checkout), user-specific GPU rules that belong in
`config/workspace_profile.local.json`, unignored real project files. Replace
visible private names with `<private_project>`. Rerun `privacy_audit` after any
HANDOFF/README/prompt/release-note edit.

## 5. Package the artifact (when sharing/submitting)

```bash
python -m scripts.commands.release.verify_harness --project <name> --skip-paper-build
python -m scripts.commands.reports.artifact_packager --project <name>          # manifest
python -m scripts.commands.reports.artifact_packager --project <name> --tar     # archive
```
Packager fails on local absolute paths in included text — move them to the local
profile; use `--allow-local-paths` only for private/internal archives. Large
checkpoints/datasets/caches are intentionally excluded — document them as
external artifacts.

## 6. Harness release gate (when tagging the harness itself)

```bash
python -m scripts.commands.release.release_check --project template --version <vX.Y.Z> --skip-paper-build --strict-template-state
```

## Guardrails

- Do not edit real project state just to pass a publish audit.
- Keep `config/workspace_profile.local.json` ignored and out of git.
- A project is not handoff-ready until closeout audit + strict validation pass.
