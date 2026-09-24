"""Run official agent CLIs with file prompts, bounded time, and durable logs."""

from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
from pathlib import Path

from scripts.harness import HarnessError, repo_root


def cli_prefix(provider: str) -> list[str]:
    executable = shutil.which(provider)
    if not executable:
        raise HarnessError(f"Install and authenticate the {provider} CLI first.")
    # npm's Windows command shim is a batch file. Invoke its JS entry directly
    # so prompts never pass through cmd.exe or shell interpolation.
    if os.name == "nt" and Path(executable).suffix.lower() in {".cmd", ".bat", ".ps1"}:
        package, entry = {
            "codex": ("@openai/codex", "bin/codex.js"),
            "claude": ("@anthropic-ai/claude-code", "cli.js"),
        }[provider]
        script = Path(executable).parent / "node_modules" / package / entry
        node = shutil.which("node")
        if not node or not script.is_file():
            raise HarnessError(f"Cannot resolve {provider} npm entry; install its native CLI or npm package.")
        return [node, str(script)]
    return [executable]


def stop_process(process: subprocess.Popen) -> None:
    """Terminate only the process tree launched for this invocation."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       capture_output=True, check=False)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait()


def run_agent(provider: str, prompt: Path, *, timeout: int = 1800,
              output: Path | None = None, extra_args: list[str] | None = None) -> int:
    if os.environ.get("RESEARCH_AGENT_CHILD") == "1":
        raise HarnessError("Nested paid runners are disabled; return follow-up work to the director queue.")
    if timeout <= 0:
        raise HarnessError("Timeout must be positive.")
    content = prompt.read_text(encoding="utf-8")
    argv = cli_prefix(provider)
    if provider == "codex":
        argv += ["exec", "--sandbox", "workspace-write", "-"]
    else:
        argv += ["-p", "--permission-mode", "acceptEdits"]
    argv += extra_args or []
    log_path = output or prompt.with_suffix(".runner.log")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["RESEARCH_AGENT_CHILD"] = "1"
    with log_path.open("w", encoding="utf-8") as log:
        process = subprocess.Popen(argv, cwd=repo_root(), stdin=subprocess.PIPE,
                                   stdout=log, stderr=subprocess.STDOUT, text=True,
                                   encoding="utf-8", env=env,
                                   start_new_session=os.name != "nt")
        try:
            process.communicate(content, timeout=timeout)
        except subprocess.TimeoutExpired:
            stop_process(process)
            print(f"Agent timed out; inspect {log_path}", file=sys.stderr)
            return 124
        except BaseException:
            stop_process(process)
            raise
    print(f"Agent exit={process.returncode}; log={log_path}")
    return process.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=["codex", "claude"], required=True)
    parser.add_argument("--prompt-file", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--extra-arg", action="append", default=[])
    args = parser.parse_args()
    try:
        return run_agent(args.provider, args.prompt_file, timeout=args.timeout,
                         output=args.output, extra_args=args.extra_arg)
    except (HarnessError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
