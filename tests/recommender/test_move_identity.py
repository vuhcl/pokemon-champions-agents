"""Pass 1 type-identity helpers for static counters."""

from __future__ import annotations

import pytest

from recommender.counters import (
    _damaging_move_types,
    effective_move_type,
    type_effectiveness,
)
from recommender.legality import load_snapshot


@pytest.fixture(scope="module")
def snap():
    return load_snapshot()


def test_freeze_dry_super_effective_vs_water():
    assert type_effectiveness("Ice", ["Water"], move_id="freezedry") == 2.0


def test_blizzard_not_super_effective_vs_water():
    assert type_effectiveness("Ice", ["Water"], move_id="blizzard") == 0.5


def test_flying_press_multiplies_flying_chart():
    # Fighting vs Ghost = 0; Flying vs Ghost = 1 → product 0 without Scrappy.
    assert type_effectiveness("Fighting", ["Ghost"], move_id="flyingpress") == 0.0
    # Fighting vs Grass = 1; Flying vs Grass = 2 → 2.
    assert type_effectiveness("Fighting", ["Grass"], move_id="flyingpress") == 2.0


def test_liquid_voice_hyper_voice_counts_as_water(snap):
    assert (
        effective_move_type(snap, "Hyper Voice", ability="Liquid Voice") == "Water"
    )


@pytest.mark.parametrize(
    "ability,expected",
    [
        ("Aerilate", "Flying"),
        ("Dragonize", "Dragon"),
        ("Pixilate", "Fairy"),
        ("Refrigerate", "Ice"),
    ],
)
def test_ate_ability_normal_move_becomes_typed(snap, ability, expected):
    assert effective_move_type(snap, "Hyper Voice", ability=ability) == expected


def test_weather_ball_type_under_sun(snap):
    assert effective_move_type(snap, "Weather Ball", weather="Sun") == "Fire"
    assert effective_move_type(snap, "Weather Ball", weather="Rain") == "Water"


def test_terrain_pulse_type_when_terrain_set(snap):
    assert (
        effective_move_type(snap, "Terrain Pulse", terrain="Psychic") == "Psychic"
    )


def test_aura_wheel_morpeko_hangry_dark(snap):
    assert (
        effective_move_type(snap, "Aura Wheel", species="Morpeko-Hangry") == "Dark"
    )
    assert effective_move_type(snap, "Aura Wheel", species="Morpeko") == "Electric"


def test_raging_bull_paldea_blaze_fire(snap):
    assert (
        effective_move_type(snap, "Raging Bull", species="Tauros-Paldea-Blaze")
        == "Fire"
    )


def test_scrappy_fighting_hits_ghost():
    assert (
        type_effectiveness(
            "Fighting", ["Ghost"], attacker_ability="Scrappy"
        )
        == 1.0
    )


def test_fighting_vs_ghost_zero_without_scrappy():
    assert type_effectiveness("Fighting", ["Ghost"]) == 0.0


def test_query_counters_primarina_liquid_voice_not_walled_as_normal(snap):
    """Water Hyper Voice should not be treated as Normal for wall math."""
    types = _damaging_move_types(
        snap,
        ["Hyper Voice", "Moonblast"],
        ability="Liquid Voice",
        species="Primarina",
    )
    assert "Water" in types
    assert "Normal" not in types
