"""Dependency-circle propose + Choice mechanical-fit (ADR-015-27c / ADR-020)."""

from __future__ import annotations

from unittest.mock import patch

from recommender.nodes import apply_lock, restore_superseded
from recommender.propose import fill_team_draft
from recommender.recommend import role_spread
from recommender.reconcile import (
    simultaneous_lock_conflicts,
    _tier1_choice_status_moves,
    _tier1_speed_direction,
)
from recommender.state import Attr, ReasonRef, RecommenderState, Slot, empty_slot


def _base_state(**overrides) -> RecommenderState:
    state: RecommenderState = {
        "format_id": "[Gen 9 Champions] VGC 2026 Reg M-B",
        "game_type": "doubles",
        "regulation_mod": "champions",
        "picked_team_size": 4,
        "available_pool": [],
        "team_draft": [empty_slot() for _ in range(6)],
        "archetype": Attr(),
        "rejected": [],
        "constraints": [],
        "messages": [],
        "turn": 1,
        "superseded": [],
        "pending_flags": [],
    }
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


def test_band_locked_implies_atk_spread_no_nature_overshoot():
    slot = Slot(
        species=Attr(value="Kingambit", locked=True),
        item=Attr(value="Choice Band", locked=True),
        role=Attr(value="fast_attacker"),
    )
    filler = Slot(role=Attr(value="support_speed_control"))
    state = _base_state(team_draft=[slot, filler, *[empty_slot() for _ in range(4)]])
    out = fill_team_draft(state)
    s = out["team_draft"][0]
    assert s.spread.value is not None
    assert s.spread.value["atk"] == 32
    assert s.spread.value["spa"] == 0
    assert s.nature.value == "Adamant"
    assert s.nature.reason is not None
    assert s.nature.reason.ref == "usage"


def test_specs_locked_implies_spa_spread_no_overshoot():
    slot = Slot(
        species=Attr(value="Gholdengo", locked=True),
        item=Attr(value="Choice Specs", locked=True),
        role=Attr(value="fast_attacker"),
    )
    filler = Slot(role=Attr(value="support_speed_control"))
    state = _base_state(team_draft=[slot, filler, *[empty_slot() for _ in range(4)]])
    out = fill_team_draft(state)
    s = out["team_draft"][0]
    assert s.spread.value is not None
    assert s.spread.value["spa"] == 32
    assert s.spread.value["atk"] == 0
    assert s.nature.value == "Timid"
    assert s.nature.reason is not None
    assert s.nature.reason.ref == "usage"


def test_scarf_nature_correction_when_benchmarks_clear():
    slot = Slot(
        species=Attr(value="Garchomp", locked=True),
        item=Attr(value="Choice Scarf", locked=True),
        role=Attr(value="fast_attacker"),
    )
    filler = Slot(role=Attr(value="support_speed_control"))
    state = _base_state(team_draft=[slot, filler, *[empty_slot() for _ in range(4)]])
    with patch("recommender.propose.scarf_clears_benchmarks", return_value=True):
        out = fill_team_draft(state)
    s = out["team_draft"][0]
    assert s.spread.value is not None
    assert s.spread.value["spe"] == 32
    assert s.nature.value in ("Adamant", "Modest")
    assert s.nature.reason is not None
    assert s.nature.reason.ref == "scarf_spe_overshoot"


def test_trick_room_moveset_implies_role_and_spread():
    slot = Slot(
        species=Attr(value="Indeedee-F", locked=True),
        moveset=Attr(
            value=["Trick Room", "Psychic", "Follow Me", "Protect"],
            locked=True,
        ),
    )
    filler = Slot(role=Attr(value="support_speed_control"))
    state = _base_state(team_draft=[slot, filler, *[empty_slot() for _ in range(4)]])
    out = fill_team_draft(state)
    s = out["team_draft"][0]
    assert s.role.value == "trick_room_sweeper"
    assert s.spread.value == role_spread("trick_room_sweeper")


def test_scarf_then_status_reopens_scarf():
    state = _base_state(
        team_draft=[
            Slot(
                item=Attr(
                    value="Choice Scarf",
                    locked=True,
                    reason=ReasonRef(kind="user_stated"),
                )
            ),
            *[empty_slot() for _ in range(5)],
        ]
    )
    state["turn_payload"] = {
        "slot_index": 0,
        "attr": "moveset",
        "value": ["Protect", "Earthquake", "Dragon Claw", "Rock Slide"],
    }
    out = apply_lock(state)
    slot = out["team_draft"][0]
    assert slot.moveset.locked is True
    assert slot.item.locked is False
    assert slot.item.value is None
    assert len(out["superseded"]) == 1
    assert out["superseded"][0]["attr"] == "item"
    assert out["superseded"][0]["value"] == "Choice Scarf"

    state2 = {**state, **out}
    state2["turn_payload"] = {"slot_index": 0, "attr": "item"}
    restored = restore_superseded(state2)  # type: ignore[arg-type]
    assert restored["team_draft"][0].item.value == "Choice Scarf"
    assert restored["team_draft"][0].item.locked is True


