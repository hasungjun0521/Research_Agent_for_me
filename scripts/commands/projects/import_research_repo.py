#!/usr/bin/env python3
"""Import an existing research repository into a template-backed project."""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import shutil
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts.commands.projects.create_project import replace_project_name, validate_project_name
from scripts.harness.state import (
    HarnessError,
    append_agent_event,
    load_command_queue,
    load_loop_summary,
    now_iso,
    repo_root,
    update_agent_status,
    write_command_queue,
    write_loop_summary,
)
from scripts.commands.research.phase_gate import default_gates, gate_path, write_gates
from scripts.commands.reports.resource_ledger import default_ledger, ledger_path, write_ledger
from scripts.harness.workflow_hooks import refresh_report_index


EXCLUDED_DIR_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".ipynb_checkpoints",
    ".venv",
    "venv",
    "env",
    "ENV",
    "node_modules",
    "dist",
    "build",
    "logs",
    "tmp",
    "temp",
    "wandb",
    "runs",
    "outputs",
    "checkpoints",
    "data",
    "datasets",
}

EXCLUDED_FILE_PATTERNS = {
    ".env",
    ".env.*",
    "credentials.*",
    "*credentials.json",
    "*credentials.yaml",
    "*credentials.yml",
    "secrets.*",
    "secret.*",
    "token.*",
    "*api_key*",
    "id_rsa",
    "id_ed25519",
    "*.pem",
    "*.key",
    "*.log",
    "*.lock",
}

EXCLUDED_SUFFIXES = {
    ".7z",
    ".bin",
    ".ckpt",
    ".db",
    ".gz",
    ".h5",
    ".hdf5",
    ".npy",
    ".npz",
    ".onnx",
    ".parquet",
    ".pth",
    ".pt",
    ".safetensors",
    ".sqlite",
    ".tar",
    ".zip",
}

CODE_SUFFIXES = {
    ".c",
    ".cc",
    ".cpp",
    ".cu",
    ".go",
    ".ipynb",
    ".java",
    ".jl",
    ".js",
    ".m",
    ".py",
    ".r",
    ".rs",
    ".sh",
    ".ts",
}
DOC_SUFFIXES = {".bib", ".md", ".rst", ".tex", ".txt"}
RESULT_SUFFIXES = {".csv", ".tsv", ".jsonl"}
CONFIG_SUFFIXES = {".cfg", ".ini", ".json", ".toml", ".yaml", ".yml"}

ENTRYPOINT_NAMES = {
    "README.md",
    "README.rst",
    "requirements.txt",
    "environment.yml",
    "environment.yaml",
    "pyproject.toml",
    "setup.py",
    "package.json",
    "Dockerfile",
    "Makefile",
    "main.py",
    "train.py",
    "eval.py",
    "evaluate.py",
    "run.py",
}

STARTER_IMPORT_MARKERS = (
    "to_be_defined",
    "pending_project_terms",
    "not yet",
    "not yet generated",
)


@dataclass(frozen=True)
class SkippedFile:
    path: str
    reason: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create or update a research-agent project from projects/template and "
            "import an existing research repository into 04_code/imported_repo/."
        )
    )
    parser.add_argument("--source", required=True, help="Path to the existing research repository.")
    parser.add_argument("--project", required=True, help="Destination project name under projects/.")
    parser.add_argument("--agent", default="director", help="Agent role to record for import lifecycle status.")
    parser.add_argument(
        "--into-existing",
        action="store_true",
        help="Import into an existing project instead of creating it from the template.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the destination project when creating a new project.",
    )
    parser.add_argument(
        "--overwrite-import",
        action="store_true",
        help="Replace an existing 04_code/imported_repo folder.",
    )
    parser.add_argument(
        "--import-dir",
        default="04_code/imported_repo",
        help="Project-relative folder for the imported repository copy.",
    )
    parser.add_argument(
        "--max-file-mb",
        type=float,
        default=25.0,
        help="Skip files larger than this size. Default: 25 MB.",
    )
    parser.add_argument(
        "--record-source-path",
        action="store_true",
        help="Record the absolute source path in the import manifest. Off by default for privacy.",
    )
    parser.add_argument(
        "--allow-template-import",
        action="store_true",
        help="Allow importing into projects/template. This is blocked by default to prevent leaks.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Plan the import without writing files.")
    return parser.parse_args()


