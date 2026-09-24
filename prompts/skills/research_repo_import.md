# Research Repo Import

Use this when a user brings an existing research repository and wants it turned
into a structured project under `projects/<name>/`.

## Command

```bash
python -m scripts.commands.projects.import_research_repo --source <path-to-existing-repo> --project <project_name>
```

Use `--dry-run` first when the source is large or unfamiliar. Use
`--record-source-path` only when recording the absolute source path is safe for
the project.

## What It Does

- Creates `projects/<project_name>/` from `projects/template/` unless
  `--into-existing` is used.
- Copies the existing repository snapshot into `04_code/imported_repo/`.
- Skips VCS folders, local environments, logs, datasets, checkpoints, model
  weights, symlinks, private-looking files, and files larger than the configured
  size limit.
- Writes `02_planning/imported_repo_inventory.md`.
- Writes `00_brief/imported_repo_notes.md`.
- Adds a triage-ready `imported_repo_triage` command and next action.

## Guardrails

- Do not import private work into `projects/template/`.
- Do not move imported scratch files into `09_report/` until they are final
  reader-facing artifacts.
- Immediately persist a durable checkpoint with the import summary and triage
  direction:

```bash
python -m scripts.commands.review.progress_checkpoint record \
  --project <project> \
  --agent director \
  --kind result \
  --summary "Imported repository and created imported_repo_triage command" \
  --evidence 02_planning/imported_repo_inventory.md \
  --output 02_planning/imported_repo_inventory.md \
  --next-action "Run imported_repo_triage command" \
  --open-question "What claims, datasets, and experiments should be triaged first?"
```

- Before the next agent pass, run
  `python -m scripts.commands.projects.project_resume --project <project>` so
  the imported-repo triage starts from file state.
