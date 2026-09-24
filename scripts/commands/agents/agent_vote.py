#!/usr/bin/env python3
"""Manage multi-agent votes for high-risk commands and decisions."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from scripts.harness.runner_commands import split_runner_command
from scripts.harness.state import (
    HarnessError,
    append_agent_event,
    evaluate_vote_decision,
    find_vote_decision,
    latest_vote_counts,
    load_agent_votes,
    load_command_queue,
    mutate_agent_votes,
    mutate_command_queue,
    now_iso,
    project_root,
    repo_root,
    split_values,
    update_agent_status,
    validate_agent_votes_doc,
    write_agent_votes,
)
from scripts.harness.workflow_hooks import refresh_report_index


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage state/agent_votes.json.")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create agent_votes.json if missing.")
    init.add_argument("--project", required=True)

    open_cmd = sub.add_parser("open", help="Open a vote decision.")
    open_cmd.add_argument("--project", required=True)
    open_cmd.add_argument("--id", required=True)
    open_cmd.add_argument("--title", required=True)
    open_cmd.add_argument("--rationale", required=True)
    open_cmd.add_argument("--risk-level", choices=["low", "medium", "high", "critical"], default="high")
    open_cmd.add_argument("--command-id", default="")
    open_cmd.add_argument("--required-voter", action="append", dest="required_voters")
    open_cmd.add_argument("--min-approvals", type=int, default=2)
    open_cmd.add_argument("--max-rejections", type=int, default=0)

    vote = sub.add_parser("vote", help="Record or replace one agent's vote.")
    vote.add_argument("--project", required=True)
    vote.add_argument("--id", required=True, dest="decision_id")
    vote.add_argument("--agent", required=True)
    vote.add_argument("--vote", choices=["approve", "reject", "abstain"], required=True)
    vote.add_argument("--confidence", choices=["low", "medium", "high"], default="medium")
    vote.add_argument("--rationale", required=True)

    status = sub.add_parser("status", help="Show one decision or all decisions.")
    status.add_argument("--project", required=True)
    status.add_argument("--id", dest="decision_id")
    status.add_argument("--json", action="store_true")

    cancel = sub.add_parser("cancel", help="Cancel an open vote decision.")
    cancel.add_argument("--project", required=True)
    cancel.add_argument("--id", required=True, dest="decision_id")
    cancel.add_argument("--reason", default="")

    auto = sub.add_parser("auto", help="Generate vote prompts and optionally run voter agents.")
    auto.add_argument("--project", required=True)
    auto.add_argument("--id", dest="decision_id")
    auto.add_argument("--command-id", default="")
    auto.add_argument("--voter", action="append", dest="voters")
    auto.add_argument("--risk-level", choices=["low", "medium", "high", "critical"], default="high")
    auto.add_argument("--min-approvals", type=int, default=2)
    auto.add_argument("--prompt-dir", default="state/vote_prompts")
    auto.add_argument("--execute", action="store_true")
    auto.add_argument("--runner-command", help="Command template. Supports {prompt_file}, {project}, {vote_id}, and {agent}.")

    validate = sub.add_parser("validate", help="Validate agent_votes.json.")
    validate.add_argument("--project", required=True)

    return parser.parse_args()


def find_command(queue: dict, command_id: str) -> dict | None:
    for command in queue.get("commands", []):
        if command.get("id") == command_id:
            return command
    return None


def mark_command_requires_vote(root, command_id: str, vote_id: str, risk_level: str) -> None:
    if not command_id:
        return

    def mutate(queue: dict) -> None:
        command = find_command(queue, command_id)
        if command is None:
            raise HarnessError(f"Command not found: {command_id}")
        command["requires_vote"] = True
        command["vote_id"] = vote_id
        command["risk_level"] = risk_level
        command["updated_at"] = now_iso()

    mutate_command_queue(root, mutate)


def decision_summary(decision: dict) -> str:
    counts = latest_vote_counts(decision)
    return (
        f"{decision.get('id')}\t{decision.get('status')}\t{decision.get('risk_level')}\t"
        f"approve={counts['approve']} reject={counts['reject']} abstain={counts['abstain']}\t"
        f"{decision.get('title')}"
    )


def sync_vote_lifecycle(
    root: Path,
    *,
    event_type: str,
    agent: str,
    decision_id: str,
    status: str,
    task: str,
    notes: str,
    outputs: list[str] | None = None,
) -> None:
    outputs = outputs or ["state/agent_votes.json"]
    update_agent_status(
        root,
        agent,
        status,
        task=task,
        stage=event_type,
        outputs=outputs,
        notes=notes,
        append_note=True,
    )
    append_agent_event(
        root,
        event_type,
        agent,
        status=status,
        task=task,
        stage=event_type,
        outputs=outputs,
        notes=f"{notes} Vote decision: {decision_id}.",
    )
    refresh_report_index(root)


def safe_project_relative_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise HarnessError("Path must be project-relative and must not contain '..'.")
    return path


def read_prompt_file(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="replace").strip()


def render_vote_prompt(root: Path, decision: dict, voter: str) -> str:
    prompts = repo_root() / "prompts"
    role_prompt = read_prompt_file(prompts / "agents" / f"{voter}.md")
    shared = "\n\n".join(
        text for text in (
            read_prompt_file(prompts / "shared" / "research_context.md"),
            read_prompt_file(prompts / "shared" / "output_contracts.md"),
            read_prompt_file(prompts / "shared" / "filesystem_safety_rules.md"),
        )
        if text
    )
    payload = {
        "project": root.name,
        "voter": voter,
        "decision": decision,
        "response_contract": {
            "vote": "approve | reject | abstain",
            "confidence": "low | medium | high",
            "rationale": "one concise paragraph grounded in files and risk",
        },
    }
    return "\n\n".join([
        f"# Auto Vote Prompt: {decision.get('id')} / {voter}",
        "You are an independent voter in the file-based research-agent workspace.",
        "Review the decision and cast one vote. Do not approve unless the rationale, rollback path, and expected evidence are adequate.",
        "Return these tags exactly:",
        "<vote>approve|reject|abstain</vote>",
        "<confidence>low|medium|high</confidence>",
        "<rationale>your rationale</rationale>",
        "## Voter Role Prompt",
        role_prompt or f"Act as {voter}.",
        "## Shared Contracts",
        shared,
        "## Vote Payload",
        "```json\n" + json.dumps(payload, indent=2, ensure_ascii=False) + "\n```",
    ]) + "\n"


def vote_prompt_path(root: Path, prompt_dir: str, decision_id: str, voter: str) -> Path:
    rel = safe_project_relative_path(prompt_dir)
    safe_voter = voter.replace("/", "_").replace(" ", "_")
    return root / rel / decision_id / f"{safe_voter}.md"


def write_vote_prompt(root: Path, prompt_dir: str, decision: dict, voter: str) -> Path:
    path = vote_prompt_path(root, prompt_dir, str(decision["id"]), voter)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_vote_prompt(root, decision, voter), encoding="utf-8")
    return path


def tag_value(text: str, tag: str) -> str:
    match = re.search(fr"<{tag}>\s*(.*?)\s*</{tag}>", text, flags=re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else ""


def parse_vote_response(output: str) -> tuple[str, str, str]:
    vote = tag_value(output, "vote").lower()
    confidence = tag_value(output, "confidence").lower() or "medium"
    rationale = tag_value(output, "rationale") or output.strip()[:800] or "Runner returned no rationale."
    if vote not in {"approve", "reject", "abstain"}:
        vote = "abstain"
        rationale = f"Runner response was not parseable as an approval vote. Raw summary: {rationale}"
    if confidence not in {"low", "medium", "high"}:
        confidence = "medium"
    return vote, confidence, rationale


def runner_argv(template: str, *, prompt_file: Path, project: str, vote_id: str, agent: str) -> list[str]:
    if not template:
        raise HarnessError("--runner-command is required with --execute.")
    rendered = template.format(
        prompt_file=str(prompt_file),
        project=project,
        vote_id=vote_id,
        agent=agent,
    )
    return split_runner_command(rendered)


def record_agent_vote(root: Path, decision_id: str, agent: str, vote_value: str, confidence: str, rationale: str) -> dict:
    def mutate(data: dict) -> None:
        decision = find_vote_decision(data, decision_id)
        if decision is None:
            raise HarnessError(f"Vote decision not found: {decision_id}")
        if str(decision.get("status") or "") in {"approved", "rejected", "cancelled"}:
            raise HarnessError(f"Vote decision is already {decision.get('status')}.")
        votes = [
            vote for vote in decision.get("votes", [])
            if vote.get("agent") != agent
        ]
        votes.append({
            "agent": agent,
            "vote": vote_value,
            "confidence": confidence,
            "rationale": rationale,
            "created_at": now_iso(),
        })
        decision["votes"] = votes
        decision["status"] = evaluate_vote_decision(decision)
        decision["outcome"] = decision["status"] if decision["status"] != "open" else ""
        decision["updated_at"] = now_iso()

    data = mutate_agent_votes(root, mutate)
    decision = find_vote_decision(data, decision_id)
    if decision is None:
        raise HarnessError(f"Vote decision not found after update: {decision_id}")
    return decision


def ensure_vote_for_command(
    root: Path,
    command_id: str,
    *,
    voters: list[str],
    risk_level: str,
    min_approvals: int,
) -> str:
    command = find_command(load_command_queue(root), command_id)
    if command is None:
        raise HarnessError(f"Command not found: {command_id}")
    vote_id = str(command.get("vote_id") or f"vote_{command_id}")
    voters = voters or ["director", "critic"]
    if min_approvals < 1:
        raise HarnessError("--min-approvals must be at least 1.")

    def mutate(data: dict) -> None:
        if find_vote_decision(data, vote_id):
            return
        timestamp = now_iso()
        data["decisions"].append({
            "id": vote_id,
            "title": f"Approve command {command_id}",
            "rationale": str(command.get("why_now") or command.get("display_summary") or command.get("action") or "Important command requires approval."),
            "related_command_id": command_id,
            "risk_level": str(command.get("risk_level") or risk_level),
            "status": "open",
            "required_voters": voters,
            "min_approvals": min_approvals,
            "max_rejections": 0,
            "votes": [],
            "outcome": "",
            "created_at": timestamp,
            "updated_at": timestamp,
        })

    mutate_agent_votes(root, mutate)
    mark_command_requires_vote(root, command_id, vote_id, risk_level)
    return vote_id


def auto_vote_decision(
    root: Path,
    decision_id: str,
    *,
    voters: list[str],
    prompt_dir: str,
    execute: bool,
    runner_command: str | None,
) -> dict:
    data = load_agent_votes(root)
    decision = find_vote_decision(data, decision_id)
    if decision is None:
        raise HarnessError(f"Vote decision not found: {decision_id}")
    if str(decision.get("status") or "") in {"approved", "rejected", "cancelled"}:
        return decision
    voters = voters or [
        str(voter).strip()
        for voter in decision.get("required_voters", [])
        if str(voter).strip()
    ] or ["director", "critic"]
    for voter in voters:
        latest = load_agent_votes(root)
        decision = find_vote_decision(latest, decision_id)
        if decision is None:
            raise HarnessError(f"Vote decision not found: {decision_id}")
        if str(decision.get("status") or "") in {"approved", "rejected", "cancelled"}:
            return decision
        if any(vote.get("agent") == voter for vote in decision.get("votes", [])):
            continue
        prompt_file = write_vote_prompt(root, prompt_dir, decision, voter)
        if not execute:
            print(prompt_file.relative_to(root).as_posix())
            continue
        argv = runner_argv(
            runner_command or "",
            prompt_file=prompt_file,
            project=root.name,
            vote_id=decision_id,
            agent=voter,
        )
        completed = subprocess.run(argv, cwd=repo_root(), text=True, capture_output=True, check=False)
        output = (completed.stdout or "") + (completed.stderr or "")
        if completed.returncode != 0:
            vote_value = "abstain"
            confidence = "low"
            rationale = f"Runner exited with {completed.returncode}. Output: {output[:800]}"
        else:
            vote_value, confidence, rationale = parse_vote_response(output)
        decision = record_agent_vote(root, decision_id, voter, vote_value, confidence, rationale)
        print(decision_summary(decision))
    latest = load_agent_votes(root)
    decision = find_vote_decision(latest, decision_id)
    if decision is None:
        raise HarnessError(f"Vote decision not found: {decision_id}")
    return decision


def main() -> int:
    args = parse_args()
    try:
        root = project_root(args.project)
        if args.command == "init":
            votes = load_agent_votes(root)
            write_agent_votes(root, votes)
            print(f"votes: {len(votes.get('decisions', []))}")
            return 0

        if args.command == "open":
            required_voters = split_values(args.required_voters)
            if args.min_approvals < 1:
                raise HarnessError("--min-approvals must be at least 1.")
            if args.max_rejections < 0:
                raise HarnessError("--max-rejections must be non-negative.")

            def mutate(data: dict) -> None:
                if find_vote_decision(data, args.id):
                    raise HarnessError(f"Vote decision already exists: {args.id}")
                timestamp = now_iso()
                data["decisions"].append({
                    "id": args.id,
                    "title": args.title,
                    "rationale": args.rationale,
                    "related_command_id": args.command_id,
                    "risk_level": args.risk_level,
                    "status": "open",
                    "required_voters": required_voters,
                    "min_approvals": args.min_approvals,
                    "max_rejections": args.max_rejections,
                    "votes": [],
                    "outcome": "",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                })

            mutate_agent_votes(root, mutate)
            mark_command_requires_vote(root, args.command_id, args.id, args.risk_level)
            sync_vote_lifecycle(
                root,
                event_type="agent_vote_open",
                agent="director",
                decision_id=args.id,
                status="waiting",
                task=f"Opened vote decision {args.id}.",
                notes=f"Vote opened for risk level {args.risk_level}; required voters: {', '.join(required_voters) or 'not specified'}.",
            )
            print(f"opened vote: {args.id}")
            return 0

        if args.command == "vote":
            decision = record_agent_vote(
                root,
                args.decision_id,
                args.agent,
                args.vote,
                args.confidence,
                args.rationale,
            )
            sync_vote_lifecycle(
                root,
                event_type="agent_vote_cast",
                agent=args.agent,
                decision_id=args.decision_id,
                status="waiting",
                task=f"Cast {args.vote} vote for {args.decision_id}.",
                notes=f"Vote confidence: {args.confidence}; decision status is {decision.get('status')}.",
            )
            print(decision_summary(decision))
            return 0

        if args.command == "auto":
            voters = split_values(args.voters)
            decision_id = args.decision_id or ""
            if args.command_id:
                decision_id = ensure_vote_for_command(
                    root,
                    args.command_id,
                    voters=voters,
                    risk_level=args.risk_level,
                    min_approvals=args.min_approvals,
                )
            if not decision_id:
                raise HarnessError("--id or --command-id is required for auto voting.")
            decision = auto_vote_decision(
                root,
                decision_id,
                voters=voters,
                prompt_dir=args.prompt_dir,
                execute=args.execute,
                runner_command=args.runner_command,
            )
            prompt_output = f"{safe_project_relative_path(args.prompt_dir).as_posix()}/{decision_id}/"
            sync_vote_lifecycle(
                root,
                event_type="agent_vote_auto",
                agent="director",
                decision_id=decision_id,
                status="waiting",
                task=f"Ran automatic voting for {decision_id}.",
                notes=f"Automatic vote status is {decision.get('status')}; execute={bool(args.execute)}.",
                outputs=["state/agent_votes.json", prompt_output],
            )
            print(decision_summary(decision))
            return 0 if not args.execute or str(decision.get("status") or "") == "approved" else 1

        if args.command == "cancel":
            def mutate(data: dict) -> None:
                decision = find_vote_decision(data, args.decision_id)
                if decision is None:
                    raise HarnessError(f"Vote decision not found: {args.decision_id}")
                decision["status"] = "cancelled"
                decision["outcome"] = args.reason or "cancelled"
                decision["updated_at"] = now_iso()

            mutate_agent_votes(root, mutate)
            sync_vote_lifecycle(
                root,
                event_type="agent_vote_cancel",
                agent="director",
                decision_id=args.decision_id,
                status="waiting",
                task=f"Cancelled vote decision {args.decision_id}.",
                notes=args.reason or "Vote cancelled.",
            )
            print(f"cancelled vote: {args.decision_id}")
            return 0

        if args.command == "status":
            data = load_agent_votes(root)
            decisions = data.get("decisions", [])
            if args.decision_id:
                decision = find_vote_decision(data, args.decision_id)
                if decision is None:
                    raise HarnessError(f"Vote decision not found: {args.decision_id}")
                decisions = [decision]
            if args.json:
                print(json.dumps({"project": args.project, "decisions": decisions}, indent=2, ensure_ascii=False))
            else:
                for decision in decisions:
                    print(decision_summary(decision))
            return 0

        if args.command == "validate":
            data = load_agent_votes(root)
            warnings = validate_agent_votes_doc(data)
            if warnings:
                for warning in warnings:
                    print(f"warning: {warning}", file=sys.stderr)
                return 1
            print(f"valid agent votes: {args.project}")
            return 0

        raise HarnessError(f"Unknown command: {args.command}")
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