def test_status_then_scarf_reopens_moveset():
    state = _base_state(
        team_draft=[
            Slot(
                moveset=Attr(
                    value=["Protect", "Sleep Powder", "Hurricane", "Bug Buzz"],
                    locked=True,
                    reason=ReasonRef(kind="user_stated"),
                )
            ),
            *[empty_slot() for _ in range(5)],
        ]
    )
    state["turn_payload"] = {
        "slot_index": 0,
        "attr": "item",
        "value": "Choice Scarf",
    }
    out = apply_lock(state)
    slot = out["team_draft"][0]
    assert slot.item.locked is True
    assert slot.item.value == "Choice Scarf"
    assert slot.moveset.locked is False
    assert slot.moveset.value is None
    assert out["superseded"][0]["attr"] == "moveset"


def test_simultaneous_scarf_protect_neither_locks():
    state = _base_state()
    state["turn_payload"] = {
        "slot_index": 0,
        "locks": [
            {"attr": "item", "value": "Choice Scarf"},
            {
                "attr": "moveset",
                "value": ["Protect", "Earthquake", "Outrage", "Rock Slide"],
            },
        ],
    }
    out = apply_lock(state)
    slot = out["team_draft"][0]
    assert slot.item.locked is False
    assert slot.moveset.locked is False
    assert any(
        f["flag_kind"] == "simultaneous_lock_conflict" for f in out["pending_flags"]
    )


def test_simultaneous_vivillon_partial_apply():
    state = _base_state()
    state["turn_payload"] = {
        "slot_index": 0,
        "locks": [
            {"attr": "species", "value": "Vivillon"},
            {
                "attr": "moveset",
                "value": ["Sleep Powder", "Hurricane", "Bug Buzz", "Protect"],
            },
            {"attr": "item", "value": "Choice Scarf"},
        ],
    }
    out = apply_lock(state)
    slot = out["team_draft"][0]
    assert slot.species.locked is True
    assert slot.species.value == "Vivillon"
    assert slot.item.locked is False
    assert slot.moveset.locked is False
    flags = [
        f
        for f in out["pending_flags"]
        if f["flag_kind"] == "simultaneous_lock_conflict"
    ]
    assert len(flags) == 1
    assert set(flags[0]["value"]["conflict"]) == {"item", "moveset"}


def test_choice_plus_trick_not_mismatch():
    slot = Slot(
        item=Attr(value="Choice Specs", locked=True),
        moveset=Attr(
            value=["Trick", "Shadow Ball", "Make It Rain", "Flash Cannon"],
            locked=True,
        ),
    )
    assert _tier1_choice_status_moves(slot) is None


def test_choice_plus_switcheroo_not_mismatch():
    slot = Slot(
        item=Attr(value="Choice Band", locked=True),
        moveset=Attr(
            value=["Switcheroo", "Knock Off", "Sucker Punch", "Iron Head"],
            locked=True,
        ),
    )
    assert _tier1_choice_status_moves(slot) is None


def test_scarf_plus_trick_room_speed_direction():
    slot = Slot(
        item=Attr(value="Choice Scarf", locked=True),
        moveset=Attr(
            value=["Trick Room", "Psychic", "Shadow Ball", "Dazzling Gleam"],
            locked=True,
        ),
    )
    assert _tier1_speed_direction(slot) is not None
    assert simultaneous_lock_conflicts(slot) == [("item", "moveset")]


def test_scarf_and_tr_locked_leave_spread_unset():
    slot = Slot(
        species=Attr(value="Indeedee-F", locked=True),
        item=Attr(value="Choice Scarf", locked=True),
        moveset=Attr(
            value=["Trick Room", "Psychic", "Follow Me", "Helping Hand"],
            locked=True,
        ),
        role=Attr(value="trick_room_sweeper"),
    )
    filler = Slot(role=Attr(value="support_speed_control"))
    state = _base_state(team_draft=[slot, filler, *[empty_slot() for _ in range(4)]])
    out = fill_team_draft(state)
    draft = out.get("team_draft", state["team_draft"])
    assert draft[0].spread.value is None
