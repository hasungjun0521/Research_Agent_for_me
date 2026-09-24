#!/usr/bin/env python3
"""Build a reproducibility manifest and optional archive for 09_report artifacts."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tarfile
from pathlib import Path
from typing import Any

from scripts.commands.release.privacy_audit import LOCAL_ABSOLUTE_PATH_RE
from scripts.harness.report_lifecycle import sync_report_lifecycle
from scripts.harness.state import HarnessError, now_iso, project_root, repo_root

INCLUDE_DIRS = [
    "09_report",
    "state/project_health.md",
    "state/state_doctor.md",
    "03_experiments",
    "04_code/src",
    "04_code/tests",
    "08_baselines/baseline_registry.json",
    "03_experiments/dataset_registry.json",
    "03_experiments/metric_registry.json",
    "03_experiments/artifact_registry.csv",
    "05_results/experiment_results.csv",
    "05_results/experiment_journal.md",
    "05_results/experiment_journal.csv",
    "05_results/claim_graph.md",
    "05_results/claim_graph.json",
    "05_results/data_metric_audit.md",
    "05_results/data_metric_audit.json",
    "06_writing/terminology.md",
    "07_reviews/agent_quality_audit.md",
    "08_baselines/baseline_compare.md",
    "08_baselines/code_structure_plan.md",
]
REQUIRED_ARTIFACTS = [
    "state/project_health.md",
    "03_experiments/data_roots.md",
    "03_experiments/experiment_dag.json",
    "03_experiments/artifact_registry.csv",
    "05_results/experiment_results.csv",
    "05_results/experiment_journal.md",
    "05_results/experiment_journal.csv",
    "05_results/claim_graph.md",
    "06_writing/terminology.md",
]
EXCLUDE_PARTS = {"__pycache__", ".pytest_cache", ".git", "checkpoints", "wandb", "node_modules"}
EXCLUDE_SUFFIXES = {".pt", ".pth", ".ckpt", ".bin", ".zip", ".tar", ".gz", ".npy", ".npz", ".pkl", ".pickle"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a reproducibility artifact manifest/archive.")
    parser.add_argument("--project", required=True)
    parser.add_argument("--tar", action="store_true", help="Create a .tar.gz archive under 09_report/.")
    parser.add_argument("--dry-run", action="store_true", help="Build the manifest in memory without writing files.")
    parser.add_argument("--agent", default="writing_agent", help="Agent role to credit for non-dry-run artifact packaging.")
    parser.add_argument(
        "--allow-local-paths",
        action="store_true",
        help="Allow local absolute paths in packaged text files. Use only for private/internal archives.",
    )
    parser.add_argument(
        "--allow-incomplete",
        action="store_true",
        help="Allow packaging even when required working evidence files are missing.",
    )
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_commit() -> str:
    try:
        result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=repo_root(), text=True, capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def should_include(path: Path) -> bool:
    if any(part in EXCLUDE_PARTS for part in path.parts):
        return False
    if path.suffix.lower() in EXCLUDE_SUFFIXES:
        return False
    return path.is_file()


def iter_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for rel in INCLUDE_DIRS:
        path = root / rel
        if path.is_file() and should_include(path):
            files.append(path)
        elif path.is_dir():
            files.extend(child for child in path.rglob("*") if should_include(child))
    return sorted(set(files))


def missing_required_artifacts(root: Path) -> list[str]:
    return [relative for relative in REQUIRED_ARTIFACTS if not (root / relative).is_file()]


def file_contains_local_path(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
    return bool(LOCAL_ABSOLUTE_PATH_RE.search(text))


def build_manifest(root: Path, *, allow_local_paths: bool = False, allow_incomplete: bool = False) -> dict[str, Any]:
    missing = missing_required_artifacts(root)
    if missing and not allow_incomplete:
        raise HarnessError(
            "Required working evidence files are missing from the artifact package: "
            + ", ".join(missing)
            + ". Create them or pass --allow-incomplete for an explicit draft/internal package."
        )
    files = []
    for path in iter_files(root):
        rel = path.relative_to(root).as_posix()
        if not allow_local_paths and file_contains_local_path(path):
            raise HarnessError(
                f"Packaged file contains a local absolute path: {rel}. "
                "Move private paths to config/workspace_profile.local.json or pass --allow-local-paths for private archives."
            )
        files.append({"path": rel, "bytes": path.stat().st_size, "sha256": sha256(path)})
    return {
        "project": root.name,
        "generated_at": now_iso(),
        "repo_commit": git_commit(),
        "file_count": len(files),
        "files": files,
        "required_artifacts": {
            "expected": REQUIRED_ARTIFACTS,
            "missing": missing,
        },
        "notes": "Large checkpoints, datasets, cache folders, and VCS internals are intentionally excluded.",
    }


def write_manifest(root: Path, manifest: dict[str, Any]) -> Path:
    path = root / "09_report" / "artifact_manifest.json"
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def write_archive(root: Path, manifest: dict[str, Any]) -> Path:
    archive = root / "09_report" / f"{root.name}_artifact.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for item in manifest["files"]:
            path = root / item["path"]
            if path == archive:
                continue
            tar.add(path, arcname=f"{root.name}/{item['path']}")
        manifest_path = root / "09_report" / "artifact_manifest.json"
        if manifest_path.is_file():
            tar.add(manifest_path, arcname=f"{root.name}/09_report/artifact_manifest.json")
    return archive


def main() -> int:
    args = parse_args()
    try:
        root = project_root(args.project)
        manifest = build_manifest(root, allow_local_paths=args.allow_local_paths, allow_incomplete=args.allow_incomplete)
        manifest_path = None if args.dry_run else write_manifest(root, manifest)
        archive_path = write_archive(root, manifest) if args.tar and not args.dry_run else None
        payload = {
            "project": args.project,
            "manifest": manifest_path.relative_to(root).as_posix() if manifest_path else "09_report/artifact_manifest.json",
            "archive": archive_path.relative_to(root).as_posix() if archive_path else "",
            "file_count": manifest["file_count"],
            "files": [item["path"] for item in manifest["files"]],
        }
        if not args.dry_run:
            outputs = [payload["manifest"]]
            if payload["archive"]:
                outputs.append(payload["archive"])
            sync_report_lifecycle(
                root,
                agent=args.agent,
                event_type="artifact_packager",
                status="waiting",
                task=f"Packaged reproducibility artifacts for {args.project}.",
                outputs=outputs,
                notes=(
                    f"Artifact manifest covers {manifest['file_count']} files. "
                    "Use the manifest and archive for reviewer-facing reproducibility checks."
                ),
                refresh_report=True,
            )
        if args.json:
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print(f"artifact manifest: {payload['manifest']} ({payload['file_count']} files)")
            if payload["archive"]:
                print(f"archive: {payload['archive']}")
        return 0
    except (HarnessError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
