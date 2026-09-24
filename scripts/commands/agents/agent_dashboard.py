#!/usr/bin/env python3
"""Serve a lightweight local dashboard for research-agent status."""

from __future__ import annotations

import argparse
import json
import mimetypes
import secrets
import socket
import sys
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

try:
    from scripts.harness import repo_root as harness_repo_root
except ModuleNotFoundError:
    from scripts.harness import repo_root as harness_repo_root

try:
    from scripts.commands.dashboard.dashboard_command_runner import (
        command_catalog,
        run_dashboard_command,
    )
    from scripts.commands.dashboard.dashboard_sources import build_dashboard_sources
    from scripts.commands.reports.report_snapshot import build_report_snapshot
    from scripts.harness.state import (
        HarnessError,
        discover_run_states,
        load_agent_events,
        load_agent_messages,
        load_agent_votes,
        load_command_queue,
        load_gpu_queue,
        load_loop_summary,
        load_pattern_memory,
        load_ralph_loop,
        validate_agent_events,
        validate_agent_messages_doc,
        validate_agent_status_doc,
        validate_agent_votes_doc,
        validate_command_queue_doc,
        validate_gpu_queue_doc,
        validate_loop_summary_doc,
        validate_pattern_memory_doc,
        validate_ralph_loop_doc,
        validate_run_state_doc,
    )
    from scripts.harness.workspace_profile import public_workspace_profile
except ModuleNotFoundError:
    from scripts.commands.dashboard.dashboard_command_runner import (
        command_catalog,
        run_dashboard_command,
    )
    from scripts.commands.dashboard.dashboard_sources import build_dashboard_sources
    from scripts.commands.reports.report_snapshot import build_report_snapshot
    from scripts.harness.state import (
        HarnessError,
        discover_run_states,
        load_agent_events,
        load_agent_messages,
        load_agent_votes,
        load_command_queue,
        load_gpu_queue,
        load_loop_summary,
        load_pattern_memory,
        load_ralph_loop,
        validate_agent_events,
        validate_agent_messages_doc,
        validate_agent_status_doc,
        validate_agent_votes_doc,
        validate_command_queue_doc,
        validate_gpu_queue_doc,
        validate_loop_summary_doc,
        validate_pattern_memory_doc,
        validate_ralph_loop_doc,
        validate_run_state_doc,
    )
    from scripts.harness.workspace_profile import public_workspace_profile


DEFAULT_PORT = 8765
ACTIVE_STATUSES = {"running"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Serve a local dashboard for project agent status."
    )
    parser.add_argument(
        "--project",
        default="template",
        help="Default project folder under projects/.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind.")
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Port to bind. Default: {DEFAULT_PORT}.",
    )
    parser.add_argument(
        "--share-token",
        default="",
        help="Require this token as a URL query parameter before serving the dashboard or API.",
    )
    parser.add_argument(
        "--unsafe-no-token",
        action="store_true",
        help="Allow non-local dashboard binding without --share-token. Not recommended.",
    )
    parser.add_argument(
        "--enable-command-runner",
        action="store_true",
        help="Enable allowlisted local command execution from the Console view.",
    )
    return parser.parse_args()


def repo_root() -> Path:
    return harness_repo_root()


def dashboard_html() -> str:
    return (repo_root() / "dashboard" / "index.html").read_text(encoding="utf-8")


def dashboard_asset(name: str) -> str:
    if name not in {"core.js", "app.js", "styles.css"}:
        raise FileNotFoundError(f"Dashboard asset not found: {name}")
    return (repo_root() / "dashboard" / name).read_text(encoding="utf-8")


def project_root(project_name: str) -> Path:
    if not project_name:
        raise ValueError("Project name is required.")
    candidate = Path(project_name)
    if candidate.is_absolute() or len(candidate.parts) != 1 or ".." in candidate.parts:
        raise ValueError("Project name must be a single folder name under projects/.")
    root = repo_root() / "projects" / candidate
    if not root.is_dir():
        raise FileNotFoundError(f"Project not found: {project_name}")
    return root


def read_text(path: Path, max_chars: int = 6000) -> str:
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n\n[truncated]"


