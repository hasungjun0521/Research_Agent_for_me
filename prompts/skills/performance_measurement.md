# Performance Measurement Skill

Use this when code, analysis, or agent workflow is slow.

## Procedure

1. Measure first: wall time, memory, GPU utilization, data loading time, or token count.
2. Identify one bottleneck.
3. Apply one fix.
4. Re-measure and record before/after.
5. Keep optimization patches separate from behavior changes.

## Common Fixes

- Cache parsed metadata instead of rereading large files.
- Use tiny fixtures before full datasets.
- Batch independent analyses.
- Replace broad file reads with `rg` filters and structure reports.
- Reduce prompt context to decision-critical files.
