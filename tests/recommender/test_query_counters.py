"""Tests for recommender.counters.query_counters."""

from __future__ import annotations

from unittest.mock import patch

from recommender.counters import (
    ASSUMED_FAINTED_TEAMMATES,
    ASSUMED_HITS_TAKEN,
    KO_THRESHOLD_BP,
    QUERY_COUNTERS_SLACK,
    _ko_best_move,
    _scaled_base_power,
    query_counters,
    threat_tier,
    type_effectiveness,
)
from recommender.legality import load_snapshot
from recommender.ids import to_id
from recommender.matchup import effective_accuracy, expected_hit_factor
from recommender.ranking import rank_and_cut
from recommender.state import ThreatCandidate
from recommender.usage_data import ingame_species_map


def test_expected_hit_factor_distribution_and_skill_link():
    hits, folded = expected_hit_factor("bulletseed", None, 1.0)
    assert abs(hits - 3.1) < 1e-9
    assert folded is False

    hits_sl, folded_sl = expected_hit_factor("bulletseed", "Skill Link", 1.0)
    assert hits_sl == 5.0
    assert folded_sl is False

    hits_pb, folded_pb = expected_hit_factor("populationbomb", "Skill Link", 0.9)
    assert hits_pb == 10.0
    assert folded_pb is True  # certain sequence — do not also × accuracy


def test_expected_hit_factor_phase3_multi_hits():
    for mid in ("bonerush", "watershuriken"):
        hits, folded = expected_hit_factor(mid, None, 1.0)
        assert abs(hits - 3.1) < 1e-9
        assert folded is False
        hits_sl, folded_sl = expected_hit_factor(mid, "Skill Link", 1.0)
        assert hits_sl == 5.0
        assert folded_sl is False

    for mid in ("dualwingbeat", "doublehit", "dragondarts", "twinbeam"):
        hits, folded = expected_hit_factor(mid, None, 1.0)
        assert hits == 2.0
        assert folded is False
        hits_sl, folded_sl = expected_hit_factor(mid, "Skill Link", 0.9)
        assert hits_sl == 2.0
        assert folded_sl is False

    expected_ta = sum(0.9**i for i in range(1, 4))
    hits_ta, folded_ta = expected_hit_factor("tripleaxel", None, 0.9)
    assert folded_ta is True
    assert abs(hits_ta - expected_ta) < 1e-9
    hits_ta_sl, folded_ta_sl = expected_hit_factor("tripleaxel", "Skill Link", 0.9)
    assert hits_ta_sl == 3.0
    assert folded_ta_sl is True


def test_effective_accuracy_compound_eyes_and_no_guard():
    assert effective_accuracy(70, "No Guard") == 1.0
    assert abs(effective_accuracy(70, "Compound Eyes") - 0.91) < 1e-9
    assert effective_accuracy(True, None) == 1.0
    assert effective_accuracy(None, None) == 1.0


def test_threat_tier_axis_count():
    assert threat_tier(frozenset({"ko_threshold", "wall"})) == 0
    assert threat_tier(frozenset({"ko_threshold"})) == 1
    assert threat_tier(frozenset({"wall"})) == 1
    assert threat_tier(frozenset()) == 2


def test_ko_binary_at_threshold():
    """Synthetic effective_bp gate via KO_THRESHOLD_BP constant."""
    # 100 BP SE STAB: 100*2*1.5 = 300 >= 200 → clears
    assert 100 * 2.0 * 1.5 >= KO_THRESHOLD_BP
    # 80 BP neutral no STAB: 80 < 200 → no clear
    assert 80 * 1.0 * 1.0 < KO_THRESHOLD_BP

    # Real: Orthworm (Steel) vs a strong Fighting coverage user should KO-match.
    # Use Blaziken as candidate against Orthworm as anchor via full query.
    out = query_counters({"species": "Orthworm"}, n=50)
    assert any("ko_threshold" in c.threat_kinds for c in out)
    # Below-threshold: a known non-threat typing with weak moves is hard to guarantee
    # on real data; assert score semantics on returned KO matches instead.
    for c in out:
        if "ko_threshold" in c.threat_kinds:
            assert c.ko_threshold_score >= 1.0
        else:
            assert c.ko_threshold_score < 1.0 or c.ko_threshold_score == 0.0