def read_json_file(path: Path, fallback: dict) -> dict:
    if not path.is_file():
        return fallback
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return fallback
    return data if isinstance(data, dict) else fallback


def load_status_file(root: Path) -> dict:
    path = root / "state" / "agent_status.json"
    if not path.is_file():
        return {
            "project": root.name,
            "last_updated": "",
            "active_status_values": sorted(ACTIVE_STATUSES),
            "agents": [],
        }
    return json.loads(path.read_text(encoding="utf-8"))


def load_session_summaries(root: Path) -> list[dict]:
    sessions_dir = root / "state" / "sessions"
    if not sessions_dir.is_dir():
        return []
    sessions: list[dict] = []
    for path in sorted(sessions_dir.glob("*/session.json")):
        data = read_json_file(path, {})
        if data:
            sessions.append(data)
    return sessions


def safe_mtime(path: Path) -> float:
    if not path.exists():
        return 0.0
    return path.stat().st_mtime


def iso_from_timestamp(timestamp: float) -> str:
    if timestamp <= 0:
        return ""
    return datetime.fromtimestamp(timestamp, timezone.utc).astimezone().isoformat(timespec="seconds")


def normalize_status(status: object) -> str:
    return str(status or "").strip().lower()


def parse_timestamp(value: object) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value))
    except ValueError:
        return None


def extract_current_stage(current_state: str) -> str:
    lines = current_state.splitlines()
    for index, line in enumerate(lines):
        if line.strip().lower() == "## current stage":
            for candidate in lines[index + 1 :]:
                stripped = candidate.strip()
                if stripped:
                    return stripped.strip("`")
    return ""


