"""Tests for the agent-memory compaction command."""

from __future__ import annotations

from datetime import date
from datetime import datetime as _real_datetime
from pathlib import Path

from scripts.commands.review import memory_compact
from scripts.commands.review.memory_compact import (
    plan_compaction,
    render_archive_addition,
    render_live,
    run_compact,
)

HEADER = (
    "# Agent Memory\n\n"
    "Stable facts.\n\n"
    "## Stable Project Facts\n\n"
    "- Project name: demo\n\n"
    "## Operating Model\n\n"
    "- Use harness CLIs.\n"
)


def _checkpoint(stamp: str, note: str) -> str:
    return (
        f"\n## Memory Checkpoint: {stamp}\n\n"
        f"- Source: result by `director`\n"
        f"- Summary: {note}\n"
        f"- {note}\n"
    )


def _seed_memory(root: Path, checkpoints: list[tuple[str, str]]) -> Path:
    path = root / "state" / "agent_memory.md"
    path.parent.mkdir(parents=True)
    text = HEADER + "".join(_checkpoint(s, n) for s, n in checkpoints)
    path.write_text(text, encoding="utf-8")
    return path


def test_split_keeps_curated_sections_separate_from_checkpoints():
    text = HEADER + _checkpoint("2026-01-01T10:00:00+09:00", "old note")
    segments = memory_compact.split_segments(text)
    kinds = [s["kind"] for s in segments]
    assert kinds.count("checkpoint") == 1
    curated = "".join(s["text"] for s in segments if s["kind"] == "curated")
    assert "## Stable Project Facts" in curated
    assert "## Operating Model" in curated
    assert "old note" not in curated


def test_old_checkpoints_archived_recent_and_curated_kept(tmp_path):
    root = tmp_path / "proj"
    _seed_memory(root, [
        ("2026-01-01T10:00:00+09:00", "ancient"),
        ("2026-05-01T10:00:00+09:00", "old"),
        ("2026-06-10T10:00:00+09:00", "recent"),
    ])
    result = run_compact(root, older_than_days=30, keep_recent=1,
                         apply=True, today=date(2026, 6, 12),
                         stamp="2026-06-12T22:00:00+09:00")
    assert result["archived_count"] == 2
    assert result["kept_count"] == 1
    live = (root / "state" / "agent_memory.md").read_text(encoding="utf-8")
    assert "## Stable Project Facts" in live      # curated kept
    assert "recent" in live                        # recent kept
    assert "ancient" not in live and "old" not in live
    archive = (root / "state" / "sessions" / "memory_archive.md").read_text(encoding="utf-8")
    assert "ancient" in archive and "old" in archive
    assert result["bytes_after"] < result["bytes_before"]


def test_keep_recent_pins_newest_even_when_old(tmp_path):
    root = tmp_path / "proj"
    _seed_memory(root, [
        ("2026-01-01T10:00:00+09:00", "a"),
        ("2026-01-02T10:00:00+09:00", "b"),
        ("2026-01-03T10:00:00+09:00", "c"),
    ])
    # All three are older than cutoff, but keep_recent=2 pins the two newest.
    plan = plan_compaction(
        (root / "state" / "agent_memory.md").read_text(encoding="utf-8"),
        older_than_days=30, keep_recent=2, today=date(2026, 6, 12))
    archived = [s["stamp"] for s in plan["archived"]]
    assert archived == ["2026-01-01T10:00:00+09:00"]


def test_checkpoint_body_with_markdown_heading_is_not_fragmented(tmp_path):
    """A '## ' line inside a checkpoint body must not split the block."""
    root = tmp_path / "proj"
    path = root / "state" / "agent_memory.md"
    path.parent.mkdir(parents=True)
    path.write_text(
        HEADER
        + "\n## Memory Checkpoint: 2026-01-01T10:00:00+09:00\n\n"
          "- Summary: did X\n"
          "## A subheading the agent wrote in the note\n"
          "- trailing detail\n",
        encoding="utf-8")
    plan = plan_compaction(path.read_text(encoding="utf-8"),
                           older_than_days=30, keep_recent=0, today=date(2026, 6, 12))
    assert len(plan["archived"]) == 1
    archived_text = plan["archived"][0]["text"]
    # The whole block — including the body subheading and trailing detail —
    # archives together; nothing is left orphaned in the live file.
    assert "## A subheading the agent wrote in the note" in archived_text
    assert "trailing detail" in archived_text
    kept = "".join(s["text"] for s in plan["kept_segments"])
    assert "trailing detail" not in kept
    assert "## Stable Project Facts" in kept


