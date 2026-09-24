"""Tests for the bounded log digest command."""

from __future__ import annotations

from pathlib import Path

from scripts.commands.experiments.log_digest import DEFAULT_PATTERNS, build_digest, main


def _write_log(path: Path, n_filler: int = 500, n_errors: int = 10) -> None:
    lines = ["start of training run", "config: lr=1e-4 batch=8"]
    for i in range(n_filler):
        lines.append(f"step {i} loss=0.{i:04d}")
        if i % (n_filler // n_errors) == 0:
            lines.append(f"ERROR: CUDA out of memory at step {i}")
    lines.append("final eval acc=61.2")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_digest_contains_head_tail_and_matches(tmp_path):
    log = tmp_path / "run.log"
    _write_log(log)
    digest = build_digest(log, head_bytes=200, tail_bytes=200,
                          patterns=list(DEFAULT_PATTERNS), max_matches=200)
    assert "start of training run" in digest          # head
    assert "final eval acc=61.2" in digest            # tail
    assert "CUDA out of memory" in digest             # pattern match
    assert "pattern_matches_total: 10" in digest      # one line per oom step, counted once


def test_match_truncation_is_explicit(tmp_path):
    log = tmp_path / "run.log"
    log.write_text("\n".join(f"ERROR number {i}" for i in range(50)) + "\n", encoding="utf-8")
    # head/tail disabled so only the match-retention block can satisfy these.
    digest = build_digest(log, head_bytes=0, tail_bytes=0,
                          patterns=[r"error"], max_matches=10)
    assert "[L1] ERROR number 0" in digest            # first half kept
    assert "[L50] ERROR number 49" in digest          # last half kept
    assert "matched lines omitted" in digest          # no silent caps
    assert "--max-matches 50" in digest


def test_head_and_tail_never_overlap(tmp_path):
    log = tmp_path / "run.log"
    log.write_text("\n".join(f"line {i:03d}" for i in range(100)) + "\n", encoding="utf-8")
    size = log.stat().st_size
    digest = build_digest(log, head_bytes=600, tail_bytes=600,
                          patterns=[r"error"], max_matches=10)
    # head covers bytes [0,600); tail must start at 600, not size-600.
    assert digest.count("line 050") == 1
    assert f"## Tail (last {size - 600} bytes)" in digest


def test_invalid_pattern_is_clean_error(tmp_path, capsys):
    log = tmp_path / "run.log"
    log.write_text("hello\n", encoding="utf-8")
    assert main(["--log", str(log), "--pattern", "["]) == 1
    assert "Invalid --pattern regex" in capsys.readouterr().out


def test_no_matches_path(tmp_path):
    log = tmp_path / "clean.log"
    log.write_text("all good\nnothing to see\n", encoding="utf-8")
    digest = build_digest(log, head_bytes=64, tail_bytes=64,
                          patterns=[r"error"], max_matches=10)
    assert "No pattern matches found." in digest


def test_main_writes_out_file_and_errors_on_missing(tmp_path, capsys):
    log = tmp_path / "run.log"
    _write_log(log, n_filler=20, n_errors=2)
    out = tmp_path / "digest.md"
    assert main(["--log", str(log), "--out", str(out)]) == 0
    assert out.is_file() and "Log Digest" in out.read_text(encoding="utf-8")
    assert main(["--log", str(tmp_path / "missing.log")]) == 1
    assert "error:" in capsys.readouterr().out
