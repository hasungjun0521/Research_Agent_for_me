# Agent Quality Audit

Use to check whether prior agent work is actually resumable from files.

## When To Use

- A session feels hard to continue from state files.
- Commands are marked done but outputs are unclear.
- Experiment result checkpoints lack explanation.
- You need to judge agent handoff quality before continuing.

## Agent Workflow

1. Audit agent events, progress checkpoints, command queue, and done outputs.
2. Flag done events without output files.
3. Flag experiment results without analysis/rationale.
4. Use findings to repair memory, next actions, or experiment journals before continuing.

## Output

- `07_reviews/agent_quality_audit.md`
