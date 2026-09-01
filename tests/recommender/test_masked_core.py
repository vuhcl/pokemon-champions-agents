"""Masked alternate-core discovery."""

from __future__ import annotations

import os
from contextlib import ExitStack
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch

import pytest

from recommender.anchor_roles import resolve_anchor_build
from recommender.condition_resilience import (
    assess_condition_resilience,
    provided_conditions,
    team_field_states,
)
from recommender.nodes import _compute_team_review, classify_pending, discover_multi_locked, initialize
from recommender.present_text import format_turn
from recommender.slot_fill import AnnotatedCandidate, CoreSlotConflict
from recommender.state import Attr, CandidateEvidence, Slot, empty_slot
from recommender.team_candidates import (
    MaskedCorePackage,
    annotate_composition_impact,
    build_team_threat_objective,
    collect_locked_anchor_contexts,
    detect_core_resource_conflicts,
    discover_masked_core_package,
    gather_masked_core_packages,
    independently_strong_category_a,
    mega_ceiling_notices,
    merge_multi_locked_candidates,
    remaining_open_after_place,
    should_try_masked_core,
    _package_label,
    _search_gap_fill,
)
from recommender.teammate_types import TeammateEvidence, TeammateQueryResult
from recommender.teammates import pairwise_teammate_lift, query_shared_teammates
from recommender.threat_counters import query_candidates_for_threats
from recommender.usage_data import lineage_ids, to_id

REG = "champions-reg-mb"

pytestmark_live = pytest.mark.skipif(
    os.environ.get("CALC_LIVE") != "1",
    reason="needs live calc service (CALC_LIVE=1)",
)


def _locked(
    species: str,
    *,
    role: str = "bulky_attacker",
    ability: str = "Pressure",
    item: str = "Leftovers",
    moves: list[str] | None = None,
) -> Slot:
    return Slot(
        role=Attr(role, locked=True),
        species=Attr(species, locked=True),
        ability=Attr(ability, locked=True),
        item=Attr(item, locked=True),
        moveset=Attr(moves or ["Tackle", "Protect", "Rest", "Sleep Talk"], locked=True),
        spread=Attr(
            {"hp": 32, "atk": 32, "def": 2, "spa": 0, "spd": 0, "spe": 0},
            locked=True,
        ),
        nature=Attr("Adamant", locked=True),
    )


def _state(draft: list[Slot] | None = None, **extra):
    base = {
        "format_id": "[Gen 9 Champions] VGC 2026 Reg M-B",
        "game_type": "doubles",
        "regulation_mod": "champions-reg-mb",
        "picked_team_size": 4,
        "available_pool": [],
        "team_draft": draft or [empty_slot() for _ in range(6)],
        "archetype": Attr(),
        "rejected": [],
        "constraints": [],
        "messages": [],
    }
    base.update(extra)
    return base


def _evidence(*, usage: bool = True) -> CandidateEvidence:
    return CandidateEvidence(
        basis="usage_backed" if usage else "mechanical_only",
        confidence="high",
        producer_name="test",
    )


def _candidate(
    species: str,
    *,
    wastes: bool = True,
    usage: bool = True,
    threat: bool = True,
    conflicts: tuple[CoreSlotConflict, ...] = (),
) -> AnnotatedCandidate:
    row = None
    if threat:
        row = SimpleNamespace(verified_vs=(("x", object()),), verified_score=8.0)
    return AnnotatedCandidate(
        species=species,
        matching_needs=(),
        source="threat",
        threat_row=row,  # type: ignore[arg-type]
        spec={"species": species},
        evidence=(_evidence(usage=usage),),
        branches=frozenset({"threat"}),
        wastes_core_slot=wastes,
        core_slot_conflicts=conflicts,
    )


def _fill(species: str = "Pelipper") -> AnnotatedCandidate:
    return _candidate(species, wastes=False, conflicts=())


def _conflict(*, slot: int = 0) -> CoreSlotConflict:
    return CoreSlotConflict(
        kind="weather",
        locked_slot_index=slot,
        locked_species="Charizard-Mega-Y",
        resource="Sun",
    )


