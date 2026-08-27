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
    assert "support_speed_control" in vocabulary


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


def test_no_usage_hatterene_fills_kit_but_leaves_ability_unresolved():
    from recommender.slot_fill import build_provisional_slot
    from recommender.state import PendingSlotIntent, UnresolvedSlotRefinement

    intent = PendingSlotIntent(
        schema_version=1,
        slot_index=2,
        species="Hatterene",
        source="mechanical",
        target_role_decision=TargetRoleDecision(
            role_id="trick_room_setter",
            source="other",
            evidence=(),
            needed_constraints=("move:trickroom",),
            confidence="high",
            provenance=("test",),
        ),
        base_slot_fingerprint="x",
    )
    state = _base_state(archetype=Attr(value=["TrickRoom"], locked=True))
    with patch("recommender.propose.featured_or_common_set", return_value=None):
        result = build_provisional_slot(intent, state)
    assert isinstance(result, UnresolvedSlotRefinement)
    assert result.reason == "incomplete_build"
    assert result.unresolved_fields == ("ability",)


def test_no_usage_mimikyu_refines_to_provisional_slot():
    from recommender.slot_fill import build_provisional_slot
    from recommender.state import PendingSlotIntent, ProvisionalSlot

    intent = PendingSlotIntent(
        schema_version=1,
        slot_index=5,
        species="Mimikyu",
        source="owned",
        target_role_decision=TargetRoleDecision(
            role_id="fast_attacker",
            source="other",
            evidence=(),
            needed_constraints=(),
            confidence="medium",
            provenance=("test",),
        ),
        base_slot_fingerprint="x",
    )
    with patch("recommender.propose.featured_or_common_set", return_value=None):
        result = build_provisional_slot(intent, _base_state())
    assert isinstance(result, ProvisionalSlot)
    assert result.ability == "Disguise"
    assert result.item
    assert result.nature
    assert len(result.moves) == 4
    assert "protect" in {m.lower() for m in result.moves}
    assert sum(result.spread_dict().values()) == 66


def _no_usage_provisional(species: str, role_id: str, **decision_kw):
    from recommender.slot_fill import build_provisional_slot
    from recommender.state import PendingSlotIntent

    intent = PendingSlotIntent(
        schema_version=1,
        slot_index=0,
        species=species,
        source="owned",
        target_role_decision=TargetRoleDecision(
            role_id=role_id,  # type: ignore[arg-type]
            source="other",
            evidence=(),
            needed_constraints=decision_kw.get("needed_constraints", ()),
            confidence=decision_kw.get("confidence", "medium"),
            provenance=("test",),
        ),
        base_slot_fingerprint="x",
    )
    state = decision_kw.get("state") or _base_state()
    with patch("recommender.propose.featured_or_common_set", return_value=None):
        return build_provisional_slot(intent, state)


def test_no_usage_mimikyu_fast_physical_attacker_fills():
    from recommender.state import ProvisionalSlot

    result = _no_usage_provisional("Mimikyu", "fast_physical_attacker")
    assert isinstance(result, ProvisionalSlot)
    assert result.ability == "Disguise"
    assert len(result.moves) == 4
    assert "protect" in {m.lower() for m in result.moves}
    assert sum(result.spread_dict().values()) == 66


def test_no_usage_mimikyu_swords_dance_attacker_fills():
    from recommender.ids import to_id
    from recommender.state import ProvisionalSlot

    result = _no_usage_provisional("Mimikyu", "swords_dance_attacker")
    assert isinstance(result, ProvisionalSlot)
    mids = {to_id(m) for m in result.moves}
    assert "swordsdance" in mids
    assert "protect" in mids
    assert len(result.moves) == 4


def test_no_usage_incineroar_bulky_pivot_moves_fill_ability_unresolved():
    from recommender.state import UnresolvedSlotRefinement

    result = _no_usage_provisional("Incineroar", "bulky_pivot")
    assert isinstance(result, UnresolvedSlotRefinement)
    assert result.reason == "incomplete_build"
    assert result.unresolved_fields == ("ability",)


def test_no_usage_sinistcha_redirection_leaves_moves_short():
    from recommender.state import UnresolvedSlotRefinement

    result = _no_usage_provisional("Sinistcha", "redirection")
    assert isinstance(result, UnresolvedSlotRefinement)
    assert result.reason == "incomplete_build"
    assert "moves" in result.unresolved_fields


