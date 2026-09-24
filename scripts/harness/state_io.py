"""Atomic JSON and state-file helpers."""

from __future__ import annotations

import csv
import errno
import json
import os
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any

from .errors import HarnessError

if os.name == "nt":
    import msvcrt
else:
    import fcntl


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def quarantine_corrupt_json(path: Path, reason: str) -> Path:
    """Preserve an unreadable JSON state file under a .corrupt-* name.

    Only call this from an explicit, user-requested repair path (for example
    state_doctor --repair) while holding the file's state lock. Normal load
    paths must keep raising on corrupt JSON instead of silently renaming
    state files (read-only commands must never mutate project state).
    """
    timestamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S")
    backup = path.with_name(f"{path.name}.corrupt-{timestamp}-{os.getpid()}")
    try:
        os.replace(path, backup)
    except OSError as replace_exc:
        raise HarnessError(
            f"Invalid JSON in {path}: {reason}; could not preserve the unreadable file: {replace_exc}"
        ) from replace_exc
    return backup


def load_json(path: Path, fallback: Any | None = None) -> Any:
    if not path.exists():
        if fallback is not None:
            return fallback
        raise HarnessError(f"JSON file not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HarnessError(
            f"Invalid JSON in {path}: {exc}. Preview recovery with "
            "'python -m scripts.commands.projects.state_doctor --project <name> --dry-run-repair' "
            "and apply it with '--repair' to quarantine and rebuild the file."
        ) from exc


@contextmanager
def locked_state_file(path: Path):
    """Serialize writers using a permanent, non-truncated sidecar.

    Never unlink the sidecar: a waiting process may already have it open, so
    replacing its directory entry would create two independently locked files.
    Windows can lock a byte beyond EOF, including on an empty legacy sidecar.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(f"{path.name}.lock")
    with lock_path.open("a+b") as lock:
        if os.name == "nt":
            # LK_LOCK stops retrying after ten seconds. Explicit nonblocking
            # retries preserve flock's indefinite wait for long transactions.
            while True:
                lock.seek(0)
                try:
                    msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                    break
                except OSError as exc:
                    if exc.errno not in (errno.EACCES, errno.EAGAIN, errno.EDEADLK):
                        raise
                    time.sleep(0.05)
        else:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if os.name == "nt":
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(lock.fileno(), fcntl.LOCK_UN)


def atomic_write_json_unlocked(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        with tmp.open("w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except Exception:
        tmp.unlink(missing_ok=True)
        raise


def atomic_write_json(path: Path, data: Any) -> None:
    with locked_state_file(path):
        atomic_write_json_unlocked(path, data)


def split_values(values: list[str] | None) -> list[str]:
    if not values:
        return []
    result: list[str] = []
    for value in values:
        for part in value.split(","):
            stripped = part.strip()
            if stripped:
                result.append(stripped)
    return result

def read_csv(path: Path, header: list[str]) -> list[dict[str, str]]:
    if not path.is_file():
        return []
    with path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != header:
            raise HarnessError(f"{path} has unexpected header.\nFound: {reader.fieldnames}\nExpected: {header}")
        return [
            {field: str(row.get(field) or "") for field in header}
            for row in reader
            if any(str(value or "").strip() for value in row.values())
        ]

def write_csv(path: Path, header: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with locked_state_file(path):
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=header)
            writer.writeheader()
            writer.writerows(rows)

def upsert_rows(
    existing: list[dict[str, str]],
    new_rows: list[dict[str, str]],
    key_fields: tuple[str, ...],
) -> list[dict[str, str]]:
    index = {tuple(row.get(field, "") for field in key_fields): row for row in existing}
    ordered_keys = [tuple(row.get(field, "") for field in key_fields) for row in existing]
    for row in new_rows:
        key = tuple(row.get(field, "") for field in key_fields)
        if key not in index:
            ordered_keys.append(key)
        index[key] = row
    return [index[key] for key in ordered_keys]
