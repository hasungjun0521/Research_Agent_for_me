# Workflow State Reconcile

Use this skill when validation or project closeout reports stale command
owners, running experiments without running agents, or commands that bypass vote
gates.

## Diagnose

Start with:

```bash
python -m scripts.commands.projects.project_closeout --project <project>
python -m scripts.commands.projects.validate_project --project <project> --strict
```

## Reconcile Commands And Agents

- If work is genuinely running, mark the owner running:

```bash
python -m scripts.commands.agents.agent_status start --project <project> --agent <agent> --command-id <cmd_id> --task "<current task>"
```

- If work stopped, finish or block it with the owning script:

```bash
python -m scripts.commands.agents.agent_status finish --project <project> --agent <agent> --command-id <cmd_id> --status done --task "<completed task>"
python -m scripts.commands.review.command_queue update --project <project> --id <cmd_id> --status blocked --note "<blocker>"
```

## Reconcile Vote Gates

- If the command should require approval, open or complete the vote through
  `scripts/commands/agents/agent_vote.py`; do not remove vote requirements by editing JSON.
- If a command already ran without approval, record the risk decision explicitly
  before treating the result as valid.

## Closeout

```bash
python -m scripts.commands.projects.project_closeout --project <project> --write-report
```

Dashboard refresh is not part of this default skill. Use
`prompts/skills/dashboard_refresh.md` only when dashboard mode is explicitly
enabled.
