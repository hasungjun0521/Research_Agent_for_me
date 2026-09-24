"""Tests for the weekly dev deck command.

Data-collection tests use only the standard library. Rendering tests require the
optional ``deck`` extra and are skipped when it is not installed.
"""
from __future__ import annotations

import os
import time
from datetime import date, timedelta
from pathlib import Path

import pytest

from scripts.commands.reports import weekly_deck


def _seed_project(root: Path, today: date) -> None:
    (root / "state" / "sessions").mkdir(parents=True)
    (root / "05_results" / "figures").mkdir(parents=True)
    in_win = (today - timedelta(days=2)).isoformat()
    out_win = (today - timedelta(days=40)).isoformat()
    log = [
        f'{{"timestamp": "{in_win}T10:00:00", "kind": "experiment_result", "summary": "exp A", "exp_id": "e1"}}',
        f'{{"timestamp": "{in_win}T11:00:00", "kind": "result", "summary": "finding B"}}',
        f'{{"timestamp": "{in_win}T12:00:00", "kind": "blocker", "summary": "blk resolved"}}',
        f'{{"timestamp": "{out_win}T10:00:00", "kind": "result", "summary": "old"}}',
    ]
    (root / "state" / "progress_hooks.jsonl").write_text("\n".join(log), encoding="utf-8")
    (root / "05_results" / "experiment_results.csv").write_text(
        "experiment_id,claim_id,dataset,split,method,baseline_id,metric,value,delta,status,evidence,caveat\n"
        "exp1,c1,ds,test,m1,b1,acc,63.5,2.3,done,ev,\n"
        "exp2,c1,ds,test,m1,b1,acc,62.0,1.0,done,ev,\n",
        encoding="utf-8")
    (root / "state").mkdir(exist_ok=True)
    (root / "state" / "next_actions.md").write_text(
        "# Next Actions\n<!-- comment -->\n- action one\n- action two\nplain text line\n", encoding="utf-8")
    # in-window and out-of-window figures
    fig_in = root / "05_results" / "figures" / "good.png"
    fig_out = root / "05_results" / "figures" / "stale.png"
    fig_in.write_bytes(b"\x89PNG\r\n")
    fig_out.write_bytes(b"\x89PNG\r\n")
    mid = time.mktime((today - timedelta(days=1)).timetuple())
    old = time.mktime((today - timedelta(days=60)).timetuple())
    os.utime(fig_in, (mid, mid))
    os.utime(fig_out, (old, old))


def test_collect_week_data_counts(tmp_path: Path) -> None:
    today = date.today()
    root = tmp_path / "proj"
    _seed_project(root, today)
    week = weekly_deck.collect_week_data(
        root=root, repo=tmp_path, project="proj",
        since=today - timedelta(days=7), until=today,
        metric=None, max_figures=4, cover_date="week", title=None)

    assert week["metric"] == "acc"
    assert week["title"] == "proj"
    # highlights: experiment_result + result in window (not blocker, not old)
    assert "exp A" in week["highlights"]
    assert "finding B" in week["highlights"]
    assert "old" not in week["highlights"]
    kpis = {k["label"]: k["value"] for k in week["kpis"]}
    assert kpis["실험"] == 1            # one experiment_result/exp_id in window
    assert kpis["블로커 기록"] == 1      # one blocker record in window
    assert week["kpis"][1]["value"] == "+2.30"   # best delta
    assert len(week["deltas"]) == 2
    assert week["trend"] is not None and len(week["trend"]["ours"]) == 2
    assert week["next_actions"] == ["action one", "action two"]
    assert [f["caption"] for f in week["figures"]] == ["good"]


def test_results_window_filtered_by_journal(tmp_path: Path) -> None:
    """Result rows whose journal updated_at is outside the window are excluded."""
    today = date.today()
    root = tmp_path / "proj"
    _seed_project(root, today)
    in_win = (today - timedelta(days=2)).isoformat()
    out_win = (today - timedelta(days=40)).isoformat()
    (root / "05_results" / "experiment_journal.csv").write_text(
        "updated_at,experiment,rationale,dataset,method,baseline,result_summary,result_analysis,evidence,caveat\n"
        f"{in_win}T10:00:00,exp1,,,,,ok,why,ev,\n"
        f"{out_win}T10:00:00,exp2,,,,,ok,why,ev,\n",
        encoding="utf-8")
    week = weekly_deck.collect_week_data(
        root=root, repo=tmp_path, project="proj",
        since=today - timedelta(days=7), until=today,
        metric=None, max_figures=4, cover_date="week", title=None)
    assert [d["name"] for d in week["deltas"]] == ["exp1"]
    assert week["trend"] is None  # one in-window point is not enough for a trend


def test_collect_week_data_empty(tmp_path: Path) -> None:
    today = date.today()
    root = tmp_path / "empty"
    (root / "state" / "sessions").mkdir(parents=True)
    week = weekly_deck.collect_week_data(
        root=root, repo=tmp_path, project="empty",
        since=today - timedelta(days=7), until=today,
        metric=None, max_figures=4, cover_date="today", title="Empty")
    assert week["highlights"] == []
    assert week["trend"] is None
    assert week["deltas"] == []
    assert week["figures"] == []
    assert week["cover_date"] == today.isoformat()


def test_resolve_template_cli_override(tmp_path: Path) -> None:
    custom = tmp_path / "base.pptx"
    custom.write_bytes(b"x")
    assert weekly_deck.resolve_template(tmp_path, str(custom)) == custom


def test_require_deps_message() -> None:
    pytest.importorskip("pptx", reason="deck extra installed -> skip the missing-deps path")
    # When deps ARE present, _require_deps must not raise.
    pytest.importorskip("matplotlib")
    weekly_deck._require_deps()


def test_build_deck_fallback(tmp_path: Path) -> None:
    pytest.importorskip("pptx")
    pytest.importorskip("matplotlib")
    from scripts.commands.reports import weekly_deck_builder as builder
    today = date.today()
    week = {
        "title": "Demo", "project": "demo", "since": today - timedelta(days=7), "until": today,
        "cover_date": "week", "metric": "acc", "takeaway": "ok",
        "kpis": [{"label": "실험", "value": 3, "unit": "건", "color": "accent"}],
        "highlights": ["did a thing"], "trend": None, "deltas": [],
        "next_actions": ["next thing"], "figures": [],
    }
    out = tmp_path / "deck.pptx"
    builder.build_deck(week, None, out, tmp_path / "_build")
    assert out.is_file() and out.stat().st_size > 0


def test_strip_bracket_decorations_on_template() -> None:
    pptx = pytest.importorskip("pptx")
    template = weekly_deck.repo_root() / "config" / "ppt_template_local.pptx"
    if not template.is_file():
        pytest.skip("local template not present")
    from scripts.commands.reports import weekly_deck_builder as builder
    prs = pptx.Presentation(str(template))
    assert builder.strip_bracket_decorations(prs) >= 1
