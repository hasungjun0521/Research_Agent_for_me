"""Unit tests for source credibility audit bib-entry hygiene checks."""

from __future__ import annotations

from scripts.commands.reports import source_credibility_audit as sca

DIRTY_BIB = """
@article{dup_key,
  title = {First Title},
  author = {A. Author},
  year = {2024},
  journal = {NeurIPS},
}

@article{dup_key,
  title = {Second Title},
  author = {B. Author},
  year = {2023},
  journal = {ICML},
}

@misc{todo_placeholder_entry,
  title = {Some Placeholder Title},
  author = {C. Author},
  year = {2024},
}

@article{near_a,
  title = {Deep   Learning, for Robots!},
  author = {D. Author},
  year = {2022},
  journal = {Journal X},
}

@article{near_b,
  title = "deep learning for robots",
  author = {E. Author},
  year = {2021},
  journal = {Journal Y},
}

@article{missing_stuff,
  title = {Has Title Only},
}

@article{arxiv_one,
  title = {Preprint One},
  author = {F. Author},
  year = {2024},
  journal = {arXiv preprint arXiv:2401.00001},
}

@misc{arxiv_two,
  title = {Preprint Two},
  author = {G. Author},
  year = {2025},
  url = {https://arxiv.org/abs/2502.12345},
}
"""

CLEAN_BIB = """
@article{clean_one,
  title = {A Clean Title},
  author = {A. Author},
  year = {2024},
  journal = {NeurIPS},
}

@inproceedings{clean_two,
  title = {Another Distinct Title},
  author = {B. Author},
  year = {2023},
  booktitle = {ICML},
}
"""

NEW_CHECK_NAMES = {
    "bib_duplicate_keys",
    "bib_placeholder_entries",
    "bib_near_duplicate_titles",
    "bib_missing_fields",
    "bib_arxiv_preprints",
}

ORIGINAL_SUMMARY_KEYS = {
    "bibliography_keys",
    "citation_keys",
    "paper_notes",
    "missing_citations",
    "uncited_sources",
    "claim_rows_without_source",
}


def make_project(tmp_path, bib_text, name="unit_project"):
    root = tmp_path / name
    (root / "01_literature").mkdir(parents=True)
    (root / "01_literature" / "papers.bib").write_text(bib_text, encoding="utf-8")
    return root


def checks_by_name(report):
    return {check["check"]: check for check in report["checks"]}


def test_dirty_bib_flags_each_hygiene_check(tmp_path):
    root = make_project(tmp_path, DIRTY_BIB)
    report = sca.audit_project(root)

    hygiene = report["bib_hygiene"]
    assert hygiene["entries"] == 8
    assert hygiene["duplicate_keys"] == ["dup_key"]
    assert hygiene["placeholder_keys"] == ["todo_placeholder_entry"]
    assert hygiene["near_duplicate_titles"] == [["near_a", "near_b"]]
    assert hygiene["missing_field_total"] == 1
    assert hygiene["missing_field_entries"] == ["missing_stuff: missing author, year"]
    assert hygiene["missing_field_details_capped"] is False
    assert hygiene["arxiv_preprint_count"] == 2

    summary = report["summary"]
    assert summary["bib_entries"] == 8
    assert summary["duplicate_bib_keys"] == 1
    assert summary["placeholder_bib_entries"] == 1
    assert summary["near_duplicate_bib_titles"] == 1
    assert summary["bib_entries_missing_fields"] == 1
    assert summary["arxiv_preprints"] == 2
    assert ORIGINAL_SUMMARY_KEYS <= set(summary)

    checks = checks_by_name(report)
    assert NEW_CHECK_NAMES <= set(checks)
    assert checks["bib_duplicate_keys"]["status"] == "blocker"
    assert checks["bib_placeholder_entries"]["status"] == "blocker"
    assert checks["bib_near_duplicate_titles"]["status"] == "blocker"
    assert checks["bib_missing_fields"]["status"] == "warning"
    assert checks["bib_arxiv_preprints"]["status"] == "info"

    assert any("duplicate bib key" in item for item in report["blockers"])
    assert any("placeholder bib entry" in item for item in report["blockers"])
    assert any("near-duplicate bib title" in item for item in report["blockers"])
    assert any("missing essential field" in item for item in report["warnings"])
    # The arXiv count is informational only: never a warning or blocker.
    assert not any("arxiv" in item.lower() for item in report["warnings"])
    assert not any("arxiv" in item.lower() for item in report["blockers"])


