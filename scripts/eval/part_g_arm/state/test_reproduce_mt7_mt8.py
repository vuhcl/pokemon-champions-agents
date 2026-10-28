"""Part 3 stop-rule checks (no model). ~30s in-process calc."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("PART_G_V4_CALC_BACKEND", "inprocess")

from scripts.eval.part_g_arm.state.reproduce_mt7_mt8 import CASES, run_case


@pytest.mark.parametrize("name", list(CASES))
def test_mt7_mt8_case_matches_key_feasibility(name: str):
    row = run_case(name, CASES[name])
    assert row["pass"], row
