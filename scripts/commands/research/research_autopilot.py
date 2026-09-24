"""Create research work and execute its ready queue with bounded autonomy."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

from scripts.commands.agents.agent_orchestrator import (
    command_owner,
    ensure_vote_gate,
    finish_command,
    mark_dispatched,
    render_prompt,
    serial_readiness_reasons,
)
from scripts.commands.agents.agent_runner import run_agent
from scripts.harness import HarnessError, atomic_write_json, now_iso, project_root, repo_root
from scripts.harness.state import load_command_queue


def harness(module: str, *args: str) -> None:
    result = subprocess.run([sys.executable, "-m", "scripts.commands." + module, *args],
                            cwd=repo_root(), check=False)
    if result.returncode:
        raise HarnessError(f"{module} failed (exit {result.returncode}).")


def refresh_context(root: Path, session: Path, timeout: int) -> None:
    """Refresh deterministic diagnostics before asking an agent to choose work."""
    deadline = time.monotonic() + timeout
    for module, arguments in (
        ("project_resume", []),
        ("state_doctor", ["--write-report"]),
        ("project_health", ["--write"]),
    ):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise HarnessError("Diagnostic preflight exceeded the run time limit.")
        with (session / f"preflight_{module}.log").open("w", encoding="utf-8") as log:
            try:
                result = subprocess.run(
                    [sys.executable, "-m", f"scripts.commands.projects.{module}",
                     "--project", root.name, *arguments], cwd=repo_root(),
                    stdout=log, stderr=subprocess.STDOUT, timeout=remaining, check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise HarnessError(f"{module} preflight timed out; inspect its log.") from exc
        if result.returncode:
            raise HarnessError(f"{module} preflight failed; inspect {session} before continuing.")


def plan(root: Path) -> dict:
    queue = load_command_queue(root)
    ready, excluded = [], []
    for command in queue.get("commands", []):
        if command.get("status") == "done":
            continue
        reasons = serial_readiness_reasons(queue, command)
        try:
            ensure_vote_gate(root, command)
        except HarnessError as exc:
            reasons.append(str(exc))
        if reasons:
            excluded.append({"id": command["id"], "reasons": reasons})
        else:
            ready.append(command)
    ready.sort(key=lambda c: ({"high": 0, "medium": 1, "low": 2}.get(c.get("priority"), 1),
                             str(c.get("created_at", "")), c["id"]))
    # Another native session may own work. Do not start competing mutations.
    active = [c["id"] for c in queue.get("commands", []) if c.get("status") == "in progress"]
    return {"project": root.name, "ready": ready, "excluded": excluded,
            "active": active, "next": ready[0]["id"] if ready and not active else None}


def outputs_snapshot(root: Path, command: dict) -> dict[str, str]:
    result = {}
    for value in command.get("expected_outputs", []):
        path = (root / value).resolve()
        if not path.is_relative_to(root.resolve()):
            raise HarnessError(f"Output escapes project: {value}")
        if path.is_file():
            digest = hashlib.sha256()
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            result[value] = digest.hexdigest()
        elif path.is_dir():
            # A directory's existence alone is not evidence of completed work.
            result[value] = "directory"
        else:
            result[value] = "missing"
    return result


def closeout_error(root: Path, command: dict, before: dict[str, str]) -> str:
    updated = next((c for c in load_command_queue(root)["commands"]
                    if c["id"] == command["id"]), None)
    if not updated or updated.get("status") != "done":
        return "Agent did not explicitly settle the command as done; review its log and project state."
    after = outputs_snapshot(root, command)
    if not after or "missing" in after.values():
        return "Expected output evidence is missing."
    if not any(digest not in {"missing", "directory"} and digest != before.get(path)
               and not (root / path).resolve().relative_to(root.resolve()).as_posix().startswith("state/")
               and (root / path).resolve().relative_to(root.resolve()).as_posix() not in {"HANDOFF.md", "README.md"}
               for path, digest in after.items()):
        return "No expected evidence file changed; review is required before continuing."
    return ""


def execute(root: Path, *, provider: str, max_steps: int, timeout: int, max_seconds: int) -> dict:
    if min(max_steps, timeout, max_seconds) <= 0:
        raise HarnessError("Step and time limits must be positive.")
    if root.name == "template":
        raise HarnessError("Create a real project first; template is never an execution target.")
    session_root = root / "state/sessions"
    session_root.mkdir(parents=True, exist_ok=True)
    lock = session_root / "autopilot.lock"
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise HarnessError("Autopilot already owns this project. If interrupted, verify the recorded PID "
                           "has stopped before removing state/sessions/autopilot.lock.") from exc
    try:
        try:
            os.write(descriptor, str(os.getpid()).encode())
        finally:
            os.close(descriptor)
    except BaseException:
        lock.unlink(missing_ok=True)
        raise
    session = session_root / ("autopilot_" + uuid.uuid4().hex[:12])
    report = {"started_at": now_iso(), "provider": provider, "status": "running", "steps": []}
    deadline = time.monotonic() + max_seconds
    try:
        session.mkdir()
        if not plan(root)["active"]:
            refresh_context(root, session, max_seconds)
        for _ in range(max_steps):
            remaining = int(deadline - time.monotonic())
            if remaining <= 0:
                report["status"] = "time_limit"
                break
            current = plan(root)
            if not current["next"]:
                report["status"] = "needs_attention" if current["active"] or current["excluded"] else "queue_drained"
                report["readiness"] = current
                break
            command = next(c for c in current["ready"] if c["id"] == current["next"])
            before = outputs_snapshot(root, command)
            # Filenames do not trust queue IDs.
            prompt = session / f"step_{len(report['steps']) + 1}.md"
            closeout = (
                "\n## Autonomous execution closeout\n"
                "Work only on this command and project. Read workflows/default_research_flow.yaml "
                "when planning. A director must queue the next evidence-backed research tasks with "
                "dependencies and concrete file outputs through command_queue. Workers do not launch "
                "nested autopilot or other paid runners. Use the existing experiment planner, GPU "
                "scheduler, experiment_complete, claim graph, writing and review workflows as relevant. "
                "Never invent measurements, citations, approvals, or scientific completion. "
                "Missing access or approval is a blocker. Before returning, validate your outputs, "
                "record a progress_checkpoint, update HANDOFF.md and current/next state, then use "
                "agent_orchestrator finish for this command with status done or blocked and an evidence "
                "note. A zero process exit is not task completion.\n"
            )
            prompt.write_text(render_prompt(root, command) + closeout, encoding="utf-8")
            mark_dispatched(root, command, prompt)
            step = {"command_id": command["id"], "owner": command_owner(command),
                    "prompt": prompt.relative_to(root).as_posix(), "status": "running"}
            report["steps"].append(step)
            atomic_write_json(session / "run.json", report)
            code = run_agent(provider, prompt, timeout=min(timeout, remaining))
            error = closeout_error(root, command, before) if code == 0 else f"Runner exited {code}."
            step.update({"exit_code": code, "status": "needs_review" if error else "done", "note": error})
            if error:
                finish_command(root, command["id"], "blocked", error, [])
                report["status"] = "needs_attention"
                break
            atomic_write_json(session / "run.json", report)
        else:
            report["status"] = "step_limit"
    except BaseException as exc:
        report.update({"status": "interrupted", "error": str(exc)})
        raise
    finally:
        report["finished_at"] = now_iso()
        try:
            atomic_write_json(session / "run.json", report)
        finally:
            lock.unlink(missing_ok=True)
    report["report"] = str(session / "run.json")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    start = sub.add_parser("init", help="Create a project, capture the idea, and queue director planning.")
    start.add_argument("--project", required=True)
    start.add_argument("--idea", required=True)
    for name in ("plan", "run"):
        command = sub.add_parser(name)
        command.add_argument("--project", required=True)
        if name == "run":
            command.add_argument("--provider", choices=["codex", "claude"], required=True)
            command.add_argument("--max-steps", type=int, default=3)
            command.add_argument("--timeout", type=int, default=1800)
            command.add_argument("--max-seconds", type=int, default=3600)
    args = parser.parse_args()
    try:
        if args.action == "init":
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", args.project) or args.project == "template":
                raise HarnessError("Use a new project name with letters, digits, underscores or hyphens.")
            if not args.idea.strip():
                raise HarnessError("A research idea is required.")
            harness("projects.create_project", "create", args.project)
            harness("projects.brief_intake", "apply", "--project", args.project,
                    "--research-question", args.idea, "--write")
            harness("review.command_queue", "update", "--project", args.project, "--id", "cmd_002",
                    "--owner", "director", "--priority", "high", "--action",
                    "Turn the brief into a research plan and queue the next ready tasks. "
                    "Use the full research lifecycle, explicit dependencies, concrete output files, "
                    "and existing approval gates. Include follow-up director review tasks after evidence stages.",
                    "--input", "00_brief/research_question.md", "--output", "02_planning/director_plan.md",
                    "--done-when", "A concrete plan and dependency-aware next tasks exist in the queue.")
            return 0
        root = project_root(args.project)
        result = plan(root) if args.action == "plan" else execute(
            root, provider=args.provider, max_steps=args.max_steps,
            timeout=args.timeout, max_seconds=args.max_seconds)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 2 if result.get("status") == "needs_attention" else 0
    except (HarnessError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
