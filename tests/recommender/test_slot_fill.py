"""ADR-023 slot-fill orchestrator: annotate, present, lock, hand-off."""

from __future__ import annotations

from unittest.mock import patch

from recommender.ids import to_id
from recommender.propose import fill_team_draft
from recommender.slot_fill import (
    SlotFillContext,
    SlotFillResponse,
    _FO_PROTECTION_ABILITIES,
    _field_label_matches,
    annotate_overlap,
    merge_need_resolved,
    present_candidates,
    resolve_all_support_needs,
    resolve_need_candidates,
    run_slot_fill_terminal,
)
from recommender.state import (
    Attr,
    RecommenderState,
    Slot,
    ThreatCandidate,
    ThreatCounterCandidate,
    empty_slot,
)
from recommender.support_needs import RoleShapeContext, SupportNeed


def _tc(species: str, *, usage_rank: int | None = 10, verified_score: float = 1.0) -> ThreatCounterCandidate:
    cand = ThreatCandidate(
        ladder_species=species,
        usage_rank=usage_rank,
        form=species,
        showdown_usage_pct=None,
        showdown_formes=(),
        spec={"species": species},
        build_source="ingame",
    )
    return ThreatCounterCandidate(
        candidate=cand,
        threats_countered=("t1",),
        threats_countered_count=1,
        verified_score=verified_score,
        verified_vs=(),
    )


def _trick_room_need() -> SupportNeed:
    return SupportNeed(
        category="trick_room",
        name="Trick Room",
        description="Needs Trick Room.",
        trigger="speed_tier:low_no_priority",
        stance="need",
    )


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
    }
    state.update(overrides)  # type: ignore[typeddict-item]
    return state


def test_farigiraf_multi_branch_annotates_and_is_default():
    """Kingambit-shaped need + Farigiraf in threat counters → default."""
    need = _trick_room_need()
    # Incineroar does not learn Trick Room — single-branch peer with higher verified_score.
    ctx = SlotFillContext(
        anchor={"species": "Kingambit"},
        role_shape_context=RoleShapeContext(match_status="partial", primary_function="offense"),
        threat_counter_results=[
            _tc("Incineroar", usage_rank=1, verified_score=5.0),
            _tc("Farigiraf", usage_rank=20, verified_score=1.0),
        ],
        support_needs=[need],
    )
    rows = annotate_overlap(ctx)
    by_name = {r.species: r for r in rows}
    assert any(n.category == "trick_room" for n in by_name["Farigiraf"].matching_needs)
    assert by_name["Farigiraf"].source == "both"
    assert by_name["Incineroar"].matching_needs == ()
    assert by_name["Incineroar"].source == "threat"

    presentation = present_candidates(ctx, slot_index=1)
    assert presentation.default == "Farigiraf"
    assert "Incineroar" in presentation.alternatives or "Incineroar" in presentation.options


def test_single_branch_no_false_positive_overlap():
    need = _trick_room_need()
    ctx = SlotFillContext(
        anchor={"species": "Kingambit"},
        role_shape_context=RoleShapeContext(match_status="partial"),
        threat_counter_results=[_tc("Incineroar", usage_rank=1, verified_score=5.0)],
        support_needs=[need],
    )
    rows = annotate_overlap(ctx)
    assert len(rows) == 1
    assert rows[0].matching_needs == ()
    assert rows[0].source == "threat"
    presentation = present_candidates(ctx, slot_index=0)
    assert presentation.default == "Incineroar"


def test_merge_need_resolved_surfaces_need_only_species():
    need = _trick_room_need()
    ctx = SlotFillContext(
        anchor={"species": "Kingambit"},
        role_shape_context=RoleShapeContext(match_status="partial"),
        threat_counter_results=[_tc("Incineroar")],
        support_needs=[need],
        chosen_need=need,
        need_resolved_candidates=["Farigiraf", "Incineroar"],
    )
    rows = merge_need_resolved(ctx)
    by_name = {r.species: r for r in rows}
    assert by_name["Farigiraf"].source == "need"
    assert by_name["Farigiraf"].threat_row is None
    assert any(n.category == "trick_room" for n in by_name["Farigiraf"].matching_needs)
    assert by_name["Incineroar"].source == "both"


