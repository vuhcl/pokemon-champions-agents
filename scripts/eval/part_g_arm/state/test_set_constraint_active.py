"""FU21: set_constraint_active + find_species honors still_active."""

from __future__ import annotations

from scripts.eval.part_g_arm.state.fixtures import empty_team
from scripts.eval.part_g_arm.state.tools import (
    add_constraint,
    find_species,
    read_constraints,
    set_constraint_active,
    set_tool_fields,
)


def _add_type(state, pred: str, value: str):
    return add_constraint(
        state,
        pred,
        "team_wide",
        "mechanically-checkable",
        mechanical_kind="type",
        value=value,
    )


def test_deactivate_read_and_find_species():
    set_tool_fields(True)
    try:
        st = empty_team()
        st, _ = _add_type(st, "type:Water", "Water")
        # Axis newest-wins: adding Fire deactivates Water.
        st, _ = _add_type(st, "type:Fire", "Fire")
        read = read_constraints(st)
        assert len(read["constraints"]) == 2
        assert read["constraints"][0]["still_active"] is False
        assert read["constraints"][1]["still_active"] is True
        fire_only = find_species(st, learns_move="Protect")
        assert fire_only["status"] == "ok"
        # Deactivate Fire (index 2); reactivate Water (index 1).
        st, out = set_constraint_active(st, 2, False)
        assert out["ok"] and out["changed"]
        assert out["constraints"][1]["still_active"] is False
        st, out_w = set_constraint_active(st, 1, True)
        assert out_w["constraints"][0]["still_active"] is True
        after = find_species(st, learns_move="Protect")
        assert after["status"] == "ok"
        names = after["species"]
        assert names
        from recommender.legality import load_snapshot, species_types

        snap = load_snapshot()
        for name in names[:20]:
            types = {t.casefold() for t in (species_types(snap, name) or [])}
            assert "water" in types
    finally:
        set_tool_fields(False)


def test_idempotent_and_unknown_index():
    set_tool_fields(True)
    try:
        st = empty_team()
        st, _ = _add_type(st, "type:Water", "Water")
        st2, out = set_constraint_active(st, 1, True)
        assert out["ok"] and out["changed"] is False
        assert st2 is st
        st3, out3 = set_constraint_active(st, 1, False)
        assert out3["changed"] is True
        st4, out4 = set_constraint_active(st3, 1, False)
        assert out4["changed"] is False
        _, bad = set_constraint_active(st4, 99, False)
        msg = str(bad.get("slot_commit_error") or bad.get("message") or bad)
        assert "out of range" in msg
        assert "1..1" in msg
    finally:
        set_tool_fields(False)


def test_reactivate_supersedes_conflicting_active():
    set_tool_fields(True)
    try:
        st = empty_team()
        st, _ = _add_type(st, "type:Water", "Water")
        st, out = set_constraint_active(st, 1, False)
        assert out["changed"]
        st, _ = _add_type(st, "type:Fire", "Fire")
        # Reactivate Water → should deactivate Fire (same kind/scope).
        st, out2 = set_constraint_active(st, 1, True)
        assert out2["changed"]
        rows = out2["constraints"]
        assert rows[0]["still_active"] is True
        assert rows[0]["mechanical_value"] == "Water"
        assert rows[1]["still_active"] is False
        assert st.get("constraints_superseded")
    finally:
        set_tool_fields(False)


def test_mt6_sequence_fire_deactivated():
    """MT6 t2 'Keep Water only': after Water then Fire (Fire wins), deactivate Fire + reactivate Water."""
    set_tool_fields(True)
    try:
        st = empty_team()
        st, _ = _add_type(st, "type:Water", "Water")
        st, _ = _add_type(st, "type:Fire", "Fire")
        sequence = [
            ("add_constraint", {"predicate": "type:Water", "mechanical_kind": "type", "value": "Water"}),
            ("add_constraint", {"predicate": "type:Fire", "mechanical_kind": "type", "value": "Fire"}),
            ("set_constraint_active", {"constraint": 2, "active": False}),
            ("set_constraint_active", {"constraint": 1, "active": True}),
            ("find_species", {"learns_move": "Protect"}),
        ]
        st, _ = set_constraint_active(st, 2, False)
        st, out = set_constraint_active(st, 1, True)
        assert out["constraints"][0]["still_active"] is True
        assert out["constraints"][1]["still_active"] is False
        found = find_species(st, learns_move="Protect")
        assert found["status"] == "ok"
        from recommender.legality import load_snapshot, species_types

        snap = load_snapshot()
        for name in found["species"]:
            types = {t.casefold() for t in (species_types(snap, name) or [])}
            assert "water" in types
            assert "fire" in types or "water" in types  # Water required; Fire not required
        # Explicit: Fire-only mons are excluded (no Fire filter, but Water required).
        print("MT6 call sequence:", sequence)
        print("find_species count after Keep Water only:", found["count"])
    finally:
        set_tool_fields(False)


def test_flags_off_schema_excludes_set_constraint_active():
    from scripts.eval.part_g_arm.state.tools import combined_specs

    off = combined_specs(tool_fields=False, wrapper=False, draft=False)
    assert not any(s["function"]["name"] == "set_constraint_active" for s in off)
    on = combined_specs(tool_fields=True, wrapper=False, draft=False)
    assert any(s["function"]["name"] == "set_constraint_active" for s in on)


def test_still_active_survives_jsonable_round_trip():
    """Snapshot/checkpointer path: still_active survives to_jsonable."""
    from recommender.arm_tools import to_jsonable

    set_tool_fields(True)
    try:
        st = empty_team()
        st, _ = _add_type(st, "type:Water", "Water")
        st, _ = set_constraint_active(st, 1, False)
        blob = to_jsonable(st["constraints"])
        assert blob[0]["still_active"] is False
        # Rehydrate into set_constraint_active / find_species via dataclass list is
        # production's job; the JSON surface is what the checkpointer stores.
        assert "still_active" in blob[0]
    finally:
        set_tool_fields(False)
