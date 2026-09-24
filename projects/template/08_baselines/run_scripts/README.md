# Baseline Run Scripts

Store wrapper scripts or command templates for running baselines.

Rules:

- Prefer small wrappers that call the original baseline entry point.
- Keep full commands in `08_baselines/baseline_registry.json` and `03_experiments/<exp_id>/run_log.md`.
- Do not hide dataset paths, seeds, or config overrides inside undocumented scripts.
