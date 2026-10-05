"""Chaos row conversion: published set%, no top-12 cap, blank keys dropped."""

from __future__ import annotations

from recommender.usage_chaos import (
    chaos_species_row,
    chaos_url,
    chaos_weights_to_common,
    common_sets_from_detail,
    detail_raw_count,
    usage_pct_from_chaos,
)


def test_chaos_url_shape():
    assert (
        chaos_url("2026-07", "gen9championsvgc2026regmb", 1500)
        == "https://www.smogon.com/stats/2026-07/chaos/gen9championsvgc2026regmb-1500.json"
    )


def test_set_pct_uses_ability_denom_not_raw():
    raw = {"auroraveil": 40.17, "protect": 40.0, "shadowball": 19.83}
    # With denom 200 (ability-weight sum), veil set% is 20.085 — not share-of-moves.
    out = chaos_weights_to_common(raw, denom=200.0)
    by_name = {row["name"]: row["pct"] for row in out}
    assert by_name["auroraveil"] == 20.085
    assert len(out) == 3


def test_no_top_12_cap():
    raw = {f"move{i}": float(20 - i) for i in range(20)}
    out = chaos_weights_to_common(raw, denom=100.0)
    assert len(out) == 20
    assert out[0]["name"] == "move0"
    assert out[-1]["name"] == "move19"


def test_blank_keys_dropped():
    out = chaos_weights_to_common(
        {"": 50, "  ": 10, "Fake Out": 40}, denom=100.0
    )
    assert [row["name"] for row in out] == ["Fake Out"]


def test_usage_pct_fraction_vs_already_percent():
    assert usage_pct_from_chaos({"usage": 0.2346}) == 23.46
    assert usage_pct_from_chaos({"usage": 23.46}) == 23.46


def test_raw_count_invalid_is_none():
    assert detail_raw_count({}) is None
    assert detail_raw_count({"Raw count": 0}) is None
    assert detail_raw_count({"Raw count": 915119}) == 915119.0


def test_indeedee_f_trick_room_published_golden():
    # From /tmp/chaos_mc_1500.json: ab_sum≈448631.27, trickroom weight≈366594.68
    detail = {
        "Raw count": 833895,
        "usage": 0.05,
        "Abilities": {"Psychic Surge": 448631.27},
        "Items": {"Safety Goggles": 200000.0},
        "Moves": {"trickroom": 366594.6778343521, "followme": 100.0},
    }
    moves, _items, abilities, flags = common_sets_from_detail(detail)
    assert not any(flags.values())
    by_move = {m["name"]: m["pct"] for m in moves}
    assert abs(by_move["trickroom"] - 81.714) < 0.001
    assert abs(sum(a["pct"] for a in abilities) - 100.0) < 0.01


def test_empty_abilities_moves_use_items_denom():
    detail = {
        "Abilities": {},
        "Items": {"Leftovers": 50.0},
        "Moves": {"protect": 40.0, "trickroom": 10.0},
    }
    moves, items, abilities, flags = common_sets_from_detail(detail)
    assert flags["items_bucket"] is True
    assert flags["moves_via_items"] is True
    assert flags["moves_unscaled"] is False
    assert abilities == []
    assert {m["name"]: m["pct"] for m in moves}["protect"] == 80.0
    assert {i["name"]: i["pct"] for i in items}["Leftovers"] == 100.0


def test_empty_abilities_and_items_moves_fail_closed():
    detail = {
        "Abilities": {},
        "Items": {},
        "Moves": {"protect": 40.0},
    }
    moves, items, abilities, flags = common_sets_from_detail(detail)
    assert moves == []
    assert items == []
    assert abilities == []
    assert flags["moves_unscaled"] is True
    row = chaos_species_row(
        "Test",
        detail,
        resolve_move=lambda n: n,
        resolve_item=lambda n: n,
        resolve_ability=lambda n: n,
    )
    assert row["common_moves"] == []
    assert row["showdown_moves_pct_unscaled"] is True
