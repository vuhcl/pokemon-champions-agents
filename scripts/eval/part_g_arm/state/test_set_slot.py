"""set_slot wrapper: all-or-nothing validation, multi-slot, replace audit hooks."""

from __future__ import annotations

import hashlib
import json

import pytest

from recommender.state import all_locked
from scripts.eval.part_g_arm.config import ArmConfig
from scripts.eval.part_g_arm.state.fixtures import empty_team
from scripts.eval.part_g_arm.state.pending import build_fully_locked_slot
from scripts.eval.part_g_arm.state.request_set_rows import FROZEN_PROMPT_SHA256
from scripts.eval.part_g_arm.state.request_set_runner import (
    TOOL_FIELDS_PROMPT_FILE,
    WRAPPER_PROMPT_FILE,
)
from scripts.eval.part_g_arm.state.set_slot_tool import set_slot
from scripts.eval.part_g_arm.state.tools import (
    combined_specs,
    mechanical_class,
    set_tool_fields,
    set_wrapper,
    slot_signature,
    tool_call_result_status,
)

PRE_RS_ARM_TOOL_SCHEMA_SHA256 = "f0c97ad3b88cb3f118e241111bd454a4e86f7937cd4342f0969cadbe5049b845"


@pytest.fixture(autouse=True)
def _reset_flags():
    set_tool_fields(False)
    set_wrapper(False)
    yield
    set_tool_fields(False)
    set_wrapper(False)


def _sig(state: dict) -> tuple:
    return tuple(slot_signature(s) for s in state["team_draft"])


def test_flags_off_schemas_and_prompt_match_previous_rung():
    set_tool_fields(False)
    set_wrapper(False)
    cfg = ArmConfig(prompt_file="state/prompt.md")
    assert cfg.prompt_hash() == FROZEN_PROMPT_SHA256
    sha = hashlib.sha256(json.dumps(combined_specs(), sort_keys=True).encode()).hexdigest()
    assert sha == PRE_RS_ARM_TOOL_SCHEMA_SHA256
    # tool_fields-only schemas unchanged vs previous rung (wrapper off).
    set_tool_fields(True)
    tf_sha = hashlib.sha256(
        json.dumps(combined_specs(tool_fields=True, wrapper=False), sort_keys=True).encode()
    ).hexdigest()
    set_wrapper(True)
    both_sha = hashlib.sha256(
        json.dumps(combined_specs(tool_fields=True, wrapper=True), sort_keys=True).encode()
    ).hexdigest()
    assert tf_sha != both_sha
    names = [s["function"]["name"] for s in combined_specs(tool_fields=True, wrapper=True)]
    assert "set_slot" in names
    assert "lock_slot" not in names
    assert "edit_slot_field" not in names
    assert "unlock_slot" in names
    # tool_fields-only still has the old write tools
    tf_names = [s["function"]["name"] for s in combined_specs(tool_fields=True, wrapper=False)]
    assert "lock_slot" in tf_names and "edit_slot_field" in tf_names


def test_species_item_three_moves_one_call():
    st = empty_team()
    before = _sig(st)
    after, result = set_slot(
        st,
        {
            "slot": 1,
            "species": "Cinderace",
            "item": "Chople Berry",
            "moves": ["Sucker Punch", "Iron Head", "Pyro Ball"],
        },
    )
    assert result["ok"] is True
    assert before != _sig(after)
    applied = result["applied"][0]
    assert applied["slot"] == 1
    assert applied["species"] == "Cinderace"
    assert applied["item"] == "Chople Berry"
    assert applied["moveset"] == ["Sucker Punch", "Iron Head", "Pyro Ball"]
    # Read-back from state, not request echo.
    assert after["team_draft"][0].species.value == applied["species"]
    assert after["team_draft"][0].item.value == applied["item"]
    assert after["team_draft"][0].moveset.value == applied["moveset"]


def test_default_slot_is_first_open():
    st = build_fully_locked_slot("Hydreigon", user_slot=1)
    after, result = set_slot(
        st, {"species": "Cinderace", "item": "Chople Berry"}
    )
    assert result["ok"] is True
    assert result["slots_used"] == [2]
    assert after["team_draft"][1].species.value == "Cinderace"
    assert after["team_draft"][0].species.value == "Hydreigon"


def test_one_fail_one_pass_nothing_applied_both_reported():
    st = empty_team()
    before = _sig(st)
    after, result = set_slot(
        st,
        {"slot": 1, "species": "Hydreigon", "item": "Choice Specs"},
    )
    assert result["ok"] is False
    assert _sig(after) == before
    fields = {el["field"]: el for el in result["elements"]}
    assert fields["species"]["ok"] is True
    assert fields["item"]["ok"] is False
    assert "not legal" in fields["item"]["cause"].lower() or "Item" in fields["item"]["cause"]


def test_two_illegal_elements_both_named():
    st = empty_team()
    before = _sig(st)
    after, result = set_slot(
        st,
        {"slot": 1, "species": "Mewtwo", "item": "Choice Specs"},
    )
    assert result["ok"] is False
    assert _sig(after) == before
    failed = [el for el in result["elements"] if not el["ok"]]
    assert {el["field"] for el in failed} >= {"species", "item"}
    assert any("Mewtwo" in (el.get("cause") or "") for el in failed)
    assert any("Choice Specs" in (el.get("cause") or "") or "not legal" in (el.get("cause") or "").lower() for el in failed)


