"""FU18: HC2 / HD1 / MT3 play all request-set turns live; t2 carries t1 process flags."""

from __future__ import annotations

from scripts.eval.part_g_arm.state.request_set_rows import (
    load_request_rows,
    resolve_start_state,
    turns_for_row,
)
def _rows():
    return {r["id"]: r for r in load_request_rows()}


def test_hc2_mt3_hd1_play_all_turns_from_empty():
    rows = _rows()
    for rid, n in (("HC2", 2), ("MT3", 3), ("HD1", 2)):
        st, meta = resolve_start_state(rows[rid])
        assert st is not None
        assert "empty_team" in (meta.get("source") or "")
        live = turns_for_row(rows[rid], st)
        assert len(live) == n, (rid, live)


def test_hd1_live_texts():
    rows = _rows()
    st, _ = resolve_start_state(rows["HD1"])
    assert turns_for_row(rows["HD1"], st) == [
        "What type is Toxapex?",
        "No, Toxapex is not Water/Poison",
    ]


def test_stamp_t1_process_flags():
    from scripts.eval.part_g_arm.state.request_set_runner import stamp_t1_process_flags

    mt3 = [
        {"tool_calls": [{"name": "add_constraint"}]},
        {"tool_calls": []},
    ]
    stamp_t1_process_flags("MT3", mt3)
    assert mt3[1]["t1_add_constraint_called"] is True
    mt3_miss = [{"tool_calls": [{"name": "read_team"}]}, {"tool_calls": []}]
    stamp_t1_process_flags("MT3", mt3_miss)
    assert mt3_miss[1]["t1_add_constraint_called"] is False

    hd1 = [
        {"tool_calls": [{"name": "get_typing"}]},
        {"tool_calls": []},
    ]
    stamp_t1_process_flags("HD1", hd1)
    assert hd1[1]["t1_get_typing_called"] is True
