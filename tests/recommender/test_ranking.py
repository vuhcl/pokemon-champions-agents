"""Tests for recommender.ranking.rank_and_cut."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from recommender.ranking import rank_and_cut


@dataclass(frozen=True)
class Scored:
    name: str
    score: float
    tier: int = 0


def test_flat_sort_and_cut():
    xs = ["c", "a", "b", "d"]
    assert rank_and_cut(xs, key=lambda x: x, n=2, order="ascending") == ["a", "b"]
    assert rank_and_cut(xs, key=lambda x: x, n=2, order="descending") == ["d", "c"]
    assert rank_and_cut(xs, key=lambda x: x, n=0) == []


def test_tier0_alone_exceeds_n():
    xs = [Scored("a", 3), Scored("b", 2), Scored("c", 1)]
    out = rank_and_cut(xs, key=lambda x: x.score, n=2, tier=lambda x: 0)
    assert len(out) == 3
    assert len(out) > 2
    assert [x.name for x in out] == ["a", "b", "c"]


def test_tier0_empty_tier1_fills_to_n():
    xs = [
        Scored("p", 5, tier=1),
        Scored("q", 4, tier=1),
        Scored("r", 3, tier=1),
        Scored("s", 2, tier=1),
    ]
    out = rank_and_cut(xs, key=lambda x: x.score, n=2, tier=lambda x: x.tier)
    assert [x.name for x in out] == ["p", "q"]


def test_tier0_under_n_tier1_remainder():
    xs = [
        Scored("a", 1, tier=0),
        Scored("b", 2, tier=0),
        Scored("c", 3, tier=0),
        Scored("d", 50, tier=1),
        Scored("e", 40, tier=1),
        Scored("f", 30, tier=1),
        Scored("g", 20, tier=1),
        Scored("h", 10, tier=1),
    ]
    out = rank_and_cut(xs, key=lambda x: x.score, n=5, tier=lambda x: x.tier)
    assert [x.name for x in out] == ["c", "b", "a", "d", "e"]


def test_bonus_fits_slack_kept_whole():
    # n=3: tier0 has 3 → n reached; tier1 has 2; slack=2 → bound=5; 3+2<=5 keep whole
    xs = [
        Scored("a", 1, tier=0),
        Scored("b", 2, tier=0),
        Scored("c", 3, tier=0),
        Scored("d", 9, tier=1),
        Scored("e", 8, tier=1),
    ]
    out = rank_and_cut(
        xs, key=lambda x: x.score, n=3, tier=lambda x: x.tier, slack=2
    )
    assert [x.name for x in out] == ["c", "b", "a", "d", "e"]


def test_bonus_exceeds_slack_skipped_entirely():
    # n=3: tier0 has 3; tier1 has 3; slack=2 → bound=5; 3+3>5 skip all of tier1
    xs = [
        Scored("a", 1, tier=0),
        Scored("b", 2, tier=0),
        Scored("c", 3, tier=0),
        Scored("d", 9, tier=1),
        Scored("e", 8, tier=1),
        Scored("f", 7, tier=1),
    ]
    out = rank_and_cut(
        xs, key=lambda x: x.score, n=3, tier=lambda x: x.tier, slack=2
    )
    assert [x.name for x in out] == ["c", "b", "a"]
    assert "d" not in {x.name for x in out}


def test_slack_int_additive():
    # n=4, slack=1 → bound=5. After 4 from tier0+fill, 1-member bonus fits.
    xs = [
        Scored("a", 1, tier=0),
        Scored("b", 2, tier=0),
        Scored("c", 3, tier=0),
        Scored("d", 4, tier=0),
        Scored("e", 99, tier=1),
    ]
    out = rank_and_cut(
        xs, key=lambda x: x.score, n=4, tier=lambda x: x.tier, slack=1
    )
    assert [x.name for x in out] == ["d", "c", "b", "a", "e"]


def test_slack_float_multiplicative():
    # n=10, slack=1.5 → bound=15. Fill to 10 from tier1 (tier0 empty), then
    # 4-member tier2 bonus fits; would skip a 6-member (tested separately shape).
    xs = [Scored(f"t1-{i}", 100 - i, tier=1) for i in range(10)] + [
        Scored(f"t2-{i}", 50 - i, tier=2) for i in range(4)
    ]
    out = rank_and_cut(
        xs, key=lambda x: x.score, n=10, tier=lambda x: x.tier, slack=1.5
    )
    assert len(out) == 14
    assert all(x.tier == 1 for x in out[:10])
    assert all(x.tier == 2 for x in out[10:])


def test_slack_float_multiplicative_skip_oversized_bonus():
    xs = [Scored(f"t1-{i}", 100 - i, tier=1) for i in range(10)] + [
        Scored(f"t2-{i}", 50 - i, tier=2) for i in range(6)
    ]
    out = rank_and_cut(
        xs, key=lambda x: x.score, n=10, tier=lambda x: x.tier, slack=1.5
    )
    assert len(out) == 10
    assert all(x.tier == 1 for x in out)


def test_slack_strict_minus_one():
    xs = [
        Scored("a", 1, tier=0),
        Scored("b", 2, tier=0),
        Scored("c", 3, tier=0),
        Scored("d", 9, tier=1),
    ]
    out = rank_and_cut(
        xs, key=lambda x: x.score, n=3, tier=lambda x: x.tier, slack=-1
    )
    assert [x.name for x in out] == ["c", "b", "a"]


def test_slack_identities_no_bonus_room():
    xs = [
        Scored("a", 1, tier=0),
        Scored("b", 2, tier=0),
        Scored("c", 3, tier=0),
        Scored("d", 9, tier=1),
    ]
    for slack in (0, 1.0):
        out = rank_and_cut(
            xs, key=lambda x: x.score, n=3, tier=lambda x: x.tier, slack=slack
        )
        assert [x.name for x in out] == ["c", "b", "a"], f"slack={slack!r}"


def test_order_ascending_vs_descending():
    xs = [Scored("a", 1), Scored("b", 2), Scored("c", 3)]
    desc = rank_and_cut(xs, key=lambda x: x.score, n=3, order="descending")
    asc = rank_and_cut(xs, key=lambda x: x.score, n=3, order="ascending")
    assert [x.name for x in desc] == ["c", "b", "a"]
    assert [x.name for x in asc] == ["a", "b", "c"]


def test_non_usage_numeric_score_key():
    xs = [Scored("low", 1.5), Scored("high", 9.25), Scored("mid", 4.0)]
    out = rank_and_cut(xs, key=lambda x: x.score, n=2)
    assert [x.name for x in out] == ["high", "mid"]


def test_n_zero_tiered_keeps_tier0_only():
    xs = [
        Scored("a", 1, tier=0),
        Scored("b", 2, tier=0),
        Scored("c", 99, tier=1),
    ]
    out = rank_and_cut(xs, key=lambda x: x.score, n=0, tier=lambda x: x.tier)
    assert [x.name for x in out] == ["b", "a"]


def test_negative_n_raises():
    with pytest.raises(ValueError):
        rank_and_cut(["a"], key=lambda x: x, n=-1)
