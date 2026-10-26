"""Lock Garchomp in slot 2: the extractor's number is converted before apply_lock.

Before the conversion, the recorded parse (slot_index 2) wrote the third slot.
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


def test_lock_garchomp_in_user_slot_2_writes_internal_index_1():
    payload = _lock(2)
    assert payload["slot_index"] == 1
    out = _apply(payload)
    assert not out.get("slot_commit_error")
    assert out["team_draft"][1].species.value == "Garchomp"
    assert out["team_draft"][1].species.locked
    assert out["team_draft"][2].species.value is None


def test_user_slot_0_is_refused_and_writes_nothing():
    out = _apply(_lock(0))
    assert out.get("slot_commit_error") == LOCK_BAD_SLOT_MSG
    assert "team_draft" not in out


def test_user_slot_7_on_a_six_slot_team_is_refused_and_writes_nothing():
    out = _apply(_lock(7))
    assert out.get("slot_commit_error") == LOCK_BAD_SLOT_MSG
    assert "team_draft" not in out