def test_vacuous_wall_status_only_falls_back_to_stab():
    # Status-only moves must not vacuous-match the entire legal pool.
    out = query_counters(
        {"species": "Blaziken-Mega", "moves": ["Protect", "Will-O-Wisp", "Roost"]},
        n=20,
    )
    assert len(out) >= 1
    # Compare to empty-moves (explicit STAB) — same attack types → same result set
    out_stab = query_counters({"species": "Blaziken-Mega"}, n=20)
    assert {c.form for c in out} == {c.form for c in out_stab}


def test_blaziken_mega_ceruledge_wall():
    # Usage-primary within-tier key admits wall-only Ceruledge at default n=20.
    out = query_counters({"species": "Blaziken-Mega"}, n=20)
    cer = next(c for c in out if to_id(c.form) == "ceruledge")
    assert "wall" in cer.threat_kinds
    # Fire/Ghost typing does not SE into Fire/Fighting — wall-only, not KO.
    assert "ko_threshold" not in cer.threat_kinds


def test_ko_non_stab_identifiable():
    """Non-STAB best move still tags ko_threshold with ko_best_was_stab False."""
    # Orthworm is pure Steel — Fighting coverage from non-Fighting typings is non-STAB.
    out = query_counters({"species": "Orthworm"}, n=80)
    nonstab = [
        c
        for c in out
        if "ko_threshold" in c.threat_kinds and c.ko_best_was_stab is False
    ]
    assert nonstab, "expected at least one KO clear via non-STAB coverage"


def test_multi_axis_tier_precedes_single():
    both = ThreatCandidate(
        ladder_species="A",
        usage_rank=99,
        form="A",
        showdown_usage_pct=None,
        showdown_formes=(),
        spec={"species": "A"},
        build_source="ingame",
        threat_kinds=frozenset({"ko_threshold", "wall"}),
        ko_threshold_score=1.0,
    )
    one = ThreatCandidate(
        ladder_species="B",
        usage_rank=1,
        form="B",
        showdown_usage_pct=None,
        showdown_formes=(),
        spec={"species": "B"},
        build_source="ingame",
        threat_kinds=frozenset({"ko_threshold"}),
        ko_threshold_score=1.0,
    )
    assert threat_tier(both.threat_kinds) < threat_tier(one.threat_kinds)

    out = query_counters({"species": "Blaziken-Mega"}, n=20)
    # All dual-axis results must appear before any single-axis in the list.
    saw_single = False
    for c in out:
        if threat_tier(c.threat_kinds) == 0:
            assert not saw_single
        else:
            saw_single = True


def test_usage_within_tier_ordinal():
    ig = ingame_species_map()
    out = query_counters({"species": "Blaziken-Mega"}, n=20)
    # Within the single-axis (tier 1) block, usage_rank should be ascending among known ranks.
    tier1 = [c for c in out if threat_tier(c.threat_kinds) == 1 and c.usage_rank is not None]
    ranks = [c.usage_rank for c in tier1]
    assert ranks == sorted(ranks)
    # Cross-check against real map for a couple of returned species.
    for c in tier1[:3]:
        entry = ig.get(to_id(c.form)) or ig.get(to_id(c.ladder_species))
        if entry and entry.get("usage_rank") is not None:
            assert c.usage_rank == int(entry["usage_rank"])


def test_no_featured_set_skips_ko_wall_still_possible():
    # Force featured_or_common_set → None; legality ability still allows walls.
    with patch("recommender.counters.featured_or_common_set", return_value=None):
        out = query_counters({"species": "Blaziken-Mega"}, n=50)
    assert out
    assert all("ko_threshold" not in c.threat_kinds for c in out)
    assert any("wall" in c.threat_kinds for c in out)


def test_empty_unknown_species():
    assert query_counters({"species": "DefinitelyNotRealMon"}, n=20) == []


def test_type_effectiveness_basics():
    assert type_effectiveness("Water", ["Fire"]) == 2.0
    assert type_effectiveness("Fighting", ["Ghost"]) == 0.0
    assert type_effectiveness("Fire", ["Bug", "Steel"]) == 4.0


