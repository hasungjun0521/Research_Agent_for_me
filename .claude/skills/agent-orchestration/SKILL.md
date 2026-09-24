---
name: agent-orchestration
description: Dispatch independent command-queue work as bounded multi-agent passes. Use proactively (no need for the user to say "multi-agent") for deep research, broad codebase review, multi-file implementation, independent experiment batches, baseline/code/result-review splits — any work where separate agents own disjoint files/questions. Keep the critical-path task local; dispatch only safe independent sidecar work. Wraps scripts.commands.agents.agent_orchestrator.
---

# Agent Orchestration

Turn open command-queue work into one or more concrete agent passes. Prefer a
bounded parallel batch when multiple independent commands are ready; fall back to
a serial pass otherwise. Source: `prompts/skills/agent_orchestration.md`.

Always keep the immediate blocking/critical-path task local. Dispatch only
independent sidecar work that proceeds without waiting on your next local step.
Never batch commands with unresolved `depends_on`, shared output paths,
unapproved vote gates, or unclear ownership.

## Workflow

1. Inspect parallel state before serial work:
   ```bash
   python -m scripts.commands.agents.agent_orchestrator status-parallel --project <project>
   python -m scripts.commands.review.command_queue list --project <project> --verbose
   ```
   Use `open_parallel_diagnostics` / `unfinished_dependencies` to explain why a
   command is not yet safe to parallelize.

2. Plan a safe parallel batch (preview), then write prompts:
   ```bash
   python -m scripts.commands.agents.agent_orchestrator parallel --project <project> --max-agents 4
   python -m scripts.commands.agents.agent_orchestrator parallel --project <project> --max-agents 4 --write
   ```
   Explicit `parallel --id <cmd>` must fail with a reason when a command is
   unsafe — a missing id is not a harmless skip.

3. Execute. Prefer a configured runner profile when one exists:
   ```bash
   python -m scripts.commands.agents.agent_orchestrator parallel --project <project> \
     --max-agents 4 --write --execute --runner-profile <profile>
   ```
   Use `--runner-command "<agent-cli> --prompt-file {prompt_file}"` only for a
   one-off override.

4. If prompts were prepared in an earlier session, run them (dry-run first):
   ```bash
   python -m scripts.commands.agents.agent_orchestrator run-prepared --project <project> --group <group> --dry-run
   python -m scripts.commands.agents.agent_orchestrator run-prepared --project <project> --group <group> --runner-profile <profile>
   ```
   `run-prepared` must fail rather than launch a command with unfinished
   `depends_on`. Use `--all-prepared` only to intentionally run every group.

5. Serial fallback when no safe batch exists:
   ```bash
   python -m scripts.commands.agents.agent_orchestrator next --project <project>
   python -m scripts.commands.agents.agent_orchestrator prompt --project <project> --id <command_id> --write
   python -m scripts.commands.agents.agent_orchestrator dispatch --project <project> --id <command_id>
   ```

6. After verifying worker outputs, close the batch / command:
   ```bash
   python -m scripts.commands.agents.agent_orchestrator finish-parallel --project <project> --group <group> --status done --note "<verification>"
   python -m scripts.commands.agents.agent_orchestrator finish --project <project> --id <command_id> --status done --note "<verification>"
   ```

## Guardrails

- Never mark a batch `done` without a verification note or evidence/result file;
  never mark `blocked`/`deferred` without a reason note.
- Harness checkpoint files (`state/current_state.md`, `agent_memory.md`,
  `next_actions.md`, etc.) are coordination outputs, not substantive work
  products — don't use them as a command's only `expected_outputs`.