def validate_import_dir(value: str) -> Path:
    candidate = Path(value)
    if candidate.is_absolute():
        raise HarnessError("--import-dir must be project-relative.")
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise HarnessError("--import-dir must not contain empty, '.', or '..' segments.")
    if candidate.parts[:1] != ("04_code",):
        raise HarnessError("Imported repositories must be placed under 04_code/.")
    return candidate


def has_starter_import_marker(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in STARTER_IMPORT_MARKERS)


def should_skip_file(path: Path, relative: Path, max_bytes: int) -> str:
    if path.is_symlink():
        return "symlink"
    if path.suffix.lower() in EXCLUDED_SUFFIXES:
        return "excluded_suffix"
    for pattern in EXCLUDED_FILE_PATTERNS:
        if fnmatch.fnmatch(path.name, pattern):
            return "private_or_generated_name"
    try:
        size = path.stat().st_size
    except OSError:
        return "unreadable"
    if size > max_bytes:
        return "larger_than_max_file_mb"
    if any(part in EXCLUDED_DIR_NAMES for part in relative.parts[:-1]):
        return "excluded_parent_dir"
    return ""


def classify_file(relative: Path) -> str:
    lowered_parts = [part.lower() for part in relative.parts]
    suffix = relative.suffix.lower()
    if "result" in " ".join(lowered_parts) or "results" in lowered_parts or "figures" in lowered_parts:
        return "results"
    if suffix in RESULT_SUFFIXES:
        return "results"
    if suffix in CODE_SUFFIXES:
        return "code"
    if suffix in DOC_SUFFIXES:
        if "paper" in lowered_parts or suffix == ".tex":
            return "writing"
        return "docs"
    if suffix in CONFIG_SUFFIXES or relative.name in ENTRYPOINT_NAMES:
        return "config"
    return "assets"


def walk_importable_files(source: Path, max_bytes: int) -> tuple[list[Path], list[SkippedFile]]:
    copied: list[Path] = []
    skipped: list[SkippedFile] = []
    for current, dirs, files in os.walk(source):
        current_path = Path(current)
        dirs[:] = [name for name in dirs if name not in EXCLUDED_DIR_NAMES]
        for name in sorted(files):
            path = current_path / name
            relative = path.relative_to(source)
            reason = should_skip_file(path, relative, max_bytes)
            if reason:
                skipped.append(SkippedFile(relative.as_posix(), reason))
                continue
            copied.append(relative)
    return sorted(copied), skipped


def setup_project(destination: Path, project_name: str, *, force: bool, into_existing: bool, dry_run: bool) -> list[str]:
    root = repo_root()
    template = root / "projects" / "template"
    changed: list[str] = []
    if into_existing:
        if not destination.is_dir():
            raise HarnessError(f"Project does not exist: {destination.relative_to(root)}")
        return changed
    if not template.is_dir():
        raise HarnessError(f"Template directory not found: {template}")
    if destination.exists():
        if not force:
            raise HarnessError(f"Project already exists: {destination.relative_to(root)}. Use --force to overwrite it.")
        changed.append(str(destination.relative_to(root)))
        if not dry_run:
            shutil.rmtree(destination)
    changed.append(str(destination.relative_to(root)))
    if not dry_run:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(template, destination)
        replace_project_name(destination, project_name)
        if not gate_path(destination).exists():
            write_gates(destination, default_gates(project_name))
        if not ledger_path(destination).exists():
            write_ledger(destination, default_ledger(project_name))
        (destination / "state" / "checkpoints").mkdir(parents=True, exist_ok=True)
        refresh_report_index(destination)
    return changed