def test_query_counters_slack_is_multiplicative_headroom():
    assert isinstance(QUERY_COUNTERS_SLACK, float)
    assert QUERY_COUNTERS_SLACK > 1.0


def test_multiplicative_slack_bonus_keep_and_skip():
    """Synthetic pools: slack=1.5 keeps whole tier-1 when it fits; skips when not."""
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class Item:
        name: str
        tier: int
        score: float

    # n=4, slack=1.5 → bound=round(6)=6. t0=4 (≥n), t1=2 → 4+2<=6 keep whole.
    keep_pool = [
        Item("a", 0, 3),
        Item("b", 0, 2),
        Item("c", 0, 1),
        Item("d", 0, 0),
        Item("e", 1, 9),
        Item("f", 1, 8),
    ]
    kept = rank_and_cut(
        keep_pool,
        key=lambda x: x.score,
        n=4,
        tier=lambda x: x.tier,
        slack=1.5,
        order="descending",
    )
    assert [x.name for x in kept] == ["a", "b", "c", "d", "e", "f"]

    # Same t0, but t1 has 3 → 4+3=7 > 6 → skip entire bonus tier.
    skip_pool = keep_pool + [Item("g", 1, 7)]
    skipped = rank_and_cut(
        skip_pool,
        key=lambda x: x.score,
        n=4,
        tier=lambda x: x.tier,
        slack=1.5,
        order="descending",
    )
    assert [x.name for x in skipped] == ["a", "b", "c", "d"]


def test_candidate_pool_restricts_results():
    # Full scan for comparison — pick a small restrictive subset of returned forms.
    full = query_counters({"species": "Blaziken-Mega"}, n=20)
    assert len(full) >= 2
    allowed_forms = [full[0].form, full[1].form]
    pool = [{"species": f} for f in allowed_forms]
    out = query_counters({"species": "Blaziken-Mega"}, n=20, candidate_pool=pool)
    assert out
    assert {c.form for c in out} <= set(allowed_forms)


def test_candidate_pool_empty_returns_empty():
    assert (
        query_counters({"species": "Blaziken-Mega"}, n=20, candidate_pool=[]) == []
    )


def test_battle_state_bp_assumptions_not_conflated():
    """Fainted-ally=2 vs hits-taken=1 are independent (ADR-023 follow-up)."""
    assert ASSUMED_FAINTED_TEAMMATES == 2
    assert ASSUMED_HITS_TAKEN == 1
    assert ASSUMED_FAINTED_TEAMMATES != ASSUMED_HITS_TAKEN

    assert _scaled_base_power("lastrespects", 50) == 50 * (1 + ASSUMED_FAINTED_TEAMMATES)
    assert _scaled_base_power("ragefist", 50) == 50 * (1 + ASSUMED_HITS_TAKEN)
    assert _scaled_base_power("lastrespects", 50) == 150
    assert _scaled_base_power("ragefist", 50) == 100
    assert _scaled_base_power("shadowball", 80) == 80

    snap = load_snapshot()
    # Ghost → Fighting is neutral (1×). Last Respects 150 STAB = 150*1*1.5 = 225.
    lr_bp, _ = _ko_best_move(
        snap,
        moves=["Last Respects"],
        cand_types=["Ghost"],
        anchor_types=["Fighting"],
        ability=None,
    )
    assert abs(lr_bp - 150 * 1.5) < 1e-6

    rf_bp, _ = _ko_best_move(
        snap,
        moves=["Rage Fist"],
        cand_types=["Ghost", "Fighting"],
        anchor_types=["Fighting"],
        ability=None,
    )
    assert abs(rf_bp - 100 * 1.5) < 1e-6

    # Supreme Overlord: Ability multiplies ebp by 1.2 (fainted assumption A).
    # Iron Head (Steel) vs Fairy is 2× SE.
    so_bp, _ = _ko_best_move(
        snap,
        moves=["Iron Head"],
        cand_types=["Dark", "Steel"],
        anchor_types=["Fairy"],
        ability="Supreme Overlord",
    )
    base_bp, _ = _ko_best_move(
        snap,
        moves=["Iron Head"],
        cand_types=["Dark", "Steel"],
        anchor_types=["Fairy"],
        ability=None,
    )
    assert abs(so_bp - base_bp * 1.2) < 1e-6
    assert so_bp > base_bp