def test_resolve_need_stub_categories():
    need = SupportNeed(
        category="defensive_coverage",
        name="Defensive coverage",
        description="x",
        trigger="asymmetry",
    )
    try:
        resolve_need_candidates(need, _base_state())
        assert False, "expected NotImplementedError"
    except NotImplementedError as e:
        assert "deferred" in str(e)


def test_terminal_e2e_lock_then_refinement_handoff():
    need = _trick_room_need()
    ctx = SlotFillContext(
        anchor={"species": "Kingambit"},
        role_shape_context=RoleShapeContext(match_status="partial"),
        threat_counter_results=[
            _tc("Farigiraf", usage_rank=5, verified_score=2.0),
            _tc("Incineroar", usage_rank=1, verified_score=1.0),
        ],
        support_needs=[need],
    )
    annotate_overlap(ctx)
    state = _base_state(
        team_draft=[
            empty_slot(),
            empty_slot(),
            *[empty_slot() for _ in range(4)],
        ]
    )
    # Pre-fill a role elsewhere so fill doesn't only invent roles.
    state["team_draft"][0] = Slot(role=Attr(value="bulky_attacker"))

    result = run_slot_fill_terminal(
        ctx,
        state,
        slot_index=1,
        response=SlotFillResponse(action="accept_default"),
    )
    assert not result.deferred
    assert result.presentation.default == "Farigiraf"
    assert "team_draft" in result.state_updates

    merged = {**state, **result.state_updates}
    assert merged["team_draft"][1].species.value == "Farigiraf"
    assert merged["team_draft"][1].species.locked is True

    moves = ["Protect", "Psychic", "Thunderbolt", "Trick Room"]
    item = "Sitrus Berry"
    spread = {"hp": 32, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 2}
    with (
        patch(
            "recommender.propose.featured_or_common_set",
            return_value={"species": "Farigiraf", "moves": moves, "item": item},
        ),
        patch(
            "recommender.propose.get_resolved_build",
            return_value={
                "spread": spread,
                "source_tier": "champions-native",
                "verified": True,
            },
        ),
    ):
        refined = fill_team_draft(merged)  # type: ignore[arg-type]

    slot = refined["team_draft"][1]
    assert slot.moveset.value == moves
    assert slot.item.value == item
    assert slot.spread.value == spread
    assert slot.moveset.locked is False


def test_deferral_discardable_reenterable():
    need = _trick_room_need()
    ctx = SlotFillContext(
        anchor={"species": "Kingambit"},
        role_shape_context=RoleShapeContext(match_status="partial"),
        threat_counter_results=[_tc("Farigiraf")],
        support_needs=[need],
    )
    annotate_overlap(ctx)
    state = _base_state()
    before = [s.species.value for s in state["team_draft"]]

    result = run_slot_fill_terminal(
        ctx,
        state,
        slot_index=0,
        response=SlotFillResponse(action="defer"),
    )
    assert result.deferred is True
    assert result.state_updates == {}
    assert [s.species.value for s in state["team_draft"]] == before

    # Re-enter: fresh context is fine.
    ctx2 = SlotFillContext(
        anchor={"species": "Kingambit"},
        role_shape_context=RoleShapeContext(match_status="partial"),
        threat_counter_results=[_tc("Farigiraf")],
        support_needs=[need],
    )
    annotate_overlap(ctx2)
    assert ctx2.annotated_candidates is not None


def test_accept_with_empty_pool_raises():
    ctx = SlotFillContext(
        anchor={"species": "Kingambit"},
        role_shape_context=RoleShapeContext(match_status="partial"),
        threat_counter_results=[],
        support_needs=[_trick_room_need()],
    )
    annotate_overlap(ctx)
    try:
        run_slot_fill_terminal(
            ctx,
            _base_state(),
            slot_index=0,
            response=SlotFillResponse(action="accept_default"),
        )
        assert False, "expected ValueError"
    except ValueError as e:
        assert "no species" in str(e)