def test_dirty_bib_markdown_mentions_hygiene_findings(tmp_path):
    root = make_project(tmp_path, DIRTY_BIB)
    markdown = sca.render_markdown(sca.audit_project(root))
    assert "## Bib Entry Hygiene" in markdown
    assert "bib_duplicate_keys" in markdown
    assert "bib_placeholder_entries" in markdown
    assert "bib_near_duplicate_titles" in markdown
    assert "bib_missing_fields" in markdown
    assert "bib_arxiv_preprints" in markdown
    assert "missing_stuff: missing author, year" in markdown
    assert "arXiv preprints (informational): 2" in markdown


def test_dirty_bib_rows_reach_csv(tmp_path):
    root = make_project(tmp_path, DIRTY_BIB)
    report = sca.audit_project(root)
    csv_path = sca.write_csv(root, report)
    content = csv_path.read_text(encoding="utf-8")
    for check_name in NEW_CHECK_NAMES:
        assert check_name in content


def test_strict_exit_codes_via_main(tmp_path, monkeypatch, capsys):
    dirty = make_project(tmp_path, DIRTY_BIB, name="dirty_project")
    clean = make_project(tmp_path, CLEAN_BIB, name="clean_project")
    roots = {"dirty_project": dirty, "clean_project": clean}
    monkeypatch.setattr(sca, "project_root", lambda name: roots[name])

    assert sca.main(["--project", "dirty_project", "--strict"]) == 1
    assert sca.main(["--project", "clean_project", "--strict"]) == 0
    capsys.readouterr()


def test_clean_bib_yields_no_new_warnings_or_blockers(tmp_path):
    root = make_project(tmp_path, CLEAN_BIB)
    report = sca.audit_project(root)

    assert report["blockers"] == []
    checks = checks_by_name(report)
    assert checks["bib_duplicate_keys"]["status"] == "pass"
    assert checks["bib_placeholder_entries"]["status"] == "pass"
    assert checks["bib_near_duplicate_titles"]["status"] == "pass"
    assert checks["bib_missing_fields"]["status"] == "pass"
    assert checks["bib_arxiv_preprints"]["status"] == "info"
    assert not any("bib" in item.lower() for item in report["warnings"])

    summary = report["summary"]
    assert summary["bib_entries"] == 2
    assert summary["duplicate_bib_keys"] == 0
    assert summary["placeholder_bib_entries"] == 0
    assert summary["near_duplicate_bib_titles"] == 0
    assert summary["bib_entries_missing_fields"] == 0
    assert summary["arxiv_preprints"] == 0


def test_empty_title_field_counts_as_placeholder(tmp_path):
    bib = "@article{empty_title, title = {}, author = {A}, year = {2024}}\n"
    root = make_project(tmp_path, bib)
    report = sca.audit_project(root)
    assert report["bib_hygiene"]["placeholder_keys"] == ["empty_title"]


def test_malformed_bib_never_crashes(tmp_path):
    malformed = CLEAN_BIB + "\n@article{broken, title = {unclosed brace\nrandom garbage ===\n@@@\n"
    root = make_project(tmp_path, malformed)
    report = sca.audit_project(root)
    hygiene = report["bib_hygiene"]
    assert hygiene["entries"] >= 3
    assert "clean_one" not in hygiene["duplicate_keys"]
    # Rendering the malformed result must not crash either.
    assert "## Bib Entry Hygiene" in sca.render_markdown(report)


def test_missing_field_details_capped_at_fifty_with_note(tmp_path):
    parts = []
    for index in range(60):
        tag = f"{index:03d}"
        parts.append(
            "@article{key_" + tag + ",\n"
            "  title = {Distinct Title " + tag + "},\n"
            "  author = {A. Author},\n"
            "}\n"
        )
    root = make_project(tmp_path, "\n".join(parts))
    report = sca.audit_project(root)

    hygiene = report["bib_hygiene"]
    assert hygiene["missing_field_total"] == 60
    assert len(hygiene["missing_field_entries"]) == 50
    assert hygiene["missing_field_details_capped"] is True

    markdown = sca.render_markdown(report)
    assert "showing first 50 of 60" in markdown


def test_nested_brace_titles_parse_fully():
    """Depth-2 brace values (whole-title protection + protected acronym) must
    not truncate at the first comma."""
    from scripts.commands.reports.source_credibility_audit import parse_bib_entries

    entries = parse_bib_entries(
        "@article{nested2026,\n"
        "  title = {{Deep {RNN} Models for Speech, Part One}},\n"
        "  author = {Author, Some},\n"
        "  year = {2026},\n"
        "}\n")
    assert entries[0]["key"] == "nested2026"
    assert entries[0]["fields"]["title"] == "{Deep {RNN} Models for Speech, Part One}"
    assert entries[0]["fields"]["year"] == "2026"
