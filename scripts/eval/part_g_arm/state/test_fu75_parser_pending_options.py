"""FU75: parser_pending_options flag — summary field + profile + prompt-po."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.eval.part_g_arm.state.fixtures import empty_team
from scripts.eval.part_g_arm.state.graded_turn_texts import overlapping_4grams
from scripts.eval.part_g_arm.state.guard_parser import (
    PARSER_PROMPT_PATH,
    PARSER_PROMPT_PO_PATH,
    compact_state_summary,
    parser_prompt_sha256,
)
from scripts.eval.part_g_arm.state.pending import try_load_fixture
from scripts.eval.part_g_arm.state.tools import (
    parser_pending_options_enabled,
    set_parser_pending_options,
    set_parser_v2,
)

HERE = Path(__file__).resolve().parent


@pytest.fixture(autouse=True)
def _reset_flags():
    set_parser_pending_options(False)
    set_parser_v2(False)
    yield
    set_parser_pending_options(False)
    set_parser_v2(False)


def test_flag_default_off():
    assert parser_pending_options_enabled() is False


def test_summary_omits_pending_options_when_flag_off():
    result = try_load_fixture("OL2b")
    assert result["loaded"] and result["state"] is not None
    summary = compact_state_summary(result["state"])
    assert "pending_options" not in summary
    assert summary["pending_kind"] == "candidate_selection"


def test_summary_includes_options_for_candidate_selection():
    result = try_load_fixture("OL2b")
    assert result["loaded"] and result["state"] is not None
    set_parser_pending_options(True)
    summary = compact_state_summary(result["state"])
    assert summary["pending_kind"] == "candidate_selection"
    assert summary["pending_options"] == [
        {"index": 1, "label": "Garchomp"},
        {"index": 2, "label": "Incineroar"},
        {"index": 3, "label": "Jolteon"},
    ]


def test_summary_empty_options_when_no_pending_screen():
    set_parser_pending_options(True)
    summary = compact_state_summary(empty_team())
    assert summary["pending_kind"] is None
    assert summary["pending_options"] == []


def test_revised_arm_profile_includes_parser_pending_options():
    from scripts.eval.part_g_arm.state.request_set_runner import (
        DEFAULT_RUN_FLAGS,
        REVISED_ARM_PROFILE_FLAGS,
    )

    assert DEFAULT_RUN_FLAGS["parser_pending_options"] is False
    assert REVISED_ARM_PROFILE_FLAGS["parser_pending_options"] is True
    resolved = {**DEFAULT_RUN_FLAGS, **REVISED_ARM_PROFILE_FLAGS}
    assert resolved["parser_pending_options"] is True
    assert resolved["parser_v2"] is False


def test_cli_rejects_parser_pending_options_without_guard(tmp_path):
    from scripts.eval.part_g_arm.state import request_set_runner as rsr

    with pytest.raises(SystemExit, match="require the guard rung"):
        rsr.main(["--parser-pending-options", "--row", "DM1", "--stub", str(tmp_path)])


def test_po_prompt_differs_and_no_graded_4gram_overlap():
    v1 = PARSER_PROMPT_PATH.read_text(encoding="utf-8")
    po = PARSER_PROMPT_PO_PATH.read_text(encoding="utf-8")
    assert po != v1
    assert "pending_options" in po
    assert overlapping_4grams(po) == set()


def test_po_prompt_selected_when_flag_on():
    sha_off = parser_prompt_sha256()
    set_parser_pending_options(True)
    sha_on = parser_prompt_sha256()
    assert sha_on != sha_off
    assert sha_on == __import__("hashlib").sha256(PARSER_PROMPT_PO_PATH.read_bytes()).hexdigest()


def test_process_metric_mirrors_flag():
    from scripts.eval.part_g_arm.state.process_metric_scorer import flags_from_run_record

    flags = flags_from_run_record(
        {"run_flags": {"guard": True, "parser_pending_options": True}}
    )
    assert flags["parser_pending_options"] is True
