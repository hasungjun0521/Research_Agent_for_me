"""Unit tests for the atomic JSON state I/O primitives."""

from __future__ import annotations

import json
import multiprocessing
import time
from pathlib import Path

import pytest

from scripts.harness.errors import HarnessError
from scripts.harness.state_io import (
    atomic_write_json,
    atomic_write_json_unlocked,
    load_json,
    locked_state_file,
    quarantine_corrupt_json,
    split_values,
)


def test_load_json_missing_with_fallback_returns_fallback(tmp_path):
    fallback = {"commands": []}
    assert load_json(tmp_path / "missing.json", fallback=fallback) is fallback


def test_load_json_missing_without_fallback_raises(tmp_path):
    with pytest.raises(HarnessError, match="not found"):
        load_json(tmp_path / "missing.json")


def test_load_json_corrupt_raises_and_leaves_file_untouched(tmp_path):
    path = tmp_path / "queue.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(HarnessError, match="state_doctor"):
        load_json(path, fallback={"commands": []})
    assert path.read_text(encoding="utf-8") == "{not json"
    assert list(tmp_path.iterdir()) == [path]


def test_atomic_write_json_roundtrip_and_lock_file(tmp_path):
    path = tmp_path / "doc.json"
    atomic_write_json(path, {"a": 1})
    assert json.loads(path.read_text(encoding="utf-8")) == {"a": 1}
    assert path.read_text(encoding="utf-8").endswith("\n")
    assert (tmp_path / "doc.json.lock").exists()
    leftovers = [entry.name for entry in tmp_path.iterdir() if entry.name.startswith(".doc")]
    assert leftovers == [], "temp file must not survive the atomic replace"


def test_quarantine_corrupt_json_preserves_bytes(tmp_path):
    path = tmp_path / "doc.json"
    path.write_text("{broken", encoding="utf-8")
    backup = quarantine_corrupt_json(path, "test reason")
    assert not path.exists()
    assert backup.name.startswith("doc.json.corrupt-")
    assert backup.read_text(encoding="utf-8") == "{broken"


def test_quarantine_missing_file_raises_harness_error(tmp_path):
    with pytest.raises(HarnessError, match="could not preserve"):
        quarantine_corrupt_json(tmp_path / "gone.json", "reason")


def test_locked_state_file_creates_sidecar_lock(tmp_path):
    path = tmp_path / "doc.json"
    with locked_state_file(path):
        assert (tmp_path / "doc.json.lock").exists()


def test_split_values_handles_commas_and_blanks():
    assert split_values(["a,b", " c ", "", "d,,e"]) == ["a", "b", "c", "d", "e"]
    assert split_values(None) == []


def _lock_contender(path, started, acquired):
    started.set()
    with locked_state_file(Path(path)):
        acquired.set()


def _increment_locked_counter(path, started, iterations):
    started.wait(10)
    path = Path(path)
    for _ in range(iterations):
        with locked_state_file(path):
            value = load_json(path)["count"]
            time.sleep(0.001)
            atomic_write_json_unlocked(path, {"count": value + 1})


def test_lock_blocks_another_process_and_releases_after_exception(tmp_path):
    # Spawn exercises independent file descriptors on Windows and POSIX.
    ctx = multiprocessing.get_context("spawn")
    path = tmp_path / "shared.json"
    started, acquired = ctx.Event(), ctx.Event()
    contender = ctx.Process(target=_lock_contender, args=(str(path), started, acquired))
    try:
        with pytest.raises(RuntimeError, match="release lock"):
            with locked_state_file(path):
                contender.start()
                assert started.wait(10), "contender did not start"
                assert not acquired.wait(0.3), "concurrent process entered the lock"
                raise RuntimeError("release lock")
        assert acquired.wait(10), "lock was not released after an exception"
        contender.join(10)
        assert contender.exitcode == 0
        assert path.with_name(path.name + ".lock").exists()
    finally:
        if contender.is_alive():
            contender.terminate()
            contender.join(10)


def test_concurrent_locked_updates_do_not_lose_writes(tmp_path):
    ctx = multiprocessing.get_context("spawn")
    path = tmp_path / "counter.json"
    atomic_write_json(path, {"count": 0})
    started = ctx.Event()
    workers = [
        ctx.Process(target=_increment_locked_counter, args=(str(path), started, 20))
        for _ in range(2)
    ]
    try:
        for worker in workers:
            worker.start()
        started.set()
        for worker in workers:
            worker.join(15)
            assert worker.exitcode == 0
        assert load_json(path) == {"count": 40}
    finally:
        for worker in workers:
            if worker.is_alive():
                worker.terminate()
                worker.join(10)


def test_lock_sidecar_is_never_truncated_or_replaced(tmp_path):
    path = tmp_path / "doc.json"
    sidecar = path.with_name(path.name + ".lock")
    sidecar.write_bytes(b"legacy marker")
    original_inode = sidecar.stat().st_ino
    for _ in range(2):
        with locked_state_file(path):
            pass
    assert sidecar.read_bytes() == b"legacy marker"
    assert sidecar.stat().st_ino == original_inode
