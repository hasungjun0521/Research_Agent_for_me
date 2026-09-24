# Privacy Publish Audit

Use this skill before publishing, sharing, or tagging the harness.

## Procedure

```bash
python -m scripts.commands.release.privacy_audit
python -m scripts.commands.release.check_publishable
python -m scripts.commands.release.release_check --project template --version v8.0.0 --skip-paper-build --strict-template-state
```

## What To Look For

- Private project directory names leaking into root docs, dashboard code, prompts,
  or scripts.
- Local absolute paths such as home directories or lab checkout paths.
- User-specific GPU rules that should live in `config/workspace_profile.local.json`.
- External reference workspace names or reference-domain product names.
- Unignored real project files under `projects/`.

## Guardrails

- Do not edit real project state just to pass a publish audit.
- Replace visible private names with `<private_project>` or `<project_name>`.
- Keep `config/workspace_profile.local.json` ignored and out of git.
- Rerun `python -m scripts.commands.release.privacy_audit` after any HANDOFF, README, dashboard,
  prompt, or release-note edit.