def test_no_checkpoint_is_lost_across_live_and_archive(tmp_path):
    """Round-trip: every original checkpoint appears exactly once in either
    the rewritten live file or the archive — never dropped, never duplicated."""
    import re
    root = tmp_path / "proj"
    path = _seed_memory(root, [
        ("2026-01-01T10:00:00+09:00", "a"),
        ("2026-03-01T10:00:00+09:00", "b"),
        ("2026-06-09T10:00:00+09:00", "c"),
        ("2026-06-11T10:00:00+09:00", "d"),
    ])
    original = re.findall(r"## Memory Checkpoint: (.+)", path.read_text(encoding="utf-8"))
    plan = plan_compaction(path.read_text(encoding="utf-8"),
                           older_than_days=30, keep_recent=1, today=date(2026, 6, 12))
    live = render_live(plan["kept_segments"])
    archive = render_archive_addition(plan["archived"], "S")
    combined = re.findall(r"## Memory Checkpoint: (.+)", live) + \
        re.findall(r"## Memory Checkpoint: (.+)", archive)
    assert sorted(combined) == sorted(original)
    assert len(combined) == len(set(combined))
    # Body-level conservation: each checkpoint's full block text survives
    # exactly once across the live file and the archive.
    plan = plan_compaction(path.read_text(encoding="utf-8"),
                           older_than_days=30, keep_recent=1, today=date(2026, 6, 12))
    for note in ("a", "b", "c", "d"):
        body = f"- Summary: {note}\n"
        assert (live.count(body) + archive.count(body)) == 1


def test_undated_checkpoints_are_never_archived(tmp_path):
    root = tmp_path / "proj"
    _seed_memory(root, [("not-a-date", "weird"), ("2026-01-01T10:00:00+09:00", "old")])
    plan = plan_compaction(
        (root / "state" / "agent_memory.md").read_text(encoding="utf-8"),
        older_than_days=30, keep_recent=0, today=date(2026, 6, 12))
    stamps = [s["stamp"] for s in plan["archived"]]
    assert "not-a-date" not in stamps
    assert "2026-01-01T10:00:00+09:00" in stamps


def test_preview_does_not_write(tmp_path):
    root = tmp_path / "proj"
    path = _seed_memory(root, [("2026-01-01T10:00:00+09:00", "old")])
    before = path.read_text(encoding="utf-8")
    result = run_compact(root, older_than_days=30, keep_recent=0,
                         apply=False, today=date(2026, 6, 12), stamp="x")
    assert result["archived_count"] == 1
    assert result["applied"] is False
    assert path.read_text(encoding="utf-8") == before
    assert not (root / "state" / "sessions" / "memory_archive.md").exists()


def test_main_missing_memory_file_exits_1(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(memory_compact, "project_root", lambda name: tmp_path / "missing")
    (tmp_path / "missing").mkdir()
    code = memory_compact.main(["--project", "missing"])
    assert code == 1
    assert "Memory file not found" in capsys.readouterr().out


class _FixedDatetime(_real_datetime):
    """datetime stand-in so main() does not depend on the wall clock.

    Subclasses the real datetime so fromisoformat/etc. keep working; only now()
    is pinned.
    """

    @classmethod
    def now(cls, tz=None):
        return _real_datetime(2026, 6, 12, 22, 0, 0).astimezone(tz)


def test_main_json_output(tmp_path, monkeypatch, capsys):
    root = tmp_path / "proj"
    _seed_memory(root, [("2026-01-01T10:00:00+09:00", "old")])
    monkeypatch.setattr(memory_compact, "project_root", lambda name: root)
    monkeypatch.setattr(memory_compact, "datetime", _FixedDatetime)
    code = memory_compact.main(["--project", "proj", "--keep-recent", "0", "--json"])
    assert code == 0
    import json
    payload = json.loads(capsys.readouterr().out)
    assert payload["archived_count"] == 1
    assert payload["applied"] is False
