"""FU74 review: parser v2 no graded overlap; prompt-cut schema + model-facing refusal."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from recommender.arm_tools import dumps
from scripts.eval.part_g_arm.state.graded_turn_texts import overlapping_4grams
from scripts.eval.part_g_arm.state.guard_exec import (
    REFUSAL_MESSAGE_LEGACY,
    REFUSAL_MESSAGE_PROMPT_CUT,
    check_call,
    model_facing_tool_result,
)
from scripts.eval.part_g_arm.state.tools import (
    combined_specs,
    set_draft,
    set_guard,
    set_ix_tools_v1,
    set_parser_v2,
    set_prompt_cut,
    set_tool_fields,
    set_tool_fixes_v2,
    set_unlock_keeps_values,
    set_wrapper,
)

HERE = Path(__file__).resolve().parent
PARSER_V2 = HERE / "prompt_guard_parser_v2.md"
PROMPT_CUT = HERE / "prompt_guard_cut.md"
DEV_FU74 = HERE / "dev_guard_parser_labels_fu74.json"

_TOOL_LINE = re.compile(
    r"^-\s*([a-z_][a-z0-9_]*)\s*(?:\(([^)]*)\))?",
    re.MULTILINE,
)


@pytest.fixture(autouse=True)
def _flags_off():
    set_prompt_cut(False)
    set_parser_v2(False)
    set_tool_fields(False)
    set_wrapper(False)
    set_draft(False)
    set_guard(False)
    set_unlock_keeps_values(False)
    set_ix_tools_v1(False)
    set_tool_fixes_v2(False)
    yield
    set_prompt_cut(False)
    set_parser_v2(False)
    set_tool_fields(False)
    set_wrapper(False)
    set_draft(False)
    set_guard(False)
    set_unlock_keeps_values(False)
    set_ix_tools_v1(False)
    set_tool_fixes_v2(False)


def test_parser_v2_prompt_no_graded_4gram_overlap():
    text = PARSER_V2.read_text(encoding="utf-8")
    assert overlapping_4grams(text) == set()


def test_fu74_dev_labels_no_graded_4gram_overlap():
    doc = json.loads(DEV_FU74.read_text(encoding="utf-8"))
    assert len(doc["rows"]) >= 15
    for row in doc["rows"]:
        ov = overlapping_4grams(row["text"])
        assert ov == set(), (row["id"], ov)


def test_prompt_cut_tools_registered_under_profile():
    """Every tool name cited in prompt_guard_cut.md is bound under revised-arm schemas."""
    set_tool_fields(True)
    set_wrapper(True)
    set_draft(True)
    set_guard(True)
    set_unlock_keeps_values(True)
    set_ix_tools_v1(True)
    specs = combined_specs(tool_fields=True, wrapper=True, draft=True)
    by_name = {s["function"]["name"]: s["function"] for s in specs}
    assert "clear_slot" in by_name
    assert "unlock_slot" in by_name
    # unlock_slot(slot) — no replace under unlock_keeps_values
    unlock_props = by_name["unlock_slot"]["parameters"]["properties"]
    assert "slot" in unlock_props
    assert "replace" not in unlock_props
    clear_props = by_name["clear_slot"]["parameters"]["properties"]
    assert "slot" in clear_props
    assert "replace" in clear_props

    prompt = PROMPT_CUT.read_text(encoding="utf-8")
    cited: dict[str, str | None] = {}
    for m in _TOOL_LINE.finditer(prompt):
        cited[m.group(1)] = m.group(2)
    # clear_slot is mentioned mid-line next to unlock_slot; catch both shapes.
    clear_m = re.search(r"clear_slot\(([^)]*)\)", prompt)
    assert clear_m, "prompt_guard_cut.md must document clear_slot(…)"
    cited["clear_slot"] = clear_m.group(1)
    for name, args in cited.items():
        if name not in by_name:
            continue
        assert name in by_name, name
    assert "unlock_slot" in cited
    assert "clear_slot" in by_name
    assert cited["unlock_slot"] is not None and "slot" in cited["unlock_slot"]
    assert "replace" not in (cited["unlock_slot"] or "")
    assert cited["clear_slot"] is not None and "replace" in cited["clear_slot"]


def test_model_facing_refusal_strips_tool_and_class_under_prompt_cut():
    full = {
        "status": "refused",
        "guard_blocked": True,
        "tool": "set_slot",
        "args": {"slot": 1, "species": "Venusaur"},
        "reason": "tool not in allowed set for class ASK",
        "class": "ASK",
        "message": REFUSAL_MESSAGE_PROMPT_CUT,
    }
    set_prompt_cut(False)
    legacy_facing = model_facing_tool_result(full)
    assert legacy_facing.get("tool") == "set_slot"
    assert legacy_facing.get("class") == "ASK"
    legacy_ser = dumps(legacy_facing)
    assert "set_slot" in legacy_ser and "ASK" in legacy_ser

    set_prompt_cut(True)
    cut_facing = model_facing_tool_result(full)
    assert "tool" not in cut_facing
    assert "class" not in cut_facing
    assert "reason" not in cut_facing
    assert cut_facing["message"] == REFUSAL_MESSAGE_PROMPT_CUT
    cut_ser = dumps(cut_facing)
    assert "set_slot" not in cut_ser
    assert '"ASK"' not in cut_ser and "class ASK" not in cut_ser
    # Document exact strings for report_74.
    assert json.loads(legacy_ser)["tool"] == "set_slot"
    assert "tool" not in json.loads(cut_ser)


def test_check_call_refusal_full_result_still_has_fields_for_log():
    set_prompt_cut(True)
    refused = check_call(
        "set_slot",
        {"slot": 1},
        state={},
        guard_class="ASK",
        allowed=set(),
        confirms_replacement=False,
        pending_asked=None,
    )
    assert refused is not None
    assert refused["guard_blocked"] is True
    assert refused["tool"] == "set_slot"
    assert refused["class"] == "ASK"
    assert refused["message"] == REFUSAL_MESSAGE_PROMPT_CUT
    facing = model_facing_tool_result(refused)
    assert "tool" not in facing and "class" not in facing
