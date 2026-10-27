"""Checkpoint tests for the stateful arm wrappers. No model calls."""

import json
from dataclasses import replace

from recommender.arm_tools import TOOL_SPECS
from recommender.nodes import REPICK_REQUIRES_LOCKED_MSG
from recommender.state import Attr
from scripts.eval.part_g_arm.config import ArmConfig
from scripts.eval.part_g_arm.state.fixtures import dev_key_document, empty_team, one_locked_slot
from scripts.eval.part_g_arm.state.harness import grade_row, snapshot
from scripts.eval.part_g_arm.state.tools import (
    check_hypothetical,
    combined_specs,
    commit_slot,
    draft_signature,
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
    assert len(specs) == n + 6


def test_non_species_field_change_is_wrote():
    before = one_locked_slot(LEGAL, user_slot=1)
    after = {
        **before,
        "team_draft": [
            replace(before["team_draft"][0], ability=Attr(value="Overgrow", locked=True)),
            *before["team_draft"][1:],
        ],
    }
    assert before["team_draft"][0].species.value == after["team_draft"][0].species.value
    assert mechanical_class(snapshot(before), snapshot(after), [{"name": "commit_slot", "result": {}}]) == "wrote"


def test_lock_flag_change_alone_is_wrote():
    before = one_locked_slot(LEGAL, user_slot=1)
    after = {
        **before,
        "team_draft": [
            replace(before["team_draft"][0], ability=Attr(value=None, locked=True)),
            *before["team_draft"][1:],
        ],
    }
    assert before["team_draft"][0].ability.value == after["team_draft"][0].ability.value
    assert before["team_draft"][0].ability.locked is False
    assert after["team_draft"][0].ability.locked is True
    assert mechanical_class(snapshot(before), snapshot(after), []) == "wrote"


def test_identical_states_are_not_wrote():
    state = one_locked_slot(LEGAL, user_slot=1)
    assert draft_signature(state) == draft_signature(snapshot(state))
    assert mechanical_class(snapshot(state), snapshot(state), []) == "no change"
    assert mechanical_class(state, state, [{"name": "get_typing", "result": {}}]) == "lookup only"


def test_dev_keys_match_the_snapshot_and_the_prompt_path():
    on_disk = json.loads(((__import__("pathlib").Path(__file__).resolve().parents[2]
                           / "scripts/eval/part_g_arm/state/dev_keys.json")).read_text())
    assert on_disk["species"] == KEYS["species"]
    assert ArmConfig(prompt_file="state/prompt.md").prompt_text().startswith("You build a six-slot")


def test_grade_row_flags_a_state_tool_on_the_lookup_row():
    turn = {"mechanical_class": "lookup only", "state_after": {"slots": []},
            "tool_calls": [{"name": "lock_slot", "result": {}}, {"name": "get_typing", "result": {"types": KEYS["species"]["Venusaur"]["types"]}}]}
    assert grade_row("dev-lookup", [turn], KEYS)


def test_ol_fixture_loads_without_converting_slot_numbers():
    from scripts.eval.part_g_arm.state.pending import load_fixture

    state = load_fixture("OL10a")
    assert state["team_draft"][0].species.value == "Rillaboom"
    assert state["team_draft"][0].species.locked is True
    assert state["pending_presentation"]["kind"] == "candidate_selection"
    assert state["pending_presentation"]["slot_index"] == 1


def test_h27_builds_candidate_selection_through_present_candidates():
    from scripts.eval.part_g_arm.state.pending import load_fixture

    state = load_fixture("H27")
    pending = state["pending_presentation"]
    assert pending["kind"] == "candidate_selection"
    assert pending["slot_index"] == 2
    names = [opt["species"] for opt in pending["options"]]
    assert names[:3] == ["Garchomp", "Incineroar", "Rillaboom"]


def test_refused_tools_leave_a_loaded_pending_screen():
    from scripts.eval.part_g_arm.state.pending import load_fixture

    planted = load_fixture("OL1")
    pending = planted["pending_presentation"]
    for call in (
        lambda: lock_slot(planted, 0, LEGAL),
        lambda: unlock_slot(planted, 1),
        lambda: commit_slot(planted),
    ):
        new, patch = call()
        assert new["pending_presentation"] is pending
        assert "pending_presentation" not in patch
        assert patch.get("slot_commit_error")


def test_fully_locked_unlock_and_fbc_commit_write():
    from scripts.eval.part_g_arm.state.pending import build_fbc_pending, build_fully_locked_slot
    from recommender.state import all_locked

    locked = build_fully_locked_slot(LEGAL, user_slot=1)
    assert all_locked(locked["team_draft"][0])
    unlocked, patch = unlock_slot(locked, 1)
    assert patch.get("slot_commit_error") is None
    assert unlocked["team_draft"][0].species.value is None
    assert unlocked["pending_presentation"] is None
    assert mechanical_class(snapshot(locked), snapshot(unlocked), [{"name": "unlock_slot", "result": patch}]) == "wrote"

    fbc = build_fbc_pending(LEGAL, slot_index=0)
    committed, commit_patch = commit_slot(fbc)
    assert commit_patch.get("slot_commit_error") is None
    assert committed["team_draft"][0].species.value == LEGAL
    assert committed["team_draft"][0].ability.locked is True
    assert committed["pending_presentation"] is None
    assert mechanical_class(snapshot(fbc), snapshot(committed), [{"name": "commit_slot", "result": commit_patch}]) == "wrote"


def test_check_hypothetical_never_writes_and_reports_clauses():
    empty = empty_team()
    empty["pending_presentation"] = {"kind": "planted"}
    item = check_hypothetical(
        empty,
        [{"species": "Venusaur", "item": "Wide Lens"},
         {"species": "Blastoise", "item": "Wide Lens"}],
    )
    assert item["verdict"] == "item_clause"
    assert item["conflicts_with_slot"] == 1
    assert empty["team_draft"][0].species.value is None
    assert empty["pending_presentation"]["kind"] == "planted"

    species = check_hypothetical(
        empty_team(),
        [{"species": "Venusaur"}, {"species": "Venusaur-Mega"}],
    )
    assert species["verdict"] == "species_clause"

    unknown = check_hypothetical(empty_team(), [{"species": "Bulbasaur"}])
    assert unknown["verdict"] in {"illegal_species", "unknown_species"}

    ok = check_hypothetical(empty_team(), [{"species": "Venusaur", "item": "Wide Lens"}])
    assert ok["verdict"] == "ok"
    assert mechanical_class(
        empty, empty, [{"name": "check_hypothetical", "result": ok}]
    ) == "lookup only"


def test_v4_fixture_loader_internal_slots_and_one_based_refuse():
    from scripts.eval.part_g_arm.state.pending import build_cs_pending, load_fixture, try_load_fixture

    hn2c = load_fixture("HN2c")
    assert hn2c["team_draft"][0].species.value == "Annihilape"
    assert hn2c["team_draft"][0].nature.value == "Jolly"
    assert hn2c["team_draft"][0].spread.value["spe"] == 32

    is2 = load_fixture("IS2")
    assert is2["team_draft"][0].species.value == "Basculegion"
    assert is2["team_draft"][0].item.value == "Choice Scarf"

    refused = try_load_fixture("H18b")
    assert refused["loaded"] is False
    assert "1-based" in (refused["error"] or "")

    ic1 = try_load_fixture("IC1")
    assert ic1["loaded"] is False
    assert "no slot fields" in (ic1["error"] or "")

    cs = build_cs_pending(["Venusaur", "Blastoise"], slot_index=0)
    assert cs["pending_presentation"]["kind"] == "candidate_selection"
    assert [o["species"] for o in cs["pending_presentation"]["options"]] == ["Venusaur", "Blastoise"]


def test_check_hypothetical_item_only_placements_use_distinct_slots():
    same = check_hypothetical(empty_team(), [{"item": "Wide Lens"}, {"item": "Wide Lens"}])
    assert same["verdict"] == "item_clause"
    assert same["conflicts_with_slot"] == 1

    distinct = check_hypothetical(empty_team(), [{"item": "Wide Lens"}, {"item": "Zoom Lens"}])
    assert distinct["verdict"] == "ok"

    three = check_hypothetical(
        empty_team(),
        [{"item": "Wide Lens"}, {"item": "Zoom Lens"}, {"item": "Scope Lens"}],
    )
    assert three["verdict"] == "ok"

    full = empty_team()
    for index in range(6):
        full["team_draft"][index] = replace(
            full["team_draft"][index], item=Attr(value="Wide Lens", locked=True)
        )
    jammed = check_hypothetical(full, [{"item": "Zoom Lens"}])
    assert jammed["verdict"] == "bad_slot_index"
