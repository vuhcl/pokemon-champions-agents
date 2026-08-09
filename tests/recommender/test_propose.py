"""Fixed-order propose_team_draft / fill_team_draft."""

from __future__ import annotations

from typing import get_args
from unittest.mock import patch

from recommender.nodes import propose_team_draft
from recommender.propose import _pick_role, fill_team_draft
from recommender.state import (
    Attr,
    ReasonRef,
    RecommenderState,
    Slot,
    TargetRoleDecision,
    TargetRoleId,
    UnresolvedTargetRoleDecision,
    empty_slot,
)
from recommender.usage_spreads import SpreadChoice


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
    }
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


def test_empty_draft_fills_at_least_one_role():
    out = fill_team_draft(_base_state())
    assert "team_draft" in out
    roles = [s.role for s in out["team_draft"] if s.role.value is not None]
    assert len(roles) >= 1
    assert roles[0].locked is False
    assert roles[0].reason is not None
    assert roles[0].reason.kind == "core_detection"
    assert roles[0].value == "bulky_attacker"
    assert roles[0].reason.ref == "coverage_gap"


def test_idempotent_second_call():
    state = _base_state()
    first = fill_team_draft(state)
    state = {**state, **first}
    second = fill_team_draft(state)  # type: ignore[arg-type]
    assert second == {}


def test_role_decided_species_stays_none():
    slot = Slot(role=Attr(value="bulky_attacker", locked=True))
    state = _base_state(team_draft=[slot, *[empty_slot() for _ in range(5)]])
    out = fill_team_draft(state)
    draft = out.get("team_draft", state["team_draft"])
    assert draft[0].species.value is None


def test_species_cache_hit_refines():
    moves = ["Earthquake", "Dragon Claw", "Rock Slide", "Protect"]
    item = "Life Orb"
    spread = {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32}
    slot = Slot(species=Attr(value="Garchomp", locked=True))
    # Pre-existing role elsewhere so we don't coverage_gap-fill this slot's role.
    filler = Slot(role=Attr(value="support_speed_control"))
    state = _base_state(
        team_draft=[slot, filler, *[empty_slot() for _ in range(4)]]
    )

    with (
        patch(
            "recommender.propose.featured_or_common_set",
            return_value={"species": "Garchomp", "moves": moves, "item": item},
        ),
        patch(
            "recommender.propose.get_resolved_build",
            return_value={"spread": spread, "source_tier": "champions-native", "verified": True},
        ),
    ):
        out = fill_team_draft(state)

    s = out["team_draft"][0]
    assert s.moveset.value == moves
    assert s.item.value == item
    assert s.spread.value == spread
    assert s.moveset.locked is False
    assert s.moveset.reason is not None
    assert s.moveset.reason.kind == "tier1_cache"


def test_species_refine_persists_usage_ability_with_provenance():
    slot = Slot(species=Attr(value="Pelipper", locked=True))
    filler = Slot(role=Attr(value="bulky_attacker"))
    state = _base_state(
        team_draft=[slot, filler, *[empty_slot() for _ in range(4)]]
    )
    usage = {
        "species": "Pelipper",
        "ability": "Drizzle",
        "moves": ["Hurricane", "Weather Ball", "Tailwind", "Wide Guard"],
        "item": "Focus Sash",
    }
    with (
        patch("recommender.propose.featured_or_common_set", return_value=usage),
        patch("recommender.propose.get_resolved_build", return_value=None),
        patch("recommender.propose.select_usage_spread", return_value=None),
        patch("recommender.propose.get_relevant_threats", return_value=[]),
    ):
        out = fill_team_draft(state)

    ability = out["team_draft"][0].ability
    assert ability.value == "Drizzle"
    assert ability.locked is False
    assert ability.reason == ReasonRef(kind="tier2_heuristic", ref="usage")