def build_health_warnings(root: Path, status: dict, command_queue: dict, run_states: list[dict], loop_summary: dict, agent_messages: dict, gpu_queue: dict, agent_votes: dict, pattern_memory: dict, ralph_loop: dict) -> list[str]:
    warnings: list[str] = []
    try:
        warnings.extend(validate_agent_status_doc(status))
    except HarnessError as exc:
        warnings.append(f"agent_status.json invalid: {exc}")
    try:
        warnings.extend(validate_command_queue_doc(command_queue))
    except HarnessError as exc:
        warnings.append(f"command_queue.json invalid: {exc}")
    try:
        warnings.extend(validate_loop_summary_doc(loop_summary))
    except HarnessError as exc:
        warnings.append(f"loop_summary.json invalid: {exc}")
    try:
        warnings.extend(validate_agent_messages_doc(agent_messages))
    except HarnessError as exc:
        warnings.append(f"agent_messages.json invalid: {exc}")
    try:
        warnings.extend(validate_agent_votes_doc(agent_votes))
    except HarnessError as exc:
        warnings.append(f"agent_votes.json invalid: {exc}")
    try:
        warnings.extend(validate_agent_events(root))
    except HarnessError as exc:
        warnings.append(f"agent_events.jsonl invalid: {exc}")
    try:
        warnings.extend(validate_pattern_memory_doc(pattern_memory))
    except HarnessError as exc:
        warnings.append(f"pattern_memory.json invalid: {exc}")
    try:
        warnings.extend(validate_ralph_loop_doc(ralph_loop))
    except HarnessError as exc:
        warnings.append(f"ralph_loop.json invalid: {exc}")
    try:
        warnings.extend(validate_gpu_queue_doc(gpu_queue))
    except HarnessError as exc:
        warnings.append(f"gpu_experiment_queue.json invalid: {exc}")

    known_agents = {agent.get("name") for agent in status.get("agents", []) if isinstance(agent, dict)}
    agents_by_name = {
        agent.get("name"): agent
        for agent in status.get("agents", [])
        if isinstance(agent, dict) and agent.get("name")
    }
    for command in command_queue.get("commands", []):
        owner = str(command.get("owner_agent") or "")
        if owner and "/" not in owner and owner not in known_agents and owner != "user":
            warnings.append(f"Command {command.get('id')} references unknown owner_agent: {owner}")
        if normalize_status(command.get("status")) == "in progress":
            owner_agents = [part.strip() for part in owner.replace(",", "/").split("/") if part.strip()]
            concrete_owners = [agent for agent in owner_agents if agent in agents_by_name]
            if not concrete_owners:
                warnings.append(f"Command {command.get('id')} is in progress but has no known agent owner.")
            elif not any(normalize_status(agents_by_name[name].get("status")) == "running" for name in concrete_owners):
                warnings.append(f"Command {command.get('id')} is in progress but no owner agent is running.")

    command_ids = {command.get("id") for command in command_queue.get("commands", []) if isinstance(command, dict)}
    exp_ids = {path.name for path in (root / "03_experiments").glob("exp_*") if path.is_dir()}
    for message in agent_messages.get("messages", []):
        from_agent = str(message.get("from_agent") or "")
        to_agent = str(message.get("to_agent") or "")
        message_id = message.get("id", "<unknown>")
        if from_agent and from_agent not in known_agents and from_agent != "user":
            warnings.append(f"Message {message_id} references unknown from_agent: {from_agent}")
        if to_agent and to_agent not in known_agents and to_agent != "user":
            warnings.append(f"Message {message_id} references unknown to_agent: {to_agent}")
        command_id = message.get("related_command_id")
        if command_id and command_id not in command_ids:
            warnings.append(f"Message {message_id} references unknown related_command_id: {command_id}")
        exp_id = message.get("related_exp_id")
        if exp_id and exp_id not in exp_ids:
            warnings.append(f"Message {message_id} references unknown related_exp_id: {exp_id}")
        if (
            normalize_status(message.get("kind")) == "blocker"
            and normalize_status(message.get("priority")) == "high"
            and normalize_status(message.get("status")) in {"open", "acknowledged", "blocked"}
        ):
            warnings.append(f"High-priority blocker message is unresolved: {message_id}")

    now = datetime.now().astimezone()
    for agent in status.get("agents", []):
        if normalize_status(agent.get("status")) != "running":
            continue
        updated_at = parse_timestamp(agent.get("updated_at"))
        if not updated_at:
            warnings.append(f"Running agent {agent.get('name')} has no valid updated_at heartbeat.")
            continue
        age_seconds = (now - updated_at).total_seconds()
        if age_seconds > 600:
            warnings.append(f"Running agent {agent.get('name')} heartbeat is stale ({int(age_seconds // 60)} minutes).")

    for run_state in run_states:
        try:
            warnings.extend(validate_run_state_doc(run_state))
        except HarnessError as exc:
            warnings.append(f"run_state for {run_state.get('exp_id', '<unknown>')} invalid: {exc}")
        if normalize_status(run_state.get("status")) != "running":
            continue
        updated_at = parse_timestamp(run_state.get("updated_at"))
        if not updated_at:
            warnings.append(f"Running experiment {run_state.get('exp_id')} has no valid heartbeat.")
            continue
        age_seconds = (now - updated_at).total_seconds()
        if age_seconds > 600:
            warnings.append(f"Running experiment {run_state.get('exp_id')} heartbeat is stale ({int(age_seconds // 60)} minutes).")
    return warnings