def _objective_row(species: str = "Gholdengo"):
    threat = SimpleNamespace(spec={"species": species})
    return SimpleNamespace(threat=threat)


def _four_locked_draft() -> list[Slot]:
    return [
        _locked("Archaludon"),
        _locked("Incineroar"),
        _locked("Amoonguss"),
        _locked(
            "Charizard-Mega-Y",
            ability="Drought",
            item="Charizardite Y",
            moves=["Heat Wave", "Protect", "Weather Ball", "Solar Beam"],
        ),
        empty_slot(),
        empty_slot(),
    ]


def _locked_from_species(species: str, *, role: str = "bulky_attacker") -> Slot:
    build = resolve_anchor_build(species, regulation=REG)
    return Slot(
        role=Attr(role, locked=True),
        species=Attr(build.species or species, locked=True),
        ability=Attr(build.ability or "", locked=True),
        item=Attr(build.item or "", locked=True),
        moveset=Attr(list(build.moves or ()), locked=True),
        spread=Attr(dict(build.spread or {}), locked=True),
        nature=Attr(build.nature or "Serious", locked=True),
    )


def _sun_core_sequential_draft() -> list[Slot]:
    """Transcript A: 4 locks in order, filling slot 5 (index 4)."""
    return [
        _locked_from_species("Archaludon", role="bulky_special_attacker"),
        _locked_from_species("Incineroar", role="support"),
        _locked_from_species("Amoonguss", role="support"),
        _locked_from_species("Charizard-Mega-Y", role="sun_setter"),
        empty_slot(),
        empty_slot(),
    ]


def _run_sequential_annotation_pipeline(state: dict[str, Any]):
    draft = state["team_draft"]
    contexts = collect_locked_anchor_contexts(state)
    resilience = assess_condition_resilience(contexts)
    locked_species = [
        str(slot.species.value)
        for slot in draft
        if slot.species.value and slot.species.locked
    ]
    shared = query_shared_teammates(locked_species, state["regulation_mod"])
    review = _compute_team_review(state, {"configurable": {"thread_id": "masked-core-test"}})
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
    return {
        "contexts": contexts,
        "candidates": candidates,
        "objective": objective,
        "resilience": resilience,
    }


def _gap_fill_patches(fill: AnnotatedCandidate):
    return (
        patch(
            "recommender.team_candidates.merge_multi_locked_candidates",
            return_value=[fill],
        ),
        patch(
            "recommender.team_candidates.annotate_composition_impact",
            side_effect=lambda rows, *args, **kwargs: list(rows),
        ),
        patch(
            "recommender.team_candidates.rank_multi_locked_by_category",
            side_effect=lambda rows, *args: list(rows),
        ),
        patch(
            "recommender.threat_counters.query_candidates_for_threats",
            return_value=SimpleNamespace(status="available", candidates=()),
        ),
    )


def _gap_fill_patches_multi(*fills: AnnotatedCandidate):
    return (
        patch(
            "recommender.team_candidates.merge_multi_locked_candidates",
            return_value=list(fills),
        ),
        patch(
            "recommender.team_candidates.annotate_composition_impact",
            side_effect=lambda rows, *args, **kwargs: list(rows),
        ),
        patch(
            "recommender.team_candidates.rank_multi_locked_by_category",
            side_effect=lambda rows, *args: list(rows),
        ),
        patch(
            "recommender.threat_counters.query_candidates_for_threats",
            return_value=SimpleNamespace(status="available", candidates=()),
        ),
        patch("recommender.team_candidates._calc_agrees", return_value=True),
    )


def _run_gap_fill(*args, fill: AnnotatedCandidate, **kwargs):
    with ExitStack() as stack:
        for item in _gap_fill_patches(fill):
            stack.enter_context(item)
        return _search_gap_fill(*args, **kwargs)


def _run_gap_fill_multi(*args, fills: tuple[AnnotatedCandidate, ...], **kwargs):
    with ExitStack() as stack:
        for item in _gap_fill_patches_multi(*fills):
            stack.enter_context(item)
        return _search_gap_fill(*args, **kwargs)


