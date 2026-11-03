"""FU24 §2: flags-off tool results match main for a fixed fixture."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.eval.part_g_arm.state.fixtures import empty_team
from scripts.eval.part_g_arm.state.harness import snapshot
from scripts.eval.part_g_arm.state.pending import build_fully_locked_slot
from scripts.eval.part_g_arm.state.tools import (
    add_constraint,
    find_species,
    read_constraints,
    restore_constraint_tool,
    set_draft,
    set_guard,
    set_tool_fields,
    set_wrapper,
    show_candidates,
)

GOLDEN = (
    Path(__file__).resolve().parent
    / "expected_tools_fu16"
    / "flags_off_tool_outputs_main.json"
)


def _flags_off() -> None:
    set_tool_fields(False)
    set_wrapper(False)
    set_draft(False)
    set_guard(False)


def _bundle() -> dict:
    """Same fixture used to capture main's golden."""
    st = empty_team()
    st, _r_add1 = add_constraint(
        st,
        "prefer Water types",
        "team_wide",
        "mechanically-checkable",
        mechanical_kind="type",
        value="Water",
    )
    st, r_add2 = add_constraint(
        st,
        "prefer Fire types",
        "team_wide",
        "mechanically-checkable",
        mechanical_kind="type",
        value="Fire",
    )
    st, r_restore = restore_constraint_tool(st)
    read = read_constraints(st)
    fs = find_species(st, types=["Grass"], n=3)
    st2 = build_fully_locked_slot("Venusaur", user_slot=1)
    after, show = show_candidates(st2, 2)
    pending = after.get("pending_presentation") or {}
    return {
        "add_constraint": r_add2,
        "restore_constraint": r_restore,
        "read_constraints": read,
        "find_species": fs,
        "show_candidates": show,
        "pending_keys": sorted(pending.keys()),
        "pending_has_fingerprint": "team_fingerprint" in pending,
        "snapshot": snapshot(after),
    }


def test_flags_off_tool_outputs_equal_main_golden():
    _flags_off()
    got = json.loads(json.dumps(_bundle(), sort_keys=True, default=str))
    expected = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert got == expected
    # Explicit: no index/id leak, no fingerprint at flags-off.
    for c in got["read_constraints"]["constraints"]:
        assert "index" not in c and "id" not in c
    assert got["pending_has_fingerprint"] is False
    assert "team_fingerprint" not in json.dumps(got["snapshot"], default=str)
