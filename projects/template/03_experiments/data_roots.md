# Experiment Data Roots

Use this file to keep dataset roots, derived-data locations, and split files
auditable. Do not put credentials or private access tokens here.

| Data ID | Root / URI | Split / Version | Produced By | Used By Experiments | Status | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| pending_dataset_root | pending | pending split/version | user or data intake agent | exp_001 | planned | Replace with concrete dataset root, split/version, and provenance before running experiments. |

## Rules

- Keep raw data, derived data, cache directories, and evaluation splits separate.
- Record whether each path is local, shared storage, object storage, or a
  generated artifact.
- If a root is machine-specific, store the stable identifier here and put the
  exact private path in `config/workspace_profile.local.json` or local notes
  that are not committed.
- Before expensive runs, confirm the data root, split, and checksum or version
  are the intended ones.
