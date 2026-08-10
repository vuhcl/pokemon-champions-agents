"""ADR-023 slot-fill orchestrator: annotate, present, select, refine."""

from __future__ import annotations

from typing import Literal, get_args
from unittest.mock import patch

import pytest

from recommender.anchor_roles import classify_anchor_role, resolve_anchor_build
from recommender.ids import to_id
from recommender.move_narrowing import CandidateMeta, NarrowResult
from recommender.nodes import commit_full_slot
from recommender.role_compendium import (
    CompendiumRoleEvidence,
    ReverseCompendiumEvidence,
)
from recommender.slot_fill import (
    AnnotatedCandidate,
    NeedResolvedCandidate,
    REVIEWED_STRATEGIC_TARGET_ROLES,
    SlotFillContext,
    SlotFillResponse,
    _FO_PROTECTION_ABILITIES,
    _sort_annotated,
    _threat_evidence,
    _union_move_candidates,
    _field_label_matches,
    annotate_overlap,
    build_anchored_slot_fill_context,
    build_provisional_slot,
    derive_target_role,
    merge_need_resolved,
    present_candidates,
    resolve_all_support_needs,
    resolve_need_candidates,
    run_slot_fill_terminal,
    target_role_from_strategic_evidence,
)
from recommender.state import (
    Attr,
    CandidateEvidence,
    PendingSlotIntent,
    ProvisionalSlot,
    RecommenderState,
    Slot,
    TargetRoleDecision,
    TargetRoleId,
    ThreatCandidate,
    ThreatCounterCandidate,
    UnresolvedSlotRefinement,
    UnresolvedTargetRoleDecision,
    all_locked,
    empty_slot,
    slot_fingerprint,
)
from recommender.support_needs import RoleShapeContext, SupportNeed


