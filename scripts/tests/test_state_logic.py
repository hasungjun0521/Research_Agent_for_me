"""Unit tests for command-queue and vote-gate logic in scripts/harness/state.py."""

from __future__ import annotations

import pytest

from scripts.harness.state import (
    HarnessError,
    evaluate_vote_decision,
    load_command_queue,
    mutate_command_queue,
    owner_matches,
    update_command_for_agent,
    validate_command_queue_doc,
)


def make_command(command_id, *, owner="code_agent", status="open", depends_on=None):
    command = {
        "id": command_id,
        "action": f"do {command_id}",
        "owner_agent": owner,
        "priority": "medium",
        "status": status,
        "display_summary": "summary",
        "why_now": "why",
        "done_when": "done",
        "parallel_group": "",
    }
    if depends_on is not None:
        command["depends_on"] = depends_on
    return command


def queue_doc(commands):
    return {"project": "unit", "commands": commands}


class TestCommandQueueValidation:
    def test_dependency_cycle_is_rejected(self):
        doc = queue_doc([
            make_command("a", depends_on=["b"]),
            make_command("b", depends_on=["a"]),
        ])
        with pytest.raises(HarnessError, match="cycle"):
            validate_command_queue_doc(doc)

    def test_unknown_dependency_is_rejected(self):
        doc = queue_doc([make_command("a", depends_on=["ghost"])])
        with pytest.raises(HarnessError, match="unknown command id"):
            validate_command_queue_doc(doc)

    def test_self_dependency_is_rejected(self):
        doc = queue_doc([make_command("a", depends_on=["a"])])
        with pytest.raises(HarnessError, match="depends on itself"):
            validate_command_queue_doc(doc)

    def test_duplicate_command_id_is_rejected(self):
        doc = queue_doc([make_command("a"), make_command("a")])
        with pytest.raises(HarnessError, match="Duplicate command id"):
            validate_command_queue_doc(doc)

    def test_valid_chain_passes(self):
        doc = queue_doc([
            make_command("a"),
            make_command("b", depends_on=["a"]),
            make_command("c", depends_on=["a", "b"]),
        ])
        assert isinstance(validate_command_queue_doc(doc), list)


class TestMutateCommandQueue:
    def test_add_then_load_roundtrip(self, tmp_path):
        mutate_command_queue(tmp_path, lambda doc: doc["commands"].append(make_command("cmd_x")))
        loaded = load_command_queue(tmp_path)
        assert [command["id"] for command in loaded["commands"]] == ["cmd_x"]

    def test_invalid_mutation_is_not_persisted(self, tmp_path):
        mutate_command_queue(tmp_path, lambda doc: doc["commands"].append(make_command("cmd_x")))
        with pytest.raises(HarnessError):
            mutate_command_queue(
                tmp_path,
                lambda doc: doc["commands"].append({"id": "bad", "status": "nope", "priority": "medium"}),
            )
        loaded = load_command_queue(tmp_path)
        assert [command["id"] for command in loaded["commands"]] == ["cmd_x"]

    def test_update_command_enforces_ownership(self, tmp_path):
        mutate_command_queue(
            tmp_path,
            lambda doc: doc["commands"].append(make_command("cmd_x", owner="code_agent")),
        )
        with pytest.raises(HarnessError, match="owned by"):
            update_command_for_agent(tmp_path, "cmd_x", "critic", "done")
        update_command_for_agent(tmp_path, "cmd_x", "code_agent", "done")
        loaded = load_command_queue(tmp_path)
        assert loaded["commands"][0]["status"] == "done"


def test_owner_matches_supports_multi_owner_strings():
    assert owner_matches("code_agent/critic", "critic")
    assert owner_matches("code_agent, critic", "code_agent")
    assert not owner_matches("code_agent", "critic")


class TestEvaluateVoteDecision:
    def base_decision(self, **overrides):
        decision = {
            "status": "open",
            "min_approvals": 2,
            "max_rejections": 0,
            "required_voters": [],
            "votes": [],
        }
        decision.update(overrides)
        return decision

    def test_open_until_min_approvals(self):
        decision = self.base_decision(votes=[{"agent": "a", "vote": "approve"}])
        assert evaluate_vote_decision(decision) == "open"

    def test_approved_at_min_approvals(self):
        decision = self.base_decision(
            votes=[{"agent": "a", "vote": "approve"}, {"agent": "b", "vote": "approve"}]
        )
        assert evaluate_vote_decision(decision) == "approved"

    def test_rejection_over_budget_rejects(self):
        decision = self.base_decision(
            votes=[
                {"agent": "a", "vote": "approve"},
                {"agent": "b", "vote": "approve"},
                {"agent": "c", "vote": "reject"},
            ]
        )
        assert evaluate_vote_decision(decision) == "rejected"

    def test_required_voter_must_vote(self):
        decision = self.base_decision(
            required_voters=["critic"],
            votes=[{"agent": "a", "vote": "approve"}, {"agent": "b", "vote": "approve"}],
        )
        assert evaluate_vote_decision(decision) == "open"
        decision["votes"].append({"agent": "critic", "vote": "abstain"})
        assert evaluate_vote_decision(decision) == "approved"

    def test_cancelled_short_circuits(self):
        assert evaluate_vote_decision(self.base_decision(status="cancelled")) == "cancelled"
