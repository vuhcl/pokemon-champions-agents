from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from recommender.constraint_enforcement import (
    MechanicalSpec,
    apply_mechanical_constraints_to_discovery,
    build_constraint,
    filter_candidates,
    matches_species,
    partition_constraints,
    resolve_mechanical,
    soft_rank_bonus,
)
from recommender.nodes import discover_multi_locked, discover_single_locked
from recommender.slot_fill import (
    AnchoredSlotDiscovery,
    AnnotatedCandidate,
    SlotFillContext,
    SlotFillPresentation,
    SlotFillTerminalResult,
    PresentedCandidate,
)
from recommender.state import (
    Attr,
    CandidateEvidence,
    Constraint,
    RecommenderState,
    Slot,
    TeamReviewResult,
    TeamThreatDiscovery,
    empty_slot,
)
from recommender.support_needs import RoleShapeContext, SupportNeed

VGC_MB = "[Gen 9 Champions] VGC 2026 Reg M-B"
SPREAD = {"hp": 32, "atk": 32, "def": 2, "spa": 0, "spd": 0, "spe": 0}

_OBVIOUS_NEED = [
    SupportNeed(
        category="trick_room",
        name="Trick Room",
        description="Low Spe attacker with no priority.",
        trigger="speed_tier:low_no_priority",
        stance="need",
    )
]


def _candidate(species: str) -> AnnotatedCandidate:
    return AnnotatedCandidate(
        species=species,
        matching_needs=(),
        source="test",
        evidence=(),
        composition_fit="neutral",
    )


def _evidence(*, usage: bool = True) -> CandidateEvidence:
    return CandidateEvidence(
        basis="usage_backed" if usage else "mechanical_only",
        confidence="high",
        producer_name="test",
    )


def _filter_stub_candidate(species: str) -> AnnotatedCandidate:
    """Stub with enough fields for discovery constraint filtering."""
    row = SimpleNamespace(verified_vs=(("x", object()),), verified_score=8.0)
    return AnnotatedCandidate(
        species=species,
        matching_needs=(),
        source="threat",
        threat_row=row,  # type: ignore[arg-type]
        spec={"species": species},
        evidence=(_evidence(),),
        branches=frozenset({"threat"}),
        wastes_core_slot=False,
    )


def _locked(
    species: str,
    *,
    item: str = "Leftovers",
    ability: str = "Pressure",
) -> Slot:
    return Slot(
        role=Attr("bulky_attacker", locked=True),
        species=Attr(species, locked=True),
        ability=Attr(ability, locked=True),
        item=Attr(item, locked=True),
        moveset=Attr(["Protect", "Tackle", "Rest", "Sleep Talk"], locked=True),
        spread=Attr(dict(SPREAD), locked=True),
        nature=Attr("Adamant", locked=True),
    )


def _state(draft: list[Slot], **extra) -> RecommenderState:
    base: RecommenderState = {
        "format_id": VGC_MB,
        "game_type": "doubles",
        "regulation_mod": "champions-reg-mb",
        "picked_team_size": 4,
        "available_pool": [],
        "team_draft": draft,
        "archetype": Attr(),
        "rejected": [],
        "constraints": [],
        "messages": [],
    }
    base.update(extra)  # type: ignore[typeddict-item]
    return base


def _grass_hard_constraint() -> Constraint:
    return Constraint(
        "hard",
        "type:grass",
        0,
        True,
        "per_slot",
        "mechanically-checkable",
        mechanical=MechanicalSpec("type", "Grass", "per_slot", "type:grass"),
    )


def test_resolve_mechanical_structured_and_predicate():
    payload = {
        "type": "hard",
        "predicate": "user said grass",
        "scope": "per_slot",
        "groundedness": "mechanically-checkable",
        "mechanical_kind": "type",
        "mechanical_value": "grass",
    }
    c = build_constraint(payload, source_turn=1)
    assert c.mechanical is not None
    assert c.mechanical.kind == "type"
    assert c.mechanical.value == "Grass"

    parsed = resolve_mechanical(
        Constraint(
            "hard",
            "type:fire",
            0,
            True,
            "per_slot",
            "mechanically-checkable",
        )
    )
    assert parsed is not None and parsed.value == "Fire"


