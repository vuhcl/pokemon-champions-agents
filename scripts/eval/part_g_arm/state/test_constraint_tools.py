"""4b add_constraint / read_constraints / restore_constraint."""

from __future__ import annotations

from scripts.eval.part_g_arm.state.fixtures import empty_team
from scripts.eval.part_g_arm.state.tools import (
    add_constraint,
    mechanical_class,
    read_constraints,
    restore_constraint_tool,
    steering_signature,
)


def test_ms6_water_type_mechanical():
    """MS6: slot 1 Water → mechanical_kind=type exists; echo slot1 Water."""
    st = empty_team()
    after, res = add_constraint(
        st,
        "Water",
        "per_slot",
        "mechanically-checkable",
        slot=1,
        mechanical_kind="type",
        value="Water",
    )
    assert res.get("ok"), res
    assert res.get("slot") == 1
    c = res["constraint"]
    assert c["mechanical_kind"] == "type"
    assert c["mechanical_value"] == "Water"
    assert c["slot"] == 1
    assert "slot 1" in c["predicate"].lower() and "water" in c["predicate"].lower()
    read = read_constraints(after)
    assert any(
        r.get("mechanical_kind") == "type" and r.get("slot") == 1
        for r in read["constraints"]
    )
    before_snap = {"steering": list(steering_signature(st)), "slots": []}
    after_snap = {"steering": list(steering_signature(after)), "slots": []}
    assert mechanical_class(before_snap, after_snap, [{"name": "add_constraint", "result": res}]) == "recorded"


def test_mt3_no_intimidate_judgment_only():
    """No ban-ability kind — judgment-only predicate path."""
    st = empty_team()
    after, res = add_constraint(
        st, "No Intimidate.", "team_wide", "judgment-only"
    )
    assert res.get("ok"), res
    c = res["constraint"]
    assert c["groundedness"] == "judgment-only"
    assert c["mechanical_kind"] is None
    assert "intimidate" in c["predicate"].casefold()


def test_hc2_no_weather_judgment_only():
    st = empty_team()
    after, res = add_constraint(
        st, "No weather.", "team_wide", "judgment-only"
    )
    assert res.get("ok"), res
    assert after["constraints"][-1].mechanical is None
    assert after["constraints"][-1].groundedness == "judgment-only"


def test_judgment_only_refuses_mechanical_args():
    st = empty_team()
    after, res = add_constraint(
        st,
        "No Intimidate.",
        "team_wide",
        "judgment-only",
        mechanical_kind="ability",
        value="Intimidate",
    )
    assert res.get("slot_commit_error")
    assert after is st or after.get("constraints") == st.get("constraints")


def test_restore_after_type_supersede():
    st = empty_team()
    st, _ = add_constraint(
        st,
        "Fire",
        "per_slot",
        "mechanically-checkable",
        mechanical_kind="type",
        value="Fire",
    )
    st = {**st, "turn": 1}
    st, _ = add_constraint(
        st,
        "Water",
        "per_slot",
        "mechanically-checkable",
        mechanical_kind="type",
        value="Water",
    )
    assert any(not c.still_active for c in st["constraints"])
    assert st.get("constraints_superseded")
    after, res = restore_constraint_tool(st)
    assert res.get("ok"), res
    active = [c for c in after["constraints"] if c.still_active]
    assert len(active) == 1
    assert active[0].mechanical is not None
    assert active[0].mechanical.value == "Fire"


def test_restore_empty_log_refuses():
    st = empty_team()
    after, res = restore_constraint_tool(st)
    assert res.get("slot_commit_error")
    assert (after.get("constraints") or []) == (st.get("constraints") or [])


def test_read_constraints_empty():
    assert read_constraints(empty_team()) == {"constraints": []}