def test_no_usage_klefki_screens_support_moves_fill_ability_unresolved():
    from recommender.state import UnresolvedSlotRefinement

    result = _no_usage_provisional("Klefki", "screens_support")
    assert isinstance(result, UnresolvedSlotRefinement)
    assert result.reason == "incomplete_build"
    assert result.unresolved_fields == ("ability",)


def test_no_usage_pelipper_rain_setter_leaves_moves_short():
    from recommender.state import UnresolvedSlotRefinement

    result = _no_usage_provisional("Pelipper", "rain_setter")
    assert isinstance(result, UnresolvedSlotRefinement)
    assert result.reason == "incomplete_build"
    assert "moves" in result.unresolved_fields


def test_usage_hit_sinistcha_keeps_usage_provenance():
    slot = Slot(
        species=Attr(value="Sinistcha", locked=True),
        role=Attr(value="redirection"),
    )
    filler = Slot(role=Attr(value="bulky_attacker"))
    state = _base_state(team_draft=[slot, filler, *[empty_slot() for _ in range(4)]])
    out = fill_team_draft(state)
    s = out["team_draft"][0]
    assert s.ability.value
    assert s.item.value
    assert s.moveset.value and len(s.moveset.value) == 4
    assert s.ability.reason is not None
    assert s.ability.reason.ref == "usage"
    assert s.item.reason is not None
    assert s.item.reason.ref != "tier3_item_default"


def test_tier3_role_spread_sets_nature_when_usage_spreads_miss():
    moves = ["Trick Room", "Psychic", "Dazzling Gleam", "Protect"]
    item = "Life Orb"
    slot = Slot(
        species=Attr(value="Hatterene", locked=True),
        role=Attr(value="trick_room_setter"),
        moveset=Attr(value=moves, locked=False),
        item=Attr(value=item, locked=False),
    )
    filler = Slot(role=Attr(value="bulky_attacker"))
    state = _base_state(team_draft=[slot, filler, *[empty_slot() for _ in range(4)]])
    with (
        patch("recommender.propose.featured_or_common_set", return_value=None),
        patch("recommender.propose.get_resolved_build", return_value=None),
        patch("recommender.propose.select_usage_spread", return_value=None),
        patch("recommender.propose.get_relevant_threats", return_value=[]),
    ):
        out = fill_team_draft(state)
    s = out["team_draft"][0]
    assert s.spread.value is not None
    assert sum(s.spread.value.values()) == 66
    assert s.spread.reason is not None
    assert s.spread.reason.ref == "tier3_role"
    assert s.nature.value is not None
    assert s.nature.reason == ReasonRef(kind="tier2_heuristic", ref="tier3_nature")


def test_multi_ability_without_role_match_leaves_ability_unresolved():
    slot = Slot(
        species=Attr(value="Hatterene", locked=True),
        role=Attr(value="fast_attacker"),
    )
    filler = Slot(role=Attr(value="bulky_attacker"))
    state = _base_state(team_draft=[slot, filler, *[empty_slot() for _ in range(4)]])
    with patch("recommender.propose.featured_or_common_set", return_value=None):
        out = fill_team_draft(state)
    assert out["team_draft"][0].ability.value is None


def test_role_constraint_ability_is_synthesized_and_not_present_mechanism():
    from recommender.anchor_roles import classify_anchor_role, resolve_anchor_build
    from recommender.role_compendium import ReverseCompendiumEvidence

    slot = Slot(
        species=Attr(value="Pelipper", locked=True),
        role=Attr(value="rain_setter"),
    )
    filler = Slot(role=Attr(value="bulky_attacker"))
    state = _base_state(team_draft=[slot, filler, *[empty_slot() for _ in range(4)]])
    with (
        patch("recommender.propose.featured_or_common_set", return_value=None),
        patch("recommender.propose.get_resolved_build", return_value=None),
        patch("recommender.propose.select_usage_spread", return_value=None),
        patch("recommender.propose.get_relevant_threats", return_value=[]),
    ):
        out = fill_team_draft(state)
    ability = out["team_draft"][0].ability
    assert ability.value == "Drizzle"
    assert ability.reason == ReasonRef(kind="tier2_heuristic", ref="tier3_role_ability")

    resolved = resolve_anchor_build(out["team_draft"][0])
    assert resolved.source_for("ability") == "synthesized"
    decision = classify_anchor_role(
        resolved, compendium=ReverseCompendiumEvidence()
    )
    assert not any(
        m.kind == "automatic_condition_setting" and m.present
        for m in decision.mechanisms
    )


