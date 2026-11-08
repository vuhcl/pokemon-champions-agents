"""FU74: revised-arm wiring (keys, flags, seeds, prompt cut, isolation)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.eval.part_g_arm.state.guard_exec import (
    REFUSAL_MESSAGE_LEGACY,
    REFUSAL_MESSAGE_PROMPT_CUT,
    _refusal_message,
)
from scripts.eval.part_g_arm.state.revised_keys import (
    FU74_SEED_ROWS,
    apply_turn_text_override,
    key_set,
    load_fu74_seed_state,
    load_request_text_overrides,
    merge_hand_turns,
    pin_hashes_for_key_set,
    points_by_row_id,
    rev5_user_turn_text,
    set_key_set,
)
from scripts.eval.part_g_arm.state.request_set_rows import turns_for_row
from scripts.eval.part_g_arm.state.tools import (
    parser_v2_enabled,
    prompt_cut_enabled,
    set_ix_tools_v1,
    set_parser_v2,
    set_prompt_cut,
    ix_tools_v1_enabled,
)

HERE = Path(__file__).resolve().parent


@pytest.fixture(autouse=True)
def _reset_flags():
    set_key_set("committed")
    set_ix_tools_v1(False)
    set_prompt_cut(False)
    set_parser_v2(False)
    yield
    set_key_set("committed")
    set_ix_tools_v1(False)
    set_prompt_cut(False)
    set_parser_v2(False)


def test_merged_keys_replace_ix_not_merge_points():
    turns = merge_hand_turns("fu74")
    assert "IX1__t1" in turns
    assert turns["IX1__t1"]["points"][0]["text"].startswith("The arm states what it means")
    # Exactly one turn key per IX row.
    ix_keys = [k for k in turns if k.startswith("IX")]
    assert sorted(ix_keys) == ["IX1__t1", "IX5__t1", "IX7__t1"]
    fu72 = json.loads((HERE / "keys_fu72" / "hand_keys_fu72.json").read_text())
    assert fu72["turns"]["IX1__t1"]["points"][0]["text"] != turns["IX1__t1"]["points"][0]["text"]


def test_fu74_points_bypass_errata_acceptance():
    from scripts.eval.part_g_arm.state.errata_read import acceptance_with_key_overrides
    from scripts.eval.part_g_arm.state.hand_audit_form import build_sections_from_transcript

    pts = points_by_row_id("fu74")
    assert "IX1" in pts
    # Errata may rewrite some rows; when points_by_id is set, those points win alone.
    transcript = [{"id": "IX1", "turns": [{"user": "x", "final_text": "y"}]}]
    sections = build_sections_from_transcript(
        transcript,
        acceptance_by_id={"IX1": "old;acceptance;text"},
        points_by_id=pts,
    )
    assert len(sections) == 1
    texts = [p["text"] for p in sections[0]["points"]]
    assert any("redirection" in t for t in texts)
    assert "old" not in texts[0]
    # Sanity: errata path still exists for committed (no points_by_id).
    _ = acceptance_with_key_overrides


def test_request_text_overrides_match_rev5():
    set_key_set("fu74")
    overrides = load_request_text_overrides("fu74")
    assert overrides
    for key, text in overrides.items():
        rid, _, turn = key.partition("__t")
        csv_text = rev5_user_turn_text(rid, int(turn))
        assert csv_text == text, (key, csv_text, text)
        played = apply_turn_text_override(rid, int(turn) - 1, "ORIGINAL", key_set="fu74")
        assert played == text


def test_overrides_off_by_default():
    assert load_request_text_overrides("committed") == {}
    assert apply_turn_text_override("MR2", 0, "orig", key_set="committed") == "orig"


def test_fu74_seeds_only_under_option():
    set_key_set("committed")
    # Default path must not use fu74 seed loader for MR4.
    from scripts.eval.part_g_arm.state.request_set_rows import resolve_start_state

    st, meta = resolve_start_state({"id": "MR4", "state": "two locked"})
    assert st is not None
    assert "keys_fu72/seeds" not in str(meta.get("source"))

    set_key_set("fu74")
    st2, meta2 = load_fu74_seed_state("MR4")
    assert st2 is not None
    assert "mr4_incineroar_garchomp_item_unlocked" in str(meta2.get("source") or meta2.get("seed_file"))
    # Item unlocked on both.
    slot0 = st2["team_draft"][0]
    assert slot0.item.value is not None
    assert slot0.item.locked is False
    assert slot0.species.locked is True


def test_seed_rows_cover_brief_list():
    assert FU74_SEED_ROWS == frozenset(
        {"DM2", "H18b", "MR3", "MR4", "MS2", "MS3", "MW2", "RB1", "TB2"}
    )


def test_pin_hashes_fu74_include_seeds_and_revised_hash():
    pins = pin_hashes_for_key_set("fu74")
    assert pins["key_set"] == "fu74"
    assert "revised_key_hash" in pins
    assert "seed_index_sha256" in pins
    assert "seed_mr4_incineroar_garchomp_item_unlocked.v1.json_sha256" in pins


def test_refusal_message_prompt_cut():
    set_prompt_cut(False)
    legacy = _refusal_message(name="set_slot", cls="ASK")
    assert "set_slot" in legacy and "ASK" in legacy
    assert legacy == REFUSAL_MESSAGE_LEGACY.format(name="set_slot", cls="ASK")
    set_prompt_cut(True)
    cut = _refusal_message(name="set_slot", cls="ASK")
    assert cut == REFUSAL_MESSAGE_PROMPT_CUT
    assert "set_slot" not in cut and "ASK" not in cut


def test_prompt_cut_and_parser_v2_flags_default_off():
    assert prompt_cut_enabled() is False
    assert parser_v2_enabled() is False
    assert ix_tools_v1_enabled() is False


def test_turns_for_row_applies_override_under_fu74():
    set_key_set("fu74")
    row = {"id": "MR2", "prompt": "Lock Choice Specs on a legal mon"}
    turns = turns_for_row(row, None)
    assert turns == ["Lock Choice Specs on Hatterene"]


def test_cli_rejects_prompt_cut_without_guard(tmp_path):
    from scripts.eval.part_g_arm.state import request_set_runner as rsr

    with pytest.raises(SystemExit, match="require the guard rung"):
        rsr.main(["--prompt-cut", "--row", "DM1", "--stub", str(tmp_path)])


def test_cli_rejects_parser_v2_without_guard(tmp_path):
    from scripts.eval.part_g_arm.state import request_set_runner as rsr

    with pytest.raises(SystemExit, match="require the guard rung"):
        rsr.main(["--parser-v2", "--row", "DM1", "--stub", str(tmp_path)])

def test_default_run_flags_include_fu74_offs():
    from scripts.eval.part_g_arm.state.request_set_runner import DEFAULT_RUN_FLAGS

    assert DEFAULT_RUN_FLAGS["ix_tools_v1"] is False
    assert DEFAULT_RUN_FLAGS["prompt_cut"] is False
    assert DEFAULT_RUN_FLAGS["parser_v2"] is False


def test_process_metric_flags_include_ix_tools():
    from scripts.eval.part_g_arm.state.process_metric_scorer import flags_from_run_record

    flags = flags_from_run_record(
        {
            "run_flags": {
                "tool_fields": True,
                "wrapper": True,
                "draft": True,
                "guard": True,
                "judge": False,
                "sticky_locks": True,
                "unlock_keeps_values": True,
                "tool_fixes_v2": True,
                "ix_tools_v1": True,
                "prompt_cut": True,
                "parser_v2": True,
            }
        }
    )
    assert flags["ix_tools_v1"] is True
    assert flags["prompt_cut"] is True
    assert flags["parser_v2"] is True


def test_prompt_guard_cut_differs_from_guard():
    guard = (HERE / "prompt_guard.md").read_text(encoding="utf-8")
    cut = (HERE / "prompt_guard_cut.md").read_text(encoding="utf-8")
    assert guard != cut
    assert "clear_slot" in cut
    assert "wipes an occupied slot" not in cut
    assert "naming the class of the request" not in cut
    assert "Do not name internal tool names" in cut


def test_parser_v2_prompt_exists_and_differs():
    v1 = (HERE / "prompt_guard_parser.md").read_text(encoding="utf-8")
    v2 = (HERE / "prompt_guard_parser_v2.md").read_text(encoding="utf-8")
    assert v1 != v2
    assert "write the guard may refuse is still WRITE" in v2
