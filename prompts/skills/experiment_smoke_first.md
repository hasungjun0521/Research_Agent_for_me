# Experiment Smoke-First Skill

Use this before expensive experiments or baseline reproductions.

## Procedure

1. Run import/config/data-loader checks on a tiny fixture.
2. Run one forward/eval step if a model exists.
3. Verify output files are created in the expected directory.
4. If the smoke test is CPU-heavy, long-running, or likely to interfere with
   interactive CPU work, queue it as a bounded GPU smoke job through
   `gpu_scheduler add`, inspect `gpu_scheduler plan`, then use
   `gpu_scheduler dispatch --execute` only after the local GPU profile is
   enabled.
5. Record the smoke command and result before full-scale launch.
6. Only queue the full run after the smoke result is clean or the remaining risk is documented.

## Evidence

Record:

- command
- config
- dataset fixture
- observed output path
- CPU/GPU resource choice and reason
- failure or pass reason