def copy_imported_repo(source: Path, root: Path, import_rel: Path, files: list[Path], *, dry_run: bool) -> None:
    target_root = root / import_rel
    if dry_run:
        return
    target_root.mkdir(parents=True, exist_ok=True)
    for relative in files:
        source_file = source / relative
        target_file = target_root / relative
        target_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, target_file)


def detect_entrypoints(files: list[Path]) -> list[str]:
    entrypoints: list[str] = []
    for relative in files:
        if relative.name in ENTRYPOINT_NAMES:
            entrypoints.append(relative.as_posix())
    return sorted(entrypoints)


def build_manifest(
    *,
    source: Path,
    project_name: str,
    import_rel: Path,
    files: list[Path],
    skipped: list[SkippedFile],
    max_file_mb: float,
    record_source_path: bool,
) -> dict[str, Any]:
    categories = Counter(classify_file(path) for path in files)
    return {
        "project": project_name,
        "source_name": source.name,
        "source_path": str(source) if record_source_path else "",
        "source_path_recorded": bool(record_source_path),
        "imported_at": now_iso(),
        "import_dir": import_rel.as_posix(),
        "max_file_mb": max_file_mb,
        "copied_file_count": len(files),
        "skipped_file_count": len(skipped),
        "category_counts": dict(sorted(categories.items())),
        "entrypoints": detect_entrypoints(files),
        "copied_files": [path.as_posix() for path in files[:500]],
        "copied_files_truncated": len(files) > 500,
        "skipped_files": [skipped_file.__dict__ for skipped_file in skipped[:500]],
        "skipped_files_truncated": len(skipped) > 500,
        "excluded_dirs": sorted(EXCLUDED_DIR_NAMES),
        "excluded_suffixes": sorted(EXCLUDED_SUFFIXES),
        "restore_supported": False,
        "notes": "The imported repository is a working snapshot. Large/private/generated artifacts are intentionally skipped.",
    }


def write_manifest(root: Path, import_rel: Path, manifest: dict[str, Any]) -> str:
    path = root / import_rel / "IMPORT_MANIFEST.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return str(path.relative_to(root))


