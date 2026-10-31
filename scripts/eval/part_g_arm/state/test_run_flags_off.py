"""Flags default off → PRE-RS-ARM prompt + tool schema identity."""

from __future__ import annotations

import hashlib
import json

from scripts.eval.part_g_arm.config import ArmConfig
from scripts.eval.part_g_arm.state.request_set_rows import FROZEN_PROMPT_SHA256
from scripts.eval.part_g_arm.state.request_set_runner import (
    DEFAULT_RUN_FLAGS,
    build_run_parameters,
)
from scripts.eval.part_g_arm.state.tools import combined_specs

# From LAST_DEV_RUN.md / PRE-RS-ARM freeze era.
PRE_RS_ARM_TOOL_SCHEMA_SHA256 = "f0c97ad3b88cb3f118e241111bd454a4e86f7937cd4342f0969cadbe5049b845"


def test_default_flags_all_off():
    assert DEFAULT_RUN_FLAGS == {
        "tool_fields": False,
        "wrapper": False,
        "guard": False,
        "judge": False,
    }


def test_flags_off_prompt_and_tool_schema_match_pre_rs_arm():
    cfg = ArmConfig(prompt_file="state/prompt.md")
    assert cfg.prompt_hash() == FROZEN_PROMPT_SHA256
    assert FROZEN_PROMPT_SHA256 == "bd2b69cde151fdb4dd2431c294ca46f4fbc251f54cebd82a13844d4eba0aaf86"
    specs = combined_specs()
    schema_sha = hashlib.sha256(json.dumps(specs, sort_keys=True).encode()).hexdigest()
    assert schema_sha == PRE_RS_ARM_TOOL_SCHEMA_SHA256
    rec = build_run_parameters(cfg, {"digest": "x"})
    assert rec["run_flags"] == DEFAULT_RUN_FLAGS
    assert rec["tool_schema_sha256"] == PRE_RS_ARM_TOOL_SCHEMA_SHA256
    assert rec["prompt_sha256"] == FROZEN_PROMPT_SHA256
