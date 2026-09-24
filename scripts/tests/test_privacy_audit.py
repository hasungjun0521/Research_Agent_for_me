"""Cross-platform local-path coverage for publication privacy checks."""

from __future__ import annotations

import json

import pytest

from scripts.commands.release.privacy_audit import (
    audit_privacy,
    default_private_markers,
    scan_file,
)


def local_paths():
    backslash = chr(92)
    windows = "C:" + backslash + backslash.join(("Users", "Example", "research"))
    return [
        windows,
        windows.replace(backslash, "/"),
        json.dumps({"output": windows}),
        "D:" + backslash + backslash.join(("datasets", "private")),
        backslash * 2 + backslash.join(("lab-server", "private-share", "results")),
        "/" + "/".join(("Users", "Example", "research")),
        "/" + "/".join(("home", "example", "research")),
        "/" + "/".join(("data", "private", "results")),
    ]


@pytest.mark.parametrize("content", local_paths())
def test_scan_file_detects_local_paths_across_platforms(tmp_path, content):
    path = tmp_path / "report.md"
    path.write_text("output=" + content, encoding="utf-8")
    assert scan_file(path, markers=[])


@pytest.mark.parametrize("content", [
    "projects/template/04_code/train.py",
    "https://example.org/data/dataset",
    "Use pathlib.Path for platform-independent paths.",
    chr(92) * 2 + "claim(?:id)?" + chr(92) * 2 + "{([^}]+",
])
def test_scan_file_allows_relative_paths_and_urls(tmp_path, content):
    path = tmp_path / "report.md"
    path.write_text(content, encoding="utf-8")
    assert not scan_file(path, markers=[])


def test_audit_reports_file_without_echoing_private_contents(tmp_path):
    path = tmp_path / "report.md"
    path.write_text(local_paths()[0], encoding="utf-8")
    report = audit_privacy(tmp_path, paths=[path.name], markers=[])
    assert report["ok"] is False
    assert report["findings"] == [{"path": "report.md", "issue": "private_or_local_marker"}]
    assert local_paths()[0] not in json.dumps(report)


def test_default_markers_use_windows_username(tmp_path, monkeypatch):
    monkeypatch.delenv("USER", raising=False)
    monkeypatch.setenv("USERNAME", "example-researcher")
    assert "example-researcher's" in default_private_markers(tmp_path)