def write_inventory(root: Path, manifest: dict[str, Any]) -> str:
    path = root / "02_planning" / "imported_repo_inventory.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    categories = manifest.get("category_counts", {})
    entrypoints = manifest.get("entrypoints", [])
    skipped = manifest.get("skipped_files", [])
    lines = [
        "# Imported Repository Inventory",
        "",
        f"- Source name: `{manifest['source_name']}`",
        f"- Imported at: `{manifest['imported_at']}`",
        f"- Imported copy: `{manifest['import_dir']}/`",
        f"- Copied files: {manifest['copied_file_count']}",
        f"- Skipped files: {manifest['skipped_file_count']}",
        f"- Source path recorded: {'yes' if manifest['source_path_recorded'] else 'no'}",
        "",
        "## Category Counts",
        "",
    ]
    if categories:
        for name, count in sorted(categories.items()):
            lines.append(f"- {name}: {count}")
    else:
        lines.append("- No files were copied.")
    lines.extend(["", "## Entry Points To Inspect", ""])
    if entrypoints:
        lines.extend(f"- `{manifest['import_dir']}/{item}`" for item in entrypoints[:25])
    else:
        lines.append("- No common entry point files were detected.")
    lines.extend(["", "## Skipped File Examples", ""])
    if skipped:
        lines.extend(f"- `{item['path']}`: {item['reason']}" for item in skipped[:25])
    else:
        lines.append("- No files were skipped.")
    lines.extend([
        "",
        "## Next Steps",
        "",
        "1. Read the imported README, config files, and main scripts.",
        "2. Fill `00_brief/research_question.md` and `00_brief/motivation.md` from the imported repo.",
        "3. Move only final, reader-facing artifacts into `09_report/`.",
        "4. Register datasets, metrics, claims, and experiments through the harness scripts.",
        "5. Run `python -m scripts.commands.projects.project_resume --project <project>` before the next agent pass.",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")
    return str(path.relative_to(root))


def write_brief_notes(root: Path, manifest: dict[str, Any]) -> str:
    path = root / "00_brief" / "imported_repo_notes.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    text = (
        "# Imported Repository Notes\n\n"
        f"Imported `{manifest['source_name']}` into `{manifest['import_dir']}/`.\n\n"
        "Use this file to summarize what the existing repository was trying to prove,\n"
        "which artifacts are final, which experiments are trustworthy, and what must be\n"
        "re-run before making claims in `09_report/`.\n\n"
        "## Triage Questions\n\n"
        "- What is the main research question?\n"
        "- Which scripts reproduce the core result?\n"
        "- Which datasets, metrics, and baselines are required?\n"
        "- Which outputs are final artifacts versus scratch files?\n"
        "- What evidence is missing before a reviewer should trust the result?\n"
    )
    path.write_text(text, encoding="utf-8")
    return str(path.relative_to(root))


def append_markdown_section(path: Path, title: str, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""
    separator = "\n" if existing and not existing.endswith("\n") else ""
    block = "\n".join(["", f"## {title}", "", *lines]).rstrip() + "\n"
    path.write_text(existing + separator + block, encoding="utf-8")


def add_file_state_next_step(root: Path, project_name: str, manifest: dict[str, Any]) -> list[str]:
    changed: list[str] = []
    timestamp = now_iso()
    command_id = "imported_repo_triage"
    command = {
        "id": command_id,
        "action": "Triage the imported repository and convert it into a research-agent project plan.",
        "owner_agent": "director",
        "priority": "high",
        "status": "open",
        "required_inputs": [
            manifest["import_dir"],
            "02_planning/imported_repo_inventory.md",
            "00_brief/imported_repo_notes.md",
        ],
        "expected_outputs": [
            "00_brief/research_question.md",
            "00_brief/motivation.md",
            "02_planning/director_plan.md",
            "03_experiments/experiment_registry.yaml",
            "state/next_actions.md",
        ],
        "depends_on": [],
        "parallel_group": "imported_repo_triage",
        "display_summary": "Inspect the imported repo and turn it into a concrete research workflow.",
        "why_now": "The imported files need triage before agents can safely run experiments or claim results.",
        "done_when": "The brief, director plan, experiment registry, and next actions explain what to preserve, rerun, or discard.",
        "requires_vote": False,
        "vote_id": "",
        "risk_level": "medium",
        "created_at": timestamp,
        "updated_at": timestamp,
        "notes": f"Imported source: {manifest['source_name']}",
    }
    queue = load_command_queue(root)
    commands = [item for item in queue.get("commands", []) if item.get("id") != command_id]
    queue["commands"] = [command] + commands
    queue["project"] = project_name
    queue["last_updated"] = timestamp
    write_command_queue(root, queue)
    changed.append("state/command_queue.json")
    changed.append("state/next_actions.md")

    next_action = {
        "action": command["action"],
        "owner_agent": "director",
        "priority": "high",
        "expected_outputs": command["expected_outputs"],
        "display_summary": command["display_summary"],
        "why_now": command["why_now"],
        "done_when": command["done_when"],
        "notes": "Start by reading the imported repository inventory.",
        "created_at": timestamp,
    }
    summary = load_loop_summary(root)
    summary["project"] = project_name
    summary["status"] = "planned"
    summary["goal"] = "Triage the imported repository into a reproducible research workflow."
    summary["summary"] = (
        f"Imported `{manifest['source_name']}` with {manifest['copied_file_count']} copied file(s). "
        "The next step is to inspect the imported repo and decide what should become claims, experiments, and final artifacts."
    )
    summary["last_updated"] = timestamp
    summary["results"] = [{
        "title": "Existing repository imported",
        "status": "done",
        "summary": f"Snapshot copied to `{manifest['import_dir']}/`; inventory written for triage.",
        "evidence_files": [
            "02_planning/imported_repo_inventory.md",
            f"{manifest['import_dir']}/IMPORT_MANIFEST.json",
        ],
        "updated_at": timestamp,
    }]
    existing_next = [
        item for item in summary.get("next_actions", [])
        if isinstance(item, dict) and item.get("action") != next_action["action"]
    ]
    summary["next_actions"] = [next_action] + existing_next
    write_loop_summary(root, summary)
    changed.append("state/loop_summary.json")

    append_markdown_section(
        root / "state" / "current_state.md",
        f"Imported Repository Snapshot: {timestamp}",
        [
            f"- Imported source name: `{manifest['source_name']}`",
            f"- Imported copy: `{manifest['import_dir']}/`",
            f"- Copied files: {manifest['copied_file_count']}",
            f"- Skipped files: {manifest['skipped_file_count']}",
            "- Next: run `imported_repo_triage` before using imported results as evidence.",
        ],
    )
    append_markdown_section(
        root / "state" / "agent_memory.md",
        f"Import Memory: {timestamp}",
        [
            f"- Existing repository snapshot lives in `{manifest['import_dir']}/`.",
            "- Large/private/generated artifacts were intentionally skipped.",
            "- Do not move imported outputs to `09_report/` until they are audited and reader-facing.",
        ],
    )
    append_markdown_section(
        root / "HANDOFF.md",
        f"Latest Import: {timestamp}",
        [
            f"- Imported source name: `{manifest['source_name']}`",
            f"- Imported copy: `{manifest['import_dir']}/`",
            "- Next best action: complete command `imported_repo_triage`.",
            "- Required first read: `02_planning/imported_repo_inventory.md`.",
        ],
    )
    changed.extend(["state/current_state.md", "state/agent_memory.md", "HANDOFF.md"])

    return changed


def write_import_seed_files(root: Path, manifest: dict[str, Any]) -> list[str]:
    changed: list[str] = []
    import_dir = str(manifest["import_dir"]).rstrip("/")
    data_roots = root / "03_experiments" / "data_roots.md"
    data_roots_text = data_roots.read_text(encoding="utf-8", errors="replace") if data_roots.exists() else ""
    if has_starter_import_marker(data_roots_text) or not data_roots_text.strip():
        data_roots.write_text(
            "\n".join([
                "# Data Roots",
                "",
                "| dataset_id | purpose | root_uri | split_or_version | checksum_or_manifest | local_path_policy | notes |",
                "| --- | --- | --- | --- | --- | --- | --- |",
                (
                    f"| imported_repository | Imported source triage | `{import_dir}/` | import snapshot | "
                    f"`{import_dir}/IMPORT_MANIFEST.json` | Keep paths project-relative; do not rely on private absolute source paths. | "
                    "Director triage should refine this row with concrete dataset roots before experiments. |"
                ),
                "",
            ]),
            encoding="utf-8",
        )
        changed.append("03_experiments/data_roots.md")

    terminology = root / "06_writing" / "terminology.md"
    terminology_text = terminology.read_text(encoding="utf-8", errors="replace") if terminology.exists() else ""
    if has_starter_import_marker(terminology_text) or not terminology_text.strip():
        terminology.write_text(
            "\n".join([
                "# Terminology",
                "",
                "| term | canonical meaning | preferred usage | avoid | notes |",
                "| --- | --- | --- | --- | --- |",
                (
                    "| imported repository | Existing research code snapshot copied for triage. | "
                    "imported repository | imported repo | Refine after the research question, method names, datasets, metrics, and baselines are defined. |"
                ),
                "",
            ]),
            encoding="utf-8",
        )
        changed.append("06_writing/terminology.md")
    return changed


def sync_import_agent(root: Path, agent: str, manifest: dict[str, Any]) -> list[str]:
    outputs = [
        f"{manifest['import_dir']}/",
        f"{manifest['import_dir']}/IMPORT_MANIFEST.json",
        "02_planning/imported_repo_inventory.md",
        "00_brief/imported_repo_notes.md",
        "03_experiments/data_roots.md",
        "06_writing/terminology.md",
        "state/command_queue.json",
        "state/next_actions.md",
        "state/loop_summary.json",
        "state/current_state.md",
        "state/agent_memory.md",
        "HANDOFF.md",
    ]
    task = "Imported existing research repository and queued triage."
    notes = (
        f"Imported `{manifest['source_name']}` into `{manifest['import_dir']}/`; "
        "director triage must inspect copied files before using them as evidence."
    )
    update_agent_status(
        root,
        agent,
        "waiting",
        task=task,
        stage="import_research_repo",
        outputs=outputs,
        notes=notes,
        append_note=True,
    )
    append_agent_event(
        root,
        "import_research_repo",
        agent,
        status="waiting",
        task=task,
        stage="import_research_repo",
        outputs=outputs,
        notes=notes,
    )
    return ["state/agent_status.json", "state/agent_events.jsonl"]


def run_import(args: argparse.Namespace) -> dict[str, Any]:
    project_relpath = validate_project_name(args.project)
    project_name = project_relpath.as_posix()
    if project_name == "template" and not args.allow_template_import:
        raise HarnessError("Refusing to import into projects/template without --allow-template-import.")
    import_rel = validate_import_dir(args.import_dir)
    source = Path(args.source).expanduser().resolve()
    if not source.is_dir():
        raise HarnessError(f"Source repository not found: {source}")
    root = repo_root()
    destination = root / "projects" / project_relpath
    if source == destination.resolve() or destination.resolve() in source.parents:
        raise HarnessError("Source repository must not be the destination project or a child of it.")
    target_import = destination / import_rel
    if target_import.exists() and not args.overwrite_import:
        raise HarnessError(f"Import folder already exists: {target_import.relative_to(root)}. Use --overwrite-import.")
    max_bytes = int(args.max_file_mb * 1024 * 1024)
    files, skipped = walk_importable_files(source, max_bytes)
    manifest = build_manifest(
        source=source,
        project_name=project_name,
        import_rel=import_rel,
        files=files,
        skipped=skipped,
        max_file_mb=args.max_file_mb,
        record_source_path=args.record_source_path,
    )
    changed = setup_project(
        destination,
        project_name,
        force=args.force,
        into_existing=args.into_existing,
        dry_run=args.dry_run,
    )
    if not args.dry_run:
        if target_import.exists() and args.overwrite_import:
            shutil.rmtree(target_import)
        copy_imported_repo(source, destination, import_rel, files, dry_run=False)
        changed.extend([
            write_manifest(destination, import_rel, manifest),
            write_inventory(destination, manifest),
            write_brief_notes(destination, manifest),
        ])
        changed.extend(write_import_seed_files(destination, manifest))
        changed.extend(add_file_state_next_step(destination, project_name, manifest))
        changed.extend(sync_import_agent(destination, args.agent, manifest))
        refresh_report_index(destination)
    return {
        "ok": True,
        "project": project_name,
        "source_name": manifest["source_name"],
        "destination": str(destination.relative_to(root)),
        "import_dir": import_rel.as_posix(),
        "dry_run": bool(args.dry_run),
        "copied_file_count": len(files),
        "skipped_file_count": len(skipped),
        "entrypoints": manifest["entrypoints"],
        "category_counts": manifest["category_counts"],
        "changed": changed,
    }


def main() -> int:
    args = parse_args()
    try:
        result = run_import(args)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (HarnessError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
