#!/usr/bin/env python3
"""Manage state/agent_messages.json for agent-to-agent coordination."""

from __future__ import annotations

import argparse
import sys

from scripts.harness.state import (
    MESSAGE_KINDS,
    MESSAGE_PRIORITIES,
    MESSAGE_STATUSES,
    HarnessError,
    agent_messages_path,
    append_agent_event,
    default_agent_messages,
    load_agent_messages,
    mutate_agent_messages,
    now_iso,
    project_root,
    write_agent_messages,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage agent-to-agent messages.")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="Create agent_messages.json if missing.")
    init.add_argument("--project", required=True)

    send = sub.add_parser("send", help="Send a message from one agent to another.")
    send.add_argument("--project", required=True)
    send.add_argument("--id", required=True)
    send.add_argument("--from-agent", required=True)
    send.add_argument("--to-agent", required=True)
    send.add_argument("--kind", choices=sorted(MESSAGE_KINDS), default="request")
    send.add_argument("--priority", choices=sorted(MESSAGE_PRIORITIES), default="medium")
    send.add_argument("--subject", required=True)
    send.add_argument("--body", required=True)
    send.add_argument("--related-command-id", default="")
    send.add_argument("--related-claim-id", default="")
    send.add_argument("--related-exp-id", default="")
    send.add_argument("--required-response", default="")

    update = sub.add_parser("update", help="Update message metadata or status.")
    update.add_argument("--project", required=True)
    update.add_argument("--id", required=True)
    update.add_argument("--status", choices=sorted(MESSAGE_STATUSES))
    update.add_argument("--priority", choices=sorted(MESSAGE_PRIORITIES))
    update.add_argument("--to-agent")
    update.add_argument("--subject")
    update.add_argument("--body")
    update.add_argument("--response")

    respond = sub.add_parser("respond", help="Respond to a message and optionally resolve it.")
    respond.add_argument("--project", required=True)
    respond.add_argument("--id", required=True)
    respond.add_argument("--from-agent", required=True, help="Agent writing the response.")
    respond.add_argument("--response", required=True)
    respond.add_argument("--status", choices=sorted(MESSAGE_STATUSES), default="resolved")

    list_cmd = sub.add_parser("list", help="List messages.")
    list_cmd.add_argument("--project", required=True)
    list_cmd.add_argument("--agent", help="Show messages sent to or from this agent.")
    list_cmd.add_argument("--status", choices=sorted(MESSAGE_STATUSES))

    return parser.parse_args()


def find_message(messages: list[dict], message_id: str) -> dict:
    for message in messages:
        if message.get("id") == message_id:
            return message
    raise HarnessError(f"Message not found: {message_id}")


def message_event_status(message: dict) -> str:
    status = str(message.get("status") or "").lower()
    if status == "blocked":
        return "blocked"
    return "waiting"


def record_message_event(root, event_type: str, agent: str, message: dict, task: str) -> None:
    append_agent_event(
        root,
        event_type,
        agent,
        status=message_event_status(message),
        task=task,
        stage="agent_messages",
        outputs=["state/agent_messages.json"],
        notes=f"Message {message.get('id')} {message.get('from_agent')}->{message.get('to_agent')}: {message.get('subject', '')}",
    )


def main() -> int:
    args = parse_args()
    try:
        root = project_root(args.project)
        if args.command == "init":
            path = agent_messages_path(root)
            if path.exists():
                data = load_agent_messages(root)
            else:
                data = default_agent_messages(args.project)
                write_agent_messages(root, data)
            print(f"messages: {len(data['messages'])}")
            return 0

        timestamp = now_iso()
        if args.command == "send":
            sent_message: dict = {}

            def send_message(data: dict) -> None:
                nonlocal sent_message
                if any(message.get("id") == args.id for message in data["messages"]):
                    raise HarnessError(f"Message already exists: {args.id}")
                sent_message = {
                    "id": args.id,
                    "from_agent": args.from_agent,
                    "to_agent": args.to_agent,
                    "kind": args.kind,
                    "priority": args.priority,
                    "status": "open",
                    "subject": args.subject,
                    "body": args.body,
                    "related_command_id": args.related_command_id,
                    "related_claim_id": args.related_claim_id,
                    "related_exp_id": args.related_exp_id,
                    "required_response": args.required_response,
                    "response": "",
                    "created_at": timestamp,
                    "updated_at": timestamp,
                    "resolved_at": "",
                }
                data["messages"].append(sent_message)
            mutate_agent_messages(root, send_message)
            record_message_event(root, "agent_message_send", args.from_agent, sent_message, f"Sent message {args.id}.")
            print(f"sent: {args.id}")
            return 0

        if args.command == "update":
            updated_message: dict = {}

            def update_message(data: dict) -> None:
                nonlocal updated_message
                message = find_message(data["messages"], args.id)
                for field in ("status", "priority", "to_agent", "subject", "body", "response"):
                    value = getattr(args, field, None)
                    if value is not None:
                        message[field] = value
                message["updated_at"] = timestamp
                if args.status == "resolved" and not message.get("resolved_at"):
                    message["resolved_at"] = timestamp
                updated_message = dict(message)
            mutate_agent_messages(root, update_message)
            record_message_event(
                root,
                "agent_message_update",
                str(updated_message.get("from_agent") or "director"),
                updated_message,
                f"Updated message {args.id}.",
            )
            print(f"updated: {args.id}")
            return 0

        if args.command == "respond":
            responded_message: dict = {}

            def respond_to_message(data: dict) -> None:
                nonlocal responded_message
                message = find_message(data["messages"], args.id)
                if message.get("to_agent") != args.from_agent:
                    raise HarnessError(
                        f"Only recipient {message.get('to_agent')} can respond; got {args.from_agent}."
                    )
                message["response"] = args.response
                message["status"] = args.status
                message["updated_at"] = timestamp
                if args.status == "resolved":
                    message["resolved_at"] = timestamp
                responded_message = dict(message)
            mutate_agent_messages(root, respond_to_message)
            record_message_event(root, "agent_message_respond", args.from_agent, responded_message, f"Responded to message {args.id}.")
            print(f"responded: {args.id}")
            return 0

        if args.command == "list":
            data = load_agent_messages(root)
            for message in data["messages"]:
                if args.status and message.get("status") != args.status:
                    continue
                if args.agent and args.agent not in {message.get("from_agent"), message.get("to_agent")}:
                    continue
                print(
                    f"{message['id']}\t{message['status']}\t{message['priority']}\t"
                    f"{message.get('from_agent', '')}->{message.get('to_agent', '')}\t"
                    f"{message.get('subject', '')}"
                )
            return 0

        raise HarnessError(f"Unknown command: {args.command}")
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
