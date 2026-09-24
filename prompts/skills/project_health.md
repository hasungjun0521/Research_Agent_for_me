# Project Health

Use as the dashboard-free project status surface.

Project health is a research progress report, not a final paper report and not
a browser dashboard. It answers: "Is this project moving correctly, what is
blocked, and what should the next agent do first?"

Use state doctor instead when the main problem is contradictory or missing file
state rather than research progress quality.

## When To Use

- Starting a new continuation session.
- The user asks what is left or whether the project is healthy.
- Dashboard is disabled or should not be used.
- You need a plain-language next best action from current file state.

## Agent Workflow

1. Generate or refresh `state/project_health.md`.
2. Treat critical/high issues as the default next action unless the user overrides.
3. If `state/project_health.md` or `state/state_doctor.md` is still a starter
   file, refresh state doctor first, then project health before trusting the
   reported status.
4. If the user wants the recommended work routed, preview the suggested command
   entries first, then enqueue them instead of hand-editing
   `state/command_queue.json`. Health-derived commands use a `health_` id
   prefix for traceability.
   Check each suggested command's required inputs before enqueueing; repair
   commands should not require files that the repair itself is supposed to
   recreate.
5. Do not export this to `09_report/`; it is working state.
6. If health is poor because state is inconsistent, run state doctor next.

## Output

- `state/project_health.md`