def _query_result(row: TeammateEvidence) -> TeammateQueryResult:
    return TeammateQueryResult(
        anchor_id="swampertmega",
        anchor_name="Swampert-Mega",
        status="available",
        source="showdown-offline",
        rows=(row,),
        raw_count=1,
        truncated=False,
        caveats=(),
    )


def test_pairwise_teammate_lift_divides_conditional_by_usage():
    row = TeammateEvidence(
        species_id="pelipper",
        name="Pelipper",
        rank=1,
        conditional_pct=20.0,
        chaos_weight=None,
        attribution_status="exact",
    )
    with patch(
        "recommender.teammates.showdown_species_map",
        return_value={"pelipper": {"usage_pct": 10.0}},
    ):
        assert (
            pairwise_teammate_lift(
                "Swampert-Mega", "Pelipper", query=lambda *_: _query_result(row)
            )
            == 2.0
        )


def test_pairwise_teammate_lift_missing_usage_is_none():
    row = TeammateEvidence(
        species_id="pelipper",
        name="Pelipper",
        rank=1,
        conditional_pct=20.0,
        chaos_weight=None,
        attribution_status="exact",
    )
    with patch("recommender.teammates.showdown_species_map", return_value={}):
        assert (
            pairwise_teammate_lift(
                "Swampert-Mega", "Pelipper", query=lambda *_: _query_result(row)
            )
            is None
        )


def test_pairwise_teammate_lift_non_exact_is_none():
    row = TeammateEvidence(
        species_id="pelipper",
        name="Pelipper",
        rank=1,
        conditional_pct=20.0,
        chaos_weight=None,
        attribution_status="ambiguous",
    )
    with patch(
        "recommender.teammates.showdown_species_map",
        return_value={"pelipper": {"usage_pct": 10.0}},
    ):
        assert (
            pairwise_teammate_lift(
                "Swampert-Mega", "Pelipper", query=lambda *_: _query_result(row)
            )
            is None
        )


def test_search_gap_fill_rejects_when_working_too_small():
    draft = [
        _locked(
            "Charizard-Mega-Y",
            role="sun_setter",
            ability="Drought",
            item="Charizardite Y",
            moves=["Heat Wave", "Protect", "Weather Ball", "Solar Beam"],
        ),
        *[empty_slot() for _ in range(5)],
    ]
    state = _state(draft)
    locked = collect_locked_anchor_contexts(state)
    candidate = _candidate("Swampert-Mega", conflicts=(_conflict(),))
    fill = _fill("Pelipper")
    result = _run_gap_fill(
        candidate,
        state,
        locked,
        frozenset({0}),
        (_objective_row(),),
        1,
        fill=fill,
    )
    assert result is None


def test_search_gap_fill_rejects_empty_objective():
    draft = _four_locked_draft()
    state = _state(draft)
    locked = collect_locked_anchor_contexts(state)
    candidate = _candidate("Swampert-Mega", conflicts=(_conflict(slot=3),))
    fill = _fill("Pelipper")
    result = _run_gap_fill(
        candidate,
        state,
        locked,
        frozenset({3}),
        (),
        4,
        fill=fill,
    )
    assert result is None


def test_search_gap_fill_skips_budget_exhausting_first_pick():
    draft = _four_locked_draft()
    state = _state(draft)
    locked = collect_locked_anchor_contexts(state)
    candidate = _candidate("Swampert-Mega", conflicts=(_conflict(slot=3),))
    conflicting = _candidate(
        "Aerodactyl-Mega",
        wastes=False,
        conflicts=(
            CoreSlotConflict("mega", 4, "Swampert-Mega", "swampert"),
        ),
    )
    clean = _fill("Primarina")
    result = _run_gap_fill_multi(
        candidate,
        state,
        locked,
        frozenset({3}),
        (_objective_row(),),
        4,
        fills=(conflicting, clean),
    )
    assert result is not None
    assert result.species == "Primarina"


