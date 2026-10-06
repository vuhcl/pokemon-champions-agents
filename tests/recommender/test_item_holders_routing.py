"""Routing tests for try_route_item_holders + classify_input gate."""

from __future__ import annotations

from typing import Any

import pytest

from recommender.ids import to_id
from recommender.item_holders import (
    NEAR_MISS_MSG,
    ability_ids_from_species,
    format_item_holders_result,
    item_species_move_overlap_ids,
    legal_item_ids,
    query_item_holders,
    try_route_item_holders,
)
from recommender.legality import load_snapshot
from recommender.nodes import classify_input
from recommender.present_text import format_turn
from recommender.state import (
    Attr,
    PendingPresentation,
    Slot,
    empty_slot,
)

REG = "champions-reg-mc"


def _levenshtein(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        cur = [i]
        for j, cb in enumerate(b, start=1):
            cur.append(
                min(cur[j - 1] + 1, prev[j] + 1, prev[j - 1] + (ca != cb))
            )
        prev = cur
    return prev[-1]


def near_legal_item_entity_ids(snap: dict[str, Any]) -> set[str]:
    """Non-item species/move/ability ids within edit distance ≤2 of a legal item id."""
    legal = legal_item_ids(snap)
    item_ids = set((snap.get("items") or {}).keys())
    entities: set[str] = set()
    entities |= set((snap.get("species") or {}).keys())
    entities |= set((snap.get("moves") or {}).keys())
    entities |= ability_ids_from_species(snap)
    entities -= item_ids
    out: set[str] = set()
    for eid in entities:
        for iid in legal:
            if _levenshtein(eid, iid) <= 2:
                out.add(eid)
                break
    return out


def test_ability_ids_union_nonempty():
    snap = load_snapshot()
    assert ability_ids_from_species(snap)


def test_metronome_overlap_exactly_metronome():
    snap = load_snapshot()
    assert item_species_move_overlap_ids(snap) == {"metronome"}


def test_metronome_routes_to_item_holders():
    """Item wins when id is both item and move (documented)."""
    routed = try_route_item_holders("who uses Metronome", regulation=REG)
    assert routed is not None
    msg = routed["turn_payload"]["message"]
    expected = format_item_holders_result(
        query_item_holders("Metronome", regulation=REG)
    )
    assert msg == expected


def test_psychic_sead_near_miss_fail_closed():
    routed = try_route_item_holders("who uses Psychic Sead", regulation=REG)
    assert routed is not None
    assert routed["turn_payload"]["message"] == NEAR_MISS_MSG


def test_phrase_absent_fall_through():
    assert try_route_item_holders("Psychic Seed please", regulation=REG) is None


def test_other_intent_fall_through():
    assert (
        try_route_item_holders(
            "who uses Life Orb — change its item instead",
            regulation=REG,
        )
        is None
    )


@pytest.mark.parametrize(
    "name",
    ["Salamence", "Leer", "Magneton", "Poison Jab"],
)
def test_spot_near_legal_entities_in_computed_set(name: str):
    snap = load_snapshot()
    computed = near_legal_item_entity_ids(snap)
    assert to_id(name) in computed


def test_completeness_near_legal_entities_fall_through():
    snap = load_snapshot()
    computed = near_legal_item_entity_ids(snap)
    assert computed  # non-vacuous
    for eid in sorted(computed):
        # Prefer display name when available for species/moves.
        display = eid
        sp = (snap.get("species") or {}).get(eid)
        if sp and sp.get("name"):
            display = str(sp["name"])
        else:
            mv = (snap.get("moves") or {}).get(eid)
            if mv and mv.get("name"):
                display = str(mv["name"])
        assert (
            try_route_item_holders(f"who uses {display}", regulation=REG) is None
        ), display


def test_trick_room_garchomp_tailwind_fall_through():
    for text in (
        "who runs Trick Room",
        "who uses Garchomp",
        "what runs Tailwind",
    ):
        assert try_route_item_holders(text, regulation=REG) is None


def test_exact_item_message_matches_formatter():
    routed = try_route_item_holders("who uses Psychic Seed", regulation=REG)
    assert routed is not None
    expected = format_item_holders_result(
        query_item_holders("Psychic Seed", regulation=REG)
    )
    assert routed["turn_payload"]["message"] == expected


def test_classify_input_preserves_pending_and_no_claim_stamp():
    pending: PendingPresentation = {
        "schema_version": 1,
        "kind": "full_build_confirmation",
        "slot_index": 0,
        "options": (),
    }
    # Minimal slot so format_turn can render build body when present.
    slot = empty_slot()
    slot.species = Attr(value="Incineroar")
    state = {
        "pending_input": "who uses Charcoal",
        "pending_presentation": pending,
        "regulation_mod": "champions",
        "turn": 3,
        "team_draft": [slot],
        "provisional_slot": {
            "species": "Incineroar",
            "ability": "Intimidate",
            "item": "Safety Goggles",
            "moves": ["Flare Blitz", "Knock Off", "Parting Shot", "Fake Out"],
            "nature": "Adamant",
            "evs": {"hp": 4, "atk": 252, "def": 0, "spa": 0, "spd": 0, "spe": 252},
        },
    }
    # Avoid LLM: if route fails we'd call classify_pending — must not.
    out = classify_input(state, turn_intent_parser=None)
    assert out["turn_intent"] == "pending_response"
    assert "pending_presentation" not in out  # leave screen
    msg = out["turn_payload"]["message"]
    assert "weak to" in msg or "type-boost" in msg or "Observed holders" in msg
    assert out.get("last_system_claim") is None

    # format_turn shows holders message + pending body.
    merged = {**state, **out, "pending_presentation": pending}
    rendered = format_turn(merged, unmatched=True)
    assert "Observed holders" in rendered
    assert "Incineroar" in rendered


def test_try_route_bad_regulation_falls_through():
    assert try_route_item_holders("who uses Life Orb", regulation="not-a-reg") is None


def test_try_route_unknown_regulation_matching_phrase_does_not_raise():
    # Must not propagate ValueError into classify_input.
    out = try_route_item_holders(
        "who uses Psychic Seed", regulation="totally-unknown-reg"
    )
    assert out is None


def test_classify_input_missing_regulation_mod_non_matching_unchanged():
    """State without regulation_mod + non-holders phrase: gate is a no-op."""
    from unittest.mock import patch

    state = {
        "pending_input": "xyzzy not holders",
        "pending_presentation": None,
        "team_draft": [],
        "turn": 0,
    }
    sentinel = {
        "turn_intent": "pending_response",
        "turn_payload": {"message": "Didn't catch that."},
    }
    with patch("recommender.nodes.classify_pending", return_value=sentinel) as cp:
        out = classify_input(state, turn_intent_parser=object())
    cp.assert_called_once()
    assert out["turn_intent"] == "pending_response"
    assert (out.get("turn_payload") or {}).get("message") == "Didn't catch that."


def test_claim_stamp_not_set_for_type_words_in_tier2():
    """stamp_system_claim runs on pending_response; holders text must not stamp."""
    state = {
        "pending_input": "who uses Occa Berry",
        "pending_presentation": None,
        "regulation_mod": "champions",
        "turn": 1,
        "team_draft": [],
    }
    out = classify_input(state, turn_intent_parser=None)
    assert out["turn_intent"] == "pending_response"
    assert "weak to Fire" in out["turn_payload"]["message"] or "Observed holders" in out[
        "turn_payload"
    ]["message"]
    assert out.get("last_system_claim") is None
