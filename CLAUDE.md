@AGENTS.md

# Claude Code Instructions

This file is the Claude Code entrypoint. It imports the shared `AGENTS.md`
rules above; everything there applies. The sections below are only the
Claude-specific deltas — kept deliberately short because this file is loaded
into every session.

## Startup

- Harness maintenance: read `HANDOFF.md` first; `ARCHITECTURE.md` when the task
  touches workflow design; `README.md` for user workflow context.
- Project work: run `python -m scripts.commands.projects.project_resume
  --project <name>` (or `--list` to find the active project), then read that
  project's `HANDOFF.md` and `state/` files before deciding. Dispatched tasks
  follow the rendered prompt under the project `state/` folder plus the role
  prompt in `prompts/agents/`.
- The user talks to Claude, not the Python harness: run the harness CLIs
  yourself instead of telling the user which command to run.

## Claude-Specific Rules

- Prefer Claude Code's own session/background capabilities plus the harness
  command queue/orchestrator. The workspace Ralph loop
  (`scripts.commands.review.ralph_loop`) is legacy/optional; if an external
  runner is needed, use the generic `--execute --runner-command` path, not the
  Codex-specific flags.
- `prompts/skills/` are Markdown runbooks, not installed tools — load only the
  files relevant to the task (`prompts/skills/README.md` is the index). Codex
  skill references in `prompts/shared/skill_usage.md` are workflow guidance,
  not available tools.
- `.claude/skills/` agent skills are auto-discovered lifecycle entrypoints
  (see `docs/installed_agent_skills.md`); prefer them over re-deriving
  workflows.
- Mark long-running work through `scripts.commands.agents.agent_status`
  (running / heartbeat / done / blocked) and use
  `scripts.commands.agents.agent_messages` for questions, blockers, and
  cross-agent handoffs.
- The dashboard is optional support tooling: no dashboard/UI work unless
  explicitly requested. If touched, keep `dashboard/index.html` as markup,
  `dashboard/styles.css` as styling, and JavaScript in external scripts; park
  removed behavior with restoration notes.
- Keep user-facing docs "ask Claude/Codex to do the work" first, with Python
  commands as implementation details.

## Token Discipline

- Never read large logs directly — use
  `python -m scripts.commands.experiments.log_digest --log <path>`.
- Use `project_resume --list` instead of scanning every project's state to
  find the active project.
- When `state/agent_memory.md` has grown with many old checkpoint blocks,
  compact it (`python -m scripts.commands.review.memory_compact --project
  <name> --apply`) so the always-loaded file stops taxing context.
- Dispatched worker prompts default to the lean style (shared contracts as
  read-on-demand pointers). Pass `--prompt-style full` only when a runner
  cannot read repository files.
- Read `prompts/skills/context_budgeting.md` before long multi-step passes;
  do not re-read large static docs (`scripts/README.md`, `ARCHITECTURE.md`)
  when a `--help` or a targeted grep answers the question.
