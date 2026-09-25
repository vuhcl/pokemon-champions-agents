"""Axis-replacement supersede for hard MechanicalSpec constraints."""

from __future__ import annotations

from recommender.constraint_enforcement import (
    MechanicalSpec,
    apply_constraint_axis_supersede,
    restore_constraint_axis,
)
from recommender.nodes import restore_constraint
from recommender.state import Constraint


def _hard(
    *,
    kind: str,
    value: str,
    scope: str = "per_slot",
    predicate: str | None = None,
    source_turn: int = 1,
    soft: bool = False,
) -> Constraint:
    pred = predicate or f"{kind}:{value}"
    return Constraint(
        type="soft" if soft else "hard",
        predicate=pred,
        source_turn=source_turn,
        still_active=True,
        scope=scope,  # type: ignore[arg-type]
        groundedness="mechanically-checkable",
        mechanical=MechanicalSpec(kind, value, scope, pred),  # type: ignore[arg-type]
    )


def _active_on_axis(
    constraints: list[Constraint], kind: str, scope: str
) -> list[Constraint]:
    out = []
    for c in constraints:
        if not c.still_active or c.type != "hard" or c.mechanical is None:
            continue
        if c.mechanical.kind == kind and c.mechanical.scope == scope:
            out.append(c)
    return out


def test_type_axis_supersede_newest_wins():
    older = _hard(kind="type", value="Fire", predicate="type:fire", source_turn=1)
    newer = _hard(kind="type", value="Water", predicate="type:water", source_turn=2)
    constraints, sup, flags = apply_constraint_axis_supersede(
        [older], newer, turn=2
    )
    assert len(constraints) == 2
    assert constraints[0].still_active is False
    assert constraints[1].still_active is True
    assert constraints[1].mechanical is not None
    assert constraints[1].mechanical.value == "Water"
    assert len(sup) == 1
    assert sup[0]["constraint_index"] == 0
    assert sup[0]["won_by_index"] == 1
    assert sup[0]["value"] == "Fire"
    assert len(flags) == 1
    assert flags[0]["flag_kind"] == "constraint_axis_superseded"


def test_soft_contradicting_hard_triggers_nothing():
    hard = _hard(kind="type", value="Fire", predicate="type:fire")
    soft = _hard(
        kind="type", value="Water", predicate="prefer water", soft=True
    )
    constraints, sup, flags = apply_constraint_axis_supersede(
        [hard], soft, turn=2
    )
    assert constraints[0].still_active is True
    assert constraints[1].type == "soft"
    assert constraints[1].still_active is True
    assert sup == []
    assert flags == []


def test_ability_axis_supersede():
    a = _hard(kind="ability", value="Intimidate", predicate="ability:intimidate")
    b = _hard(kind="ability", value="Guts", predicate="ability:guts", source_turn=2)
    constraints, sup, flags = apply_constraint_axis_supersede([a], b, turn=2)
    assert constraints[0].still_active is False
    assert constraints[1].mechanical is not None
    assert constraints[1].mechanical.value == "Guts"
    assert len(sup) == 1 and len(flags) == 1


def test_item_axis_supersede():
    a = _hard(kind="item", value="Choice Scarf", predicate="Choice Scarf")
    b = _hard(
        kind="item",
        value="Leftovers",
        predicate="Leftovers",
        source_turn=2,
    )
    constraints, sup, _flags = apply_constraint_axis_supersede([a], b, turn=2)
    assert constraints[0].still_active is False
    assert constraints[1].mechanical is not None
    assert constraints[1].mechanical.value == "Leftovers"
    assert len(sup) == 1


def test_same_value_no_supersede():
    a = _hard(kind="type", value="Fire", predicate="type:fire")
    b = _hard(kind="type", value="Fire", predicate="type:fire again", source_turn=2)
    constraints, sup, flags = apply_constraint_axis_supersede([a], b, turn=2)
    assert constraints[0].still_active is True
    assert constraints[1].still_active is True
    assert sup == [] and flags == []


def test_restore_constraint_axis_true_swap():
    older = _hard(kind="type", value="Fire", predicate="type:fire", source_turn=1)
    newer = _hard(kind="type", value="Water", predicate="type:water", source_turn=2)
    constraints, sup, _flags = apply_constraint_axis_supersede(
        [older], newer, turn=2
    )
    entry = sup[0]
    swapped = restore_constraint_axis(constraints, entry)
    assert swapped is not None
    active = _active_on_axis(swapped, "type", "per_slot")
    assert len(active) == 1
    assert active[0].mechanical is not None
    assert active[0].mechanical.value == "Fire"
    assert swapped[1].still_active is False


def test_restore_constraint_node_one_level():
    older = _hard(kind="type", value="Fire", predicate="type:fire", source_turn=1)
    newer = _hard(kind="type", value="Water", predicate="type:water", source_turn=2)
    constraints, sup, flags = apply_constraint_axis_supersede(
        [older], newer, turn=2
    )
    state = {
        "format_id": "gen9vgc2026regmb",
        "game_type": "doubles",
        "regulation_mod": "champions",
        "picked_team_size": 4,
        "available_pool": [],
        "team_draft": [],
        "archetype": None,
        "rejected": [],
        "constraints": constraints,
        "constraints_superseded": list(sup),
        "constraint_flags": list(flags),
        "messages": [],
        "turn": 3,
        "turn_payload": {},
    }
    out = restore_constraint(state)  # type: ignore[arg-type]
    assert "constraints" in out
    active = _active_on_axis(out["constraints"], "type", "per_slot")
    assert len(active) == 1
    assert active[0].mechanical is not None
    assert active[0].mechanical.value == "Fire"
    assert out["constraints"][1].still_active is False
    assert out["constraints_superseded"] == []

    state2 = {**state, **out}
    out2 = restore_constraint(state2)  # type: ignore[arg-type]
    assert out2 == {}


def test_restore_snapshot_mismatch_noop():
    older = _hard(kind="type", value="Fire", predicate="type:fire", source_turn=1)
    entry = {
        "constraint_index": 0,
        "kind": "type",
        "scope": "per_slot",
        "value": "Water",  # mismatch
        "predicate": "type:fire",
        "source_turn": 1,
        "turn_removed": 2,
        "reason": "test",
        "won_by_index": 1,
    }
    assert restore_constraint_axis([older], entry) is None  # type: ignore[arg-type]


def test_no_duplicate_items_excluded():
    a = _hard(
        kind="no_duplicate_items",
        value="",
        scope="team_wide",
        predicate="no duplicate items",
    )
    # Second no_dup also has empty value — same value, but kind is excluded by early return
    b = _hard(
        kind="no_duplicate_items",
        value="",
        scope="team_wide",
        predicate="no duplicate items again",
        source_turn=2,
    )
    constraints, sup, flags = apply_constraint_axis_supersede([a], b, turn=2)
    assert constraints[0].still_active is True
    assert len(constraints) == 2
    assert sup == [] and flags == []