def test_species_cache_miss_uses_contextual_tier2_spread_and_nature():
    moves = ["Earthquake", "Dragon Claw", "Rock Slide", "Protect"]
    item = "Life Orb"
    slot = Slot(species=Attr(value="Garchomp", locked=True))
    filler = Slot(role=Attr(value="support_speed_control"))
    state = _base_state(
        team_draft=[slot, filler, *[empty_slot() for _ in range(4)]]
    )
    expected = {"hp": 20, "atk": 32, "def": 14, "spa": 0, "spd": 0, "spe": 0}

    with (
        patch(
            "recommender.propose.featured_or_common_set",
            return_value={"species": "Garchomp", "moves": moves, "item": item},
        ),
        patch("recommender.propose.get_resolved_build", return_value=None),
        patch(
            "recommender.propose.select_usage_spread",
            return_value=SpreadChoice(
                spread=expected,
                nature="Adamant",
                source="tier2_usage_offline",
                rationale="selected rank=2",
            ),
        ) as select,
        patch("recommender.propose.get_relevant_threats", return_value=[]),
    ):
        out = fill_team_draft(state)

    s = out["team_draft"][0]
    assert s.moveset.value == moves
    assert s.item.value == item
    assert s.spread.value == expected
    assert s.nature.value == "Adamant"
    assert s.spread.reason is not None
    assert s.spread.reason.kind == "tier2_heuristic"
    assert s.spread.reason.ref == "tier2_usage_offline"
    select.assert_called_once()


def test_archetype_bias_trick_room():
    state = _base_state(
        archetype=Attr(value=["TrickRoom"], locked=True, reason=ReasonRef(kind="user_stated"))
    )
    out = fill_team_draft(state)
    roles = [s.role.value for s in out["team_draft"] if s.role.value]
    assert "trick_room_setter" in roles
    hit = next(s for s in out["team_draft"] if s.role.value == "trick_room_setter")
    assert hit.role.reason is not None
    assert hit.role.reason.ref == "TrickRoom"


def test_pick_role_returns_actionable_immutable_target_decision():
    decision = _pick_role([empty_slot()], ["Tailwind"], False, False)
    assert isinstance(decision, TargetRoleDecision)
    assert decision.role_id == "tailwind_setter"
    assert decision.needed_constraints == ("role:tailwind_setter",)
    vocabulary = set(get_args(TargetRoleId))
    assert {"bulky_pivot", "fast_pivot"} <= vocabulary
    assert "support_speed_control" not in vocabulary


def test_pick_role_preserves_ambiguous_speed_control():
    decision = _pick_role(
        [empty_slot()], ["TrickRoom", "Tailwind"], False, False
    )
    assert isinstance(decision, UnresolvedTargetRoleDecision)
    assert decision.reason == "ambiguous_speed_control"
    assert decision.ambiguity == ("trick_room_setter", "tailwind_setter")


def test_partial_refine_preserves_moveset():
    moves = ["Earthquake", "Dragon Claw", "Rock Slide", "Protect"]
    item = "Life Orb"
    spread = {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32}
    slot = Slot(
        species=Attr(value="Garchomp", locked=True),
        moveset=Attr(value=moves, locked=False, reason=ReasonRef(kind="user_stated")),
    )
    filler = Slot(role=Attr(value="support_speed_control"))
    state = _base_state(
        team_draft=[slot, filler, *[empty_slot() for _ in range(4)]]
    )

    with (
        patch(
            "recommender.propose.featured_or_common_set",
            return_value={"species": "Garchomp", "moves": ["Outrage"], "item": item},
        ),
        patch(
            "recommender.propose.get_resolved_build",
            return_value={"spread": spread, "source_tier": "cache", "verified": True},
        ) as cache,
    ):
        out = fill_team_draft(state)

    s = out["team_draft"][0]
    assert s.moveset.value == moves  # preserved
    assert s.item.value == item
    assert s.spread.value == spread
    cache.assert_called_once()
    assert cache.call_args.args[1] == moves


def test_nodes_wrapper_delegates():
    with patch("recommender.propose.fill_team_draft", return_value={"team_draft": []}) as m:
        out = propose_team_draft(_base_state())
    assert out == {"team_draft": []}
    m.assert_called_once()
