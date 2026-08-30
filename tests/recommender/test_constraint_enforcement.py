from __future__ import annotations

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
from recommender.slot_fill import AnnotatedCandidate
from recommender.state import Attr, Constraint, Slot, empty_slot


def _candidate(species: str) -> AnnotatedCandidate:
    return AnnotatedCandidate(
        species=species,
        matching_needs=(),
        source="test",
        evidence=(),
        composition_fit="neutral",
    )


def _locked(species: str, *, types_ok: bool = True) -> Slot:
    # Species name only matters for team_wide monotype tests via load_snapshot.
    del types_ok
    return Slot(
        role=Attr("bulky_attacker", locked=True),
        species=Attr(species, locked=True),
        ability=Attr("Pressure", locked=True),
        item=Attr("Leftovers", locked=True),
        moveset=Attr(["Protect", "Tackle", "Rest", "Sleep Talk"], locked=True),
        spread=Attr({"hp": 32, "atk": 32, "def": 2, "spa": 0, "spd": 0, "spe": 0}, locked=True),
        nature=Attr("Adamant", locked=True),
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
