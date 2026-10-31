"""Unit tests for usage/meta read tools + derived_keys leaf compares (ADR-060)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from recommender.ids import to_id
from scripts.eval.part_g_arm.config import ArmConfig
from scripts.eval.part_g_arm.state.errata_read import load_derived_keys_effective
from scripts.eval.part_g_arm.state.request_set_rows import FROZEN_PROMPT_SHA256
from scripts.eval.part_g_arm.state.tools import combined_specs, set_tool_fields, set_wrapper
from scripts.eval.part_g_arm.state.usage_meta_tools import (
    USAGE_META_SPECS,
    get_common_speeds,
    get_meta_threats,
    get_usage_spreads,
    get_usage_stats,
)

PRE_RS_ARM_TOOL_SCHEMA_SHA256 = "f0c97ad3b88cb3f118e241111bd454a4e86f7937cd4342f0969cadbe5049b845"
KEYS = load_derived_keys_effective()
HERE = Path(__file__).resolve().parent


@pytest.fixture(autouse=True)
def _reset_flags():
    set_tool_fields(False)
    set_wrapper(False)
    yield
    set_tool_fields(False)
    set_wrapper(False)


def _schema_tokens(*, tool_fields: bool, wrapper: bool = False) -> int:
    return len(
        json.dumps(
            combined_specs(tool_fields=tool_fields, wrapper=wrapper),
            sort_keys=True,
        )
    )


def test_flags_off_byte_identical():
    set_tool_fields(False)
    set_wrapper(False)
    cfg = ArmConfig(prompt_file="state/prompt.md")
    assert cfg.prompt_hash() == FROZEN_PROMPT_SHA256
    sha = hashlib.sha256(json.dumps(combined_specs(), sort_keys=True).encode()).hexdigest()
    assert sha == PRE_RS_ARM_TOOL_SCHEMA_SHA256


def test_usage_meta_specs_only_when_tool_fields():
    names_off = {s["function"]["name"] for s in combined_specs(tool_fields=False)}
    names_on = {s["function"]["name"] for s in combined_specs(tool_fields=True)}
    for spec in USAGE_META_SPECS:
        n = spec["function"]["name"]
        assert n not in names_off
        assert n in names_on


def test_schema_tokens_per_tool_report(capsys):
    """Print incremental schema token deltas (one tool at a time) for the brief report."""
    base = combined_specs(tool_fields=True, wrapper=False)
    # Strip existing USAGE_META_SPECS if already appended.
    base_names = {s["function"]["name"] for s in USAGE_META_SPECS}
    without = [s for s in base if s["function"]["name"] not in base_names]
    prev = len(json.dumps(without, sort_keys=True))
    print(f"tool_fields_without_usage_meta tokens={prev}")
    for spec in USAGE_META_SPECS:
        without = [*without, spec]
        cur = len(json.dumps(without, sort_keys=True))
        print(f"+{spec['function']['name']} delta={cur - prev} tokens={cur}")
        prev = cur
    assert prev == _schema_tokens(tool_fields=True, wrapper=False)


def test_get_usage_spreads_showdown_top_matches_dm1_joint():
    r = get_usage_spreads("Incineroar")
    assert r["found"] is True
    sd = next(s for s in r["sources"] if s["source"] == "showdown")
    assert sd["limit"] == 8
    assert sd["listed"] <= 8
    assert sd["pct_kind"] == "chaos_weight"
    assert "not a percent" in sd["note"].lower() or "chaos" in sd["note"].lower()
    top = sd["spreads"][0]
    joint = KEYS["dm_outputs"]["shared_incineroar_top_joint"]["joint"]
    assert top["nature"] == joint["nature"]
    assert top["sp"] == joint["evs"]
    assert top["weight"] == joint["chaos_weight"]
    assert top["pct_kind"] == "chaos_weight"
    # In-game present and labeled rank-paired.
    ig = next(s for s in r["sources"] if s["source"] == "ingame")
    assert ig["pct_kind"] == "percent"
    assert "rank-paired" in ig["note"]


def test_get_usage_spreads_missing_species():
    r = get_usage_spreads("NotARealMonXYZ")
    assert r["found"] is False
    assert "reason" in r
    assert "sources" not in r


def test_get_usage_spreads_gallade_mega_showdown_only():
    r = get_usage_spreads("Gallade-Mega")
    assert r["found"] is True
    sources = {s["source"] for s in r["sources"]}
    assert sources == {"showdown"}  # mega forme absent from in-game ladder rows
    top = r["sources"][0]["spreads"][0]
    dm6 = KEYS["dm_outputs"]["dm6"]["attacker"]
    assert top["nature"] == dm6["nature"]
    assert top["sp"] == dm6["evs"]


def test_get_common_speeds_matches_hn2b_gholdengo_cells():
    r = get_common_speeds("Gholdengo")
    assert r["found"] is True
    assert r["part0_lines"] == "part3_request_set_v4.md Part 0 L38-39"
    assert r["pct_kind"] == "chaos_weight"
    assert "not a percent" in r["note"]
    key_cells = KEYS["hn2b_forward_grid"]["opp_common_speed"]
    tool_cells = r["cells"]
    assert len(tool_cells) == 3
    diffs = []
    for tc, kc in zip(tool_cells, key_cells):
        if tc["final_spe"] != kc["final_spe"] or abs(tc["weight"] - kc["weight"]) > 1e-6:
            diffs.append((tc, kc))
    assert diffs == [], diffs
    # Contributors carry nature+SP.
    assert tool_cells[0]["contributors"]
    assert "nature" in tool_cells[0]["contributors"][0]
    assert "sp" in tool_cells[0]["contributors"][0]


def test_get_common_speeds_matches_is2_dragapult_cells():
    r = get_common_speeds("Dragapult")
    key_cells = KEYS["is2_min_spe"]["opp_common_speed"]
    assert [c["final_spe"] for c in r["cells"]] == [c["final_spe"] for c in key_cells]
    for tc, kc in zip(r["cells"], key_cells):
        assert abs(tc["weight"] - kc["weight"]) < 1e-6


def test_get_common_speeds_missing():
    r = get_common_speeds("NotARealMonXYZ")
    assert r["found"] is False


def test_get_meta_threats_shape_and_diff_vs_hu2b_key():
    r = get_meta_threats(50)
    assert r["status"] == "ok"
    assert r["listed"] >= 1
    assert "get_relevant_threats" in r["how_built"]
    assert r["threats"][0]["usage_rank"] is not None
    tool_names = {to_id(t["species"]) for t in r["threats"]}
    key = KEYS["showdown_threats_ge_452"]
    key_names = {to_id(t["name"]) for t in key["threats"]}
    only_tool = sorted(tool_names - key_names)
    only_key = sorted(key_names - tool_names)
    # Honest report: CLI ladder ≠ HU2b Showdown ≥4.52% set. Record the diff; do not force.
    assert only_tool or only_key or tool_names == key_names  # always true; diffs printed
    diff = {
        "tool_n": len(tool_names),
        "key_n": len(key_names),
        "only_tool_n": len(only_tool),
        "only_key_n": len(only_key),
        "only_tool_sample": only_tool[:10],
        "only_key_sample": only_key[:10],
        "equal": tool_names == key_names,
    }
    print("meta_threats_vs_hu2b", diff)
    # Do not force equality with HU2b (brief 3c). Current pins differ; record that.
    assert isinstance(diff["equal"], bool)


def test_get_usage_stats_kinds_and_missing():
    for kind in ("moves", "abilities", "natures"):
        r = get_usage_stats("Incineroar", kind)
        assert r["found"] is True
        assert r["kind"] == kind
        assert r["sources"]
        for src in r["sources"]:
            assert src["pct_kind"] == "percent"
            assert "percent" in src["note"].lower()
    bad = get_usage_stats("Incineroar", "items")
    assert bad["status"] == "error"
    miss = get_usage_stats("NotARealMonXYZ", "moves")
    assert miss["found"] is False


def test_dispatch_requires_tool_fields():
    from scripts.eval.part_g_arm.state.fixtures import empty_team
    from scripts.eval.part_g_arm.state.harness import dispatch

    class _Arm:
        def call(self, name, args):
            raise AssertionError("should not reach ArmTools")

    st = empty_team()
    set_tool_fields(False)
    _, patch = dispatch(st, _Arm(), "get_usage_spreads", {"species": "Incineroar"})
    assert patch.get("status") == "error"
    set_tool_fields(True)
    _, patch2 = dispatch(st, _Arm(), "get_usage_spreads", {"species": "Incineroar"})
    assert patch2.get("found") is True
