"""Chaos row conversion: set%, no top-12 cap, blank keys dropped."""

from __future__ import annotations

from recommender.usage_chaos import (
    chaos_url,
    chaos_weights_to_common,
    detail_raw_count,
    usage_pct_from_chaos,
)


def test_chaos_url_shape():
    assert (
        chaos_url("2026-07", "gen9championsvgc2026regmb", 1500)
        == "https://www.smogon.com/stats/2026-07/chaos/gen9championsvgc2026regmb-1500.json"
    )


def test_set_pct_uses_raw_count_not_share():
    raw = {"auroraveil": 40.17, "protect": 40.0, "shadowball": 19.83}
    # share% of veil would be 40.17/100 = 40.17; with raw_count 100 veil is 40.17
    # with raw_count 200 (weights don't sum to count) veil set% is 20.085
    out = chaos_weights_to_common(raw, raw_count=200.0)
    by_name = {row["name"]: row["pct"] for row in out}
    assert by_name["auroraveil"] == 20.085
    assert len(out) == 3


def test_no_top_12_cap():
    raw = {f"move{i}": float(20 - i) for i in range(20)}
    out = chaos_weights_to_common(raw, raw_count=100.0)
    assert len(out) == 20
    assert out[0]["name"] == "move0"
    assert out[-1]["name"] == "move19"


def test_blank_keys_dropped():
    out = chaos_weights_to_common(
        {"": 50, "  ": 10, "Fake Out": 40}, raw_count=100.0
    )
    assert [row["name"] for row in out] == ["Fake Out"]


def test_usage_pct_fraction_vs_already_percent():
    assert usage_pct_from_chaos({"usage": 0.2346}) == 23.46
    assert usage_pct_from_chaos({"usage": 23.46}) == 23.46


def test_raw_count_invalid_is_none():
    assert detail_raw_count({}) is None
    assert detail_raw_count({"Raw count": 0}) is None
    assert detail_raw_count({"Raw count": 915119}) == 915119.0
