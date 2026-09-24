"""Unit tests for the unified data_roots.md writers."""

from __future__ import annotations

from scripts.harness.data_roots import (
    DATA_ROOTS_HEADER,
    sync_dataset_to_data_roots,
)
from scripts.harness.experiment_registry import append_data_root_rows, data_root_row


def data_roots_text(root):
    return (root / "03_experiments" / "data_roots.md").read_text(encoding="utf-8")


def registry_row(data_id, *, root_uri="s3://bucket/x", notes="note", timestamp="2026-06-10T12:00:00"):
    return data_root_row(
        data_id=data_id,
        root_uri=root_uri,
        split_version="v1",
        produced_by="agent",
        used_by_experiments="exp_001",
        status="active",
        notes=notes,
        timestamp=timestamp,
    )


def test_both_writers_share_one_canonical_table(tmp_path):
    append_data_root_rows(tmp_path, [registry_row("ds1")])
    sync_dataset_to_data_roots(
        tmp_path,
        {"id": "ds2", "source": "s3://bucket/y", "split": "v2"},
        producer="intake",
        notes="second",
    )
    text = data_roots_text(tmp_path)
    assert text.count(DATA_ROOTS_HEADER[4]) == 1, "exactly one canonical table header"
    assert "| ds1 |" in text and "| ds2 |" in text


def test_registry_writer_upserts_instead_of_duplicating(tmp_path):
    append_data_root_rows(tmp_path, [registry_row("ds1", root_uri="s3://bucket/old")])
    append_data_root_rows(tmp_path, [registry_row("ds1", root_uri="s3://bucket/new")])
    text = data_roots_text(tmp_path)
    rows = [line for line in text.splitlines() if line.startswith("| ds1 |")]
    assert len(rows) == 1
    assert "s3://bucket/new" in rows[0]
    assert "s3://bucket/old" not in text


def test_timestamp_is_preserved_in_notes(tmp_path):
    append_data_root_rows(tmp_path, [registry_row("ds1", timestamp="2026-06-10T13:00:00")])
    assert "(updated 2026-06-10T13:00:00)" in data_roots_text(tmp_path)


def test_rows_are_never_appended_under_a_foreign_table_header(tmp_path):
    path = tmp_path / "03_experiments" / "data_roots.md"
    path.parent.mkdir(parents=True)
    legacy = "\n".join([
        "# Experiment Data Roots",
        "",
        "| Updated At | Data ID | Root / URI | Split / Version | Produced By | Used By Experiments | Status | Notes |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
        "| 2026-01-01 | old_ds | s3://bucket/legacy | v0 | agent | exp_000 | active | legacy row |",
        "",
    ])
    path.write_text(legacy, encoding="utf-8")
    append_data_root_rows(tmp_path, [registry_row("ds_new")])
    text = data_roots_text(tmp_path)
    legacy_table_index = text.index("| Updated At |")
    canonical_index = text.index(DATA_ROOTS_HEADER[4])
    new_row_index = text.index("| ds_new |")
    assert canonical_index > legacy_table_index, "canonical table appended as its own section"
    assert new_row_index > canonical_index, "new row lands under the canonical header"
    assert "| 2026-01-01 | old_ds |" in text, "legacy rows preserved untouched"


def test_starter_placeholder_row_is_replaced(tmp_path):
    path = tmp_path / "03_experiments" / "data_roots.md"
    path.parent.mkdir(parents=True)
    starter = "\n".join([
        *DATA_ROOTS_HEADER,
        "| to_be_defined | pending | pending | pending | pending | planned | starter |",
        "",
    ])
    path.write_text(starter, encoding="utf-8")
    append_data_root_rows(tmp_path, [registry_row("ds1")])
    text = data_roots_text(tmp_path)
    assert "to_be_defined" not in text
    assert "| ds1 |" in text