def _tc(
    species: str,
    *,
    usage_rank: int | None = 10,
    verified_score: float = 1.0,
    moves: tuple[str, ...] = (),
    ability: str | None = None,
) -> ThreatCounterCandidate:
    spec: dict = {"species": species}
    if moves:
        spec["moves"] = list(moves)
    if ability:
        spec["ability"] = ability
    cand = ThreatCandidate(
        ladder_species=species,
        usage_rank=usage_rank,
        form=species,
        showdown_usage_pct=None,
        showdown_formes=(),
        spec=spec,
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


def _shape(
    *, primary_function: Literal["offense", "support", "unknown"] = "unknown"
) -> RoleShapeContext:
    return RoleShapeContext(
        primary_function=primary_function,
        tankiness="unknown",
        requires_setup_turn=False,
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
        role_shape_context=_shape(primary_function="offense"),
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
        role_shape_context=_shape(),
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
    mechanical = CandidateEvidence(
        "mechanical_only", "low", "test", ("need:trick_room",)
    )
    ctx = SlotFillContext(
        anchor={"species": "Kingambit"},
        role_shape_context=_shape(),
        threat_counter_results=[_tc("Incineroar")],
        support_needs=[need],
        chosen_need=need,
        need_resolved_candidates=[
            NeedResolvedCandidate("Farigiraf", (need,), (mechanical,)),
            NeedResolvedCandidate("Incineroar", (need,), (mechanical,)),
        ],
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


def test_terminal_e2e_pending_intent_then_pure_refinement():
    need = _trick_room_need()
    ctx = SlotFillContext(
        anchor={"species": "Kingambit"},
        role_shape_context=_shape(),
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
    before = list(state["team_draft"])

    result = run_slot_fill_terminal(
        ctx,
        state,
        slot_index=1,
        response=SlotFillResponse(action="accept_default"),
    )
    assert not result.deferred
    assert result.presentation.default == "Farigiraf"
    assert result.state_updates["pending_presentation"] is None
    assert "team_draft" not in result.state_updates
    assert state["team_draft"] == before
    intent = result.state_updates["pending_slot_intent"]
    assert isinstance(intent, PendingSlotIntent)
    assert intent.species == "Farigiraf"
    assert intent.target_role_decision is not None
    assert intent.target_role_decision.role_id == "trick_room_setter"
    assert intent.evidence
    assert intent.evidence[0].basis == "usage_backed"

    moves = ["Protect", "Psychic", "Thunderbolt", "Trick Room"]
    item = "Sitrus Berry"
    spread = {"hp": 32, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 2}
    with (
        patch(
            "recommender.propose.featured_or_common_set",
            return_value={
                "species": "Farigiraf",
                "ability": "Armor Tail",
                "moves": moves,
                "item": item,
                "nature": "Modest",
            },
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
        provisional = build_provisional_slot(intent, state)

    assert isinstance(provisional, ProvisionalSlot)
    assert provisional.schema_version == 1
    assert provisional.target_role_decision.role_id == "trick_room_setter"
    assert provisional.species == "Farigiraf"
    assert provisional.ability == "Armor Tail"
    assert provisional.moves == tuple(moves)
    assert provisional.item == item
    assert provisional.nature == "Modest"
    assert provisional.spread_dict() == spread
    assert intent.evidence[0].basis == "usage_backed"
    assert state["team_draft"] == before


def test_deferral_discardable_reenterable():
    need = _trick_room_need()
    ctx = SlotFillContext(
        anchor={"species": "Kingambit"},
        role_shape_context=_shape(),
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
    assert result.state_updates == {
        "pending_presentation": None,
        "pending_slot_intent": None,
        "provisional_slot": None,
    }
    assert [s.species.value for s in state["team_draft"]] == before

    # Re-enter: fresh context is fine.
    ctx2 = SlotFillContext(
        anchor={"species": "Kingambit"},
        role_shape_context=_shape(),
        threat_counter_results=[_tc("Farigiraf")],
        support_needs=[need],
    )
    annotate_overlap(ctx2)
    assert ctx2.annotated_candidates is not None


def test_present_only_persists_ordered_options_with_sources():
    need = _trick_room_need()
    ctx = SlotFillContext(
        anchor={"species": "Kingambit"},
        role_shape_context=_shape(),
        threat_counter_results=[
            _tc("Incineroar", usage_rank=1, verified_score=5.0),
            _tc("Farigiraf", usage_rank=20, verified_score=1.0),
        ],
        support_needs=[need],
    )
    annotate_overlap(ctx)

    result = run_slot_fill_terminal(ctx, _base_state(), slot_index=2)

    assert result.presentation.options == ("Farigiraf", "Incineroar")
    pending = result.state_updates["pending_presentation"]
    assert pending["schema_version"] == 1
    assert pending["kind"] == "candidate_selection"
    assert pending["slot_index"] == 2
    assert pending["options"][0]["species"] == "Farigiraf"
    assert pending["options"][0]["source"] == "both"
    assert pending["options"][0]["target_role_decision"] == ctx.target_role_decision
    assert pending["options"][0]["evidence"][0].basis == "usage_backed"
    assert pending["options"][1]["species"] == "Incineroar"
    assert pending["options"][1]["source"] == "threat"


def test_threat_only_choice_does_not_inherit_target_role():
    ctx = SlotFillContext(
        anchor={"species": "Kingambit"},
        role_shape_context=_shape(),
        threat_counter_results=[_tc("Farigiraf"), _tc("Incineroar")],
        support_needs=[_trick_room_need()],
    )
    annotate_overlap(ctx)

    result = run_slot_fill_terminal(
        ctx,
        _base_state(),
        slot_index=2,
        response=SlotFillResponse(action="choose", species="Incineroar"),
    )

    intent = result.state_updates["pending_slot_intent"]
    assert isinstance(intent, PendingSlotIntent)
    assert intent.target_role_decision is None
    unresolved = build_provisional_slot(intent, _base_state())
    assert isinstance(unresolved, UnresolvedSlotRefinement)
    assert unresolved.reason == "unresolved_target_role"


def test_ambiguous_speed_control_is_structured_and_unresolved():
    tailwind = SupportNeed(
        category="tailwind",
        name="Tailwind",
        description="Wants Tailwind.",
        trigger="speed_tier:middling",
        stance="want",
    )
    ctx = SlotFillContext(
        anchor={"species": "Kingambit"},
        role_shape_context=_shape(),
        support_needs=[_trick_room_need(), tailwind],
    )

    decision = derive_target_role(ctx)

    assert isinstance(decision, UnresolvedTargetRoleDecision)
    assert decision.ambiguity == ("trick_room_setter", "tailwind_setter")
    assert decision.needed_constraints == ("move:trickroom",)
    assert decision.wanted_constraints == ("move:tailwind",)


_LEGACY_TARGET_ROLES = {
    "fast_attacker",
    "bulky_attacker",
    "bulky_pivot",
    "fast_pivot",
    "trick_room_sweeper",
    "trick_room_setter",
    "tailwind_setter",
}
_NEW_TARGET_ROLES = {
    "rain_setter",
    "sun_setter",
    "sand_setter",
    "snow_setter",
    "redirection",
    "swords_dance_attacker",
    "nasty_plot_attacker",
}


def _strategic_decision(species: str, role_id: str) -> TargetRoleDecision | None:
    anchor = classify_anchor_role(resolve_anchor_build(species))
    return target_role_from_strategic_evidence(
        role_id,
        anchor_role=anchor,
        compendium=anchor.compendium,
    )


def test_reviewed_strategic_roles_cover_shipped_compendium_and_preserve_legacy():
    vocabulary = set(get_args(TargetRoleId))

    assert vocabulary == _LEGACY_TARGET_ROLES | _NEW_TARGET_ROLES
    assert set(REVIEWED_STRATEGIC_TARGET_ROLES.values()) == _NEW_TARGET_ROLES | {
        "trick_room_setter"
    }
    assert set(REVIEWED_STRATEGIC_TARGET_ROLES.values()) <= vocabulary


@pytest.mark.parametrize(
    "role_id", tuple(REVIEWED_STRATEGIC_TARGET_ROLES.values())
)
def test_every_reviewed_compendium_role_produces_target_intent(role_id):
    exact = CompendiumRoleEvidence(
        species="Verified Member",
        role_id=role_id,
        category=role_id,
        condition="",
        tier="Good",
        mechanism="Verified Mechanism",
        source_file=f"{role_id}.v1.json",
    )

    decision = target_role_from_strategic_evidence(
        role_id,
        compendium=ReverseCompendiumEvidence(exact=(exact,)),
    )

    assert decision is not None
    assert decision.role_id == role_id
    assert decision.needed_constraints == (f"role:{role_id}",)
    assert decision.provenance == (f"role_compendium:{role_id}.v1.json",)


def test_strategic_role_requires_exact_compendium_or_active_mechanism():
    garchomp = classify_anchor_role(resolve_anchor_build("Garchomp"))
    assert {row.role_id for row in garchomp.compendium.species} >= {
        "swords_dance_attacker"
    }
    assert (
        target_role_from_strategic_evidence(
            "swords_dance_attacker",
            anchor_role=garchomp,
            compendium=garchomp.compendium,
        )
        is None
    )

    gholdengo = classify_anchor_role(resolve_anchor_build("Gholdengo"))
    assert {row.role_id for row in gholdengo.compendium.rejected} >= {
        "nasty_plot_attacker"
    }
    assert (
        target_role_from_strategic_evidence(
            "nasty_plot_attacker", compendium=gholdengo.compendium
        )
        is None
    )
    decision = target_role_from_strategic_evidence(
        "nasty_plot_attacker",
        anchor_role=gholdengo,
        compendium=gholdengo.compendium,
    )
    assert decision is not None
    assert decision.role_id == "nasty_plot_attacker"
    assert decision.needed_constraints == ("role:nasty_plot_attacker",)
    assert decision.confidence == "high"
    assert decision.producer_name == "target_role_from_strategic_evidence"
    assert any(row == "mechanism:nastyplot" for row in decision.evidence)

    assert target_role_from_strategic_evidence("weather_setter") is None
    assert target_role_from_strategic_evidence("unknown_role") is None


def test_strategic_role_preserves_both_matching_exact_sources():
    pelipper = classify_anchor_role(resolve_anchor_build("Pelipper"))
    decision = target_role_from_strategic_evidence(
        "rain_setter",
        anchor_role=pelipper,
        compendium=pelipper.compendium,
    )

    assert decision is not None
    assert decision.role_id == "rain_setter"
    assert any(row == "mechanism:drizzle" for row in decision.evidence)
    assert any(row.startswith("compendium:") for row in decision.evidence)
    assert any(row.startswith("anchor_role:") for row in decision.provenance)
    assert "role_compendium:weather_setter_rain.v1.json" in decision.provenance


def _assert_real_strategic_role_refines(species: str, role_id: str) -> None:
    decision = _strategic_decision(species, role_id)
    assert decision is not None
    state = _base_state()
    intent = PendingSlotIntent(
        schema_version=1,
        slot_index=0,
        species=species,
        target_role_decision=decision,
        source="need",
        base_slot_fingerprint=slot_fingerprint(state["team_draft"][0]),
    )

    provisional = build_provisional_slot(intent, state)

    assert isinstance(provisional, ProvisionalSlot)
    assert provisional.target_role_decision.role_id == role_id
    assert provisional.species == species
    assert provisional.ability
    assert provisional.item
    assert provisional.nature
    assert len(provisional.moves) == 4
    assert all(provisional.moves)
    assert set(provisional.spread_dict()) == {"hp", "atk", "def", "spa", "spd", "spe"}
    assert sum(provisional.spread_dict().values()) == 66


def test_real_sinistcha_redirection_refines_to_full_provisional_slot():
    _assert_real_strategic_role_refines("Sinistcha", "redirection")


def test_real_pelipper_rain_setter_refines_to_full_provisional_slot():
    _assert_real_strategic_role_refines("Pelipper", "rain_setter")


def test_real_tyranitar_sand_setter_refines_to_full_provisional_slot():
    _assert_real_strategic_role_refines("Tyranitar", "sand_setter")


def test_real_gholdengo_nasty_plot_refines_to_full_provisional_slot():
    _assert_real_strategic_role_refines("Gholdengo", "nasty_plot_attacker")


@pytest.mark.parametrize("role_id", get_args(TargetRoleId))
def test_every_target_role_round_trips_selection_refinement_and_commit(role_id):
    decision = TargetRoleDecision(role_id=role_id, source="other")
    ctx = SlotFillContext(
        anchor=None,
        role_shape_context=None,
        annotated_candidates=[
            AnnotatedCandidate(
                "Pelipper",
                (),
                "mixed",
                target_role_decision=decision,
                evidence=(
                    CandidateEvidence(
                        "mechanical_only", "high", "target_role_round_trip"
                    ),
                ),
            )
        ],
        candidates_pre_ranked=True,
    )
    state = _base_state()
    terminal = run_slot_fill_terminal(
        ctx,
        state,
        slot_index=0,
        response=SlotFillResponse(action="accept_default"),
    )
    intent = terminal.state_updates["pending_slot_intent"]
    assert isinstance(intent, PendingSlotIntent)
    assert intent.target_role_decision == decision

    provisional = build_provisional_slot(intent, state)
    assert isinstance(provisional, ProvisionalSlot)
    assert provisional.target_role_decision == decision

    committed = commit_full_slot(
        {
            **state,
            "pending_slot_intent": intent,
            "provisional_slot": provisional,
            "pending_presentation": {
                "schema_version": 1,
                "kind": "full_build_confirmation",
                "slot_index": 0,
                "provisional_fingerprint": provisional.fingerprint,
            },
        }
    )
    assert committed["slot_commit_error"] is None
    assert all_locked(committed["team_draft"][0])
    assert committed["team_draft"][0].role.value == role_id


def test_no_anchor_bypasses_anchor_queries():
    result = build_anchored_slot_fill_context(_base_state(), None)
    assert result.bypassed is True
    assert result.context is None


def test_clean_anchor_classification_still_runs_raw_support_analysis():
    anchor = Slot(
        role=Attr("bulky_rain_attacker", locked=True),
        species=Attr("Archaludon", locked=True),
        ability=Attr("Stamina", locked=True),
        item=Attr("Leftovers", locked=True),
        moveset=Attr(
            ["Electro Shot", "Flash Cannon", "Protect", "Dragon Pulse"], locked=True
        ),
        nature=Attr("Modest", locked=True),
        spread=Attr(
            {"hp": 32, "atk": 0, "def": 1, "spa": 5, "spd": 25, "spe": 3},
            locked=True,
        ),
    )
    result = build_anchored_slot_fill_context(
        _base_state(team_draft=[anchor, *[empty_slot() for _ in range(5)]]),
        anchor,
        user_anchor_role="bulky_rain_attacker",
        threat_counter_results=[],
    )
    assert result.anchor_role_decision.match_quality == "clean"
    assert result.context is not None
    assert result.context.support_needs
    assert not any(need.name == "Rain setter" for need in result.context.support_needs)


def _commit_state(*, ability: str = "Armor Tail", item: str = "Sitrus Berry", base: str | None = None):
    state = _base_state()
    decision = TargetRoleDecision(
        role_id="trick_room_setter",
        source="support_need",
        evidence=("trick_room",),
    )
    base_fingerprint = base or slot_fingerprint(state["team_draft"][0])
    intent = PendingSlotIntent(
        schema_version=1,
        slot_index=0,
        species="Farigiraf",
        target_role_decision=decision,
        source="need",
        base_slot_fingerprint=base_fingerprint,
    )
    provisional = ProvisionalSlot(
        schema_version=1,
        slot_index=0,
        target_role_decision=decision,
        species="Farigiraf",
        ability=ability,
        item=item,
        moves=("Psychic", "Hyper Voice", "Trick Room", "Protect"),
        nature="Modest",
        spread=(("hp", 32), ("atk", 0), ("def", 0), ("spa", 32), ("spd", 2), ("spe", 0)),
        base_slot_fingerprint=base_fingerprint,
        fingerprint="test-provisional",
    )
    return {
        **state,
        "pending_slot_intent": intent,
        "provisional_slot": provisional,
        "pending_presentation": {
            "schema_version": 1,
            "kind": "full_build_confirmation",
            "slot_index": 0,
            "provisional_fingerprint": provisional.fingerprint,
        },
    }


def test_atomic_commit_rejects_stale_slot_without_partial_update():
    state = _commit_state(base="stale")
    before = state["team_draft"]
    result = commit_full_slot(state)
    assert "team_draft" not in result
    assert state["team_draft"] == before
    assert "changed after candidate selection" in result["slot_commit_error"]


def test_atomic_commit_rejects_illegal_ability_without_partial_update():
    state = _commit_state(ability="Drizzle")
    before = state["team_draft"]
    result = commit_full_slot(state)
    assert "team_draft" not in result
    assert state["team_draft"] == before
    assert "ability:Drizzle" in result["slot_commit_error"]


def test_present_only_rejects_empty_presentation():
    ctx = SlotFillContext(
        anchor={"species": "Kingambit"},
        role_shape_context=_shape(),
        threat_counter_results=[],
        support_needs=[_trick_room_need()],
    )
    annotate_overlap(ctx)

    with pytest.raises(ValueError, match="no species"):
        run_slot_fill_terminal(ctx, _base_state(), slot_index=0)


def test_accept_with_empty_pool_raises():
    ctx = SlotFillContext(
        anchor={"species": "Kingambit"},
        role_shape_context=_shape(),
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
        role_shape_context=_shape(),
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
        role_shape_context=_shape(),
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
    assert any(to_id(row.species) == "pelipper" for row in names)


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
    ids = {to_id(row.species) for row in names}
    # At least one setter for Rain, Sun, or Snow from ABILITY_TO_FIELD.
    assert ids & {"pelipper", "torkoal", "tyranitar", "abomasnow", "ninetales", "hippowdon"}
    assert len(ids) == len(names)
    assert "role:rain_setter" in names[0].evidence[0].evidence


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
        role_shape_context=_shape(),
        threat_counter_results=[_tc("Incineroar")],
        support_needs=[tr, fo],
        chosen_need=None,
    )
    resolved = resolve_all_support_needs(ctx, _base_state())
    assert resolved
    assert ctx.need_resolved_candidates is not None
    rows = merge_need_resolved(ctx)
    assert any(r.source in ("need", "both") for r in rows)


def test_compendium_candidates_lead_stronger_raw_move_evidence():
    need = _trick_room_need()
    admitted = CompendiumRoleEvidence(
        species="Verified Setter",
        role_id="trick_room_setter",
        category="trick_room_setter",
        condition="",
        tier="Good",
        mechanism="Trick Room",
        source_file="trick_room_setter.v1.json",
    )
    raw = NarrowResult(
        candidates=["Raw Ace"],
        stopped_at=3,
        candidate_meta={
            "rawace": CandidateMeta("Raw Ace", "natural_speed", 99.0, 99.0)
        },
    )
    with (
        patch(
            "recommender.slot_fill.role_category_evidence",
            return_value=ReverseCompendiumEvidence(species=(admitted,)),
        ),
        patch("recommender.slot_fill.narrow_candidates_for_move", return_value=raw),
    ):
        rows = resolve_need_candidates(need, _base_state())

    assert [row.species for row in rows] == ["Verified Setter", "Raw Ace"]
    assert rows[0].evidence[0].basis == "compendium_backed"
    assert rows[1].evidence[0].basis == "usage_backed"


def test_species_popularity_alone_is_not_usage_backed_execution_evidence():
    need = _trick_room_need()
    raw = NarrowResult(
        candidates=["Popular Learner"],
        stopped_at=3,
        candidate_meta={
            "popularlearner": CandidateMeta(
                "Popular Learner", "natural_speed", None, 99.0
            )
        },
    )
    with (
        patch(
            "recommender.slot_fill.role_category_evidence",
            return_value=ReverseCompendiumEvidence(),
        ),
        patch("recommender.slot_fill.narrow_candidates_for_move", return_value=raw),
    ):
        rows = resolve_need_candidates(need, _base_state())

    assert rows[0].evidence[0].basis == "mechanical_only"


def test_full_role_rejection_is_not_reintroduced_by_raw_move_search():
    need = _trick_room_need()
    rejected = CompendiumRoleEvidence(
        species="Rejected Setter",
        role_id="trick_room_setter",
        category="trick_room_setter",
        condition="",
        tier=None,
        mechanism=None,
        source_file="trick_room_setter.v1.json",
        reason="failed verification",
    )
    with (
        patch(
            "recommender.slot_fill.role_category_evidence",
            return_value=ReverseCompendiumEvidence(rejected=(rejected,)),
        ),
        patch(
            "recommender.slot_fill.narrow_candidates_for_move",
            return_value=NarrowResult(["Rejected Setter", "Raw Setter"], 1),
        ),
    ):
        rows = resolve_need_candidates(need, _base_state())

    assert [row.species for row in rows] == ["Raw Setter"]


def test_unmapped_need_keeps_raw_resolution_without_compendium_query():
    need = SupportNeed("tailwind", "Tailwind", "Needs Tailwind", "speed_tier:middling")
    with (
        patch("recommender.slot_fill.role_category_evidence") as compendium,
        patch(
            "recommender.slot_fill.narrow_candidates_for_move",
            return_value=NarrowResult(["Whimsicott"], 1),
        ),
    ):
        rows = resolve_need_candidates(need, _base_state())

    compendium.assert_not_called()
    assert [row.species for row in rows] == ["Whimsicott"]
    assert rows[0].evidence[0].basis == "mechanical_only"


def test_compendium_priority_beats_all_existing_sort_pressure():
    compendium = CandidateEvidence(
        "compendium_backed",
        "medium",
        "role_category_evidence",
        ("need:trick_room", "role:trick_room_setter"),
    )
    mechanical = CandidateEvidence(
        "mechanical_only", "low", "narrow_candidates_for_move"
    )
    trick_room = _trick_room_need()
    extra = SupportNeed("screens", "Screens", "Wants screens", None)
    ctx = SlotFillContext(anchor={"species": "Kingambit"}, role_shape_context=_shape())
    ctx.annotated_candidates = [
        AnnotatedCandidate(
            "Verified Setter",
            (trick_room,),
            "need",
            evidence=(compendium,),
        ),
        AnnotatedCandidate(
            "Raw All-Rounder",
            (trick_room, extra),
            "both",
            threat_row=_tc("Raw All-Rounder", usage_rank=1, verified_score=999.0),
            evidence=(mechanical,),
        ),
    ]

    presentation = present_candidates(ctx, slot_index=1)

    assert presentation.default == "Verified Setter"
    assert presentation.options == ("Verified Setter", "Raw All-Rounder")


def test_existing_sort_keys_still_apply_within_compendium_tier():
    evidence = CandidateEvidence(
        "compendium_backed", "medium", "role_category_evidence"
    )
    need = _trick_room_need()
    extra = SupportNeed("screens", "Screens", "Wants screens", None)
    ctx = SlotFillContext(anchor={"species": "Kingambit"}, role_shape_context=_shape())
    ctx.annotated_candidates = [
        AnnotatedCandidate("One Need", (need,), "need", evidence=(evidence,)),
        AnnotatedCandidate(
            "Two Needs", (need, extra), "need", evidence=(evidence,)
        ),
    ]

    assert present_candidates(ctx, slot_index=1).default == "Two Needs"


def test_compendium_priority_requires_an_active_matching_need():
    evidence = CandidateEvidence(
        "compendium_backed", "medium", "role_category_evidence"
    )
    ctx = SlotFillContext(anchor={"species": "Kingambit"}, role_shape_context=_shape())
    ctx.annotated_candidates = [
        AnnotatedCandidate("Unrelated Member", (), "need", evidence=(evidence,))
    ]

    with pytest.raises(
        AssertionError, match="compendium-backed candidate must match an active need"
    ):
        present_candidates(ctx, slot_index=1)


def test_concrete_matching_build_promotes_compendium_confidence():
    need = _trick_room_need()
    evidence = CandidateEvidence(
        "compendium_backed",
        "medium",
        "role_category_evidence",
        ("need:trick_room", "role:trick_room_setter"),
    )
    ctx = SlotFillContext(
        anchor={"species": "Kingambit"},
        role_shape_context=_shape(),
        threat_counter_results=[
            _tc("Farigiraf", moves=("Trick Room", "Psychic"))
        ],
        support_needs=[need],
        need_resolved_candidates=[
            NeedResolvedCandidate("Farigiraf", (need,), (evidence,))
        ],
    )

    row = merge_need_resolved(ctx)[0]

    compendium = next(
        item for item in row.evidence if item.basis == "compendium_backed"
    )
    assert compendium.confidence == "high"


def test_rejected_redirector_can_still_enter_via_priority_denial():
    need = SupportNeed(
        "fake_out_protection",
        "Fake Out protection",
        "Needs protection",
        "glass_offense:fake_out",
    )
    rejected = CompendiumRoleEvidence(
        species="Farigiraf",
        role_id="redirection",
        category="redirection",
        condition="",
        tier=None,
        mechanism=None,
        source_file="redirection.v1.json",
        reason="not a redirector",
    )
    raw = NeedResolvedCandidate(
        "Farigiraf",
        (need,),
        (
            CandidateEvidence(
                "mechanical_only", "low", "_species_with_abilities"
            ),
        ),
    )
    with (
        patch(
            "recommender.slot_fill.role_category_evidence",
            return_value=ReverseCompendiumEvidence(rejected=(rejected,)),
        ),
        patch("recommender.slot_fill._raw_need_candidates", return_value=[raw]),
    ):
        rows = resolve_need_candidates(need, _base_state())

    assert [row.species for row in rows] == ["Farigiraf"]


def test_union_move_candidates_uses_deterministic_move_order():
    calls: list[str] = []

    def narrow(move, _state):
        calls.append(move)
        return NarrowResult([move.title(), "Shared"], 1)

    with patch("recommender.slot_fill.narrow_candidates_for_move", side_effect=narrow):
        names = _union_move_candidates(
            frozenset({"wish", "aromatherapy"}), _base_state()
        )

    assert calls == ["aromatherapy", "wish"]
    assert names == ["Aromatherapy", "Shared", "Wish"]


def test_static_row_cannot_outrank_verified_in_sort_annotated():
    verified = _tc("VerifiedMon", usage_rank=50, verified_score=2.0)
    # Replace with explicit estimate_kind — _tc defaults verified
    verified = ThreatCounterCandidate(
        candidate=verified.candidate,
        threats_countered=verified.threats_countered,
        threats_countered_count=verified.threats_countered_count,
        verified_score=2.0,
        verified_vs=verified.verified_vs,
        estimate_kind="verified",
    )
    static = ThreatCounterCandidate(
        candidate=_tc("StaticMon", usage_rank=1).candidate,
        threats_countered=("t1",),
        threats_countered_count=1,
        verified_score=99.0,  # falsely high — firewall must ignore
        verified_vs=(),
        estimate_kind="static",
    )
    rows = [
        AnnotatedCandidate(
            species="StaticMon",
            matching_needs=(),
            source="threat",
            threat_row=static,
            evidence=_threat_evidence(static, degradation_kind="calc_unavailable"),
        ),
        AnnotatedCandidate(
            species="VerifiedMon",
            matching_needs=(),
            source="threat",
            threat_row=verified,
            evidence=_threat_evidence(verified),
        ),
    ]
    ordered = _sort_annotated(rows)
    assert [row.species for row in ordered] == ["VerifiedMon", "StaticMon"]

