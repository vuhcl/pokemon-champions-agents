"""FU27/FU28: process-metric scorer rule unit tests."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.eval.part_g_arm.state.process_metric_scorer import (
    SET_SLOT_EQUIV,
    available_tools,
    flags_from_run_record,
    load_csv_rows,
    map_transcript_turns_to_csv,
    rung_from_flags,
    score_run,
    score_turn_calls,
)

FIXTURE_RUNG6 = (
    Path(__file__).resolve().parent
    / "fixtures"
    / "process_metric"
    / "rung6_guard_judge"
)


RUNG1_TOOLS = frozenset(
    {
        "no_lookup_needed",
        "get_typing",
        "get_abilities",
        "check_species_ability",
        "check_species_legal",
        "check_item_legal",
        "get_move_static",
        "get_speed",
        "calc_damage",
        "get_usage_items",
        "get_usage_teammates",
        "lock_slot",
        "unlock_slot",
        "reset_team",
        "commit_slot",
        "read_team",
        "read_pending",
        "select_option",
        "confirm_build",
        "reject_pending",
        "reject_option",
        "reject_all",
        "read_rejected",
        "edit_slot_field",
        "add_constraint",
        "read_constraints",
        "restore_constraint",
        "show_candidates",
        "check_learnset",
        "change_archetype",
        "read_archetype",
        "find_species",
        "check_hypothetical",
        "solve_spread",
    }
)


def _csv(**kwargs) -> dict[str, str]:
    base = {
        "row_id": "X",
        "turn": "1",
        "proposed_guard_class": "LOOKUP",
        "guard_class_override": "",
        "expected_tools_ordered": "",
        "alternative_path": "",
        "optional_tools": "",
        "new_tool_needed": "",
        "user_turn_text": "",
    }
    base.update({k: str(v) for k, v in kwargs.items()})
    return base


def _call(name: str, args: dict | None = None, *, status: str = "ok", result: dict | None = None):
    return {
        "name": name,
        "args": args or {},
        "result_status": status,
        "result": result if result is not None else {"ok": True},
    }


def test_rung_from_flags():
    assert rung_from_flags({}) == 1
    assert rung_from_flags({"tool_fields": True}) == 2
    assert rung_from_flags({"tool_fields": True, "wrapper": True}) == 3
    assert rung_from_flags({"tool_fields": True, "wrapper": True, "draft": True}) == 4
    assert rung_from_flags({"tool_fields": True, "wrapper": True, "draft": True, "guard": True}) == 5
    assert (
        rung_from_flags(
            {
                "tool_fields": True,
                "wrapper": True,
                "draft": True,
                "guard": True,
                "judge": True,
            }
        )
        == 6
    )


def test_or_path_expected_only():
    csv = _csv(expected_tools_ordered="get_typing", proposed_guard_class="LOOKUP")
    s = score_turn_calls(
        row_id="H1",
        turn=1,
        rung=1,
        effective_cls="LOOKUP",
        csv_row=csv,
        calls=[_call("get_typing", {"species": "Toxapex"})],
        user_text="What type is Toxapex?",
        available=RUNG1_TOOLS,
    )
    assert s.requirement_default == "met"
    assert s.path_used == "expected"


def test_or_path_alternative_only():
    csv = _csv(
        expected_tools_ordered="get_featured_builds",
        alternative_path="find_species",
        proposed_guard_class="LOOKUP",
        new_tool_needed="get_featured_builds",
    )
    # expected unavailable; alternative used
    s = score_turn_calls(
        row_id="X",
        turn=1,
        rung=1,
        effective_cls="LOOKUP",
        csv_row=csv,
        calls=[_call("find_species", {"types": ["Water"]})],
        user_text="Water types",
        available=RUNG1_TOOLS,
    )
    assert s.requirement_default == "met"
    assert s.path_used == "alternative"


def test_or_path_both():
    csv = _csv(
        expected_tools_ordered="get_typing",
        alternative_path="get_abilities",
        proposed_guard_class="LOOKUP",
    )
    s = score_turn_calls(
        row_id="X",
        turn=1,
        rung=1,
        effective_cls="LOOKUP",
        csv_row=csv,
        calls=[
            _call("get_typing", {"species": "Toxapex"}),
            _call("get_abilities", {"species": "Toxapex"}),
        ],
        user_text="Toxapex",
        available=RUNG1_TOOLS,
    )
    assert s.requirement_default == "met"
    assert s.path_used == "both"


def test_or_path_neither():
    csv = _csv(expected_tools_ordered="get_typing", proposed_guard_class="LOOKUP")
    s = score_turn_calls(
        row_id="X",
        turn=1,
        rung=1,
        effective_cls="LOOKUP",
        csv_row=csv,
        calls=[_call("read_team")],
        user_text="?",
        available=RUNG1_TOOLS,
    )
    assert s.requirement_default == "missed"
    assert "get_typing" in s.missing_steps


def test_a_or_b_step():
    csv = _csv(
        expected_tools_ordered="get_typing|no_lookup_needed",
        proposed_guard_class="LOOKUP",
    )
    s = score_turn_calls(
        row_id="HD1",
        turn=2,
        rung=1,
        effective_cls="LOOKUP",
        csv_row=csv,
        calls=[_call("no_lookup_needed", {"reason": "x"})],
        user_text="No, Toxapex is not Water/Poison",
        available=RUNG1_TOOLS,
    )
    assert s.requirement_default == "met"


def test_order_true_and_false():
    csv = _csv(
        expected_tools_ordered="read_team;lock_slot",
        proposed_guard_class="WRITE",
        guard_class_override="WRITE",
    )
    ok = score_turn_calls(
        row_id="X",
        turn=1,
        rung=1,
        effective_cls="WRITE",
        csv_row=csv,
        calls=[_call("read_team"), _call("lock_slot", {"slot": 1, "species": "Pelipper"})],
        user_text="Lock Pelipper",
        available=RUNG1_TOOLS,
    )
    assert ok.order_ok is True
    assert ok.order_write_before_lookup is False
    bad = score_turn_calls(
        row_id="X",
        turn=1,
        rung=1,
        effective_cls="WRITE",
        csv_row=csv,
        calls=[_call("lock_slot", {"slot": 1, "species": "Pelipper"}), _call("read_team")],
        user_text="Lock Pelipper",
        available=RUNG1_TOOLS,
    )
    assert bad.order_ok is False
    assert bad.order_write_before_lookup is True
    assert bad.requirement_default == "met"  # order never changes requirement


def test_order_ok_ignores_never_called_lookup():
    """A required pre-write lookup that was never called is a miss, not order_ok=false."""
    csv = _csv(
        expected_tools_ordered="read_team;lock_slot",
        proposed_guard_class="WRITE",
    )
    s = score_turn_calls(
        row_id="X",
        turn=1,
        rung=1,
        effective_cls="WRITE",
        csv_row=csv,
        calls=[_call("lock_slot", {"slot": 1, "species": "Pelipper"})],
        user_text="Lock Pelipper",
        available=RUNG1_TOOLS,
    )
    assert s.requirement_default == "missed"
    assert "read_team" in s.missing_steps
    assert s.order_ok is True
    assert s.order_write_before_lookup is False


def test_protocol_read_team_before_write():
    csv = _csv(expected_tools_ordered="lock_slot", proposed_guard_class="WRITE")
    s = score_turn_calls(
        row_id="X",
        turn=1,
        rung=1,
        effective_cls="WRITE",
        csv_row=csv,
        calls=[_call("read_team"), _call("lock_slot", {"slot": 1, "species": "A"})],
        user_text="Lock A",
        available=RUNG1_TOOLS,
    )
    assert s.calls[0].default_mark == "ok"
    assert s.n_extra == 0


def test_find_species_legality_is_redundant_not_protocol():
    csv = _csv(expected_tools_ordered="find_species", proposed_guard_class="LOOKUP")
    s = score_turn_calls(
        row_id="X",
        turn=1,
        rung=1,
        effective_cls="LOOKUP",
        csv_row=csv,
        calls=[
            _call("find_species", {"types": ["Water"]}, result={"species": ["Pelipper", "Toxapex"], "status": "ok"}),
            _call("check_species_legal", {"species": "Pelipper"}),
        ],
        user_text="Water types",
        available=RUNG1_TOOLS,
    )
    assert s.calls[1].default_mark == "redundant"
    assert s.n_redundant >= 1


def test_tool_absent_at_rung_is_structural_miss():
    """Path names a tool that does not exist at this rung → missed + structural=true."""
    csv = _csv(
        expected_tools_ordered="describe",
        proposed_guard_class="LOOKUP",
        new_tool_needed="",
    )
    # describe not in RUNG1_TOOLS
    s = score_turn_calls(
        row_id="GS1",
        turn=1,
        rung=1,
        effective_cls="LOOKUP",
        csv_row=csv,
        calls=[],
        user_text="Describe Pelipper",
        available=RUNG1_TOOLS,
    )
    assert s.requirement_default == "missed"
    assert s.structural is True
    assert "describe" in s.missing_steps


def test_tool_absent_with_available_alt_is_behavioral_miss():
    csv = _csv(
        expected_tools_ordered="set_constraint_active",
        alternative_path="add_constraint",
        proposed_guard_class="WRITE",
    )
    s = score_turn_calls(
        row_id="MT6",
        turn=2,
        rung=1,
        effective_cls="WRITE",
        csv_row=csv,
        calls=[],
        user_text="Keep Water only",
        available=RUNG1_TOOLS,
    )
    assert s.requirement_default == "missed"
    assert s.structural is False


def test_new_tool_needed_no_path_not_scorable():
    csv = _csv(
        expected_tools_ordered="",
        alternative_path="",
        new_tool_needed="get_featured_builds",
        proposed_guard_class="LOOKUP",
    )
    s = score_turn_calls(
        row_id="X",
        turn=1,
        rung=1,
        effective_cls="LOOKUP",
        csv_row=csv,
        calls=[],
        user_text="featured",
        available=RUNG1_TOOLS,
    )
    assert s.requirement_default == "not_scorable"
    assert s.structural is False


def test_rung1_set_slot_equivalence():
    csv = _csv(expected_tools_ordered="set_slot", proposed_guard_class="WRITE")
    s = score_turn_calls(
        row_id="MR4",
        turn=1,
        rung=1,
        effective_cls="WRITE",
        csv_row=csv,
        calls=[_call("lock_slot", {"slot": 1, "species": "Garchomp"})],
        user_text="Garchomp",
        available=RUNG1_TOOLS,
    )
    assert s.requirement_default == "met"
    assert SET_SLOT_EQUIV & RUNG1_TOOLS


def test_misused_write_on_lookup_class():
    csv = _csv(expected_tools_ordered="get_typing", proposed_guard_class="LOOKUP")
    s = score_turn_calls(
        row_id="X",
        turn=1,
        rung=1,
        effective_cls="LOOKUP",
        csv_row=csv,
        calls=[
            _call("get_typing", {"species": "Toxapex"}),
            _call("lock_slot", {"slot": 1, "species": "Toxapex"}),
        ],
        user_text="What type is Toxapex?",
        available=RUNG1_TOOLS,
    )
    assert s.n_misused >= 1
    assert any(c.default_mark == "misused" for c in s.calls if c.name == "lock_slot")


def test_replace_true_misused_unless_pending_answer():
    csv = _csv(expected_tools_ordered="set_slot", proposed_guard_class="WRITE")
    # rung with set_slot available — add it to tools for this test
    tools = RUNG1_TOOLS | {"set_slot"}
    s = score_turn_calls(
        row_id="X",
        turn=1,
        rung=4,
        effective_cls="WRITE",
        csv_row=csv,
        calls=[_call("set_slot", {"slot": 1, "species": "A", "replace": True})],
        user_text="Put A in slot 1",
        available=tools,
    )
    assert s.n_misused >= 1
    s2 = score_turn_calls(
        row_id="X",
        turn=1,
        rung=4,
        effective_cls="PENDING_ANSWER",
        csv_row=_csv(expected_tools_ordered="set_slot", proposed_guard_class="PENDING_ANSWER"),
        calls=[_call("set_slot", {"slot": 1, "species": "A", "replace": True})],
        user_text="yes replace",
        available=tools,
    )
    assert s2.n_misused == 0


def test_guard_blocked_counts_refused_and_flag():
    csv = _csv(expected_tools_ordered="get_typing", proposed_guard_class="ASK")
    s = score_turn_calls(
        row_id="X",
        turn=1,
        rung=5,
        effective_cls="ASK",
        csv_row=csv,
        calls=[
            {
                "name": "get_typing",
                "args": {"species": "Toxapex"},
                "result_status": "refused",
                "result": {"guard_blocked": True, "status": "refused"},
            }
        ],
        user_text="?",
        available=RUNG1_TOOLS,
    )
    assert s.n_refused >= 1
    assert s.n_guard_blocked >= 1
    assert s.calls[0].guard_blocked is True


def test_identical_repeat_redundant():
    csv = _csv(expected_tools_ordered="get_typing", proposed_guard_class="LOOKUP")
    s = score_turn_calls(
        row_id="X",
        turn=1,
        rung=1,
        effective_cls="LOOKUP",
        csv_row=csv,
        calls=[
            _call("get_typing", {"species": "Toxapex"}),
            _call("get_typing", {"species": "Toxapex"}),
        ],
        user_text="Toxapex",
        available=RUNG1_TOOLS,
    )
    assert s.n_redundant >= 1
    assert s.calls[1].default_mark == "redundant"


def test_map_transcript_seeded_prefix():
    assert map_transcript_turns_to_csv("HC2", 1, [1, 2]) == [(1, 2)]
    assert map_transcript_turns_to_csv("HD1", 1, [1, 2]) == [(1, 2)]
    assert map_transcript_turns_to_csv("MT3", 2, [1, 2, 3]) == [(1, 2), (2, 3)]
    assert map_transcript_turns_to_csv("H1", 1, [1]) == [(1, 1)]


def test_flags_from_legacy_run_record():
    flags = flags_from_run_record({"tool_set": ["get_typing"], "tool_schema_sha256": "x"})
    assert flags["tool_fields"] is False
    assert rung_from_flags(flags) == 1
    tools = available_tools({"tool_set": ["get_typing", "lock_slot"]}, flags)
    assert tools == frozenset({"get_typing", "lock_slot"})


def test_rung6_guard_judge_fixture_end_to_end():
    """Scorer tolerates real rung-5/6 turn fields and counts guard-blocked as refused."""
    transcript = json.loads((FIXTURE_RUNG6 / "transcript.json").read_text(encoding="utf-8"))
    run_record = json.loads((FIXTURE_RUNG6 / "run_record.json").read_text(encoding="utf-8"))
    csv_rows = load_csv_rows(FIXTURE_RUNG6 / "expected_tools.csv")
    # Confirm fixture carries the real record fields
    t0 = transcript[0]["turns"][0]
    for key in (
        "blocked_calls",
        "allowed_tools",
        "guard_class",
        "judge",
        "fallback",
    ):
        assert key in t0
    assert "retries" in t0["judge"]
    t1 = transcript[1]["turns"][0]
    assert t1["fallback"] is True
    assert t1["judge"]["retries"] == 1

    scores, summary, _path_absent = score_run(
        transcript=transcript, run_record=run_record, csv_rows=csv_rows
    )
    assert summary["rung"] == 6
    by_key = {(s.row_id, s.turn): s for s in scores if s.requirement_default != "no_run_record"}
    fx1 = by_key[("FX1", 1)]
    assert fx1.requirement_default == "met"
    assert fx1.n_guard_blocked >= 1
    assert fx1.n_refused >= 1
    assert any(c.guard_blocked for c in fx1.calls)
    assert summary["n_guard_blocked"] >= 1
    fx2 = by_key[("FX2", 1)]
    assert fx2.requirement_default == "met"
    assert fx2.order_ok is True
    assert fx2.n_misused == 0
