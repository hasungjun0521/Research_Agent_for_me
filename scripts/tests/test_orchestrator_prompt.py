"""Tests for the lean/full dispatched-prompt rendering."""

from __future__ import annotations

from scripts.commands.agents.agent_orchestrator import (
    SHARED_CONTRACT_POINTERS,
    render_shared_contracts,
)

# A heading that only exists inside the body of output_contracts.md.
OUTPUT_CONTRACTS_BODY_MARKER = "## Claim-Evidence-Uncertainty Format"
# Titles the harness smoke test requires every dispatched prompt to reference.
SMOKE_REQUIRED_TITLES = (
    "Research Routing Matrix",
    "Research Handoff Graph",
    "Research Leader Dispatch Protocol",
    "Research Risk And Confidence Matrix",
    "Research Brain Protocol",
)


def test_lean_contracts_are_pointers_not_bodies():
    lean = render_shared_contracts("lean")
    assert OUTPUT_CONTRACTS_BODY_MARKER not in lean
    for rel, title, _purpose in SHARED_CONTRACT_POINTERS:
        if rel == "prompts/shared/filesystem_safety_rules.md":
            continue
        assert rel in lean and title in lean, f"pointer missing for {rel}"
    for title in SMOKE_REQUIRED_TITLES:
        assert title in lean
    # Safety rules stay inlined (body present, no pointer bullet).
    assert "# Filesystem Safety Rules" in lean
    assert "- `prompts/shared/filesystem_safety_rules.md`" not in lean


def test_full_contracts_inline_bodies():
    full = render_shared_contracts("full")
    assert OUTPUT_CONTRACTS_BODY_MARKER in full


def test_lean_is_substantially_smaller_than_full():
    lean = render_shared_contracts("lean")
    full = render_shared_contracts("full")
    assert len(lean) < len(full) / 5
