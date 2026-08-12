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