def test_contrary_need_does_not_match_intimidate():
    need = SupportNeed(
        category="stat_lowering_partner",
        name="Stat-lowering partner",
        description="Contrary kit gap",
        trigger="ability:contrary",
    )
    ctx = SlotFillContext(
        anchor={"species": "Staraptor-Mega"},
        role_shape_context=RoleShapeContext(match_status="partial"),
        threat_counter_results=[_tc("Incineroar")],
        support_needs=[need],
    )
    rows = annotate_overlap(ctx)
    assert rows[0].matching_needs == ()
    assert rows[0].source == "threat"
    assert resolve_need_candidates(need, _base_state()) == []


def test_fake_out_need_matches_armor_tail_ability():
    assert _FO_PROTECTION_ABILITIES == frozenset(
        {"armortail", "queenlymajesty", "dazzling"}
    )
    need = SupportNeed(
        category="fake_out_protection",
        name="Fake Out protection",
        description="wants FO protection",
        trigger="glass_offense:fake_out",
    )
    ctx = SlotFillContext(
        anchor={"species": "Garchomp"},
        role_shape_context=RoleShapeContext(match_status="partial"),
        threat_counter_results=[_tc("Farigiraf"), _tc("Incineroar")],
        support_needs=[need],
    )
    rows = annotate_overlap(ctx)
    by_name = {r.species: r for r in rows}
    assert any(n.category == "fake_out_protection" for n in by_name["Farigiraf"].matching_needs)
    assert by_name["Farigiraf"].source == "both"


def test_field_label_matches_primal_weather():
    assert _field_label_matches("desolateland", "sun")
    assert _field_label_matches("primordialsea", "rain")
    assert _field_label_matches("deltastream", "strongwinds")
    assert not _field_label_matches("deltastream", "sun")
    assert not _field_label_matches("desolateland", "rain")


def test_resolve_condition_setter_rain():
    need = SupportNeed(
        category="condition_setter",
        name="Rain setter",
        description="Needs Rain",
        trigger="field_condition:any:rain",
        notes="Requires Rain",
    )
    names = resolve_need_candidates(need, _base_state())
    assert names
    assert any(to_id(n) == "pelipper" for n in names) or "Pelipper" in names


def test_resolve_condition_setter_multi_weather():
    need = SupportNeed(
        category="condition_setter",
        name="Weather setter",
        description="Needs any weather",
        trigger="field_condition:any:rain|sun|snow",
        notes="Requires any of Rain/Sun/Snow",
    )
    names = resolve_need_candidates(need, _base_state())
    assert names
    ids = {to_id(n) for n in names}
    # At least one setter for Rain, Sun, or Snow from ABILITY_TO_FIELD.
    assert ids & {"pelipper", "torkoal", "tyranitar", "abomasnow", "ninetales", "hippowdon"}


def test_resolve_healing_cleric_union_nonempty():
    need = SupportNeed(
        category="healing_cleric",
        name="Healing",
        description="wants healing",
        trigger=None,
    )
    names = resolve_need_candidates(need, _base_state())
    assert names


def test_resolve_all_and_merge_without_chosen_need():
    tr = _trick_room_need()
    fo = SupportNeed(
        category="fake_out_protection",
        name="Fake Out protection",
        description="wants FO",
        trigger="glass_offense:fake_out",
    )
    ctx = SlotFillContext(
        anchor={"species": "Garchomp"},
        role_shape_context=RoleShapeContext(match_status="partial"),
        threat_counter_results=[_tc("Incineroar")],
        support_needs=[tr, fo],
        chosen_need=None,
    )
    resolved = resolve_all_support_needs(ctx, _base_state())
    assert resolved
    assert ctx.need_resolved_candidates is not None
    rows = merge_need_resolved(ctx)
    assert any(r.source in ("need", "both") for r in rows)