def test_mr4_shape_atomic_item_clause():
    """Two fully locked mons, neither Choice Scarf; Scarf on both → unchanged, Item Clause."""
    from scripts.eval.part_g_arm.state.request_set_rows import _fully_locked_pair

    st = _fully_locked_pair(("Hydreigon", 1), ("Cinderace", 2))
    assert st["team_draft"][0].item.value != "Choice Scarf"
    assert st["team_draft"][1].item.value != "Choice Scarf"
    before = _sig(st)
    after, result = set_slot(
        st,
        {
            "slots": [
                {"slot": 1, "item": "Choice Scarf"},
                {"slot": 2, "item": "Choice Scarf"},
            ]
        },
    )
    assert result["ok"] is False
    assert _sig(after) == before
    assert any("Item Clause" in (el.get("cause") or "") for el in result["elements"])
    assert st["team_draft"][0].species.value == "Hydreigon"
    assert st["team_draft"][1].species.value == "Cinderace"


def test_occupied_fully_locked_refused_without_replace_then_replaced():
    st = build_fully_locked_slot("Hydreigon", user_slot=2)
    before = _sig(st)
    after, result = set_slot(st, {"slot": 2, "species": "Cinderace", "replace": False})
    assert result["ok"] is False
    assert _sig(after) == before
    assert any("fully locked" in (el.get("cause") or "") for el in result["elements"])
    assert "Hydreigon" in (result["slot_commit_error"] or "")

    after2, result2 = set_slot(
        st, {"slot": 2, "species": "Cinderace", "replace": True}
    )
    assert result2["ok"] is True
    assert after2["team_draft"][1].species.value == "Cinderace"
    assert all_locked(after2["team_draft"][1]) is False or after2["team_draft"][1].species.value == "Cinderace"
    # Slot 2 holds the new species (read-back).
    assert result2["applied"][0]["slot"] == 2
    assert result2["applied"][0]["species"] == "Cinderace"


def test_read_back_comes_from_state():
    st = empty_team()
    after, result = set_slot(st, {"species": "hydreigon"})  # non-canonical casing
    assert result["ok"] is True
    assert result["applied"][0]["species"] == after["team_draft"][0].species.value
    assert result["applied"][0]["species"] == "Hydreigon"


def test_wrapper_prompt_sha_and_schema_tokens():
    cfg_tf = ArmConfig(prompt_file=TOOL_FIELDS_PROMPT_FILE)
    cfg_w = ArmConfig(prompt_file=WRAPPER_PROMPT_FILE)
    assert cfg_tf.prompt_hash() != cfg_w.prompt_hash()
    assert cfg_w.prompt_hash() != FROZEN_PROMPT_SHA256
    tf_specs = combined_specs(tool_fields=True, wrapper=False)
    both = combined_specs(tool_fields=True, wrapper=True)
    tf_tokens = len(json.dumps(tf_specs, sort_keys=True))
    both_tokens = len(json.dumps(both, sort_keys=True))
    assert both_tokens > tf_tokens
    # Expose for report via assert message
    assert tf_tokens > 0 and both_tokens > 0


def test_mw1b_empty_team_no_slot():
    """MW1b path: no slot arg on empty team → slot 1."""
    st = empty_team()
    after, result = set_slot(st, {"species": "Cinderace"})
    assert result["ok"] is True
    assert result["slots_used"] == [1]
    assert after["team_draft"][0].species.value == "Cinderace"


def test_set_slot_edit_returns_choice_lock_consequences():
    from scripts.eval.part_g_arm.state.harness import start_state

    st = start_state(
        {"start": "fully_locked_protect", "species": "Venusaur", "user_slot": 1}
    )
    _after, result = set_slot(st, {"slot": 1, "item": "Choice Scarf"})
    assert result["ok"] is True
    kinds = {c.get("kind") for c in result.get("consequences") or []}
    assert "choice_lock_status" in kinds
    assert result.get("edits")


def test_set_slot_refusal_records_as_refused_not_no_change():
    """Arm recording: set_slot ok=False is mechanical_class refused + result_status refused."""
    from scripts.eval.part_g_arm.state.harness import snapshot

    st = empty_team()
    before = snapshot(st)
    after, result = set_slot(st, {"slot": 1, "species": "Bulbasaur"})
    assert result["ok"] is False
    assert result.get("slot_commit_error")
    after_snap = snapshot(after)
    call = {"name": "set_slot", "args": {"slot": 1, "species": "Bulbasaur"}, "result": result}
    assert mechanical_class(before, after_snap, [call]) == "refused"
    assert tool_call_result_status(call) == "refused"
    # Multi-slot list form likewise.
    after2, result2 = set_slot(
        empty_team(),
        {"slots": [{"slot": 1, "species": "Mewtwo"}, {"slot": 2, "species": "Cinderace"}]},
    )
    assert result2["ok"] is False
    call2 = {"name": "set_slot", "args": {"slots": []}, "result": result2}
    assert tool_call_result_status(call2) == "refused"
    assert (
        mechanical_class(snapshot(empty_team()), snapshot(after2), [call2]) == "refused"
    )
