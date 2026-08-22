"""Deterministic provisional edit review flags."""

from __future__ import annotations

from unittest.mock import patch

from recommender.edit_review import (
    collect_provisional_review_flags,
    nature_stat_modifiers,
)
from recommender.state import ProvisionalSlot, TargetRoleDecision


def _provisional(
    *,
    role_id: str = "fast_special_attacker",
    item: str = "Life Orb",
    nature: str = "Modest",
    spread: tuple[tuple[str, int], ...] = (
        ("hp", 4),
        ("atk", 0),
        ("def", 0),
        ("spa", 32),
        ("spd", 0),
        ("spe", 30),
    ),
) -> ProvisionalSlot:
    return ProvisionalSlot(
        schema_version=1,
        slot_index=0,
        target_role_decision=TargetRoleDecision(role_id=role_id, source="other"),
        species="Gholdengo",
        ability="Good as Gold",
        item=item,
        moves=("Make It Rain", "Shadow Ball", "Protect", "Nasty Plot"),
        nature=nature,
        spread=spread,
        fingerprint="fp",
    )


def test_nature_chart_timid_and_hardy():
    assert nature_stat_modifiers("Timid") == ("spe", "atk")
    assert nature_stat_modifiers("Hardy") == (None, None)


def test_nature_chart_matches_real_game_mechanics_for_all_25_natures():
    """Regression, confirmed live (2026-08-21): Jolly was an exact
    duplicate of Timid's (plus, minus) tuple -- ("spe", "atk") -- when
    Jolly's real minus-stat is "spa". Checks every nature against the
    real chart directly, not just a couple of spot-checks, since this
    exact class of isolated-single-row-copy-paste error is easy to miss
    with partial coverage.
    """
    correct = {
        "Hardy": (None, None),
        "Lonely": ("atk", "def"),
        "Brave": ("atk", "spe"),
        "Adamant": ("atk", "spa"),
        "Naughty": ("atk", "spd"),
        "Bold": ("def", "atk"),
        "Docile": (None, None),
        "Relaxed": ("def", "spe"),
        "Impish": ("def", "spa"),
        "Lax": ("def", "spd"),
        "Timid": ("spe", "atk"),
        "Hasty": ("spe", "def"),
        "Serious": (None, None),
        "Jolly": ("spe", "spa"),
        "Naive": ("spe", "spd"),
        "Modest": ("spa", "atk"),
        "Mild": ("spa", "def"),
        "Quiet": ("spa", "spe"),
        "Bashful": (None, None),
        "Rash": ("spa", "spd"),
        "Calm": ("spd", "atk"),
        "Gentle": ("spd", "def"),
        "Sassy": ("spd", "spe"),
        "Careful": ("spd", "spa"),
        "Quirky": (None, None),
    }
    for nature, expected in correct.items():
        assert nature_stat_modifiers(nature) == expected, nature


def test_jolly_does_not_conflict_with_physical_role():
    """Regression, confirmed live (2026-08-21): a Jolly-natured Kangaskhan
    on standard_physical_attacker triggered a false 'Nature Jolly conflicts
    with physical role' warning. Jolly (+Spe, -SpA) is one of the most
    common, entirely correct physical-attacker natures in the game
    precisely because it never touches Attack.
    """
    flags = collect_provisional_review_flags(
        _provisional(
            role_id="standard_physical_attacker",
            nature="Jolly",
            spread=(
                ("hp", 2),
                ("atk", 32),
                ("def", 0),
                ("spa", 0),
                ("spd", 0),
                ("spe", 32),
            ),
        ),
        {},
    )
    assert not any(f["check"] == "nature_axis_role_mismatch" for f in flags)


def test_ev_into_nature_hindered_hit_and_miss():
    hit = _provisional(
        nature="Timid",
        spread=(
            ("hp", 4),
            ("atk", 8),
            ("def", 0),
            ("spa", 24),
            ("spd", 0),
            ("spe", 30),
        ),
    )
    flags = collect_provisional_review_flags(hit, {})
    assert any(f["check"] == "ev_into_nature_hindered" for f in flags)

    miss = _provisional(nature="Timid")
    flags = collect_provisional_review_flags(miss, {})
    assert not any(f["check"] == "ev_into_nature_hindered" for f in flags)


def test_item_spread_glass_tanky():
    flags = collect_provisional_review_flags(
        _provisional(
            item="Focus Sash",
            spread=(
                ("hp", 20),
                ("atk", 0),
                ("def", 14),
                ("spa", 32),
                ("spd", 0),
                ("spe", 0),
            ),
        ),
        {},
    )
    assert any(f["check"] == "item_spread_glass_tanky" for f in flags)


def test_item_spread_offense_amp_zero_ev():
    flags = collect_provisional_review_flags(
        _provisional(
            item="Life Orb",
            spread=(
                ("hp", 32),
                ("atk", 0),
                ("def", 18),
                ("spa", 0),
                ("spd", 16),
                ("spe", 0),
            ),
        ),
        {},
    )
    assert any(f["check"] == "item_spread_offense_amp_zero_ev" for f in flags)


def test_item_spread_category_boost_wrong_stat():
    flags = collect_provisional_review_flags(
        _provisional(
            item="Muscle Band",
            spread=(
                ("hp", 4),
                ("atk", 0),
                ("def", 0),
                ("spa", 32),
                ("spd", 0),
                ("spe", 30),
            ),
        ),
        {},
    )
    assert any(f["check"] == "item_spread_category_boost_wrong_stat" for f in flags)

    flags = collect_provisional_review_flags(
        _provisional(
            item="Wise Glasses",
            role_id="fast_physical_attacker",
            nature="Jolly",
            spread=(
                ("hp", 4),
                ("atk", 32),
                ("def", 0),
                ("spa", 0),
                ("spd", 0),
                ("spe", 30),
            ),
        ),
        {},
    )
    assert any(f["check"] == "item_spread_category_boost_wrong_stat" for f in flags)


def test_item_spread_iron_ball_speed():
    flags = collect_provisional_review_flags(
        _provisional(
            item="Iron Ball",
            spread=(
                ("hp", 4),
                ("atk", 0),
                ("def", 0),
                ("spa", 32),
                ("spd", 0),
                ("spe", 30),
            ),
        ),
        {},
    )
    assert any(f["check"] == "item_spread_iron_ball_speed" for f in flags)


def test_nature_axis_role_mismatch_physical():
    flags = collect_provisional_review_flags(
        _provisional(
            role_id="fast_physical_attacker",
            nature="Modest",
            spread=(
                ("hp", 4),
                ("atk", 0),
                ("def", 0),
                ("spa", 32),
                ("spd", 0),
                ("spe", 30),
            ),
        ),
        {},
    )
    assert any(f["check"] == "nature_axis_role_mismatch" for f in flags)


def test_scarf_nature_overshoot():
    provisional = _provisional(
        item="Choice Scarf",
        nature="Timid",
        spread=(
            ("hp", 4),
            ("atk", 0),
            ("def", 0),
            ("spa", 32),
            ("spd", 0),
            ("spe", 30),
        ),
    )
    with patch(
        "recommender.edit_review.scarf_clears_benchmarks", return_value=True
    ):
        flags = collect_provisional_review_flags(
            provisional, {"regulation_mod": "champions"}
        )
    assert any(f["check"] == "scarf_nature_overshoot" for f in flags)


def test_collector_never_raises_on_minimal():
    flags = collect_provisional_review_flags(_provisional(), {})
    assert isinstance(flags, tuple)