def test_cached_nature_preferred_over_independently_sourced_usage_nature():
    """The real Archaludon bug: get_resolved_build's cache and
    featured_or_common_set are independently-sourced — combining a cached
    spread with a usage-sourced nature can pair two individually-real
    attributes into a set that no real source actually recommends. When
    the cache entry has its own confirmed nature (only set when the real
    source material explicitly ties this exact spread to it), that must
    win over whatever nature usage independently returns.
    """
    from recommender.slot_fill import build_provisional_slot
    from recommender.state import PendingSlotIntent

    intent = PendingSlotIntent(
        schema_version=1,
        slot_index=0,
        species="Archaludon",
        source="mechanical",
        target_role_decision=TargetRoleDecision(
            role_id="bulky_special_attacker",
            source="other",
            confidence="medium",
        ),
        base_slot_fingerprint="x",
    )
    fake_usage = {
        "ability": "Stamina",
        "nature": "Timid",  # deliberately conflicting with the cache below
        "moves": ["Electro Shot", "Flash Cannon", "Protect", "Dragon Pulse"],
        "item": "Leftovers",
    }
    fake_cached = {
        "spread": {"hp": 32, "atk": 0, "def": 1, "spa": 5, "spd": 25, "spe": 3},
        "nature": "Modest",
    }
    with (
        patch("recommender.propose.featured_or_common_set", return_value=fake_usage),
        patch("recommender.propose.get_resolved_build", return_value=fake_cached),
    ):
        result = build_provisional_slot(intent, _base_state())
    assert result.nature == "Modest"
    assert dict(result.spread) == fake_cached["spread"]


def test_cache_without_nature_field_falls_back_to_usage_nature():
    """Regression: most cached entries have no nature field (genuinely
    nature-flexible, or simply not yet confirmed) — those must keep falling
    back to featured_or_common_set's nature exactly as before this fix.
    """
    from recommender.slot_fill import build_provisional_slot
    from recommender.state import PendingSlotIntent

    intent = PendingSlotIntent(
        schema_version=1,
        slot_index=0,
        species="Garchomp",
        source="mechanical",
        target_role_decision=TargetRoleDecision(
            role_id="fast_physical_attacker",
            source="other",
            confidence="medium",
        ),
        base_slot_fingerprint="x",
    )
    fake_usage = {
        "ability": "Rough Skin",
        "nature": "Jolly",
        "moves": ["Earthquake", "Dragon Claw", "Protect", "Stomping Tantrum"],
        "item": "Sitrus Berry",
    }
    fake_cached = {
        "spread": {"hp": 0, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32},
        # no "nature" key at all — the common, un-confirmed case
    }
    with (
        patch("recommender.propose.featured_or_common_set", return_value=fake_usage),
        patch("recommender.propose.get_resolved_build", return_value=fake_cached),
    ):
        result = build_provisional_slot(intent, _base_state())
    assert result.nature == "Jolly"


def test_real_archaludon_data_file_produces_correct_nature_end_to_end():
    """No mocks — the real data/resolved-builds/*.jsonl file, confirming the
    fix actually landed in the real, committed data, not just in a mocked
    unit test. This is the exact live-session scenario that surfaced the bug.
    """
    from recommender.slot_fill import build_provisional_slot
    from recommender.state import PendingSlotIntent

    intent = PendingSlotIntent(
        schema_version=1,
        slot_index=0,
        species="Archaludon",
        source="mechanical",
        target_role_decision=TargetRoleDecision(
            role_id="bulky_special_attacker",
            source="other",
            confidence="medium",
        ),
        base_slot_fingerprint="x",
    )
    result = build_provisional_slot(intent, _base_state())
    assert result.nature == "Modest"
    assert dict(result.spread) == {
        "hp": 32, "atk": 0, "def": 1, "spa": 5, "spd": 25, "spe": 3,
    }


def test_explicit_empty_item_attempts_cache_lookup():
    """item=\"\" is a real key; truthiness must not skip get_resolved_build."""
    from recommender.propose import _refine_defaults

    moves = ["Brave Bird", "Flare Blitz", "Tailwind", "Protect"]
    slot = Slot(
        species=Attr(value="Talonflame", locked=True),
        moveset=Attr(value=moves, locked=True),
        item=Attr(value="", locked=True),
    )
    state = _base_state(team_draft=[slot, *[empty_slot() for _ in range(5)]])
    with patch("recommender.propose.get_resolved_build", return_value=None) as cached:
        _refine_defaults(slot, state, regulation="champions")
    cached.assert_called_once()
    assert cached.call_args.args[2] == ""