def build_dashboard_data(project_name: str) -> dict:
    root = project_root(project_name)
    status = load_status_file(root)
    agents = status.get("agents", [])
    active_statuses = {
        normalize_status(value)
        for value in (status.get("active_status_values") or sorted(ACTIVE_STATUSES))
    }

    running_agents = [
        agent.get("display_name") or agent.get("name", "")
        for agent in agents
        if normalize_status(agent.get("status")) in active_statuses
    ]
    waiting_agents = [
        agent.get("display_name") or agent.get("name", "")
        for agent in agents
        if normalize_status(agent.get("status")) == "waiting"
    ]
    blocked_count = sum(
        1 for agent in agents if normalize_status(agent.get("status")) == "blocked"
    )

    current_state = read_text(root / "state" / "current_state.md")
    next_actions = read_text(root / "state" / "next_actions.md")
    command_queue = load_command_queue(root)
    loop_summary = load_loop_summary(root)
    agent_messages = load_agent_messages(root)
    agent_events = load_agent_events(root)
    agent_votes = load_agent_votes(root)
    pattern_memory = load_pattern_memory(root)
    ralph_loop = load_ralph_loop(root)
    sessions = load_session_summaries(root)
    gpu_queue = load_gpu_queue(root)
    report_snapshot = build_report_snapshot(root)
    data_sources = build_dashboard_sources(root)
    dataset_registry = read_json_file(root / "03_experiments" / "dataset_registry.json", {"datasets": []})
    metric_registry = read_json_file(root / "03_experiments" / "metric_registry.json", {"metrics": []})
    run_states = discover_run_states(root)
    files_for_mtime = [
        root / "state" / "agent_status.json",
        root / "state" / "command_queue.json",
        root / "state" / "loop_summary.json",
        root / "state" / "agent_messages.json",
        root / "state" / "agent_events.jsonl",
        root / "state" / "agent_votes.json",
        root / "state" / "pattern_memory.json",
        root / "state" / "ralph_loop.json",
        root / "state" / "gpu_experiment_queue.json",
        root / "state" / "current_state.md",
        root / "state" / "next_actions.md",
        root / "state" / "open_questions.md",
        root / "02_planning" / "director_plan.md",
        root / "09_report" / "README.md",
        *sorted((root / "09_report" / "results").glob("**/*")),
        *sorted((root / "state" / "sessions").glob("*/session.json")),
    ]
    last_file_update = max(safe_mtime(path) for path in files_for_mtime)

    return {
        "project": status.get("project") or root.name,
        "project_path": str(root.relative_to(repo_root())),
        "workspace_profile": public_workspace_profile(repo_root()),
        "last_updated": status.get("last_updated", ""),
        "active_status_values": sorted(active_statuses),
        "current_stage": extract_current_stage(current_state),
        "agents": agents,
        "command_queue": command_queue,
        "loop_summary": loop_summary,
        "agent_messages": agent_messages,
        "agent_events": agent_events,
        "agent_votes": agent_votes,
        "sessions": sessions,
        "pattern_memory": pattern_memory,
        "ralph_loop": ralph_loop,
        "report_snapshot": report_snapshot,
        "data_sources": data_sources,
        "gpu_experiment_queue": gpu_queue,
        "dataset_registry": dataset_registry,
        "metric_registry": metric_registry,
        "experiment_runs": run_states,
        "health_warnings": build_health_warnings(root, status, command_queue, run_states, loop_summary, agent_messages, gpu_queue, agent_votes, pattern_memory, ralph_loop),
        "current_state_excerpt": current_state,
        "next_actions_excerpt": next_actions,
        "summary": {
            "active_count": len(running_agents),
            "total_count": len(agents),
            "blocked_count": blocked_count,
            "running_agents": [name for name in running_agents if name],
            "waiting_agents": [name for name in waiting_agents if name],
            "last_file_update": iso_from_timestamp(last_file_update),
        },
    }


def list_projects(default_project: str) -> dict:
    projects_dir = repo_root() / "projects"
    projects = sorted(path.name for path in projects_dir.iterdir() if path.is_dir())
    return {
        "projects": projects,
        "default_project": default_project if default_project in projects else (projects[0] if projects else ""),
    }