def test_discover_masked_core_package_skips_budget_exhausting_fill():
    draft = _four_locked_draft()
    state = _state(draft)
    locked = collect_locked_anchor_contexts(state)
    candidate = _candidate("Swampert-Mega", conflicts=(_conflict(slot=3),))
    conflicting = _candidate(
        "Aerodactyl-Mega",
        wastes=False,
        conflicts=(
            CoreSlotConflict("mega", 4, "Swampert-Mega", "swampert"),
        ),
    )
    clean = _fill("Primarina")
    with ExitStack() as stack:
        for item in _gap_fill_patches_multi(conflicting, clean):
            stack.enter_context(item)
        package = discover_masked_core_package(
            candidate,
            state,
            locked,
            objective=(_objective_row(),),
        )
    assert package is not None
    assert package.fill.species == "Primarina"


def test_should_try_false_when_working_too_small():
    draft = [
        _locked("Charizard-Mega-Y", ability="Drought", item="Charizardite Y"),
        *[empty_slot() for _ in range(5)],
    ]
    state = _state(draft)
    locked = collect_locked_anchor_contexts(state)
    candidate = _candidate("Swampert-Mega", conflicts=(_conflict(),))
    with patch(
        "recommender.team_candidates.independently_strong_category_a",
        return_value=True,
    ):
        assert should_try_masked_core(candidate, [candidate], state, locked) is False


def test_should_try_true_when_working_meets_pick():
    draft = _four_locked_draft()
    state = _state(draft)
    locked = collect_locked_anchor_contexts(state)
    candidate = _candidate("Swampert-Mega", conflicts=(_conflict(slot=3),))
    with patch(
        "recommender.team_candidates.independently_strong_category_a",
        return_value=True,
    ):
        assert should_try_masked_core(candidate, [candidate], state, locked) is True


def test_engine_returns_none_when_fill_empty():
    draft = [
        _locked(
            "Charizard-Mega-Y",
            role="sun_setter",
            ability="Drought",
            item="Charizardite Y",
            moves=["Heat Wave", "Protect", "Weather Ball", "Solar Beam"],
        ),
        *[empty_slot() for _ in range(5)],
    ]
    state = _state(draft)
    locked = collect_locked_anchor_contexts(state)
    candidate = _candidate("Swampert-Mega", conflicts=(_conflict(),))
    with patch("recommender.team_candidates._search_gap_fill", return_value=None):
        assert discover_masked_core_package(candidate, state, locked) is None


def test_engine_returns_package_for_rain_vs_sun():
    draft = [
        _locked("Archaludon", ability="Stamina", item="Assault Vest"),
        _locked(
            "Charizard-Mega-Y",
            role="sun_setter",
            ability="Drought",
            item="Charizardite Y",
            moves=["Heat Wave", "Protect", "Weather Ball", "Solar Beam"],
        ),
        *[empty_slot() for _ in range(4)],
    ]
    state = _state(draft)
    locked = collect_locked_anchor_contexts(state)
    candidate = _candidate(
        "Swampert-Mega",
        conflicts=(
            CoreSlotConflict("weather", 1, "Charizard-Mega-Y", "Sun"),
            CoreSlotConflict("mega", 1, "Charizard-Mega-Y", "charizard"),
        ),
    )
    fill = _fill("Pelipper")
    with patch("recommender.team_candidates._search_gap_fill", return_value=fill):
        package = discover_masked_core_package(candidate, state, locked)
    assert package is not None
    assert package.masked_slot_indices == (1,)
    assert package.fill.species == "Pelipper"
    assert package.label == "Weather core — Swampert-Mega, Charizard-Mega-Y benched"


