# Context Budgeting Skill

Use this when token cost or context size is a risk.

## Procedure

1. Start with `rg`/file lists before reading full files.
2. Read only the files needed for the current decision.
3. Summarize long files into claim, evidence, blocker, next action.
4. Prefer structured state files over repeated prose history.
5. Stop reading once the next concrete action is determined.
6. When session context is about 20-30% used, refresh the relevant handoff with
   the compact continuation state. Use root `HANDOFF.md` for harness
   maintenance and `projects/<name>/HANDOFF.md` for project-local research
   state. If context is already 20-30% remaining, refresh only the critical
   facts needed to resume safely.

## Known Token Sinks And Their Cheap Substitutes

- Training/SLURM logs: never read end to end — use
  `python -m scripts.commands.experiments.log_digest --log <path>`
  (bounded head/tail/failure-pattern digest).
- Finding the active project: `python -m scripts.commands.projects.project_resume --list`
  instead of reading every project's state files.
- Command usage questions: `python -m scripts.commands.<group>.<command> --help`
  or a targeted grep, not a full read of `scripts/README.md` (~17k tokens) or
  `ARCHITECTURE.md` (~4k tokens).
- Dispatched worker prompts: the orchestrator's default lean style references
  shared contracts as read-on-demand pointers (~2k tokens) instead of inlining
  them (~17k tokens); workers read only the contracts their command needs.
- Comparing two runs: `python -m scripts.commands.experiments.run_diff`
  instead of opening both experiment folders file by file.
- A bloated always-loaded memory file: `python -m
  scripts.commands.review.memory_compact --project <name> --apply` archives old
  `state/agent_memory.md` checkpoint blocks so every later resume reads less.

## Output

Keep the handoff compact:

- Decision:
- Evidence files:
- Unknowns:
- Next action:

For cross-session continuation, use the relevant `HANDOFF.md` as the durable
handoff file and include an init prompt when the next session needs a specific
starting shape.
