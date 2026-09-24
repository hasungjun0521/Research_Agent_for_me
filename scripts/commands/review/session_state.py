#!/usr/bin/env python3
"""Manage isolated per-loop session folders under state/sessions/."""

from __future__ import annotations

import argparse
import json
import secrets
import shutil
import sys
from pathlib import Path

from scripts.harness.state import (
    HarnessError,
    append_agent_event,
    atomic_write_json,
    load_json,
    now_iso,
    project_root,
)

SESSION_STATUSES = {"running", "done", "blocked", "waiting"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manage state/sessions/<session_id>/ workspaces.")
    sub = parser.add_subparsers(dest="command", required=True)

    start = sub.add_parser("start", help="Create a session workspace.")
    start.add_argument("--project", required=True)
    start.add_argument("--id", dest="session_id")
    start.add_argument("--loop-id", default="")
    start.add_argument("--goal", required=True)
    start.add_argument("--command-id", action="append", dest="command_ids")
    start.add_argument("--note", default="")

    update = sub.add_parser("update", help="Update a session workspace.")
    update.add_argument("--project", required=True)
    update.add_argument("--id", required=True, dest="session_id")
    update.add_argument("--status", choices=sorted(SESSION_STATUSES))
    update.add_argument("--goal")
    update.add_argument("--command-id", action="append", dest="command_ids")
    update.add_argument("--note")

    finish = sub.add_parser("finish", help="Finish a session workspace.")
    finish.add_argument("--project", required=True)
    finish.add_argument("--id", required=True, dest="session_id")
    finish.add_argument("--status", choices=["done", "blocked", "waiting"], required=True)
    finish.add_argument("--note", default="")

    list_cmd = sub.add_parser("list", help="List sessions.")
    list_cmd.add_argument("--project", required=True)
    list_cmd.add_argument("--json", action="store_true")

    validate = sub.add_parser("validate", help="Validate session folders.")
    validate.add_argument("--project", required=True)

    prune = sub.add_parser("prune", help="Delete a terminal session workspace.")
    prune.add_argument("--project", required=True)
    prune.add_argument("--id", required=True, dest="session_id")
    prune.add_argument(
        "--allow-running",
        action="store_true",
        help="Allow deleting a running session. Use only for template cleanup or explicit operator cleanup.",
    )

    return parser.parse_args()


def sessions_root(root: Path) -> Path:
    return root / "state" / "sessions"


def safe_session_id(session_id: str | None) -> str:
    value = session_id or f"session_{secrets.token_hex(4)}"
    candidate = Path(value)
    if candidate.is_absolute() or len(candidate.parts) != 1 or ".." in candidate.parts:
        raise HarnessError("session id must be a single folder name.")
    return value


def session_path(root: Path, session_id: str) -> Path:
    return sessions_root(root) / safe_session_id(session_id)


def session_json_path(root: Path, session_id: str) -> Path:
    return session_path(root, session_id) / "session.json"


def split_values(values: list[str] | None) -> list[str]:
    result: list[str] = []
    for value in values or []:
        for part in value.split(","):
            stripped = part.strip()
            if stripped and stripped not in result:
                result.append(stripped)
    return result


def default_session(project: str, session_id: str, loop_id: str, goal: str, command_ids: list[str], note: str) -> dict:
    timestamp = now_iso()
    return {
        "project": project,
        "schema_version": 1,
        "session_id": session_id,
        "loop_id": loop_id,
        "status": "running",
        "goal": goal,
        "command_ids": command_ids,
        "created_at": timestamp,
        "updated_at": timestamp,
        "finished_at": "",
        "notes": note,
    }


def validate_session_doc(data: dict, session_id: str) -> list[str]:
    warnings: list[str] = []
    if not isinstance(data, dict):
        raise HarnessError(f"Session {session_id} must be a JSON object.")
    if data.get("session_id") != session_id:
        warnings.append(f"Session {session_id} session_id does not match folder name.")
    if str(data.get("status") or "") not in SESSION_STATUSES:
        raise HarnessError(f"Session {session_id} has invalid status: {data.get('status')!r}.")
    if not str(data.get("goal") or "").strip():
        warnings.append(f"Session {session_id} has no goal.")
    if not isinstance(data.get("command_ids", []), list):
        raise HarnessError(f"Session {session_id} command_ids must be a list.")
    return warnings


def validate_sessions(root: Path) -> list[str]:
    warnings: list[str] = []
    base = sessions_root(root)
    if not base.exists():
        warnings.append("Missing state/sessions/ directory.")
        return warnings
    for path in sorted(base.iterdir()):
        if not path.is_dir():
            continue
        session_file = path / "session.json"
        if not session_file.is_file():
            warnings.append(f"{session_file.relative_to(root)} is missing.")
            continue
        data = load_json(session_file)
        warnings.extend(validate_session_doc(data, path.name))
        for child in ("plans", "results", "artifacts"):
            if not (path / child).is_dir():
                warnings.append(f"{path.relative_to(root)}/{child}/ is missing.")
    return warnings


def write_scratchpad(path: Path, goal: str, note: str) -> None:
    timestamp = now_iso()
    path.write_text(
        "\n".join([
            "# Session Scratchpad",
            f"## Updated: {timestamp}",
            "",
            "## Goal",
            goal,
            "",
            "## Notes",
            note or "No notes recorded yet.",
            "",
        ]),
        encoding="utf-8",
    )


def session_event_status(status: str) -> str:
    if status == "running":
        return "running"
    if status == "blocked":
        return "blocked"
    return "waiting"


def record_session_event(root: Path, event_type: str, session: dict, task: str, outputs: list[str]) -> None:
    append_agent_event(
        root,
        event_type,
        "director",
        status=session_event_status(str(session.get("status") or "")),
        task=task,
        stage="session_state",
        outputs=outputs,
        notes=f"Session {session.get('session_id')}: {session.get('goal', '')}",
    )


def main() -> int:
    args = parse_args()
    try:
        root = project_root(args.project)
        if args.command == "start":
            session_id = safe_session_id(args.session_id)
            path = session_path(root, session_id)
            if path.exists():
                raise HarnessError(f"Session already exists: {session_id}")
            for child in ("plans", "results", "artifacts"):
                (path / child).mkdir(parents=True, exist_ok=True)
            session = default_session(
                root.name,
                session_id,
                args.loop_id,
                args.goal,
                split_values(args.command_ids),
                args.note,
            )
            atomic_write_json(path / "session.json", session)
            write_scratchpad(path / "scratchpad.md", args.goal, args.note)
            record_session_event(
                root,
                "session_state_start",
                session,
                f"Started session {session_id}.",
                [
                    f"state/sessions/{session_id}/session.json",
                    f"state/sessions/{session_id}/scratchpad.md",
                ],
            )
            print(f"started session: {session_id}")
            print(path.relative_to(root).as_posix())
            return 0

        if args.command in {"update", "finish"}:
            session_id = safe_session_id(args.session_id)
            path = session_json_path(root, session_id)
            if not path.is_file():
                raise HarnessError(f"Session not found: {session_id}")
            session = load_json(path)
            if args.command == "finish":
                session["status"] = args.status
                session["finished_at"] = now_iso()
                if args.note:
                    session["notes"] = args.note
            else:
                if args.status:
                    session["status"] = args.status
                if args.goal:
                    session["goal"] = args.goal
                if args.note is not None:
                    session["notes"] = args.note
                for command_id in split_values(args.command_ids):
                    session.setdefault("command_ids", [])
                    if command_id not in session["command_ids"]:
                        session["command_ids"].append(command_id)
            session["updated_at"] = now_iso()
            validate_session_doc(session, session_id)
            atomic_write_json(path, session)
            verb = "updated" if args.command == "update" else "finished"
            record_session_event(
                root,
                f"session_state_{args.command}",
                session,
                f"{verb.title()} session {session_id}.",
                [f"state/sessions/{session_id}/session.json"],
            )
            print(f"{verb} session: {session_id} -> {session['status']}")
            return 0

        if args.command == "list":
            rows = []
            base = sessions_root(root)
            if base.exists():
                for path in sorted(base.glob("*/session.json")):
                    data = load_json(path)
                    rows.append(data)
            if args.json:
                print(json.dumps({"project": args.project, "sessions": rows}, indent=2, ensure_ascii=False))
            else:
                for row in rows:
                    print(f"{row.get('session_id')}\t{row.get('status')}\t{row.get('loop_id')}\t{row.get('goal')}")
            return 0

        if args.command == "validate":
            warnings = validate_sessions(root)
            if warnings:
                for warning in warnings:
                    print(f"warning: {warning}", file=sys.stderr)
                return 1
            print(f"valid sessions: {args.project}")
            return 0

        if args.command == "prune":
            session_id = safe_session_id(args.session_id)
            path = session_path(root, session_id)
            session_file = path / "session.json"
            if not session_file.is_file():
                raise HarnessError(f"Session not found: {session_id}")
            session = load_json(session_file)
            status = str(session.get("status") or "")
            if status == "running" and not args.allow_running:
                raise HarnessError("Refusing to prune a running session without --allow-running.")
            shutil.rmtree(path)
            record_session_event(
                root,
                "session_state_prune",
                session,
                f"Pruned session {session_id}.",
                ["state/sessions/"],
            )
            print(f"pruned session: {session_id}")
            return 0

        raise HarnessError(f"Unknown command: {args.command}")
    except HarnessError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
