"""Role-aware build synthesis on the usage-hit path."""

from __future__ import annotations

from recommender.anchor_roles import classify_anchor_role, resolve_anchor_build
from recommender.slot_fill import build_provisional_slot
from recommender.state import (
    PendingSlotIntent,
    ProvisionalSlot,
    RecommenderState,
    TargetRoleDecision,
    empty_slot,
)
from recommender.usage_data import featured_or_common_set


def _base_state(**overrides) -> RecommenderState:
    state: RecommenderState = {
        "format_id": "[Gen 9 Champions] VGC 2026 Reg M-B",
        "game_type": "doubles",
        "regulation_mod": "champions",
        "picked_team_size": 4,
        "available_pool": [],
        "team_draft": [empty_slot() for _ in range(6)],
        "archetype": __import__("recommender.state", fromlist=["Attr"]).Attr(),
        "rejected": [],
        "constraints": [],
        "messages": [],
    }
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


def _refined(species: str, role_id: str) -> ProvisionalSlot:
    state = _base_state()
    decision = TargetRoleDecision(role_id=role_id, source="usage_backed")
    intent = PendingSlotIntent(
        schema_version=1,
        slot_index=0,
        species=species,
        target_role_decision=decision,
        source="need",
    )
    result = build_provisional_slot(intent, state)
    assert isinstance(result, ProvisionalSlot)
    return result


def test_sableye_screens_support_matches_role_without_rain_dance():
    provisional = _refined("Sableye", "screens_support")
    build = resolve_anchor_build(
        "Sableye",
        provisional={
            "ability": provisional.ability,
            "item": provisional.item,
            "moves": provisional.moves,
            "nature": provisional.nature,
            "spread": provisional.spread_dict(),
        },
        role_hint="screens_support",
        regulation="champions-reg-mb",
    )
    decision = classify_anchor_role(build)
    assert decision.role_id == "screens_support"
    assert "Rain Dance" not in provisional.moves
    assert "Light Screen" in provisional.moves
    assert "Reflect" in provisional.moves


def test_ninetales_alola_screens_support_uses_snow_cloak():
    provisional = _refined("Ninetales-Alola", "screens_support")
    build = resolve_anchor_build(
        "Ninetales-Alola",
        provisional={
            "ability": provisional.ability,
            "item": provisional.item,
            "moves": provisional.moves,
            "nature": provisional.nature,
            "spread": provisional.spread_dict(),
        },
        role_hint="screens_support",
        regulation="champions-reg-mb",
    )
    decision = classify_anchor_role(build)
    assert decision.role_id == "screens_support"
    assert provisional.ability == "Snow Cloak"


def test_froslass_mega_screens_support_falls_back_to_snow_setter():
    provisional = _refined("Froslass-Mega", "screens_support")
    build = resolve_anchor_build(
        "Froslass-Mega",
        provisional={
            "ability": provisional.ability,
            "item": provisional.item,
            "moves": provisional.moves,
            "nature": provisional.nature,
            "spread": provisional.spread_dict(),
        },
        role_hint="screens_support",
        regulation="champions-reg-mb",
    )
    assert classify_anchor_role(build).role_id == "snow_setter"


def test_pelipper_rain_setter_moves_unchanged():
    default_moves = list(
        (featured_or_common_set("Pelipper", regulation="champions-reg-mb") or {}).get(
            "moves"
        )
        or []
    )
    provisional = _refined("Pelipper", "rain_setter")
    assert list(provisional.moves) == default_moves
    assert classify_anchor_role(
        resolve_anchor_build("Pelipper", regulation="champions-reg-mb")
    ).role_id == "rain_setter"


def test_grimmsnarl_screens_support_moves_unchanged():
    default_moves = list(
        (
            featured_or_common_set("Grimmsnarl", regulation="champions-reg-mb") or {}
        ).get("moves")
        or []
    )
    provisional = _refined("Grimmsnarl", "screens_support")
    assert list(provisional.moves) == default_moves
    assert classify_anchor_role(
        resolve_anchor_build("Grimmsnarl", regulation="champions-reg-mb")
    ).role_id == "screens_support"


def test_pelipper_tailwind_setter_provisional_spread_meets_budget():
    from recommender.recommend import SP_BUDGET, spread_sum

    provisional = _refined("Pelipper", "tailwind_setter")
    assert spread_sum(provisional.spread_dict()) == SP_BUDGET
    assert classify_anchor_role(
        resolve_anchor_build(
            "Pelipper",
            provisional={
                "ability": provisional.ability,
                "item": provisional.item,
                "moves": list(provisional.moves),
                "nature": provisional.nature,
                "spread": provisional.spread_dict(),
            },
            role_hint="tailwind_setter",
            regulation="champions-reg-mb",
        )
    ).role_id == "tailwind_setter"
