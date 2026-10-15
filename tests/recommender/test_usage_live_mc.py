"""B2a: M-C live is exact-tag only (no M-B chain walk)."""

from __future__ import annotations

from unittest.mock import patch

from recommender.teammates import query_teammates
from recommender.usage_data import load_usage
from recommender.usage_live import (
    _live_format_for,
    fetch_live_showdown_detail,
    supports_live_usage,
)
from recommender.usage_spreads import fetch_live_spreads, select_usage_spread


def test_live_format_exact_tag_mc_has_its_own_tuple():
    """ADR-014 2026-10-14b: M-C derives its own tuple; bare ``champions`` stays off."""
    mc_meta = load_usage("champions-reg-mc")["meta"]
    assert _live_format_for("champions-reg-mc") == (
        "2026-09",
        "gen9championsvgc2026regmc",
        1500,
    )
    # the derivation reads the snapshot meta, so the literals above must match it
    assert _live_format_for("champions-reg-mc") == (
        mc_meta["showdown_month"],
        mc_meta["showdown_format"],
        mc_meta["showdown_rating"],
    )
    assert _live_format_for("champions-reg-mc") != _live_format_for("champions-reg-mb")
    assert _live_format_for("champions") is None
    assert supports_live_usage("champions-reg-mb") is True
    assert supports_live_usage("champions-reg-mc") is True
    assert supports_live_usage("champions") is False


def test_fetch_live_showdown_detail_exact_mc_tag_uses_mc_url_only():
    fetch_live_showdown_detail.cache_clear()
    calls: list[str] = []

    def fetch(url: str):
        calls.append(url)
        return {"pokemon": {}}

    # bare product mod name: no live tuple, no fetch
    assert fetch_live_showdown_detail("Beedrill", "champions", fetch) is None
    assert calls == []
    # explicit M-C tag: one index fetch against the M-C tuple, never M-B
    assert fetch_live_showdown_detail("Beedrill", "champions-reg-mc", fetch) is None
    assert len(calls) == 1
    assert "/stats/2026-09/gen9championsvgc2026regmc/1500/_index.json" in calls[0]
    assert "regmb" not in calls[0]


def test_out_of_snapshot_mc_select_usage_spread_no_mb_live():
    """No offline entry: live gated off for M-C; no M-B URL hit; returns None."""
    fetch_live_spreads.cache_clear()
    urls: list[str] = []

    def fetch(url: str):
        urls.append(url)
        if "gen9championsvgc2026regmb" in url:
            return {"pokemon": {"Beedrill": {"usage": 1.0}}}
        return None

    with patch(
        "recommender.usage_spreads.build_synthesis_usage_entry", return_value=None
    ):
        choice = select_usage_spread(
            "Beedrill",
            "fast_attacker",
            ["U-turn"],
            regulation="champions",
            live_fetch=lambda s, r: fetch_live_spreads(s, r, fetch),
        )
    assert choice is None
    assert urls == []
    assert not any("regmb" in u for u in urls)


def test_out_of_snapshot_mc_query_teammates_production_default_no_mb():
    """Production default fetcher: M-C miss must not pull M-B live teammates."""
    fetch_live_showdown_detail.cache_clear()
    urls: list[str] = []

    def fetch(url: str):
        urls.append(url)
        return {
            "Abilities": {"Swarm": 1},
            "Teammates": {"Pelipper": 10},
        }

    with (
        patch("recommender.teammates.showdown_species_map", return_value={}),
        patch("recommender.teammates.ingame_species_map", return_value={}),
        patch(
            "recommender.usage_live.fetch_json",
            side_effect=fetch,
        ),
    ):
        result = query_teammates("Beedrill", regulation="champions")

    assert result.source != "showdown-live"
    assert urls == [] or not any("gen9championsvgc2026regmb" in u for u in urls)
    assert not any("gen9championsvgc2026regmb" in u for u in urls)
