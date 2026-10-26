"""User slot numbers count from 1. Display of an internal index adds 1."""

from __future__ import annotations

import pytest

from recommender.slot_index import SlotIndexError, display_slot, user_slot_to_index
from recommender.state import Attr, Slot, empty_slot
from recommender.team_validation import validate_team_value
from recommender.turn_intent import _EXTRACTION_SYSTEM_PROMPT


def test_user_slot_1_is_internal_0():
    assert user_slot_to_index(1) == 0


def test_user_slots_0_and_7_are_refused_on_a_six_slot_team():
    with pytest.raises(SlotIndexError):
        user_slot_to_index(0, team_size=6)
    with pytest.raises(SlotIndexError):
        user_slot_to_index(7, team_size=6)


@pytest.mark.parametrize("raw", (True, False, 1.5, "2", None))
def test_boolean_and_non_integer_slots_are_refused(raw: object):
    with pytest.raises(SlotIndexError):
        user_slot_to_index(raw)


def test_display_of_internal_0_is_1():
    assert display_slot(0) == "1"


def test_species_and_item_clause_name_slot_1_for_internal_index_0():
    draft = [empty_slot() for _ in range(6)]
    draft[0] = Slot(
        species=Attr("Incineroar", locked=True),
        item=Attr("Choice Scarf", locked=True),
    )
    species = validate_team_value("species", "Incineroar", slot_index=1, team_draft=draft)
    item = validate_team_value("item", "Choice Scarf", slot_index=1, team_draft=draft)
    assert species.refusal is not None and "slot 1" in species.refusal.message
    assert item.refusal is not None and "slot 1" in item.refusal.message


def test_extraction_prompt_states_the_slot_base():
    assert "counting from 1" in _EXTRACTION_SYSTEM_PROMPT
    assert "do not subtract 1" in _EXTRACTION_SYSTEM_PROMPT
