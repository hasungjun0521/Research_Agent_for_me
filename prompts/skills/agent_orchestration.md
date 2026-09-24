# Agent Orchestration

Use this when command queue work should become one or more concrete agent
passes. If more than one independent command is open, inspect and prepare a
bounded parallel batch before falling back to one serial agent pass.

Default trigger: use this proactively for deep research, broad codebase
inspection, multi-file implementation, independent experiment batches,
baseline/source comparisons, or result-analysis splits. The user does not need
to explicitly request "multi-agent" before you inspect parallelization
opportunities. Always keep the immediate blocking/critical-path task local, and
dispatch only independent sidecar work that can proceed without waiting on your
next local step.

1. Check routing, handoff, risk, and reusable patterns before dispatch:
   `prompts/shared/research_routing_matrix.md`,
   `prompts/shared/research_handoff_graph.md`,
   `prompts/shared/risk_confidence_matrix.md`, and
   `prompts/shared/research_brain_protocol.md`
2. Inspect parallel state before serial work:
   `python -m scripts.commands.agents.agent_orchestrator status-parallel --project <project>`
   `python -m scripts.commands.review.command_queue list --project <project> --verbose`
   `python -m scripts.commands.review.command_queue list --project <project> --json`
   Use `open_parallel_diagnostics` to fix missing outputs, unfinished
   dependencies, duplicate owner selection, or path conflicts before falling
   back to serial work.
   Treat prepared prompts marked `waiting:<dependency_ids>` as blocked until the
   listed `depends_on` commands are done. In command queue output, use
   `dependency_ready` and `unfinished_dependencies` to explain why a command is
   not safe to parallelize yet.
3. If multiple independent open commands are ready, plan a parallel batch:
   `python -m scripts.commands.agents.agent_orchestrator parallel --project <project> --max-agents 4`
   Use `--json` when another agent needs `open_parallel_diagnostics` together
   with the planned command list.
   Explicit `parallel --id <cmd>` requests should fail with a reason when a
   requested command is not safe; do not treat missing ids from the result as a
   harmless skip.
4. Write prompts for a safe parallel batch:
   `python -m scripts.commands.agents.agent_orchestrator parallel --project <project> --max-agents 4 --write`
5. If the user configured an external runner profile, use it for immediate
   concurrent execution when the batch is safe:
   `python -m scripts.commands.agents.agent_orchestrator parallel --project <project> --max-agents 4 --write --execute --runner-profile <profile>`
   Use `--runner-command` only for one-off local overrides:
   `python -m scripts.commands.agents.agent_orchestrator parallel --project <project> --max-agents 4 --write --execute --runner-command "<agent-cli> --prompt-file {prompt_file}"`
6. If prompts were already written in an earlier session, inspect and run them:
   `python -m scripts.commands.agents.agent_orchestrator run-prepared --project <project> --group <group> --dry-run`
   `python -m scripts.commands.agents.agent_orchestrator run-prepared --project <project> --group <group> --runner-profile <profile>`
   `python -m scripts.commands.agents.agent_orchestrator run-prepared --project <project> --group <group> --runner-command "<agent-cli> --prompt-file {prompt_file}"`
   `run-prepared` must fail rather than launch a scoped prepared command whose `depends_on` entries are not done.
7. After reviewing worker outputs, finish the scoped prepared batch:
   `python -m scripts.commands.agents.agent_orchestrator finish-parallel --project <project> --group <group> --status done --dry-run`
   `python -m scripts.commands.agents.agent_orchestrator finish-parallel --project <project> --group <group> --status done --note "<verification>"`
   or
   `python -m scripts.commands.agents.agent_orchestrator finish-parallel --project <project> --group <group> --status done --result-file <command_id>=<worker-result-path>`
8. Inspect the next dispatchable command when no safe parallel batch exists:
   `python -m scripts.commands.agents.agent_orchestrator next --project <project>`
   Use `next --json` when another agent needs the serial fallback plus
   `open_parallel_diagnostics` in one payload.
9. Render the prompt before execution:
   `python -m scripts.commands.agents.agent_orchestrator prompt --project <project> --id <command_id> --write`
10. Dispatch the command:
   `python -m scripts.commands.agents.agent_orchestrator dispatch --project <project> --id <command_id>`
11. When the work is verified, finish it:
   `python -m scripts.commands.agents.agent_orchestrator finish --project <project> --id <command_id> --status done --note "<verification>"`

External runner execution is opt-in. Prefer `--runner-profile` when
`config/workspace_profile.local.json` defines
`agent_runners.profiles.<name>.command`; use `--runner-command` only when the
user explicitly wants a one-off command override. If no runner profile is
configured, still write safe parallel prompts and record the batch manifest so
the user or the next agent can run prepared workers later. Runner profiles must be
non-interactive commands that accept the prepared `{prompt_file}` and return
control to the harness.
Parallel batches require independent commands: unresolved `depends_on` values,
shared expected output paths, and input/output dependencies are excluded from
the batch. Harness-managed checkpoint files such as `state/current_state.md`,
`state/agent_memory.md`, `state/next_actions.md`, `state/open_questions.md`,
`state/agent_status.json`, and `state/agent_events.jsonl` are coordination
outputs, not substantive work products; do not use them as the only
`expected_outputs` for a command that should be parallel-ready.
When a lead-style agent decomposes follow-up work, require the block from
`prompts/shared/leader_dispatch_protocol.md` and validate it with
`python -m scripts.commands.review.leader_dispatch validate --file <dispatch-output.md>`.
Then apply valid `dispatch_workers` blocks with
`python -m scripts.commands.review.leader_dispatch apply --project <project> --file <dispatch-output.md>`
so `depends_on`, `parallel_group`, and `expected_outputs` flow into
`state/command_queue.json` before parallel planning.
Use `--write-parallel-prompts` with `leader_dispatch apply` when the dispatch
should immediately write safe worker prompts and mark the selected commands
`in progress` without invoking an external runner.
Use `--all-prepared` only when intentionally running prepared prompts across
all groups; it must still fail when any selected prepared prompt has unfinished
dependencies.
When using explicit `--id` values with `run-prepared` or `finish-parallel`, the
ids must already refer to prepared `in progress` commands; invalid explicit ids
should fail rather than be skipped.
Mark it `blocked`/`deferred` with an explicit note when needed. Never mark a
parallel batch `done` in a non-dry-run close without a verification note or
evidence output/result file, and never mark it `blocked` or `deferred` without
a reason note.
