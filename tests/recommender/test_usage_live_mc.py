"""B2a: M-C live is exact-tag only (no M-B chain walk)."""

from __future__ import annotations

from unittest.mock import patch

from recommender.teammates import query_teammates
from recommender.usage_live import (
    _LIVE_FORMATS,
    _live_format_for,
    fetch_live_showdown_detail,
    supports_live_usage,
)
from recommender.usage_spreads import fetch_live_spreads, select_usage_spread


def test_live_format_exact_tag_no_mb_for_mc():
    # Red on pre-B2a main: _live_format_for("champions") returned the M-B tuple.
    assert _live_format_for("champions-reg-mb") == _LIVE_FORMATS["champions-reg-mb"]
    assert _live_format_for("champions") is None
    assert _live_format_for("champions-reg-mc") is None
    assert supports_live_usage("champions-reg-mb") is True
    assert supports_live_usage("champions") is False
    assert supports_live_usage("champions-reg-mc") is False


def test_fetch_live_showdown_detail_mc_skips_network():
    fetch_live_showdown_detail.cache_clear()
    calls: list[str] = []

    def fetch(url: str):
        calls.append(url)
        return {"pokemon": {}}

    assert fetch_live_showdown_detail("Beedrill", "champions", fetch) is None
    assert fetch_live_showdown_detail("Beedrill", "champions-reg-mc", fetch) is None
    assert calls == []


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