def test_package_label_includes_candidate_and_benched():
    draft = _four_locked_draft()
    locked = collect_locked_anchor_contexts(_state(draft))
    weather = _candidate("Kingdra", conflicts=(_conflict(slot=3),))
    mega = _candidate(
        "Blastoise-Mega",
        conflicts=(
            CoreSlotConflict("mega", 3, "Charizard-Mega-Y", "charizard"),
        ),
    )
    both = _candidate(
        "Swampert-Mega",
        conflicts=(
            CoreSlotConflict("weather", 3, "Charizard-Mega-Y", "Sun"),
            CoreSlotConflict("mega", 3, "Charizard-Mega-Y", "charizard"),
        ),
    )
    mask = frozenset({3})
    assert _package_label(weather, locked, mask) == (
        "Weather core — Kingdra, Charizard-Mega-Y benched"
    )
    assert _package_label(mega, locked, mask) == (
        "Mega core — Blastoise-Mega, Charizard-Mega-Y benched"
    )
    assert _package_label(both, locked, mask) == (
        "Weather core — Swampert-Mega, Charizard-Mega-Y benched"
    )


def test_gather_dedup_collapses_identical_packages():
    draft = _four_locked_draft()
    state = _state(draft)
    locked = collect_locked_anchor_contexts(state)
    conflict = _conflict(slot=3)
    swampert = _candidate("Swampert-Mega", conflicts=(conflict,))
    kingdra = _candidate("Kingdra", conflicts=(conflict,))
    fill = _fill("Pelipper")
    shared = MaskedCorePackage(
        swampert,
        (3,),
        fill,
        "Weather core — Swampert-Mega, Charizard-Mega-Y benched",
    )
    with (
        patch(
            "recommender.team_candidates.should_try_masked_core",
            return_value=True,
        ),
        patch(
            "recommender.team_candidates.discover_masked_core_package",
            return_value=shared,
        ),
    ):
        packages = gather_masked_core_packages([swampert, kingdra], state, locked)
    assert len(packages) == 1
    assert packages[0] is shared


def test_last_open_slot_skips_masked_core():
    draft = [
        _locked("Archaludon"),
        _locked("Incineroar"),
        _locked("Amoonguss"),
        _locked("Grimmsnarl"),
        _locked("Charizard-Mega-Y", ability="Drought", item="Charizardite Y"),
        empty_slot(),
    ]
    state = _state(draft)
    assert remaining_open_after_place(state) == 0
    candidate = _candidate(
        "Swampert-Mega",
        conflicts=(CoreSlotConflict("weather", 4, "Charizard-Mega-Y", "Sun"),),
    )
    locked = collect_locked_anchor_contexts(state)
    assert should_try_masked_core(candidate, [candidate], state, locked) is False
    assert discover_masked_core_package(candidate, state, locked) is None


def test_mechanical_only_fill_fails_dual_signal():
    draft = [
        _locked("Charizard-Mega-Y", ability="Drought", item="Charizardite Y"),
        *[empty_slot() for _ in range(5)],
    ]
    state = _state(draft)
    locked = collect_locked_anchor_contexts(state)
    candidate = _candidate(
        "Mawile-Mega",
        usage=False,
        conflicts=(CoreSlotConflict("mega", 0, "Charizard-Mega-Y", "charizard"),),
    )
    assert should_try_masked_core(candidate, [candidate], state, locked) is False


def test_two_candidates_same_mask_are_two_packages():
    draft = _four_locked_draft()
    state = _state(draft)
    locked = collect_locked_anchor_contexts(state)
    conflict = _conflict(slot=3)
    swampert = _candidate("Swampert-Mega", conflicts=(conflict,))
    kingdra = _candidate("Kingdra", conflicts=(conflict,))
    fill = _fill("Pelipper")
    with (
        patch(
            "recommender.team_candidates.independently_strong_category_a",
            return_value=True,
        ),
        patch(
            "recommender.team_candidates.discover_masked_core_package",
            side_effect=[
                MaskedCorePackage(
                    swampert,
                    (3,),
                    fill,
                    "Weather core — Swampert-Mega, Charizard-Mega-Y benched",
                ),
                MaskedCorePackage(
                    kingdra,
                    (3,),
                    fill,
                    "Weather core — Kingdra, Charizard-Mega-Y benched",
                ),
            ],
        ),
    ):
        packages = gather_masked_core_packages([swampert, kingdra], state, locked)
    assert len(packages) == 2
    assert {p.candidate.species for p in packages} == {"Swampert-Mega", "Kingdra"}
    assert packages[0].masked_slot_indices == packages[1].masked_slot_indices == (3,)


