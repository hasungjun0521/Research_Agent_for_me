"""Configure repository-local skills, hooks, and headless agent adapters."""

from __future__ import annotations

import argparse
import shlex
import sys
from pathlib import Path

from scripts.harness import HarnessError, atomic_write_json, repo_root
from scripts.harness.workspace_profile import load_json_file


def setup(root: Path, *, provider: str = "codex", dry_run: bool = False) -> list[str]:
    changes: list[str] = []
    profile_path = root / "config/workspace_profile.local.json"
    profile = load_json_file(profile_path) if profile_path.exists() else load_json_file(
        root / "config/workspace_profile.example.json")
    runners = profile.setdefault("agent_runners", {})
    runners.setdefault("default_profile", "")
    if not runners["default_profile"]:
        runners["default_profile"] = provider
    profiles = runners.setdefault("profiles", {})
    for name in ("codex", "claude"):
        item = profiles.setdefault(name, {})
        if not item.get("command"):
            item["command"] = [sys.executable, "-m", "scripts.commands.agents.agent_runner",
                               "--provider", name, "--prompt-file", "{prompt_file}"]
            item["description"] = f"Official {name} CLI via the bounded workspace adapter."
    changes.append("Initialize missing local runner settings (preserve configured commands).")

    for relative in (".agents", ".agents/skills", ".claude", "config"):
        candidate = root / relative
        if candidate.is_symlink() or not candidate.resolve().is_relative_to(root.resolve()):
            raise HarnessError(f"Setup target escapes the repository: {candidate}")
    copies: list[tuple[Path, Path]] = []
    for source in sorted((root / ".claude/skills").glob("*/SKILL.md")):
        target = root / ".agents/skills" / source.parent.name / "SKILL.md"
        if target.is_symlink() or target.parent.is_symlink():
            raise HarnessError(f"Refusing to overwrite skill symlink: {target}")
        if target.exists() and target.read_bytes() != source.read_bytes():
            raise HarnessError(f"Skill differs from canonical source; reconcile it first: {target}")
        if not target.exists():
            copies.append((source, target))
    changes.append(f"Make {len(copies)} missing skills discoverable in .agents/skills.")

    settings_path = root / ".claude/settings.local.json"
    settings = load_json_file(settings_path)
    hooks = settings.setdefault("hooks", {})
    # Claude executes command hooks in its shell, including Git Bash on Windows.
    python_path = Path(sys.executable).as_posix()
    hook_path = (root / "tools/research_session_hook.py").as_posix()
    command = f"{shlex.quote(python_path)} {shlex.quote(hook_path)}"
    for event in ("SessionStart", "Stop"):
        entries = hooks.setdefault(event, [])
        if not any("research_session_hook.py" in str(entry) for entry in entries):
            entries.append({"hooks": [{"type": "command", "command": command, "timeout": 10}]})
    changes.append("Merge repository-local Claude SessionStart and Stop hooks.")
    if not dry_run:
        atomic_write_json(profile_path, profile)
        for source, target in copies:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
        atomic_write_json(settings_path, settings)
    return changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", choices=["codex", "claude"], default="codex")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    try:
        for item in setup(repo_root(), provider=args.provider, dry_run=args.dry_run):
            print(("Would: " if args.dry_run else "OK: ") + item)
        print("CLI login and machine-specific GPU/data access remain local prerequisites.")
        return 0
    except (HarnessError, OSError, ValueError, TypeError, AttributeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
