"""Live-calc regression for support-preference Category-B diversification."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from recommender.calc_service import CalcService
from recommender.condition_resilience import assess_condition_resilience
from recommender.nodes import _compute_team_review
from recommender.slot_fill import SlotFillContext, present_candidates
from recommender.state import Attr, Slot, empty_slot
from recommender.team_candidates import (
    _categorize_candidates,
    _diversity_need_categories,
    _need_branch_evidence,
    _rank_by_need_evidence,
    _support_need_categories,
    annotate_composition_impact,
    build_team_threat_objective,
    collect_locked_anchor_contexts,
    merge_multi_locked_candidates,
    rank_multi_locked_by_category,
)
from recommender.teammates import query_shared_teammates
from recommender.threat_counters import query_candidates_for_threats
from recommender.usage_data import lineage_ids, to_id

pytestmark = pytest.mark.skipif(
    os.environ.get("CALC_LIVE") != "1",
    reason="needs live calc service (CALC_LIVE=1)",
)

REPO = Path(__file__).resolve().parents[2]


def locked_slot(
    species: str,
    *,
    role: str,
    ability: str,
    item: str,
    moves: list[str],
    nature: str,
    spread: dict[str, int],
) -> Slot:
    return Slot(
        role=Attr(role, locked=True),
        species=Attr(species, locked=True),
        ability=Attr(ability, locked=True),
        item=Attr(item, locked=True),
        moveset=Attr(moves, locked=True),
        spread=Attr(spread, locked=True),
        nature=Attr(nature, locked=True),
    )


def support_discovery_state(draft: list[Slot]) -> dict[str, Any]:
    return {
        "format_id": "[Gen 9 Champions] VGC 2026 Reg M-B",
        "game_type": "doubles",
        "regulation_mod": "champions-reg-mb",
        "picked_team_size": 4,
        "available_pool": [],
        "team_draft": draft,
        "archetype": Attr(),
        "rejected": [],
        "constraints": [],
        "messages": [],
        "team_completion_preference": "support",
        "ownership_mode": "off",
    }


def rain_core_draft() -> list[Slot]:
    return [
        locked_slot(
            "Archaludon",
            role="bulky_special_attacker",
            ability="Stamina",
            item="Leftovers",
            moves=["Electro Shot", "Flash Cannon", "Protect", "Dragon Pulse"],
            nature="Calm",
            spread={"hp": 32, "atk": 0, "def": 1, "spa": 5, "spd": 25, "spe": 3},
        ),
        locked_slot(
            "Pelipper",
            role="support_speed_control",
            ability="Drizzle",
            item="Focus Sash",
            moves=["Hurricane", "Weather Ball", "Tailwind", "Wide Guard"],
            nature="Modest",
            spread={"hp": 32, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 2},
        ),
        locked_slot(
            "Swampert-Mega",
            role="bulky_attacker",
            ability="Swift Swim",
            item="Swampertite",
            moves=["Protect", "Wave Crash", "Ice Punch", "Earthquake"],
            nature="Adamant",
            spread={"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32},
        ),
        *[empty_slot() for _ in range(3)],
    ]


def run_support_preference_pipeline(state: dict[str, Any]):
    draft = state["team_draft"]
    contexts = collect_locked_anchor_contexts(state)
    resilience = assess_condition_resilience(contexts)
    locked_species = [
        str(slot.species.value)
        for slot in draft
        if slot.species.value and slot.species.locked
    ]
    shared = query_shared_teammates(locked_species, state["regulation_mod"])
    review = _compute_team_review(state, {"configurable": {"thread_id": "support-live"}})
    assert review.status != "unavailable", review.error
    objective = build_team_threat_objective(review)
    excluded = {lineage for sp in locked_species for lineage in lineage_ids(sp)}
    threat_discovery = query_candidates_for_threats(
        objective,
        available_pool=[],
        ownership_mode="off",
        excluded_species=excluded,
        locked_contexts=contexts,
    )
    assert threat_discovery.status == "available", threat_discovery.error
    merged = merge_multi_locked_candidates(
        state,
        contexts,
        threat_discovery.candidates,
        shared,
        ownership_mode="off",
        owned_species=frozenset(),
        condition_resilience=resilience,
    )
    candidates = annotate_composition_impact(
        merged,
        state,
        locked_anchors=contexts,
        condition_resilience=resilience,
        objective=objective,
    )
    narrow_cut = rank_multi_locked_by_category(candidates, contexts, n_per_category=10)
    wide_cut = rank_multi_locked_by_category(
        candidates,
        contexts,
        category_b_uncapped=True,
    )
    ctx = SlotFillContext(
        anchor=None,
        role_shape_context=None,
        annotated_candidates=wide_cut,
        candidates_pre_ranked=True,
        condition_resilience=resilience,
        locked_contexts=contexts,
        team_completion_preference="support",
    )
    presentation = present_candidates(ctx, slot_index=3)
    return {
        "contexts": contexts,
        "candidates": candidates,
        "narrow_cut": narrow_cut,
        "wide_cut": wide_cut,
        "presentation": presentation,
    }


def test_support_preference_diversifies_beyond_tr_setter_cluster():
    state = support_discovery_state(rain_core_draft())
    with CalcService(repo_root=REPO):
        result = run_support_preference_pipeline(state)

    _, category_b, _ = _categorize_candidates(result["candidates"])
    category_b_ids = {to_id(c.species) for c in category_b}
    narrow_b_ids = {
        to_id(c.species)
        for c in result["narrow_cut"]
        if to_id(c.species) in category_b_ids
    }
    wide_b_ids = {
        to_id(c.species)
        for c in result["wide_cut"]
        if to_id(c.species) in category_b_ids
    }
    assert to_id("Sableye") in category_b_ids
    assert to_id("Sableye") not in narrow_b_ids
    assert to_id("Sableye") in wide_b_ids

    options = [row.species for row in result["presentation"].candidates]
    assert options[0] == "Sinistcha"
    # Screens must appear (Klefki / similar). Pass-2 subset redundancy means
    # a third screens-only option is no longer treated as "diverse" after
    # Klefki, so option 3 may be a pass-3 filler — that is expected. Pure
    # TR-only presentations without screens remain the failure mode.
    assert len(options) >= 2

    by_species = {to_id(c.species): c for c in result["candidates"]}
    picked_categories: set[str] = set()
    for species in options:
        picked_categories |= _diversity_need_categories(by_species[to_id(species)])
    assert "screens" in picked_categories
    assert picked_categories - {"healing_cleric", "trick_room"}
    # No option should be diversify-pure trick_room on first presentation
    # when screens is still an open need being answered by another option.
    pure_tr = [
        s
        for s in options
        if _diversity_need_categories(by_species[to_id(s)]) == frozenset({"trick_room"})
    ]
    assert not pure_tr, pure_tr

def test_support_preference_grimmsnarl_clears_strong_evidence_gate():
    state = support_discovery_state(rain_core_draft())
    with CalcService(repo_root=REPO):
        result = run_support_preference_pipeline(state)

    _, category_b, _ = _categorize_candidates(result["candidates"])
    by_species = {to_id(c.species): c for c in category_b}
    grimmsnarl = by_species.get(to_id("Grimmsnarl"))
    assert grimmsnarl is not None, "Grimmsnarl must be in category_b"

    relevant = _need_branch_evidence(grimmsnarl, condition_beneficiary=False)
    assert any(item.confidence != "low" for item in relevant), (
        "Fix A: unconditional screens with in-game commitment must not "
        "be force-low; Grimmsnarl needs a non-low need-branch confidence"
    )

    ranked_b = [
        c
        for c in _rank_by_need_evidence(
            category_b, result["contexts"], condition_beneficiary=False
        )
        if any(
            item.confidence != "low"
            for item in _need_branch_evidence(c, condition_beneficiary=False)
        )
    ]
    ranked_ids = [to_id(c.species) for c in ranked_b]
    assert to_id("Grimmsnarl") in ranked_ids
    # Redirection NeedCategory expands Category B competition (Rage Powder /
    # Follow Me users); keep a soft top-band gate, not a brittle absolute.
    assert ranked_ids.index(to_id("Grimmsnarl")) < 20

    options = [row.species for row in result["presentation"].candidates]
    # Diversify may prefer redirectors + Klefki screens when redirection is
    # an open need; Grimmsnarl still clears the evidence/rank gate above.
    screens_picked = any(
        "screens" in _diversity_need_categories(by_species[to_id(s)])
        for s in options
        if to_id(s) in by_species
    )
    assert screens_picked or "Grimmsnarl" in options


def test_support_preference_klefki_diversity_drops_acceptable_tr():
    state = support_discovery_state(rain_core_draft())
    with CalcService(repo_root=REPO):
        result = run_support_preference_pipeline(state)

    by_species = {to_id(c.species): c for c in result["candidates"]}
    klefki = by_species.get(to_id("Klefki"))
    assert klefki is not None
    raw = _support_need_categories(klefki)
    assert "screens" in raw and "trick_room" in raw
    assert _diversity_need_categories(klefki) == frozenset({"screens"})


def test_support_preference_banned_tr_profile_blocks_reject_cycle():
    state = support_discovery_state(rain_core_draft())
    with CalcService(repo_root=REPO):
        result = run_support_preference_pipeline(state)

    presentation = present_candidates(
        SlotFillContext(
            anchor=None,
            role_shape_context=None,
            annotated_candidates=result["wide_cut"],
            candidates_pre_ranked=True,
            locked_contexts=tuple(result["contexts"]),
            team_completion_preference="support",
            banned_profiles=frozenset({frozenset({"trick_room"})}),
        ),
        slot_index=3,
    )
    options = [row.species for row in presentation.candidates]
    by_species = {to_id(c.species): c for c in result["candidates"]}
    for species in options:
        cats = _diversity_need_categories(by_species[to_id(species)])
        assert cats != frozenset({"trick_room"}), (
            f"{species} pure-TR must not appear when trick_room profile is banned"
        )