def test_weather_and_mega_same_slot_is_one_mask():
    conflicts = (
        CoreSlotConflict("weather", 0, "Charizard-Mega-Y", "Sun"),
        CoreSlotConflict("mega", 0, "Charizard-Mega-Y", "charizard"),
    )
    candidate = _candidate("Swampert-Mega", conflicts=conflicts)
    assert {c.locked_slot_index for c in candidate.core_slot_conflicts} == {0}


def _resolution_pending():
    return {
        "schema_version": 2,
        "kind": "core_resolution",
        "slot_index": 2,
        "resolution_options": [
            {"id": "keep_core", "label": "Keep current core"},
            {
                "id": "package_0",
                "label": "Weather core — Swampert-Mega, Charizard-Mega-Y benched",
                "masked_slot_indices": (0,),
                "option": {
                    "species": "Swampert-Mega",
                    "source": "threat",
                    "evidence": (),
                    "track": "Weather core — Swampert-Mega, Charizard-Mega-Y benched",
                },
            },
        ],
    }


def test_core_resolution_keep_core_is_continue():
    result = classify_pending("1", _resolution_pending())
    assert result["turn_intent"] == "continue"
    assert "masked_slot_indices" not in result


def test_core_resolution_take_package_selects_candidate():
    result = classify_pending("2", _resolution_pending())
    assert result["turn_intent"] == "slot_candidate_selected"
    assert result["selected_option"]["species"] == "Swampert-Mega"
    assert result["masked_slot_indices"] == (0,)
    assert result["team_completion_preference"] is None


def test_core_resolution_present_text_lists_options():
    text = format_turn({"pending_presentation": _resolution_pending()})
    assert "Keep current core" in text
    assert "Weather core — Swampert-Mega, Charizard-Mega-Y benched" in text
    assert "defer" in text.lower()


def test_initialize_defaults_masked_slot_indices():
    out = initialize({"format_id": "[Gen 9 Champions] VGC 2026 Reg M-B"})
    assert out.get("masked_slot_indices") == ()


def test_masked_members_still_count_for_mega():
    draft = [
        _locked("Charizard-Mega-Y", ability="Drought", item="Charizardite Y"),
        *[empty_slot() for _ in range(5)],
    ]
    state = _state(draft, masked_slot_indices=(0,))
    notices = mega_ceiling_notices(state)
    assert notices


def test_team_field_states_exclude_slots_drops_masked_weather():
    draft = [
        _locked(
            "Charizard-Mega-Y",
            ability="Drought",
            item="Charizardite Y",
            moves=["Heat Wave", "Protect", "Weather Ball", "Solar Beam"],
        ),
        *[empty_slot() for _ in range(5)],
    ]
    locked = collect_locked_anchor_contexts(_state(draft))
    assert provided_conditions(locked)
    masked = provided_conditions(locked, exclude_slots=frozenset({0}))
    assert "Sun" not in masked
    fields = team_field_states(locked, exclude_slots=frozenset({0}))
    assert not any(f.get("weather") == "Sun" for f in fields)


def test_preference_cleared_on_take_package():
    result = classify_pending(
        "Weather core — Swampert-Mega, Charizard-Mega-Y benched",
        _resolution_pending(),
    )
    assert result.get("team_completion_preference") is None
    assert result["turn_intent"] == "slot_candidate_selected"


def test_detect_core_resource_conflicts_helper():
    draft = _four_locked_draft()
    contexts = collect_locked_anchor_contexts(_state(draft))
    assert detect_core_resource_conflicts(contexts[:3], 4) is False
    assert detect_core_resource_conflicts(contexts, 4) is True
    assert detect_core_resource_conflicts(contexts, None) is False