def test_hard_type_filter_and_unsatisfiable():
    grass = MechanicalSpec("type", "Grass", "per_slot", "type:grass")
    pool = [_candidate("Rillaboom"), _candidate("Pelipper")]
    filtered = filter_candidates(pool, (grass,), team_draft=[], open_slot_index=0)
    assert [c.species for c in filtered] == ["Rillaboom"]
    empty, err = apply_mechanical_constraints_to_discovery(
        pool,
        [Constraint("hard", "type:fire", 0, True, "per_slot", "mechanically-checkable")],
        team_draft=[],
        open_slot_index=0,
    )
    assert empty == []
    assert err is not None and err.kind == "constraint_unsatisfiable"


def test_unsupported_hard_still_fails_closed():
    pool = [_candidate("Rillaboom")]
    _, err = apply_mechanical_constraints_to_discovery(
        pool,
        [
            Constraint(
                "hard",
                "must be shiny",
                0,
                True,
                "team_wide",
                "mechanically-checkable",
            )
        ],
        team_draft=[],
        open_slot_index=0,
    )
    assert err is not None and err.kind == "unsupported_constraint"


def test_soft_rank_bonus_does_not_exclude():
    grass = MechanicalSpec("type", "Grass", "per_slot", "prefer grass")
    bonus_grass = soft_rank_bonus("Rillaboom", (grass,), team_draft=[], open_slot_index=0)
    bonus_other = soft_rank_bonus("Pelipper", (grass,), team_draft=[], open_slot_index=0)
    assert bonus_grass == 1
    assert bonus_other == 0


def test_partition_soft_vs_hard():
    part = partition_constraints(
        [
            Constraint("soft", "type:grass", 0, True, "per_slot", "mechanically-checkable"),
            Constraint("hard", "must be shiny", 0, True, "team_wide", "mechanically-checkable"),
        ]
    )
    assert len(part.soft_mechanical) == 1
    assert part.soft_mechanical[0].kind == "type"
    assert len(part.unenforceable_hard) == 1


def test_team_wide_monotype_rejects_locked_mismatch():
    spec = MechanicalSpec("type", "Grass", "team_wide", "grass monotype")
    draft = [_locked("Charizard"), empty_slot()]
    # Charizard is Fire/Flying — violates grass monotype with locked member.
    assert not matches_species(
        "Rillaboom",
        spec,
        team_draft=draft,
        open_slot_index=1,
    )


def test_hard_ability_intimidate_filters_via_species_can_have_ability():
    """Plan #5 — constraint_enforcement.py:251-252 (matches_species ability branch).

    Exercises real species_can_have_ability lookup: Incineroar passes, Pelipper fails.
    """
    spec = MechanicalSpec("ability", "Intimidate", "per_slot", "ability:Intimidate")
    pool = [_candidate("Incineroar"), _candidate("Pelipper")]
    filtered = filter_candidates(pool, (spec,), team_draft=[], open_slot_index=2)
    assert [c.species for c in filtered] == ["Incineroar"]

    soft = MechanicalSpec("ability", "Intimidate", "per_slot", "prefer Intimidate")
    assert soft_rank_bonus("Incineroar", (soft,), team_draft=[], open_slot_index=2) == 1
    assert soft_rank_bonus("Pelipper", (soft,), team_draft=[], open_slot_index=2) == 0


def test_hard_item_choice_scarf_uses_item_clause_not_default_item():
    """Plan #6 — constraint_enforcement.py:254-258 (item branch via team_item_ids).

    Hard item matching must respect Item Clause (team_item_ids), not
    pick_synthesized_default_item (that path is no_duplicate_items only).
    """
    spec = MechanicalSpec("item", "Choice Scarf", "per_slot", "Choice Scarf")
    pool = [_candidate("Incineroar"), _candidate("Pelipper")]
    draft_free = [_locked("Kingambit"), _locked("Farigiraf"), empty_slot(), empty_slot()]
    draft_scarf_taken = [
        _locked("Kingambit", item="Choice Scarf"),
        _locked("Farigiraf"),
        empty_slot(),
        empty_slot(),
    ]

    with patch(
        "recommender.constraint_enforcement.pick_synthesized_default_item",
        return_value="Choice Scarf",
    ) as default_item:
        free = filter_candidates(
            pool, (spec,), team_draft=draft_free, open_slot_index=2
        )
        blocked = filter_candidates(
            pool, (spec,), team_draft=draft_scarf_taken, open_slot_index=2
        )

    default_item.assert_not_called()
    assert {c.species for c in free} == {"Incineroar", "Pelipper"}
    assert blocked == []


