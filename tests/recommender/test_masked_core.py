"""Masked alternate-core discovery."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from recommender.condition_resilience import provided_conditions, team_field_states
from recommender.nodes import classify_pending, initialize
from recommender.present_text import format_turn
from recommender.slot_fill import AnnotatedCandidate, CoreSlotConflict
from recommender.state import Attr, CandidateEvidence, Slot, empty_slot
from recommender.team_candidates import (
    MaskedCorePackage,
    collect_locked_anchor_contexts,
    discover_masked_core_package,
    gather_masked_core_packages,
    mega_ceiling_notices,
    remaining_open_after_place,
    should_try_masked_core,
)
from recommender.teammate_types import TeammateEvidence, TeammateQueryResult
from recommender.teammates import pairwise_teammate_lift


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


def _conflict() -> CoreSlotConflict:
    return CoreSlotConflict(
        kind="weather",
        locked_slot_index=0,
        locked_species="Charizard-Mega-Y",
        resource="Sun",
    )


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
    assert "benched" in package.label


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
    draft = [
        _locked("Charizard-Mega-Y", ability="Drought", item="Charizardite Y"),
        *[empty_slot() for _ in range(5)],
    ]
    state = _state(draft)
    locked = collect_locked_anchor_contexts(state)
    conflict = _conflict()
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
                    swampert, (0,), fill, "Weather core — Charizard-Mega-Y benched"
                ),
                MaskedCorePackage(
                    kingdra, (0,), fill, "Weather core — Charizard-Mega-Y benched"
                ),
            ],
        ),
    ):
        packages = gather_masked_core_packages([swampert, kingdra], state, locked)
    assert len(packages) == 2
    assert {p.candidate.species for p in packages} == {"Swampert-Mega", "Kingdra"}
    assert packages[0].masked_slot_indices == packages[1].masked_slot_indices


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
                "label": "Weather core — Charizard-Mega-Y benched",
                "masked_slot_indices": (0,),
                "option": {
                    "species": "Swampert-Mega",
                    "source": "threat",
                    "evidence": (),
                    "track": "Weather core — Charizard-Mega-Y benched",
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
    assert "Weather core — Charizard-Mega-Y benched" in text
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
        "Weather core — Charizard-Mega-Y benched", _resolution_pending()
    )
    assert result.get("team_completion_preference") is None
    assert result["turn_intent"] == "slot_candidate_selected"