def test_annotate_splits_conflicts_on_sequential_bench_slot():
    state = _state(_sun_core_sequential_draft())
    pipe = _run_sequential_annotation_pipeline(state)
    conflicted = next(
        (
            c
            for c in pipe["candidates"]
            if c.core_slot_conflicts and not c.wastes_core_slot
        ),
        None,
    )
    assert conflicted is not None, "expected a non-wasting candidate with core_slot_conflicts"
    assert len(conflicted.core_slot_conflicts) > 0


def test_should_try_true_sequential_four_lock_conflict_candidate():
    state = _state(_sun_core_sequential_draft())
    pipe = _run_sequential_annotation_pipeline(state)
    pool = pipe["candidates"]
    contexts = pipe["contexts"]
    trigger = next(
        (
            c
            for c in pool
            if c.core_slot_conflicts
            and should_try_masked_core(c, pool, state, contexts)
        ),
        None,
    )
    assert trigger is not None, "expected a core-conflict candidate that triggers masked-core"
    assert trigger.wastes_core_slot is False


@pytestmark_live
def test_discover_multi_locked_core_resolution_sequential_sun_core():
    state = _state(
        _sun_core_sequential_draft(),
        team_completion_preference="balanced",
    )
    result = discover_multi_locked(state, {"configurable": {"thread_id": "masked-e2e"}})
    pending = result.get("pending_presentation") or {}
    assert pending.get("kind") == "core_resolution"
    options = [
        o
        for o in pending.get("resolution_options") or []
        if o.get("id") != "keep_core"
    ]
    assert options
    assert any(o.get("masked_slot_indices") for o in options)


@pytestmark_live
def test_gather_unique_labels_swampert_locked_core():
    draft = [
        _locked_from_species("Archaludon", role="bulky_special_attacker"),
        _locked_from_species("Incineroar", role="support"),
        _locked_from_species("Amoonguss", role="support"),
        _locked_from_species("Swampert-Mega", role="bulky_attacker"),
        empty_slot(),
        empty_slot(),
    ]
    state = _state(draft)
    pipe = _run_sequential_annotation_pipeline(state)
    packages = gather_masked_core_packages(
        pipe["candidates"], state, pipe["contexts"], objective=pipe["objective"]
    )
    assert len(packages) >= 2
    labels = [package.label for package in packages]
    assert len(set(labels)) == len(labels)
    for package in packages:
        assert package.candidate.species in package.label
        assert "Swampert-Mega" in package.label


def test_three_locked_core_slot_stays_demote_only():
    draft = [
        _locked_from_species("Charizard-Mega-Y", role="sun_setter"),
        _locked_from_species("Archaludon", role="bulky_special_attacker"),
        _locked_from_species("Incineroar", role="support"),
        empty_slot(),
        empty_slot(),
        empty_slot(),
    ]
    state = _state(draft)
    pipe = _run_sequential_annotation_pipeline(state)
    wasteful = next((c for c in pipe["candidates"] if c.wastes_core_slot), None)
    assert wasteful is not None
    assert wasteful.core_slot_conflicts == ()
    assert should_try_masked_core(wasteful, pipe["candidates"], state, pipe["contexts"]) is False


def test_bench_subset_and_conflicts_coexist_at_slot_five():
    state = _state(_sun_core_sequential_draft())
    pipe = _run_sequential_annotation_pipeline(state)
    from recommender.team_candidates import candidate_has_unmet_needed_weather_dependency
    from recommender.anchor_roles import classify_anchor_role

    target = None
    for c in pipe["candidates"]:
        if not c.core_slot_conflicts:
            continue
        build = resolve_anchor_build(c.species, regulation=REG)
        decision = classify_anchor_role(build)
        if candidate_has_unmet_needed_weather_dependency(decision, pipe["contexts"]):
            continue
        target = c
        break
    assert target is not None

    with patch(
        "recommender.coverage.candidate_improves_best_bring",
        return_value=True,
    ):
        annotated = annotate_composition_impact(
            [target],
            state,
            locked_anchors=pipe["contexts"],
            condition_resilience=pipe["resilience"],
            objective=pipe["objective"],
        )
    row = annotated[0]
    assert row.core_slot_conflicts
    assert row.improves_bench_subset is True
