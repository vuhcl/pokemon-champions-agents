"""Gap-mapped infer_role vocabulary (fast / standard / bulky × phys/special/mixed)."""

from __future__ import annotations

from typing import get_args

import pytest

from recommender.recommend import (
    SP_BUDGET,
    RoleArchetype,
    _DEPRECATED_ROLE_ALIASES,
    infer_role,
    role_spread,
)


@pytest.mark.parametrize("role", list(get_args(RoleArchetype)) + list(_DEPRECATED_ROLE_ALIASES))
def test_role_spreads_cover_all_archetypes_and_aliases(role: str):
    spread = role_spread(role)
    assert set(spread) == {"hp", "atk", "def", "spa", "spd", "spe"}
    assert sum(spread.values()) == SP_BUDGET
    assert all(0 <= value <= 32 for value in spread.values())


def test_mega_special_is_standard_special():
    assert (
        infer_role(
            ["Heat Wave", "Solar Beam", "Air Slash", "Protect"],
            "Charizardite Y",
        )
        == "standard_special_attacker"
    )


def test_mega_physical_is_standard_physical():
    assert (
        infer_role(
            ["Wave Crash", "Earthquake", "Ice Punch", "Protect"],
            "Swampertite",
        )
        == "standard_physical_attacker"
    )


def test_mega_stone_not_fast_or_bulky_axis():
    role = infer_role(
        ["Wave Crash", "Earthquake", "Ice Punch", "Protect"],
        "Swampertite",
    )
    assert role.startswith("standard_")
    assert not role.startswith("fast_")
    assert not role.startswith("bulky_")


def test_focus_sash_special_is_fast_special():
    assert (
        infer_role(
            ["Earth Power", "Sludge Bomb", "Power Gem", "Protect"],
            "Focus Sash",
        )
        == "fast_special_attacker"
    )


def test_focus_sash_physical_is_fast_physical():
    assert (
        infer_role(
            ["Earthquake", "Iron Head", "Rock Slide", "Protect"],
            "Focus Sash",
            "Sand Rush",
        )
        == "fast_physical_attacker"
    )


def test_life_orb_garchomp_fast_physical():
    assert (
        infer_role(
            ["Earthquake", "Dragon Claw", "Rock Slide", "Protect"],
            "Life Orb",
        )
        == "fast_physical_attacker"
    )


def test_choice_scarf_hydreigon_fast_special():
    assert (
        infer_role(
            ["Dark Pulse", "Draco Meteor", "Flamethrower", "Protect"],
            "Choice Scarf",
        )
        == "fast_special_attacker"
    )


def test_choice_scarf_basculegion_fast_physical():
    assert (
        infer_role(
            ["Wave Crash", "Last Respects", "Aqua Jet", "Protect"],
            "Choice Scarf",
        )
        == "fast_physical_attacker"
    )


def test_archaludon_leftovers_not_false_pivot():
    role = infer_role(
        ["Electro Shot", "Dragon Pulse", "Flash Cannon", "Protect"],
        "Leftovers",
        "Stamina",
    )
    assert role == "bulky_special_attacker"
    assert "pivot" not in role


def test_milotic_leftovers_special_bulky_not_pivot():
    role = infer_role(
        ["Scald", "Ice Beam", "Recover", "Protect"],
        "Leftovers",
    )
    assert role == "bulky_special_attacker"


def test_incineroar_parting_shot_remains_bulky_pivot():
    assert (
        infer_role(
            ["Fake Out", "Flare Blitz", "Knock Off", "Parting Shot"],
            "Sitrus Berry",
            "Intimidate",
        )
        == "bulky_pivot"
    )


def test_scarf_plus_uturn_is_fast_pivot():
    assert (
        infer_role(
            ["U-turn", "Earthquake", "Iron Head", "Protect"],
            "Choice Scarf",
        )
        == "fast_pivot"
    )


def test_sand_rush_excadrill_fast_physical():
    assert (
        infer_role(
            ["Earthquake", "Iron Head", "Rock Slide", "Protect"],
            "Steelium Z",  # ponytail: neutral placeholder; ability is the fast signal
            "Sand Rush",
        )
        == "fast_physical_attacker"
    )


def test_chlorophyll_venusaur_fast_special():
    assert (
        infer_role(
            ["Giga Drain", "Sludge Bomb", "Earth Power", "Protect"],
            "Black Glasses",
            "Chlorophyll",
        )
        == "fast_special_attacker"
    )


def test_technician_multihit_fast_physical():
    assert (
        infer_role(
            ["Population Bomb", "Bite", "Protect", "Follow Me"],
            "Wide Lens",
            "Technician",
        )
        == "fast_physical_attacker"
    )


def test_technician_vs_friend_guard_differ_on_same_moves():
    moves = ["Population Bomb", "Bite", "Protect", "Follow Me"]
    item = "Wide Lens"
    assert infer_role(moves, item, "Technician") == "fast_physical_attacker"
    assert infer_role(moves, item, "Friend Guard") == "standard_physical_attacker"


def test_grimmsnarl_screens_light_clay_screens_support():
    assert (
        infer_role(
            ["Reflect", "Light Screen", "Thunder Wave", "Parting Shot"],
            "Light Clay",
            "Prankster",
        )
        == "screens_support"
    )


def test_aurora_veil_alone_is_screens_support():
    assert (
        infer_role(
            ["Aurora Veil", "Moonblast", "Freeze-Dry", "Protect"],
            "Light Clay",
            "Snow Warning",
        )
        == "screens_support"
    )
    assert (
        infer_role(
            ["Aurora Veil", "Moonblast", "Freeze-Dry", "Protect"],
            "Leftovers",
            "Snow Warning",
        )
        == "screens_support"
    )


def test_lone_light_screen_is_not_screens_support_without_clay():
    assert (
        infer_role(
            ["Light Screen", "Moonblast", "Shadow Ball", "Protect"],
            "Leftovers",
        )
        != "screens_support"
    )
    assert (
        infer_role(
            ["Light Screen", "Moonblast", "Shadow Ball", "Protect"],
            "Light Clay",
        )
        == "screens_support"
    )


def test_bulky_status_kit_lone_screen_is_not_screens_support():
    assert (
        infer_role(
            ["Will-O-Wisp", "Light Screen", "Encore", "Disable"],
            "Leftovers",
        )
        != "screens_support"
    )


def test_assault_vest_is_not_a_screens_signal():
    assert (
        infer_role(
            ["Light Screen", "Moonblast", "Shadow Ball", "Protect"],
            "Assault Vest",
        )
        != "screens_support"
    )


def test_kingambit_black_glasses_standard_physical():
    assert (
        infer_role(
            ["Sucker Punch", "Kowtow Cleave", "Iron Head", "Protect"],
            "Black Glasses",
            "Defiant",
        )
        == "standard_physical_attacker"
    )


def test_mixed_bias_life_orb():
    assert (
        infer_role(
            ["Earthquake", "Flamethrower", "Dragon Claw", "Protect"],
            "Life Orb",
        )
        == "fast_mixed_attacker"
    )


def test_mixed_bias_mega_standard_mixed():
    assert (
        infer_role(
            ["Earthquake", "Fire Blast", "Dragon Claw", "Protect"],
            "Charizardite X",
        )
        == "standard_mixed_attacker"
    )


def test_infer_role_never_returns_deprecated_aliases():
    assert infer_role(["Earthquake"], "Life Orb") != "fast_attacker"
    assert infer_role(["Earthquake"], "Leftovers") != "bulky_attacker"
    assert infer_role(["Earthquake"], "Black Glasses") != "bulky_attacker"
