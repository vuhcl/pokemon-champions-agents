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
from recommender.condition_types import ConditionResilienceReport, ConditionResilienceRow
from recommender.slot_fill import (
    AnnotatedCandidate,
    NeedResolvedCandidate,
    REVIEWED_STRATEGIC_TARGET_ROLES,
    SlotFillContext,
    SlotFillResponse,
    _CONDITION_SETTER_TARGET_ROLES,
    _FO_PROTECTION_ABILITIES,
    _NEED_SATISFIERS,
    _NEED_TARGET_ROLES,
    _compendium_roles_for_need,
    _redundancy_tier_for_candidates,
    _scoped_evidence,
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
    resolve_condition_beneficiaries,
    resolve_need_candidates,
    run_slot_fill_terminal,
    target_role_from_needs,
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
from recommender.usage_data import lineage_ids


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


def _unmapped_beneficiary_need() -> SupportNeed:
    return SupportNeed(
        category="condition_beneficiary",
        name="Rain beneficiary",
        description="Anchor provides Rain; candidate kit-emits benefits_from Rain.",
        trigger="field_condition:provided:rain",
    )


def test_condition_beneficiary_is_not_a_target_role_mapping():
    """Search filter, not a settable open-slot role — same gap the 3a kit fallback covers."""
    assert "condition_beneficiary" not in _NEED_TARGET_ROLES
    assert "condition_beneficiary" not in _CONDITION_SETTER_TARGET_ROLES
    assert "condition_beneficiary" not in _NEED_SATISFIERS
    try:
        resolve_need_candidates(_unmapped_beneficiary_need(), _base_state())
        assert False, "expected NotImplementedError"
    except NotImplementedError:
        pass


def test_locked_anchor_lineage_exclusion_is_species_agnostic():
    """Beneficiary self-hits drop via lineage_ids of whatever is locked, not 'Pelipper'."""

    def ineligible(candidate: str, locked: list[str]) -> bool:
        locked_lineages = {lid for name in locked for lid in lineage_ids(name)}
        return to_id(candidate) in locked_lineages

    for setter in (
        "Pelipper",
        "Torkoal",
        "Tyranitar",
        "Ninetales-Alola",
        "Whimsicott",
    ):
        assert ineligible(setter, [setter]), setter
    assert ineligible("Swampert-Mega", ["Swampert"])
    assert ineligible("Tyranitar-Mega", ["Tyranitar"])
    assert ineligible("Ninetales", ["Ninetales-Alola"])
    assert not ineligible("Basculegion", ["Pelipper"])
    assert not ineligible("Venusaur", ["Torkoal"])
    assert not ineligible("Excadrill", ["Tyranitar"])


def test_condition_beneficiary_need_only_is_presented_default_over_high_score_threats():
    """Pelipper-shaped empty support_needs: matching_needs length lifts a Swift Swim user
    into pick_default_and_alternatives' top-3, above verified_score=99 threat rows.

    Locks the 'no new ranking stage' claim empirically. Does not implement discovery —
    injects the post-merge shape the design would produce.
    """
    need = _unmapped_beneficiary_need()
    evidence = CandidateEvidence(
        "mechanical_only",
        "low",
        "resolve_condition_beneficiaries",
        ("need:condition_beneficiary", "condition:Rain", "ability:swiftswim"),
    )
    ctx = SlotFillContext(
        anchor={"species": "Pelipper"},
        role_shape_context=_shape(primary_function="support"),
        threat_counter_results=[
            _tc("Incineroar", usage_rank=1, verified_score=99.0),
            _tc("Kingambit", usage_rank=2, verified_score=90.0),
            _tc("Garchomp", usage_rank=3, verified_score=80.0),
            _tc("Floette-Mega", usage_rank=4, verified_score=70.0),
            _tc("Charizard-Mega-Y", usage_rank=5, verified_score=60.0),
            _tc("Sneasler", usage_rank=6, verified_score=50.0),
            _tc("Aegislash", usage_rank=7, verified_score=40.0),
            _tc("Farigiraf", usage_rank=8, verified_score=30.0),
        ],
        support_needs=[],
        need_resolved_candidates=[
            NeedResolvedCandidate("Swampert-Mega", (need,), (evidence,)),
        ],
    )
    merge_need_resolved(ctx)
    presentation = present_candidates(ctx, slot_index=1)
    assert "Swampert-Mega" in presentation.options
    assert presentation.options.index("Swampert-Mega") < 3
    assert presentation.default == "Swampert-Mega"


def test_unmapped_need_only_swampert_mega_uses_kit_fallback_and_refines():
    """condition_beneficiary-shaped row must not inherit rain_setter or dead-end on refine."""
    need = _unmapped_beneficiary_need()
    evidence = CandidateEvidence(
        "mechanical_only",
        "low",
        "resolve_condition_beneficiaries",
        ("need:condition_beneficiary", "condition:Rain", "ability:swiftswim"),
    )
    ctx = SlotFillContext(
        anchor={"species": "Pelipper"},
        role_shape_context=_shape(primary_function="support"),
        threat_counter_results=[_tc("Incineroar", usage_rank=1, verified_score=99.0)],
        support_needs=[],
        need_resolved_candidates=[
            NeedResolvedCandidate("Swampert-Mega", (need,), (evidence,)),
        ],
    )
    rows = merge_need_resolved(ctx)
    swampert = next(r for r in rows if r.species == "Swampert-Mega")
    assert isinstance(swampert.target_role_decision, TargetRoleDecision)
    assert swampert.target_role_decision.producer_name == "slot_fill_kit_role_policy"
    assert swampert.target_role_decision.role_id != "rain_setter"
    assert swampert.target_role_decision.role_id == "fast_physical_attacker"
    assert ctx.target_role_decision is None

    state = _base_state()
    terminal = run_slot_fill_terminal(
        ctx,
        state,
        slot_index=1,
        response=SlotFillResponse(action="choose", species="Swampert-Mega"),
    )
    intent = terminal.state_updates["pending_slot_intent"]
    assert intent.target_role_decision.producer_name == "slot_fill_kit_role_policy"
    provisional = build_provisional_slot(intent, state)
    assert isinstance(provisional, ProvisionalSlot)


def test_need_only_without_kit_role_still_unresolved_on_refine():
    """Ability-table hits are not all 3a-safe when kit_role cannot map to TargetRoleId.

    Untruncated usage now gives Qwilfish fast_pivot; stub the fallback so this
    still covers the unresolved-target-role refine path.
    """
    need = _unmapped_beneficiary_need()
    evidence = CandidateEvidence(
        "mechanical_only",
        "low",
        "resolve_condition_beneficiaries",
        ("need:condition_beneficiary", "condition:Rain", "ability:swiftswim"),
    )
    ctx = SlotFillContext(
        anchor={"species": "Pelipper"},
        role_shape_context=_shape(primary_function="support"),
        threat_counter_results=[_tc("Incineroar")],
        support_needs=[],
        need_resolved_candidates=[
            NeedResolvedCandidate("Qwilfish", (need,), (evidence,)),
        ],
    )
    with patch("recommender.slot_fill._kit_fallback_target_role", return_value=None):
        rows = merge_need_resolved(ctx)
        qwil = next(r for r in rows if r.species == "Qwilfish")
        assert qwil.target_role_decision is None

        state = _base_state()
        terminal = run_slot_fill_terminal(
            ctx,
            state,
            slot_index=1,
            response=SlotFillResponse(action="choose", species="Qwilfish"),
        )
        provisional = build_provisional_slot(
            terminal.state_updates["pending_slot_intent"], state
        )
    assert isinstance(provisional, UnresolvedSlotRefinement)
    assert provisional.reason == "unresolved_target_role"


def _resolve_beneficiaries(species: str) -> list[NeedResolvedCandidate]:
    decision = classify_anchor_role(resolve_anchor_build(species))
    ctx = SlotFillContext(
        anchor={"species": species},
        role_shape_context=_shape(primary_function="support"),
        threat_counter_results=[],
        support_needs=[],
        need_resolved_candidates=[],
    )
    return resolve_condition_beneficiaries(
        ctx, decision, _base_state(), locked_species=[species]
    )


def _row_tokens(row: NeedResolvedCandidate) -> set[str]:
    return {tok for ev in row.evidence for tok in ev.evidence}


def test_resolve_condition_beneficiaries_dummy_decision_is_noop():
    ctx = SlotFillContext(
        anchor={"species": "Kingambit"},
        role_shape_context=_shape(),
        threat_counter_results=[],
        support_needs=[],
        need_resolved_candidates=[],
    )
    out = resolve_condition_beneficiaries(
        ctx, object(), _base_state(), locked_species=["Kingambit"]  # type: ignore[arg-type]
    )
    assert out == []


def test_pelipper_rain_beneficiaries_exclude_self_and_ignore_tailwind():
    rows = _resolve_beneficiaries("Pelipper")
    names = {to_id(row.species) for row in rows}
    tokens = {tok for row in rows for tok in _row_tokens(row)}
    assert "pelipper" not in names
    assert "ability:swiftswim" in tokens or "move:electroshot" in tokens
    assert "condition:Tailwind" not in tokens
    assert all(n.category == "condition_beneficiary" for row in rows for n in row.matching_needs)
    ability_hits = [
        ev
        for row in rows
        for ev in row.evidence
        if ev.producer_name == "resolve_condition_beneficiaries"
    ]
    assert ability_hits
    assert all(ev.basis == "mechanical_only" and ev.confidence == "high" for ev in ability_hits)


def test_torkoal_sun_beneficiaries_exclude_self():
    rows = _resolve_beneficiaries("Torkoal")
    names = {to_id(row.species) for row in rows}
    tokens = {tok for row in rows for tok in _row_tokens(row)}
    assert "torkoal" not in names
    assert (
        "ability:chlorophyll" in tokens
        or "move:solarbeam" in tokens
        or "move:solarblade" in tokens
    )


def test_tyranitar_sand_beneficiaries_exclude_lineage():
    rows = _resolve_beneficiaries("Tyranitar")
    names = {to_id(row.species) for row in rows}
    tokens = {tok for row in rows for tok in _row_tokens(row)}
    assert "tyranitar" not in names
    assert "tyranitarmega" not in names
    assert "ability:sandrush" in tokens or "ability:sandforce" in tokens


def test_ninetales_alola_snow_beneficiaries_exclude_lineage():
    rows = _resolve_beneficiaries("Ninetales-Alola")
    names = {to_id(row.species) for row in rows}
    tokens = {tok for row in rows for tok in _row_tokens(row)}
    assert "ninetales" not in names
    assert "ninetalesalola" not in names
    assert "ability:slushrush" in tokens


def test_whimsicott_tailwind_only_has_no_condition_beneficiaries():
    assert _resolve_beneficiaries("Whimsicott") == []


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


def test_threat_only_choice_gets_kit_fallback_not_open_slot_role():
    """Threat-only rows must not inherit the open-slot support role.

    They may still receive an identity kit TargetRoleDecision so refine is not a
    dead-end (CLI pending cleared + unresolved refine with no re-prompt).
    """
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
    assert isinstance(intent.target_role_decision, TargetRoleDecision)
    assert intent.target_role_decision.role_id != "trick_room_setter"
    assert intent.target_role_decision.producer_name == "slot_fill_kit_role_policy"
    provisional = build_provisional_slot(intent, _base_state())
    assert isinstance(provisional, ProvisionalSlot)


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
_ARCHETYPE_TARGET_ROLES = {
    "fast_physical_attacker",
    "fast_special_attacker",
    "fast_mixed_attacker",
    "standard_physical_attacker",
    "standard_special_attacker",
    "standard_mixed_attacker",
    "bulky_physical_attacker",
    "bulky_special_attacker",
    "bulky_mixed_attacker",
    "support_speed_control",
    "screens_support",
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

    assert vocabulary == (
        _LEGACY_TARGET_ROLES | _NEW_TARGET_ROLES | _ARCHETYPE_TARGET_ROLES
    )
    assert len(vocabulary) == 25
    assert set(REVIEWED_STRATEGIC_TARGET_ROLES.values()) == _NEW_TARGET_ROLES | {
        "trick_room_setter",
        "tailwind_setter",
    }
    assert REVIEWED_STRATEGIC_TARGET_ROLES["tailwindsetter"] == "tailwind_setter"
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
    # Clean match still runs raw needs — including move-derived Rain from Electro Shot.
    assert any(
        need.category == "condition_setter"
        and need.trigger == "field_condition:any:rain"
        for need in result.context.support_needs
    )


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


def test_resolve_screens_uses_real_compendium_not_generic_mechanical_only():
    """Regression: screens needs previously fell through _compendium_roles_for_need
    unmapped (unlike trick_room/fake_out_protection/condition_setter), even
    though screens_support.v1.json is fully persisted and real. This meant
    every screens-capable candidate got mechanical_only/low evidence
    regardless of actual compendium tier -- a real data-quality gap found
    while investigating the rain-suggestion display bug (2026-08-16/17),
    since it also polluted unrelated candidates' merged evidence tuples with
    spurious low-quality entries.
    """
    need = SupportNeed(
        category="screens",
        name="Screens",
        description="Attacker-shaped anchors benefit from screens support.",
        trigger=None,
    )
    names = resolve_need_candidates(need, _base_state())
    assert names
    by_id = {to_id(row.species): row for row in names}
    meowstic = by_id.get("meowstic")
    assert meowstic is not None
    assert any(e.basis == "compendium_backed" for e in meowstic.evidence)


def test_resolve_screens_deprioritizes_hard_weather_gated_candidate_under_conflicting_weather():
    """Regression, confirmed live: Abomasnow's real, correctly-attributed
    'screens' match comes from Aurora Veil (via Snow Warning), a move
    that HARD-requires Snow/Hail to be usable at all -- not just boosted,
    genuinely unusable without it. On a real team with Rain already
    locked (only one weather can be active), Abomasnow's screens value
    is currently zero, since it would never actually get to use Aurora
    Veil without abandoning the team's real weather strategy entirely.

    Deprioritized, not excluded (confirmed as the right design directly,
    not assumed): removing it entirely would discard real information --
    it might still be worth surfacing as a low-priority option, e.g. if
    the team's weather situation later changes. Downgrades BOTH basis
    and confidence, not confidence alone -- _BASIS_RANK ranks
    compendium_backed (Abomasnow's real original basis here) highest,
    and is compared before confidence in every ranking that uses this
    evidence, so a confidence-only downgrade would not have actually
    deprioritized it below genuinely-usable, lower-basis candidates.

    Confirmed the exact real evidence-tag shape before writing this fix:
    Abomasnow's screens match comes through the compendium path
    ('mechanism:Aurora Veil'), not the raw-move path
    ('move:auroraveil') -- both tag formats are checked, confirmed by
    testing this exact scenario directly against real data, not assumed
    to be the same shape.
    """
    need = SupportNeed(
        category="screens",
        name="Screens",
        description="Attacker-shaped anchors benefit from screens support.",
        trigger=None,
    )
    names = resolve_need_candidates(need, _base_state(), locked_weather="Rain")
    by_id = {to_id(row.species): row for row in names}
    abomasnow = by_id.get("abomasnow")
    assert abomasnow is not None, "must still be present, just deprioritized"
    assert all(e.basis == "mechanical_only" for e in abomasnow.evidence)
    assert all(e.confidence == "low" for e in abomasnow.evidence)
    assert any(
        "weather_conflict:requires_Snow_have_Rain" in e.evidence
        for e in abomasnow.evidence
    )
    # Real, unconditionally-usable screens candidates must be unaffected.
    grimmsnarl = by_id.get("grimmsnarl")
    assert grimmsnarl is not None
    assert not any(
        tag.startswith("weather_conflict:")
        for e in grimmsnarl.evidence
        for tag in e.evidence
    )


def test_resolve_screens_ranks_deprioritized_candidate_below_usable_ones():
    """Confirms the deprioritization actually changes ranking outcome,
    not just evidence metadata -- Abomasnow must sort below genuinely
    usable screens candidates once ranked by evidence quality (the same
    ranking select_diverse_candidates' Category B/C use)."""
    from recommender.team_candidates import _rank_by_need_evidence
    from recommender.slot_fill import AnnotatedCandidate

    need = SupportNeed(
        category="screens",
        name="Screens",
        description="Attacker-shaped anchors benefit from screens support.",
        trigger=None,
    )
    names = resolve_need_candidates(need, _base_state(), locked_weather="Rain")
    candidates = [
        AnnotatedCandidate(
            species=row.species,
            matching_needs=row.matching_needs,
            source="need",
            threat_row=None,
            spec={"species": row.species},
            evidence=row.evidence,
            branches=frozenset({"need"}),
        )
        for row in names
    ]
    ranked = _rank_by_need_evidence(candidates)
    order = [c.species for c in ranked]
    assert order.index("Abomasnow") > order.index("Grimmsnarl")


def test_resolve_screens_keeps_hard_weather_gated_candidate_undowngraded_under_matching_weather():
    """Confirms the deprioritization is genuinely conditional, not a
    blanket downgrade of Abomasnow or Aurora Veil -- under a team that
    has actually locked in Snow, Abomasnow's screens value is completely
    real and must not be touched."""
    need = SupportNeed(
        category="screens",
        name="Screens",
        description="Attacker-shaped anchors benefit from screens support.",
        trigger=None,
    )
    names = resolve_need_candidates(need, _base_state(), locked_weather="Snow")
    by_id = {to_id(row.species): row for row in names}
    abomasnow = by_id.get("abomasnow")
    assert abomasnow is not None
    assert any(e.basis == "compendium_backed" for e in abomasnow.evidence)
    assert not any(
        tag.startswith("weather_conflict:")
        for e in abomasnow.evidence
        for tag in e.evidence
    )


def test_resolve_screens_keeps_hard_weather_gated_candidate_undowngraded_with_no_locked_weather():
    """No weather locked at all (locked_weather=None, the default) -- the
    downgrade must not fire, since there's nothing to conflict with
    yet."""
    need = SupportNeed(
        category="screens",
        name="Screens",
        description="Attacker-shaped anchors benefit from screens support.",
        trigger=None,
    )
    names = resolve_need_candidates(need, _base_state())
    by_id = {to_id(row.species): row for row in names}
    abomasnow = by_id.get("abomasnow")
    assert abomasnow is not None
    assert any(e.basis == "compendium_backed" for e in abomasnow.evidence)


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


def test_compendium_species_not_diluted_by_unrecognized_raw_move_species():
    """Behavior changed intentionally, not a regression: trick_room now
    has a real compendium mapping, so a genuinely different species
    found only via raw-move search ("Raw Ace", never appearing in the
    compendium at all) is no longer added alongside the real,
    compendium-backed candidate -- confirmed live: a need with a real
    compendium should only surface candidates it actually recognizes,
    same principle as excluding Gholdengo from screens."""
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

    assert [row.species for row in rows] == ["Verified Setter"]
    assert rows[0].evidence[0].basis == "compendium_backed"


def test_species_popularity_alone_is_not_usage_backed_execution_evidence():
    """Uses healing_cleric, not trick_room -- trick_room now has a real
    compendium mapping and skips the raw-move fallback entirely for
    non-compendium species, so it can no longer exercise this test's
    actual purpose (raw-move resolution's own popularity-vs-commitment
    distinction). healing_cleric has no real compendium category and
    still uses the raw-move path unrestricted."""
    need = SupportNeed(
        category="healing_cleric",
        name="Healing / cleric support",
        description="x",
        trigger="tank_no_self_heal",
    )
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
    """Behavior changed intentionally, not a regression: trick_room now
    has a real compendium mapping, so the raw-move fallback is skipped
    entirely for it, not just for rejected species specifically. Even a
    genuinely new, non-rejected species ("Raw Setter") found only via
    raw-move search no longer gets added -- confirmed live: a need with
    a real compendium to check against should only surface candidates
    the compendium actually recognizes, the same principle behind
    excluding Gholdengo from screens despite mechanically learning the
    moves."""
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

    assert [row.species for row in rows] == []


def test_unmapped_need_keeps_raw_resolution_without_compendium_query():
    """Uses taunt_disruption, not tailwind -- tailwind now has a real
    compendium mapping (tailwind_setter), so it's no longer an example
    of an unmapped need. taunt_disruption genuinely has no compendium
    category and still skips the compendium query entirely."""
    need = SupportNeed(
        "taunt_disruption", "Taunt disruption", "Needs Taunt", None
    )
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


def test_target_role_from_needs_maps_rain_condition_setter():
    need = SupportNeed(
        category="condition_setter",
        name="Rain setter",
        description="Needs Rain",
        trigger="field_condition:any:rain",
        notes="Requires Rain",
    )
    decision = target_role_from_needs([need])
    assert isinstance(decision, TargetRoleDecision)
    assert decision.role_id == "rain_setter"


def test_archaludon_single_locked_pool_labels_rain_setter():
    from recommender.team_candidates import owned_species_ids

    slot = Slot(
        species=Attr("Archaludon", locked=True),
        role=Attr("bulky_special_attacker", locked=True),
        ability=Attr("Stamina", locked=True),
        item=Attr("Leftovers", locked=True),
        nature=Attr("Timid", locked=True),
        moveset=Attr(
            ["Electro Shot", "Dragon Pulse", "Flash Cannon", "Aura Sphere"],
            locked=True,
        ),
        spread=Attr(
            {"hp": 2, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 32},
            locked=True,
        ),
    )
    state = _base_state()
    state["team_draft"] = [slot, empty_slot()]
    disc = build_anchored_slot_fill_context(state, slot, threat_counter_results=[])
    ctx = disc.context
    assert ctx is not None
    assert any(
        n.category == "condition_setter" and n.trigger == "field_condition:any:rain"
        for n in (ctx.support_needs or [])
    )
    derive_target_role(ctx)
    annotate_overlap(ctx)
    resolve_all_support_needs(
        ctx, state, available_species=owned_species_ids(state), ownership_mode="off"
    )
    merge_need_resolved(ctx)
    labeled = [
        row
        for row in (ctx.annotated_candidates or [])
        if isinstance(row.target_role_decision, TargetRoleDecision)
        and row.target_role_decision.role_id == "rain_setter"
    ]
    ambiguous_rain = [
        row
        for row in (ctx.annotated_candidates or [])
        if isinstance(row.target_role_decision, UnresolvedTargetRoleDecision)
        and "rain_setter" in row.target_role_decision.ambiguity
    ]
    assert any(to_id(row.species) == "politoed" for row in labeled) or any(
        to_id(row.species) == "pelipper" for row in (*labeled, *ambiguous_rain)
    )



def _redundancy_test_need(category: str) -> SupportNeed:
    return SupportNeed(category=category, name="x", description="x", trigger=None)


def _redundancy_test_row(species: str, role_id: str, *categories: str) -> AnnotatedCandidate:
    return AnnotatedCandidate(
        species=species,
        matching_needs=tuple(_redundancy_test_need(c) for c in categories),
        source="usage",
        target_role_decision=TargetRoleDecision(role_id=role_id, source="usage_backed"),
    )


def test_redundancy_tier_fully_resolved_condition_deprioritizes_duplicate_role():
    """Regression, confirmed live (2026-08-18): after a Tailwind setter
    was locked, more tailwind_setter candidates were still offered as
    alternatives with no redundancy awareness at all. gap=='none' means
    the condition is fully resolved -- no backup value -- so a candidate
    whose only real contribution is the same role gets deprioritized."""
    resilience = ConditionResilienceReport(
        conditions=(
            ConditionResilienceRow(
                condition="Tailwind", classification="preferred",
                provider_count=1, providers=(), dependents=(), gap="none",
            ),
        )
    )
    rows = [
        _redundancy_test_row("Altaria", "tailwind_setter", "tailwind"),
        _redundancy_test_row("Staraptor", "tailwind_setter", "tailwind"),
        _redundancy_test_row("Garchomp", "fast_physical_attacker", "defensive_coverage"),
    ]
    tiers = _redundancy_tier_for_candidates(rows, resilience)
    assert tiers == {"Altaria": 2, "Staraptor": 2, "Garchomp": 0}


def test_redundancy_tier_missing_provider_is_never_deprioritized():
    """A genuinely unmet need (gap=='missing_provider') is always tier 0,
    regardless of how many candidates offer it -- fills_essential_gap
    already prioritizes these in ranking, and this must not undo that."""
    resilience = ConditionResilienceReport(
        conditions=(
            ConditionResilienceRow(
                condition="Tailwind", classification="preferred",
                provider_count=0, providers=(), dependents=(), gap="missing_provider",
            ),
        )
    )
    rows = [
        _redundancy_test_row("Altaria", "tailwind_setter", "tailwind"),
        _redundancy_test_row("Staraptor", "tailwind_setter", "tailwind"),
    ]
    tiers = _redundancy_tier_for_candidates(rows, resilience)
    assert tiers == {"Altaria": 0, "Staraptor": 0}


def test_redundancy_tier_spof_backup_needs_additional_value_to_rank_above_redundant():
    """Real design requirement, confirmed with Vu directly: a
    single_provider_spof condition (real backup value, per the
    condition's own essential/preferred classification) should NOT be
    prioritized ahead of other unmet needs -- UNLESS the candidate also
    contributes toward another, distinct need (the Sableye case: both a
    rain_setter and a screens provider). A SPOF-eligible role with no
    other contributing value stays tier 2, same as a fully-resolved one.
    """
    resilience = ConditionResilienceReport(
        conditions=(
            ConditionResilienceRow(
                condition="Rain", classification="preferred",
                provider_count=1, providers=(), dependents=(),
                gap="single_provider_spof",
            ),
        )
    )
    rows = [
        _redundancy_test_row("Pelipper", "rain_setter", "condition_setter"),
        _redundancy_test_row(
            "Sableye", "rain_setter", "condition_setter", "screens"
        ),
    ]
    tiers = _redundancy_tier_for_candidates(rows, resilience)
    assert tiers == {"Pelipper": 2, "Sableye": 1}


def test_redundancy_tier_non_condition_role_is_always_tier_0():
    """A candidate whose role doesn't map to any tracked condition at all
    (e.g. a pure attacker) is never deprioritized by this mechanism."""
    resilience = ConditionResilienceReport(conditions=())
    rows = [_redundancy_test_row("Garchomp", "fast_physical_attacker", "defensive_coverage")]
    tiers = _redundancy_tier_for_candidates(rows, resilience)
    assert tiers == {"Garchomp": 0}


def test_redundancy_tier_none_resilience_returns_empty():
    rows = [_redundancy_test_row("Garchomp", "fast_physical_attacker")]
    assert _redundancy_tier_for_candidates(rows, None) == {}


def test_present_candidates_routes_through_select_diverse_candidates_when_locked_contexts_present():
    """Confirms the actual wiring, not just that it doesn't crash: when
    locked_contexts is populated (the multi-locked path), present_candidates
    must call select_diverse_candidates -- the multi-signal, per-category
    selection built and validated earlier in this investigation --
    rather than the older single-ranking + redundancy-tier approach.
    """
    rows = [
        AnnotatedCandidate(
            species="Garchomp",
            matching_needs=(),
            source="threat",
            spec={"species": "Garchomp"},
            evidence=(),
        ),
    ]
    ctx = SlotFillContext(
        anchor=None,
        role_shape_context=None,
        annotated_candidates=rows,
        candidates_pre_ranked=True,
        locked_contexts=(object(),),  # non-empty is all the branch checks
    )
    with patch(
        "recommender.team_candidates.select_diverse_candidates",
        return_value={"default": "Garchomp", "alternatives": []},
    ) as mocked:
        presentation = present_candidates(ctx, slot_index=0)
    mocked.assert_called_once()
    assert presentation.default == "Garchomp"


def test_present_candidates_uses_old_path_when_locked_contexts_empty():
    """Confirms the routing is genuinely conditional -- with no
    locked_contexts (the single/zero-locked case, matching every existing
    present_candidates test in this file), the older redundancy-tier
    approach must still be used, not select_diverse_candidates."""
    rows = [
        AnnotatedCandidate(
            species="Garchomp",
            matching_needs=(),
            source="threat",
            spec={"species": "Garchomp"},
            evidence=(),
        ),
    ]
    ctx = SlotFillContext(
        anchor=None,
        role_shape_context=None,
        annotated_candidates=rows,
        candidates_pre_ranked=True,
    )
    with patch(
        "recommender.team_candidates.select_diverse_candidates"
    ) as mocked:
        presentation = present_candidates(ctx, slot_index=0)
    mocked.assert_not_called()
    assert presentation.default == "Garchomp"


def test_resolve_all_support_needs_downgrades_confidence_for_untriggered_needs():
    """Regression, confirmed live: needs generated without a specific
    trigger (trigger=None -- e.g. screens' unconditional "attacker-
    universal" generation) are real but weak, non-discriminating
    signals -- almost any offense-shaped anchor "benefits somewhat",
    which isn't the same as a genuinely specific reason. Confidence is
    downgraded to reflect where a match falls on the broad-to-specific
    spectrum; basis is left untouched -- the data source itself isn't
    questionable, only the match's specificity is. Contrasted directly
    against a real-triggered need (trick_room, speed_tier-based) in the
    same resolution call, which must keep its original confidence.
    """
    screens_need = SupportNeed(
        category="screens",
        name="Screens",
        description="Attacker-shaped anchors benefit from screens support.",
        trigger=None,
    )
    tr_need = _trick_room_need()
    ctx = SlotFillContext(
        anchor={"species": "Garchomp"},
        role_shape_context=_shape(),
        support_needs=[screens_need, tr_need],
    )
    resolved = resolve_all_support_needs(ctx, _base_state())
    by_id = {to_id(row.species): row for row in resolved}

    screens_evidence = [
        e
        for row in resolved
        for e in row.evidence
        if any("need:screens" in tag for tag in e.evidence)
    ]
    assert screens_evidence
    assert all(e.confidence == "low" for e in screens_evidence)

    tr_evidence = [
        e
        for row in resolved
        for e in row.evidence
        if any("need:trick_room" in tag for tag in e.evidence)
    ]
    assert tr_evidence
    # At least one real trick_room match should retain non-low
    # confidence -- confirms the downgrade is genuinely conditional on
    # trigger, not applied blanket to every need.
    assert any(e.confidence != "low" for e in tr_evidence)


def test_screens_excludes_species_not_in_compendium_even_if_mechanically_capable():
    """Regression, confirmed live: Gholdengo mechanically learns Light
    Screen and Reflect, but is genuinely not a recognized screens user
    in the real compendium. It must not match the screens need at all,
    not even at low/mechanical_only confidence -- confirmed as the
    right design directly: a need with a real compendium to check
    against should only surface candidates the compendium actually
    recognizes."""
    need = SupportNeed(
        category="screens",
        name="Screens",
        description="Attacker-shaped anchors benefit from screens support.",
        trigger=None,
    )
    names = resolve_need_candidates(need, _base_state())
    ids = {to_id(row.species) for row in names}
    assert "gholdengo" not in ids


def test_tailwind_need_now_uses_real_compendium():
    """Regression, confirmed live: tailwind had no compendium mapping at
    all before this fix -- every match, including a real, recognized
    "Good"-tier setter like Staraptor-Mega, only ever got raw-move
    (mechanical_only) evidence. Confirms the new mapping surfaces real
    compendium-backed evidence at the correct tier-derived confidence."""
    need = SupportNeed(
        category="tailwind",
        name="Tailwind",
        description="x",
        trigger="speed_tier:middling",
    )
    names = resolve_need_candidates(need, _base_state())
    by_id = {to_id(row.species): row for row in names}
    staraptor_mega = by_id.get("staraptormega")
    assert staraptor_mega is not None
    assert any(e.basis == "compendium_backed" for e in staraptor_mega.evidence)
    assert any(
        "tier:Good" in tag
        for e in staraptor_mega.evidence
        for tag in e.evidence
    )


def test_fake_out_protection_has_no_compendium_mapping():
    """Regression, confirmed live: redirection can't stop Fake Out
    (higher priority than redirection moves), so the previous
    fake_out_protection -> redirection compendium mapping was
    mechanically wrong. No real "priority protection" compendium
    category exists either (confirmed directly against real compendium
    data -- would only have 2 candidates even if it did, not
    representative enough to restrict against). fake_out_protection now
    has no compendium mapping at all, same as healing_cleric/
    taunt_disruption, and stays on the raw-move/ability path
    unrestricted."""
    need = SupportNeed(
        category="fake_out_protection",
        name="Fake Out protection",
        description="x",
        trigger="requires_setup_turn:fake_out",
    )
    assert _compendium_roles_for_need(need) == []


def _threat_evidence_row() -> CandidateEvidence:
    return CandidateEvidence(
        basis="usage_backed",
        confidence="high",
        producer_name="query_counters",
        branch="threat",
        evidence=("usage:test",),
    )


def _need_evidence_row(condition_beneficiary: bool = False) -> CandidateEvidence:
    tag = "need:condition_beneficiary" if condition_beneficiary else "need:healing_cleric"
    return CandidateEvidence(
        basis="mechanical_only",
        confidence="low",
        producer_name="test",
        branch="need",
        evidence=(tag,),
    )


def test_scoped_evidence_shows_real_matching_needs_evidence_not_unrelated_threat_evidence():
    """Regression, confirmed live: a candidate labeled "support/utility"
    displayed 'usage_backed, high confidence' -- evidence that actually
    belonged to its unrelated threat-counter data, while its real
    support-need match was genuinely mechanical_only/low. The label and
    the displayed evidence told two different, inconsistent stories.
    Confirms scoping to Category B specifically surfaces the real,
    weaker matching_needs evidence, not the stronger but irrelevant one.
    """
    full_evidence = (_threat_evidence_row(), _need_evidence_row())
    scoped = _scoped_evidence(full_evidence, ["B"])
    assert scoped == (_need_evidence_row(),)


def test_scoped_evidence_shows_threat_evidence_for_category_a_only():
    full_evidence = (_threat_evidence_row(), _need_evidence_row())
    scoped = _scoped_evidence(full_evidence, ["A"])
    assert scoped == (_threat_evidence_row(),)


def test_scoped_evidence_includes_all_relevant_categories_for_multi_signal():
    """A genuinely multi-signal candidate (strong in more than one
    category) should show evidence from every category it's labeled
    for, not just one."""
    full_evidence = (_threat_evidence_row(), _need_evidence_row())
    scoped = _scoped_evidence(full_evidence, ["A", "B"])
    assert set(scoped) == {_threat_evidence_row(), _need_evidence_row()}


def test_scoped_evidence_distinguishes_condition_benefit_from_support_need():
    """Category B and C both use branch='need' -- confirms they're
    correctly told apart via the need:condition_beneficiary tag, not
    conflated just because they share a branch value."""
    need_row = _need_evidence_row(condition_beneficiary=False)
    benefit_row = _need_evidence_row(condition_beneficiary=True)
    full_evidence = (need_row, benefit_row)

    scoped_b = _scoped_evidence(full_evidence, ["B"])
    assert scoped_b == (need_row,)

    scoped_c = _scoped_evidence(full_evidence, ["C"])
    assert scoped_c == (benefit_row,)


def test_scoped_evidence_falls_back_to_full_evidence_when_nothing_matches():
    """If filtering would produce an empty result (e.g. all evidence is
    teammate-branched, which doesn't correspond to any A/B/C track),
    falls back to the full, unfiltered evidence rather than silently
    showing nothing."""
    teammate_only = (
        CandidateEvidence(
            basis="teammate_backed",
            confidence="medium",
            producer_name="query_shared_teammates",
            branch="teammate",
        ),
    )
    scoped = _scoped_evidence(teammate_only, ["A"])
    assert scoped == teammate_only


def test_scoped_evidence_returns_full_evidence_when_no_category_keys():
    """No category_keys at all (e.g. the older, single-locked path that
    never sets this) -- returns the evidence unchanged, same as before
    this fix existed."""
    full_evidence = (_threat_evidence_row(), _need_evidence_row())
    assert _scoped_evidence(full_evidence, []) == full_evidence


def test_ability_based_condition_beneficiary_gets_high_not_low_confidence():
    """Regression, confirmed live: an ability-based condition-beneficiary
    match (e.g. Swift Swim under Rain) was hardcoded to confidence="low"
    regardless of how strong the match actually is -- backwards from the
    whole specificity-spectrum framework this project uses elsewhere.
    An innate ability directly interacting with a locked condition is
    the most mechanically certain, narrowest tier of evidence possible
    (no "might not run it" ambiguity the way a move-commitment check
    has) -- it should be high confidence, not the same low tier as a
    generic, broadly-applicable match. Confirmed live: Swampert-Mega's
    real Swift Swim match under a real, locked Rain team.
    """
    rows = _resolve_beneficiaries("Pelipper")
    by_id = {to_id(row.species): row for row in rows}
    swampert_mega = by_id.get("swampertmega")
    assert swampert_mega is not None
    ability_evidence = [
        ev
        for ev in swampert_mega.evidence
        if ev.producer_name == "resolve_condition_beneficiaries"
    ]
    assert ability_evidence
    assert all(ev.confidence == "high" for ev in ability_evidence)
