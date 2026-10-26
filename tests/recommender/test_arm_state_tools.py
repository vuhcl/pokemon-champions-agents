"""Checkpoint tests for the stateful arm wrappers. No model calls."""

import json

from recommender.arm_tools import TOOL_SPECS
from recommender.nodes import REPICK_REQUIRES_LOCKED_MSG
from scripts.eval.part_g_arm.config import ArmConfig
from scripts.eval.part_g_arm.state.fixtures import dev_key_document, empty_team, one_locked_slot
from scripts.eval.part_g_arm.state.harness import grade_row, snapshot
from scripts.eval.part_g_arm.state.tools import (
    combined_specs,
    commit_slot,
    lock_slot,
    mechanical_class,
    read_team,
    reset_team_state,
    unlock_slot,
)

KEYS = dev_key_document()
LEGAL = KEYS["species"]["Venusaur"]["canonical"]
ILLEGAL = "Bulbasaur"


def test_user_slot_2_writes_internal_index_1():
    state, patch = lock_slot(empty_team(), 2, LEGAL)
    assert patch.get("slot_commit_error") is None
    assert state["team_draft"][1].species.value == LEGAL
    assert state["team_draft"][1].species.locked is True
    assert state["team_draft"][0].species.value is None
    assert state["team_draft"][2].species.value is None


def test_bad_slots_leave_a_planted_pending_screen():
    for user_slot in (0, 7, True):
        state = empty_team()
        state["pending_presentation"] = {"schema_version": 1, "kind": "planted"}
        new, patch = lock_slot(state, user_slot, LEGAL)
        assert new is state
        assert new["pending_presentation"]["kind"] == "planted"
        assert "team_draft" not in patch
        assert patch["slot_commit_error"]


def test_unlock_and_commit_write_nothing():
    state = empty_team()
    unlocked, unlock_patch = unlock_slot(state, 1)
    assert "team_draft" not in unlock_patch
    assert unlock_patch["slot_commit_error"] == REPICK_REQUIRES_LOCKED_MSG
    assert unlocked["team_draft"] is state["team_draft"]
    committed, commit_patch = commit_slot(empty_team())
    assert "team_draft" not in commit_patch
    assert "missing or unsupported" in commit_patch["slot_commit_error"]


def test_one_locked_fixture_comes_from_apply_lock():
    state = one_locked_slot(LEGAL, user_slot=1)
    assert state["team_draft"][0].species.value == LEGAL
    assert state["team_draft"][0].species.locked is True
    assert read_team(state)["slots"][0]["slot"] == "1"


def test_refusal_does_not_replace_team_draft():
    state = empty_team()
    new, patch = lock_slot(state, 2, ILLEGAL)
    assert "team_draft" not in patch
    assert new["team_draft"] is state["team_draft"]
    assert all(slot.species.value is None for slot in new["team_draft"])


def test_reset_replaces_the_draft_from_the_node_dict():
    state = one_locked_slot(LEGAL, user_slot=1)
    new, patch = reset_team_state(state)
    assert patch["pending_presentation"] is None
    assert new["team_draft"] is patch["team_draft"]
    assert all(slot.species.value is None for slot in new["team_draft"])


def test_lookup_only_class_and_spec_list_is_a_copy():
    before = empty_team()
    calls = [{"name": "get_typing", "result": {"status": "ok"}}]
    assert mechanical_class(before, before, calls) == "lookup only"
    assert mechanical_class(snapshot(before), snapshot(before), calls) == "lookup only"
    wrote, _ = lock_slot(before, 2, LEGAL)
    assert mechanical_class(snapshot(before), snapshot(wrote), [{"name": "lock_slot", "result": {}}]) == "wrote"
    assert mechanical_class(before, before, [{"name": "lock_slot", "result": {"slot_commit_error": "no"}}]) == "refused"
    n = len(TOOL_SPECS)
    specs = combined_specs()
    assert len(TOOL_SPECS) == n
    assert len(specs) == n + 5


def test_dev_keys_match_the_snapshot_and_the_prompt_path():
    on_disk = json.loads(((__import__("pathlib").Path(__file__).resolve().parents[2]
                           / "scripts/eval/part_g_arm/state/dev_keys.json")).read_text())
    assert on_disk["species"] == KEYS["species"]
    assert ArmConfig(prompt_file="state/prompt.md").prompt_text().startswith("You build a six-slot")


def test_grade_row_flags_a_state_tool_on_the_lookup_row():
    turn = {"mechanical_class": "lookup only", "state_after": {"slots": []},
            "tool_calls": [{"name": "lock_slot", "result": {}}, {"name": "get_typing", "result": {"types": KEYS["species"]["Venusaur"]["types"]}}]}
    assert grade_row("dev-lookup", [turn], KEYS)
