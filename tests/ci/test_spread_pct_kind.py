"""showdown_pct_kind + spread chaos_weight labels; published-scale common_*."""

from __future__ import annotations

import json
from pathlib import Path

from recommender.usage_chaos import (
    SHOWDOWN_PCT_KIND_PUBLISHED,
    _normalize_pct_kind,
    chaos_weights_to_common,
    showdown_source_params,
)
from scripts.extract_usage.fetch_usage_mb import _munch_spreads
from scripts.extract_usage.graft_showdown_mc import graft
from scripts.extract_usage.fetch_usage_mc_munchstats import EXPECTED_SHOWDOWN_FORMAT

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "fixtures" / "chaos_spread_oracle_3spp.json"
SHOWDOWN_PATH = ROOT / "data" / "usage" / "champions-reg-mc.showdown_doubles.v1.json"

# Sampled once from committed M-C showdown (pre-transform pct values; unchanged).
COMMITTED_SPREAD_PINS = {
    "rillaboom": 51646.85905341065,
    "incineroar": 34935.824273533,
    "farigiraf": 17307.64652257607,
}


def test_normalize_pct_kind_aliases_legacy_set():
    assert _normalize_pct_kind("set") == "weight_over_raw_count"
    assert _normalize_pct_kind("weight_over_raw_count") == "weight_over_raw_count"
    assert _normalize_pct_kind(None) == "weight_over_raw_count"
    assert _normalize_pct_kind(SHOWDOWN_PCT_KIND_PUBLISHED) == SHOWDOWN_PCT_KIND_PUBLISHED


def test_munch_spreads_stamps_chaos_weight_without_rescaling():
    detail = json.loads(FIXTURE.read_text(encoding="utf-8"))["species"]["rillaboom"]
    rows = _munch_spreads(detail)
    assert rows[0]["pct"] == detail["Spreads"]["Jolly:0/32/0/0/0/32"]
    assert rows[0]["pct_kind"] == "chaos_weight"
    ab_sum = sum(float(v) for v in detail["Abilities"].values())
    ab = chaos_weights_to_common(detail["Abilities"], denom=ab_sum)
    assert abs(sum(r["pct"] for r in ab) - 100.0) < 0.02


def test_oracle_three_species_fixture_weights():
    blob = json.loads(FIXTURE.read_text(encoding="utf-8"))["species"]
    for sid, detail in blob.items():
        rows = _munch_spreads(detail)
        expected = sorted(detail["Spreads"].items(), key=lambda kv: -float(kv[1]))
        assert rows[0]["pct"] == float(expected[0][1])
        assert rows[0]["pct_kind"] == "chaos_weight"


def test_committed_showdown_pins_and_published_kind():
    snap = json.loads(SHOWDOWN_PATH.read_text(encoding="utf-8"))
    assert snap["meta"]["showdown_pct_kind"] == SHOWDOWN_PCT_KIND_PUBLISHED
    assert snap["meta"]["showdown_pct_fallback_items_bucket"] >= 0
    assert snap["meta"]["showdown_pct_fallback_moves_via_items"] >= 0
    assert snap["meta"]["showdown_pct_fallback_moves_unscaled"] >= 0
    for sid, pct in COMMITTED_SPREAD_PINS.items():
        top = snap["showdown_doubles"]["species"][sid]["top_spreads"][0]
        assert top["pct"] == pct
        assert top["pct_kind"] == "chaos_weight"
    # Golden: Indeedee-F Trick Room on published scale.
    moves = snap["showdown_doubles"]["species"]["indeedeef"]["common_moves"]
    from recommender.ids import to_id

    tr = next(m for m in moves if to_id(m["name"]) == "trickroom")
    assert abs(float(tr["pct"]) - 81.714) < 0.05


def test_graft_meta_stamps_weight_over_abilities_sum():
    out = graft(
        showdown={"a": {"id": "a", "top_spreads": [], "source": "smogon-chaos"}},
        info={"number of battles": 10},
        month="2026-09",
        format_id=EXPECTED_SHOWDOWN_FORMAT,
        rating=1500,
        extracted_at="2026-10-04T00:00:00Z",
    )
    assert out["meta"]["showdown_pct_kind"] == SHOWDOWN_PCT_KIND_PUBLISHED
    assert out["meta"]["showdown_pct_fallback_moves_unscaled"] == 0


def test_showdown_source_params_reads_new_kind(monkeypatch):
    import recommender.usage_chaos as uc

    monkeypatch.setattr(
        uc,
        "load_usage",
        lambda _r: {
            "meta": {
                "showdown_pct_kind": "set",
                "showdown_month": "2026-07",
                "showdown_format": "gen9championsvgc2026regmb",
            }
        },
    )
    assert showdown_source_params("champions-reg-mb")["pct_kind"] == (
        "weight_over_raw_count"
    )


def test_current_reg_rejects_stale_raw_kind():
    """CI guard: committed M-C must not ship weight_over_raw_count."""
    snap = json.loads(SHOWDOWN_PATH.read_text(encoding="utf-8"))
    assert snap["meta"]["showdown_pct_kind"] != "weight_over_raw_count"
    assert snap["meta"]["showdown_pct_kind"] == SHOWDOWN_PCT_KIND_PUBLISHED
