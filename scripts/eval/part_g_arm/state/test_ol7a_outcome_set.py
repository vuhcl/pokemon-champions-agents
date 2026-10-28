"""OL7a outcome_sets: bind Jolteon and ask pass; other bind fails."""

from __future__ import annotations

import copy

from recommender.arm_tools import ArmTools
from recommender.regulation_registry import active_regulation

from scripts.eval.part_g_arm.state.class_scorer import score_turn
from scripts.eval.part_g_arm.state.request_set_rows import load_request_rows, resolve_start_state
from scripts.eval.part_g_arm.state.tools import (
    draft_signature,
    mechanical_class,
    select_option,
    steering_signature,
)


def _snap(state: dict) -> dict:
    return {"slots": draft_signature(state), "steering": steering_signature(state)}


def _score(start: dict, after: dict, tool_calls: list) -> dict:
    observed = mechanical_class(start, after, tool_calls)
    turn = {
        "mechanical_class": observed,
        "state_before": _snap(start),
        "state_after": _snap(after),
        "tool_calls": tool_calls,
    }
    return score_turn(
        observed_mech=observed,
        expected_key_class="PARTIAL",
        turn=turn,
        row_id="OL7a",
    )


def _start():
    rows = {r["id"]: r for r in load_request_rows()}
    state, meta = resolve_start_state(rows["OL7a"])
    assert state is not None and meta.get("loaded")
    return state


def test_ol7a_bind_jolteon_passes():
    start = _start()
    opts = (start.get("pending_presentation") or {}).get("options") or []
    jol = next(i + 1 for i, o in enumerate(opts) if o.get("species") == "Jolteon")
    after, res = select_option(copy.deepcopy(start), jol)
    sc = _score(start, after, [{"name": "select_option", "arguments": {"option": jol}, "result": res}])
    assert sc["match"] and sc["state_expectation_met"]
    assert sc["outcome_matched"] == "bind"
    assert sc["bound_species"] == "Jolteon"


def test_ol7a_ask_passes():
    start = _start()
    arm = ArmTools(regulation=active_regulation(), allow_live=False, calc=None, include_damage_rolls=False)
    res = arm.no_lookup_needed("which option is faster?", "conceptual")
    sc = _score(
        start,
        copy.deepcopy(start),
        [{"name": "no_lookup_needed", "arguments": {"reason": "ask", "category": "conceptual"}, "result": res}],
    )
    assert sc["match"] and sc["state_expectation_met"]
    assert sc["outcome_matched"] == "ask"


def test_ol7a_other_bind_fails():
    start = _start()
    opts = (start.get("pending_presentation") or {}).get("options") or []
    other = next(i + 1 for i, o in enumerate(opts) if o.get("species") != "Jolteon")
    after, res = select_option(copy.deepcopy(start), other)
    sc = _score(start, after, [{"name": "select_option", "arguments": {"option": other}, "result": res}])
    assert sc["match"] is False
    assert sc["bound_species"] != "Jolteon"
