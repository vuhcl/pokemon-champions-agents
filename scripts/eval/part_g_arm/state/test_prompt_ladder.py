"""wrapper/draft prompts must stay tool_fields + documented rung deltas."""

from __future__ import annotations

from scripts.eval.part_g_arm.config import ArmConfig
from scripts.eval.part_g_arm.state.prompt_ladder import (
    DRAFT,
    TOOL_FIELDS,
    WRAPPER,
    build_draft_from_wrapper,
    build_wrapper_from_tool_fields,
)
from scripts.eval.part_g_arm.state.request_set_rows import FROZEN_PROMPT_SHA256
from scripts.eval.part_g_arm.state.request_set_runner import (
    DRAFT_PROMPT_FILE,
    TOOL_FIELDS_PROMPT_FILE,
    WRAPPER_PROMPT_FILE,
)
from scripts.eval.part_g_arm.state.tools import combined_specs


def test_wrapper_is_tool_fields_plus_delta():
    expected = build_wrapper_from_tool_fields(TOOL_FIELDS.read_text(encoding="utf-8"))
    assert WRAPPER.read_text(encoding="utf-8") == expected


def test_draft_is_wrapper_plus_delta():
    wrapper = build_wrapper_from_tool_fields(TOOL_FIELDS.read_text(encoding="utf-8"))
    expected = build_draft_from_wrapper(wrapper)
    assert DRAFT.read_text(encoding="utf-8") == expected


def test_flags_off_prompt_and_schema_still_pre_rs_arm():
    cfg = ArmConfig(prompt_file="state/prompt.md")
    assert cfg.prompt_hash() == FROZEN_PROMPT_SHA256
    import hashlib
    import json

    sha = hashlib.sha256(json.dumps(combined_specs(), sort_keys=True).encode()).hexdigest()
    assert sha == "f0c97ad3b88cb3f118e241111bd454a4e86f7937cd4342f0969cadbe5049b845"


def test_rung_prompt_shas_distinct_from_frozen():
    tf = ArmConfig(prompt_file=TOOL_FIELDS_PROMPT_FILE).prompt_hash()
    wr = ArmConfig(prompt_file=WRAPPER_PROMPT_FILE).prompt_hash()
    dr = ArmConfig(prompt_file=DRAFT_PROMPT_FILE).prompt_hash()
    assert len({tf, wr, dr, FROZEN_PROMPT_SHA256}) == 4
    # Printed for FU18 report (not frozen constants — ladder text still moves).
    print(f"tool_fields_sha={tf}")
    print(f"wrapper_sha={wr}")
    print(f"draft_sha={dr}")
