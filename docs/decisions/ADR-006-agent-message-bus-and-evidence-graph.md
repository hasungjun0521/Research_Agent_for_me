# ADR-006: Add Agent Message Bus And Evidence Graph IDs

## Status
Accepted

## Date
2026-05-10

## Context
The workspace can assign commands to agents and validate research rigor gates. However, command ownership is too coarse for peer-like interaction between specialized agents. A code agent may need a data analyst to confirm a metric, a writing agent may need the result interpreter to verify claim strength, and a critic may need the experiment designer to respond to a reviewer-risk blocker.

The research artifacts also need stable IDs so claims, experiments, baselines, result rows, robustness checks, and messages can be connected automatically.

## Decision
Add two linked contracts:

- `state/agent_messages.json` is the agent-to-agent message bus for questions, handoffs, review requests, blockers, decisions, and informational notes.
- `scripts/commands/agents/agent_messages.py` is the only supported writer for that file.
- `claim_id`, `experiment_id`, and `baseline_id` are required in final report tables when rows are present.
- `scripts/commands/projects/validate_project.py --strict` checks message schema, unknown agent/message references, unresolved high-priority blockers, and claim/experiment/baseline cross-references.

The command queue remains the user-visible work queue. Agent messages are narrower coordination records between role agents.

## Alternatives Considered

### Encode Agent Interaction In Command Notes

This keeps one state file, but it buries important questions and blockers inside command text. It is hard for a recipient agent to find its open requests.

### Use One Markdown Inbox Per Agent

This is easy to read, but hard to validate and hard for the dashboard to summarize. JSON gives stable fields, statuses, and references.

### Build A Live Chat Server

This would be richer, but it adds runtime complexity. The workspace already uses file-based coordination, so a JSON message bus fits the existing model.

## Consequences

- Agents can interact without relying on hidden conversation state.
- High-priority blockers become visible and block strict validation until resolved.
- Claims and results are easier to audit because final tables carry stable IDs.
- File-state summaries can show open agent-to-agent messages separately from
  user-visible commands. The optional dashboard can render the same information
  when enabled.
