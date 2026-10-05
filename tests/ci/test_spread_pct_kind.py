"""B3b: showdown_pct_kind + spread chaos_weight labels; no numeric conversion."""

from __future__ import annotations

import json
from pathlib import Path

from recommender.usage_chaos import (
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


def test_munch_spreads_stamps_chaos_weight_without_rescaling():
    detail = json.loads(FIXTURE.read_text(encoding="utf-8"))["species"]["rillaboom"]
    rows = _munch_spreads(detail)
    assert rows[0]["pct"] == detail["Spreads"]["Jolly:0/32/0/0/0/32"]
    assert rows[0]["pct_kind"] == "chaos_weight"
    # Abilities still use Raw-count denom (repo scale); spreads are not converted.
    ab = chaos_weights_to_common(detail["Abilities"], raw_count=detail["Raw count"])
    assert ab[0]["pct"] == 59.51


def test_oracle_three_species_fixture_weights():
    blob = json.loads(FIXTURE.read_text(encoding="utf-8"))["species"]
    for sid, detail in blob.items():
        rows = _munch_spreads(detail)
        expected = sorted(detail["Spreads"].items(), key=lambda kv: -float(kv[1]))
        assert rows[0]["pct"] == float(expected[0][1])
        assert rows[0]["pct_kind"] == "chaos_weight"


def test_committed_showdown_pins_unchanged_and_labeled():
    snap = json.loads(SHOWDOWN_PATH.read_text(encoding="utf-8"))
    assert snap["meta"]["showdown_pct_kind"] == "weight_over_raw_count"
    for sid, pct in COMMITTED_SPREAD_PINS.items():
        top = snap["showdown_doubles"]["species"][sid]["top_spreads"][0]
        assert top["pct"] == pct
        assert top["pct_kind"] == "chaos_weight"


def test_graft_meta_stamps_weight_over_raw_count():
    out = graft(
        showdown={"a": {"id": "a", "top_spreads": [], "source": "smogon-chaos"}},
        info={"number of battles": 10},
        month="2026-09",
        format_id=EXPECTED_SHOWDOWN_FORMAT,
        rating=1500,
        extracted_at="2026-10-04T00:00:00Z",
    )
    assert out["meta"]["showdown_pct_kind"] == "weight_over_raw_count"


def test_showdown_source_params_reads_new_kind(monkeypatch):
    import recommender.usage_chaos as uc

    monkeypatch.setattr(
        uc,
        "load_usage",
        lambda _r="champions-reg-mb": {
            "meta": {"showdown_pct_kind": "set", "showdown_month": "2026-07"}
        },
    )
    assert showdown_source_params("champions-reg-mb")["pct_kind"] == (
        "weight_over_raw_count"
    )
