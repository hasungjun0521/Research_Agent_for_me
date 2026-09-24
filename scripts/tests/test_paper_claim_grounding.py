"""Tests for the statement-to-evidence grounding check in paper_claim_linter."""

from __future__ import annotations

from scripts.commands.reports.paper_claim_linter import ungrounded_statement_warnings

ROWS = [{"value": "41.2", "delta": "1.0"}]


def test_qualitative_superlative_without_evidence_is_flagged():
    paper = "Our method substantially outperforms all prior work."
    warnings = ungrounded_statement_warnings(paper, ROWS, set())
    assert len(warnings) == 1
    assert "Ungrounded claim statement" in warnings[0]


def test_grounded_by_matching_number_is_ok():
    paper = "Our method outperforms the baseline by 41.2 points."
    assert ungrounded_statement_warnings(paper, ROWS, set()) == []


def test_grounded_by_citation_is_ok():
    paper = "Our method significantly outperforms prior work \\citep{smith2024}."
    assert ungrounded_statement_warnings(paper, ROWS, set()) == []


def test_grounded_by_claim_id_is_ok():
    paper = "Our method substantially outperforms the baseline (claim_001)."
    assert ungrounded_statement_warnings(paper, ROWS, {"claim_001"}) == []


def test_non_claim_sentences_are_ignored():
    paper = "We describe the method and the datasets used in our study."
    assert ungrounded_statement_warnings(paper, ROWS, set()) == []


def test_claim_macro_counts_as_grounding():
    paper = "Our method is state-of-the-art \\claim{c1}."
    assert ungrounded_statement_warnings(paper, ROWS, set()) == []


def test_numbered_claims_are_left_to_the_quantitative_check():
    # A numbered comparative sentence is owned by quantitative_claim_warnings
    # (which verifies the number), so the grounding check defers and stays quiet.
    paper = "Our method outperforms everything at 99.9 accuracy."
    assert ungrounded_statement_warnings(paper, ROWS, set()) == []


def test_citation_in_following_chunk_grounds_the_claim():
    # Abbreviation-split: "et al." ends a chunk, the citation lands in the next.
    paper = "Our method outperforms the approach of Smith et al. \\citep{smith2024}."
    assert ungrounded_statement_warnings(paper, ROWS, set()) == []


def test_biblatex_citation_grounds_the_claim():
    paper = "Our method outperforms prior work \\parencite{x}."
    assert ungrounded_statement_warnings(paper, ROWS, set()) == []


def test_ambiguous_adverbs_alone_do_not_trigger():
    paper = "Performance changed significantly during warmup."
    assert ungrounded_statement_warnings(paper, ROWS, set()) == []


def test_substring_traps_do_not_false_positive():
    # 'heartbeats' contains 'beats', 'Minnesota' contains 'sota' — word-boundary
    # matching must not treat these as strong claims.
    for paper in (
        "The model logs heartbeats during training.",
        "We evaluate on the Minnesota traffic dataset.",
        "This repeats the prior experimental setup.",
    ):
        assert ungrounded_statement_warnings(paper, ROWS, set()) == []