def test_discover_single_locked_applies_constraint_filter_before_terminal():
    """Plan #9 — nodes.py:1353-1368 apply_mechanical_constraints_to_discovery on single_locked path."""
    state = _state([_locked("Kingambit"), *[empty_slot() for _ in range(5)]])
    state["constraints"] = [_grass_hard_constraint()]
    merged = [_filter_stub_candidate("Rillaboom"), _filter_stub_candidate("Pelipper")]
    captured: list[SlotFillContext] = []

    context = SlotFillContext(
        anchor={"species": "Kingambit"},
        role_shape_context=RoleShapeContext(),
        threat_counter_results=[],
        support_needs=_OBVIOUS_NEED,
    )

    def merge(ctx):
        ctx.annotated_candidates = merged
        return merged

    def terminal(ctx, _state, *, slot_index):
        captured.append(ctx)
        return SlotFillTerminalResult(
            presentation=SlotFillPresentation(
                1, (PresentedCandidate("Rillaboom", "need", ()),)
            ),
            state_updates={
                "pending_presentation": {
                    "schema_version": 1,
                    "kind": "candidate_selection",
                    "slot_index": slot_index,
                    "options": [{"species": "Rillaboom", "source": "need"}],
                }
            },
            deferred=False,
        )

    with (
        patch(
            "recommender.slot_fill.build_anchored_slot_fill_context",
            return_value=AnchoredSlotDiscovery(context, object(), object(), False),
        ),
        patch("recommender.slot_fill.annotate_overlap"),
        patch("recommender.slot_fill.resolve_all_support_needs", return_value=[]),
        patch("recommender.slot_fill.resolve_condition_beneficiaries", return_value=[]),
        patch("recommender.slot_fill.merge_need_resolved", side_effect=merge),
        patch("recommender.slot_fill.run_slot_fill_terminal", side_effect=terminal),
        patch(
            "recommender.team_candidates.annotate_composition_impact",
            side_effect=lambda rows, *args, **kwargs: list(rows),
        ),
    ):
        result = discover_single_locked(state)

    assert result.get("candidate_discovery_error") is None
    assert captured
    assert [c.species for c in captured[0].annotated_candidates or []] == ["Rillaboom"]
    assert captured[0].soft_mechanical == ()


def test_discover_multi_locked_hard_type_filters_before_rank():
    """Hard-type filter must run before category ranking / presentation."""
    draft = [
        _locked("Pelipper"),
        _locked("Archaludon"),
        _locked("Incineroar"),
        _locked("Charizard-Mega-Y"),
        empty_slot(),
        empty_slot(),
    ]
    state = _state(draft, constraints=[_grass_hard_constraint()])
    state["team_completion_preference"] = "balanced"
    merged = [_filter_stub_candidate("Rillaboom"), _filter_stub_candidate("Pelipper")]
    ranked_species: list[str] = []

    def tracking_rank(candidates, *args, **kwargs):
        ranked_species.extend(c.species for c in candidates)
        return list(candidates)

    review = TeamReviewResult([], [], [])
    threat = TeamThreatDiscovery(status="available", candidates=(), error=None)
    terminal = SlotFillTerminalResult(
        presentation=SlotFillPresentation(
            1, (PresentedCandidate("Rillaboom", "threat", ()),)
        ),
        state_updates={
            "pending_presentation": {
                "schema_version": 1,
                "kind": "candidate_selection",
                "slot_index": 4,
                "options": [{"species": "Rillaboom", "source": "threat"}],
            }
        },
        deferred=False,
    )

    with (
        patch("recommender.nodes._compute_team_review", return_value=review),
        patch("recommender.nodes.query_shared_teammates", return_value=None),
        patch(
            "recommender.threat_counters.query_candidates_for_threats",
            return_value=threat,
        ),
        patch(
            "recommender.team_candidates.merge_multi_locked_candidates",
            return_value=merged,
        ),
        patch(
            "recommender.team_candidates.annotate_composition_impact",
            side_effect=lambda rows, *args, **kwargs: list(rows),
        ),
        patch(
            "recommender.team_candidates.rank_multi_locked_by_category",
            side_effect=tracking_rank,
        ),
        patch("recommender.slot_fill.run_slot_fill_terminal", return_value=terminal),
    ):
        result = discover_multi_locked(state, {})  # type: ignore[arg-type]

    assert ranked_species == ["Rillaboom"]
    pending = result.get("pending_presentation") or {}
    assert pending.get("kind") != "core_resolution"
    options = pending.get("options") or []
    if options:
        assert all(o.get("species") == "Rillaboom" for o in options)
        assert "Pelipper" not in {o.get("species") for o in options}