class DashboardHandler(BaseHTTPRequestHandler):
    default_project = "template"
    share_token = ""
    command_runner_enabled = False

    def log_message(self, format: str, *args: object) -> None:
        message = format % args
        if self.share_token:
            message = message.replace(self.share_token, "<share-token>")
        sys.stderr.write(
            f"{self.address_string()} - - [{self.log_date_time_string()}] {message}\n"
        )

    def authorized(self, parsed) -> bool:
        if not self.share_token:
            return True
        query = parse_qs(parsed.query)
        token = query.get("token", [""])[0]
        if secrets.compare_digest(token, self.share_token):
            return True
        self.send_text("Forbidden: missing or invalid dashboard share token.", status=HTTPStatus.FORBIDDEN)
        return False

    def send_json(self, payload: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_text(
        self,
        body: str,
        status: HTTPStatus = HTTPStatus.OK,
        content_type: str = "text/plain",
    ) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def read_json_body(self, max_bytes: int = 2048) -> dict:
        length_text = self.headers.get("Content-Length", "0")
        try:
            length = int(length_text)
        except ValueError as exc:
            raise ValueError("Invalid Content-Length header.") from exc
        if length <= 0 or length > max_bytes:
            raise ValueError("Invalid request body size.")
        body = self.rfile.read(length).decode("utf-8")
        data = json.loads(body)
        if not isinstance(data, dict):
            raise ValueError("JSON request body must be an object.")
        return data

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        try:
            if not self.authorized(parsed):
                return
            if parsed.path == "/":
                self.send_text(dashboard_html(), content_type="text/html")
                return
            if parsed.path == "/core.js":
                self.send_text(dashboard_asset("core.js"), content_type="application/javascript")
                return
            if parsed.path == "/app.js":
                self.send_text(dashboard_asset("app.js"), content_type="application/javascript")
                return
            if parsed.path == "/styles.css":
                self.send_text(dashboard_asset("styles.css"), content_type="text/css")
                return
            if parsed.path == "/api/projects":
                self.send_json(list_projects(self.default_project))
                return
            if parsed.path == "/api/status":
                query = parse_qs(parsed.query)
                project = query.get("project", [self.default_project])[0]
                payload = build_dashboard_data(project)
                payload["command_runner"] = {
                    "enabled": self.command_runner_enabled,
                    "commands": command_catalog(),
                }
                self.send_json(payload)
                return
            if parsed.path == "/api/validate":
                query = parse_qs(parsed.query)
                project = query.get("project", [self.default_project])[0]
                payload = build_dashboard_data(project)
                self.send_json({
                    "project": payload["project"],
                    "ok": not payload["health_warnings"],
                    "warnings": payload["health_warnings"],
                })
                return
            if parsed.path.startswith("/files/"):
                self.serve_project_file(parsed.path.removeprefix("/files/"))
                return
            self.send_text("Not found", status=HTTPStatus.NOT_FOUND)
        except (FileNotFoundError, ValueError, json.JSONDecodeError, HarnessError) as exc:
            self.send_text(str(exc), status=HTTPStatus.BAD_REQUEST)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            if not self.authorized(parsed):
                return
            if parsed.path != "/api/run-command":
                self.send_text("Not found", status=HTTPStatus.NOT_FOUND)
                return
            if not self.command_runner_enabled:
                self.send_json(
                    {
                        "ok": False,
                        "returncode": 403,
                        "stdout": "",
                        "stderr": "Dashboard command runner is disabled. Restart with --enable-command-runner.",
                    },
                    status=HTTPStatus.FORBIDDEN,
                )
                return
            body = self.read_json_body()
            project = str(body.get("project") or self.default_project)
            command_id = str(body.get("id") or "")
            self.send_json(run_dashboard_command(project, command_id))
        except (FileNotFoundError, ValueError, json.JSONDecodeError, HarnessError) as exc:
            self.send_text(str(exc), status=HTTPStatus.BAD_REQUEST)

    def serve_project_file(self, encoded_path: str) -> None:
        relative = Path(encoded_path)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Invalid file path.")
        target = repo_root() / relative
        if not target.is_file():
            raise FileNotFoundError(f"File not found: {relative}")
        if repo_root() not in target.resolve().parents:
            raise ValueError("Invalid file path.")
        content_type = mimetypes.guess_type(str(target))[0] or "text/plain"
        self.send_text(read_text(target, max_chars=20000), content_type=content_type)


def main() -> int:
    args = parse_args()
    local_hosts = {"127.0.0.1", "localhost", "::1"}
    if args.host not in local_hosts and not args.share_token and not args.unsafe_no_token:
        print(
            "error: non-local dashboard sharing requires --share-token. "
            "Pass --unsafe-no-token only on a trusted network.",
            file=sys.stderr,
        )
        return 2
    DashboardHandler.default_project = args.project
    DashboardHandler.share_token = args.share_token
    DashboardHandler.command_runner_enabled = args.enable_command_runner
    server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    url_project = quote(args.project)
    token_query = f"&token={quote(args.share_token)}" if args.share_token else ""
    print(f"Serving research agent dashboard at http://{args.host}:{args.port}/?project={url_project}{token_query}")
    if args.share_token and args.host == "0.0.0.0":
        try:
            share_host = socket.gethostbyname(socket.gethostname())
        except OSError:
            share_host = "<server-ip>"
        print(f"Share URL: http://{share_host}:{args.port}/?project={url_project}{token_query}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping dashboard.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
