"""Archetype signature None ↔ empty normalization for mechanical_class."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.eval.part_g_arm.state.tools import mechanical_class

RUN1 = Path("/Users/nowaki027/part-g-arm-runs/pre-rs-arm/b98568d/run_1/transcript.json")


def _turn(row_id: str, turn_i: int = 0) -> dict:
    tr = json.loads(RUN1.read_text(encoding="utf-8"))
    row = next(r for r in tr if r["id"] == row_id)
    return row["turns"][turn_i]


def test_ms3_t1_none_to_empty_is_no_change():
    t = _turn("MS3", 0)
    assert t["state_before"].get("archetype_sig") is None
    assert t["state_after"].get("archetype_sig") == [[], False]
    # As-run label was wrote; with normalization it must be no change.
    assert (
        mechanical_class(t["state_before"], t["state_after"], t.get("tool_calls") or [])
        == "no change"
    )


def test_mu6_t1_none_to_empty_is_no_change():
    t = _turn("MU6", 0)
    assert t["state_before"].get("archetype_sig") is None
    assert t["state_after"].get("archetype_sig") == [[], False]
    assert (
        mechanical_class(t["state_before"], t["state_after"], t.get("tool_calls") or [])
        == "no change"
    )


def test_h13_t1_none_to_rain_still_wrote():
    t = _turn("H13", 0)
    assert t["state_before"].get("archetype_sig") is None
    after = t["state_after"].get("archetype_sig")
    assert after and after[0], after
    assert (
        mechanical_class(t["state_before"], t["state_after"], t.get("tool_calls") or [])
        == "wrote"
    )
