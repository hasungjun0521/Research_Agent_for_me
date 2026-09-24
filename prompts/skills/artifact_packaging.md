# Artifact Packaging

Use this before sharing a project or preparing a submission artifact.

1. Run full verification:
   `python -m scripts.commands.release.verify_harness --project <project> --skip-paper-build`
2. Build a manifest:
   `python -m scripts.commands.reports.artifact_packager --project <project>`
3. Build an archive when needed:
   `python -m scripts.commands.reports.artifact_packager --project <project> --tar`

The package includes final report artifacts plus reproducibility-critical
working evidence such as `03_experiments/data_roots.md`,
`03_experiments/artifact_registry.csv`,
`05_results/experiment_journal.md`, `05_results/experiment_journal.csv`, and
`06_writing/terminology.md`.

The package intentionally excludes large checkpoints, datasets, caches, and VCS
internals. Keep those as separately documented external artifacts.

By default the packager fails when included text files contain local absolute
paths. Move private paths to `config/workspace_profile.local.json`; use
`--allow-local-paths` only for private/internal archives.
