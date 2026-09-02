"""Tests for ingame CBD sanity gates."""

from __future__ import annotations

from unittest.mock import patch

from recommender.usage_data import build_synthesis_usage_entry, load_usage
from recommender.usage_ingame_sanity import (
    find_stale_vs_live_suspects,
    ingame_monotonic_tail_corrupt,
    stale_vs_live_suspect,
)

SINISTCHA_STALE_INGAME = {
    "name": "Sinistcha",
    "common_moves": [
        {"name": "Shadow Ball", "pct": 22.0},
        {"name": "Strength Sap", "pct": 9.7},
        {"name": "Imprison", "pct": 3.1},
        {"name": "Scald", "pct": 1.1},
    ],
}

SINISTCHA_SHOWDOWN = {
    "common_moves": [
        {"name": "Matcha Gotcha", "pct": 45.0},
        {"name": "Rage Powder", "pct": 40.0},
        {"name": "Trick Room", "pct": 25.0},
        {"name": "Protect", "pct": 20.0},
        {"name": "Shadow Ball", "pct": 15.0},
        {"name": "Strength Sap", "pct": 10.0},
        {"name": "Imprison", "pct": 5.0},
        {"name": "Scald", "pct": 2.0},
    ],
}

GRIMMSNARL_LIVE_INGAME = {
    "common_moves": [
        {"name": "Sucker Punch", "pct": 30.0},
        {"name": "Foul Play", "pct": 25.0},
        {"name": "Scary Face", "pct": 20.0},
        {"name": "Fake Tears", "pct": 15.0},
    ],
}

GRIMMSNARL_SHOWDOWN = {
    "common_moves": [
        {"name": "Parting Shot", "pct": 35.0},
        {"name": "Reflect", "pct": 30.0},
        {"name": "Light Screen", "pct": 25.0},
        {"name": "Spirit Break", "pct": 20.0},
        {"name": "Sucker Punch", "pct": 15.0},
        {"name": "Foul Play", "pct": 10.0},
    ],
}

KLEFKI_INGAME = {
    "common_moves": [
        {"name": "Light Screen", "pct": 40.0},
        {"name": "Reflect", "pct": 35.0},
        {"name": "Dazzling Gleam", "pct": 20.0},
        {"name": "Thunder Wave", "pct": 15.0},
    ],
}

KLEFKI_SHOWDOWN = {
    "common_moves": [
        {"name": "Light Screen", "pct": 40.0},
        {"name": "Reflect", "pct": 35.0},
        {"name": "Dazzling Gleam", "pct": 20.0},
        {"name": "Thunder Wave", "pct": 15.0},
    ],
}

PELIPPER_INGAME = {
    "common_moves": [
        {"name": "Hurricane", "pct": 50.0},
        {"name": "Weather Ball", "pct": 30.0},
        {"name": "Protect", "pct": 25.0},
        {"name": "Tailwind", "pct": 20.0},
    ],
}

PELIPPER_SHOWDOWN = {
    "common_moves": [
        {"name": "Hurricane", "pct": 50.0},
        {"name": "Weather Ball", "pct": 30.0},
        {"name": "Protect", "pct": 25.0},
        {"name": "Tailwind", "pct": 20.0},
    ],
}


def test_sinistcha_stale_monotonic_tail():
    assert ingame_monotonic_tail_corrupt(SINISTCHA_STALE_INGAME, SINISTCHA_SHOWDOWN)


def test_grimmsnarl_live_not_monotonic_tail():
    assert not ingame_monotonic_tail_corrupt(GRIMMSNARL_LIVE_INGAME, GRIMMSNARL_SHOWDOWN)


def test_klefki_pelipper_not_flagged():
    assert not ingame_monotonic_tail_corrupt(KLEFKI_INGAME, KLEFKI_SHOWDOWN)
    assert not ingame_monotonic_tail_corrupt(PELIPPER_INGAME, PELIPPER_SHOWDOWN)


def test_thin_showdown_skips():
    thin = {"common_moves": [{"name": "Tackle", "pct": 10.0}]}
    assert not ingame_monotonic_tail_corrupt(SINISTCHA_STALE_INGAME, thin)


def test_stale_vs_live_suspect():
    live = {
        "common_moves": [
            {"name": "Matcha Gotcha", "pct": 45.0},
            {"name": "Rage Powder", "pct": 40.0},
            {"name": "Trick Room", "pct": 25.0},
            {"name": "Protect", "pct": 20.0},
        ],
    }
    assert stale_vs_live_suspect(SINISTCHA_STALE_INGAME, live)


def test_find_stale_vs_live_suspects():
    ingame = {"sinistcha": SINISTCHA_STALE_INGAME}

    def fake_fetch(name: str):
        if name == "Sinistcha":
            return {
                "common_moves": [
                    {"name": "Matcha Gotcha", "pct": 45.0},
                    {"name": "Rage Powder", "pct": 40.0},
                    {"name": "Trick Room", "pct": 25.0},
                    {"name": "Protect", "pct": 20.0},
                ],
            }
        return None

    suspects = find_stale_vs_live_suspects(ingame, fetch=fake_fetch)
    assert suspects == [("sinistcha", "cached=['shadowball', 'strengthsap', 'imprison', 'scald'] live=['matchagotcha', 'ragepowder', 'trickroom', 'protect']")]


def test_build_synthesis_monotonic_fallback():
    load_usage.cache_clear()
    snap = load_usage("champions-reg-mb")
    ing = dict(snap["ingame_doubles"]["species"]["sinistcha"])
    ing["common_moves"] = SINISTCHA_STALE_INGAME["common_moves"]
    with patch(
        "recommender.usage_data.ingame_species_map",
        return_value={"sinistcha": ing},
    ):
        entry = build_synthesis_usage_entry("Sinistcha", regulation="champions-reg-mb")
    assert entry is not None
    top_moves = [m["name"] for m in (entry.get("common_moves") or [])[:2]]
    assert "Matcha Gotcha" in top_moves or "matchagotcha" in str(top_moves).lower()
