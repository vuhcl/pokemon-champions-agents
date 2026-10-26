"""What the lock node does with the recorded "Lock Garchomp in slot 2" parse.

The parser sample stored slot_index 2. These tests were committed green before
the conversion, against that pass-through. The follow-up commit changes the
assertions to the 1-based contract.
"""

from __future__ import annotations

from recommender.nodes import LOCK_BAD_SLOT_MSG, apply_lock
from recommender.state import empty_slot
from recommender.turn_intent import TurnIntentExtraction, _payload_for


def _lock(user_slot: int) -> dict:
    extraction = TurnIntentExtraction(
        turn_intent="lock",
        slot_index=user_slot,
        attr="species",
        value="Garchomp",
    )
    payload = _payload_for(extraction)
    assert payload is not None
    return payload


def _apply(payload: dict) -> dict:
    draft = [empty_slot() for _ in range(6)]
    return apply_lock({"team_draft": draft, "turn_payload": payload, "turn": 0})


def test_lock_garchomp_slot_2_parse_writes_internal_index_2():
    payload = _lock(2)
    assert payload["slot_index"] == 2
    out = _apply(payload)
    assert not out.get("slot_commit_error")
    assert out["team_draft"][2].species.value == "Garchomp"
    assert out["team_draft"][2].species.locked
    assert out["team_draft"][1].species.value is None


def test_extracted_slot_0_locks_internal_index_0():
    payload = _lock(0)
    assert payload["slot_index"] == 0
    out = _apply(payload)
    assert not out.get("slot_commit_error")
    assert out["team_draft"][0].species.value == "Garchomp"
    assert out["team_draft"][1].species.value is None


def test_extracted_slot_7_is_passed_through_and_refused():
    payload = _lock(7)
    assert payload["slot_index"] == 7
    out = _apply(payload)
    assert out.get("slot_commit_error") == LOCK_BAD_SLOT_MSG
    assert "team_draft" not in out
