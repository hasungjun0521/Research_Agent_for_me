#!/usr/bin/env python3
"""Create and audit lightweight workflow checkpoints."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from scripts.harness.state import (
    HarnessError,
    append_agent_event,
    atomic_write_json,
    load_json,
    now_iso,
    project_root,
    update_agent_status,
)
from scripts.harness.workflow_hooks import refresh_report_index

SNAPSHOT_FILES = [
    "state/current_state.md",
    "state/next_actions.md",
    "state/command_queue.json",
    "state/loop_summary.json",
    "state/agent_status.json",
    "state/gpu_experiment_queue.json",
    "state/resource_ledger.json",
    "state/phase_gates.json",
    "09_report/README.md",
]


def checkpoints_dir(root: Path) -> Path:
    return root / "state" / "checkpoints"


def checkpoint_path(root: Path, checkpoint_id: str) -> Path:
    if not checkpoint_id or "/" in checkpoint_id or ".." in checkpoint_id:
        raise HarnessError("checkpoint id must be a single file-safe name.")
    return checkpoints_dir(root) / f"{checkpoint_id}.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create and audit workflow checkpoints.")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="Create a lightweight checkpoint.")
    create.add_argument("--project", required=True)
    create.add_argument("--agent", default="director")
    create.add_argument("--id", required=True)
    create.add_argument("--label", default="")
    create.add_argument("--note", default="")

    list_cmd = sub.add_parser("list", help="List checkpoints.")
    list_cmd.add_argument("--project", required=True)
    list_cmd.add_argument("--json", action="store_true")

    audit = sub.add_parser("audit", help="Validate checkpoint files.")
    audit.add_argument("--project", required=True)
    audit.add_argument("--strict", action="store_true")
    audit.add_argument("--json", action="store_true")
    return parser.parse_args()


def read_snapshot_file(root: Path, relative: str) -> dict[str, Any]:
    path = root / relative
    if not path.is_file():
        return {"path": relative, "status": "missing", "kind": "", "content": ""}
    if path.suffix == ".json":
        try:
            content: Any = json.loads(path.read_text(encoding="utf-8"))
            return {"path": relative, "status": "available", "kind": "json", "content": content}
        except json.JSONDecodeError as exc:
            return {"path": relative, "status": "invalid", "kind": "json", "content": str(exc)}
    return {"path": relative, "status": "available", "kind": "text", "content": path.read_text(encoding="utf-8", errors="replace")}


def create_checkpoint(root: Path, checkpoint_id: str, label: str, note: str) -> dict[str, Any]:
    checkpoint = {
        "project": root.name,
        "schema_version": 1,
        "id": checkpoint_id,
        "label": label or checkpoint_id,
        "note": note,
        "created_at": now_iso(),
        "restore_supported": False,
        "files": [read_snapshot_file(root, relative) for relative in SNAPSHOT_FILES],
    }
    atomic_write_json(checkpoint_path(root, checkpoint_id), checkpoint)
    return checkpoint


def sync_checkpoint_agent(root: Path, agent: str, checkpoint: dict[str, Any]) -> None:
    output = checkpoint_path(root, str(checkpoint["id"])).relative_to(root).as_posix()
    task = f"Created run checkpoint {checkpoint['id']}."
    notes = (
        f"Lightweight replay/fork snapshot `{checkpoint.get('label') or checkpoint['id']}` was saved; "
        "restore is intentionally not automatic."
    )
    update_agent_status(
        root,
        agent,
        "waiting",
        task=task,
        stage="run_checkpoint",
        outputs=[output],
        notes=notes,
        append_note=True,
    )
    append_agent_event(
        root,
        "run_checkpoint",
        agent,
        status="waiting",
        task=task,
        stage="run_checkpoint",
        outputs=[output],
        notes=notes,
    )


def list_checkpoints(root: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(checkpoints_dir(root).glob("*.json")):
        try:
            data = load_json(path)
            rows.append({
                "id": str(data.get("id") or path.stem),
                "label": str(data.get("label") or ""),
                "created_at": str(data.get("created_at") or ""),
                "note": str(data.get("note") or ""),
                "files": len(data.get("files", [])) if isinstance(data.get("files"), list) else 0,
            })
        except HarnessError:
            rows.append({"id": path.stem, "label": "", "created_at": "", "note": "invalid checkpoint JSON", "files": 0})
    return rows


def audit_checkpoints(root: Path) -> dict[str, Any]:
    warnings: list[str] = []
    for path in sorted(checkpoints_dir(root).glob("*.json")):
        try:
            data = load_json(path)
        except HarnessError as exc:
            warnings.append(f"{path.relative_to(root)}: {exc}")
            continue
        if not isinstance(data.get("files"), list):
            warnings.append(f"{path.relative_to(root)}: files must be a list.")
        if data.get("restore_supported") is not False:
            warnings.append(f"{path.relative_to(root)}: restore_supported should be false unless restore is implemented.")
    rows = list_checkpoints(root)
    return {"project": root.name, "ok": not warnings, "checkpoints": rows, "warnings": warnings}


def main() -> int:
    args = parse_args()
    try:
        root = project_root(args.project)
        if args.command == "create":
            checkpoint = create_checkpoint(root, args.id, args.label, args.note)
            sync_checkpoint_agent(root, args.agent, checkpoint)
            refresh_report_index(root)
            print(checkpoint_path(root, checkpoint["id"]).relative_to(root).as_posix())
            return 0
        if args.command == "list":
            rows = list_checkpoints(root)
            if args.json:
                print(json.dumps({"project": root.name, "checkpoints": rows}, indent=2, ensure_ascii=False))
            else:
                for row in rows:
                    print(f"{row['id']}\t{row['created_at']}\t{row['label']}")
            return 0
        if args.command == "audit":
            report = audit_checkpoints(root)
            if args.json:
                print(json.dumps(report, indent=2, ensure_ascii=False))
            else:
                print("run checkpoints OK" if report["ok"] else "run checkpoints have warnings")
                for warning in report["warnings"]:
                    print(f"warning: {warning}", file=sys.stderr)
            return 1 if args.strict and report["warnings"] else 0
        raise HarnessError(f"Unknown command: {args.command}")
    except (HarnessError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
