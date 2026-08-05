"""Tests for recommender.threat_counters.query_threat_counters."""

from __future__ import annotations

from unittest.mock import patch

from recommender.matchup import MatchupResult
from recommender.state import ThreatCandidate, ThreatCounterCandidate
from recommender.threat_counters import (
    aggregate_verified,
    pair_score,
    query_threat_counters,
)


def _tc(
    species: str,
    *,
    usage_rank: int | None = None,
    kinds: frozenset[str] | None = None,
    ko_score: float = 0.0,
) -> ThreatCandidate:
    return ThreatCandidate(
        ladder_species=species,
        usage_rank=usage_rank,
        form=species,
        showdown_usage_pct=None,
        showdown_formes=(),
        spec={"species": species, "moves": ["Tackle"], "ability": "Dummy"},
        build_source="ingame",
        threat_kinds=kinds or frozenset(),
        ko_threshold_score=ko_score,
    )


def test_pair_score_and_aggregate():
    strong = MatchupResult(outcome="clean_kill", severity="decisive")
    weak = MatchupResult(outcome="intentional_non_ko_answer", severity="toss-up")
    none = MatchupResult(outcome="no_answer", severity="toss-up")
    assert pair_score(strong) == 4.0
    assert pair_score(weak) == 2.0 * 0.25
    assert pair_score(none) == 0.0
    assert aggregate_verified([strong, weak]) == 4.0 + 0.5


def test_empty_anchor():
    assert query_threat_counters({}) == []
    with patch(
        "recommender.threat_counters.query_counters", return_value=[]
    ) as qc:
        assert query_threat_counters({"species": "Blaziken-Mega"}) == []
        assert qc.call_count == 1


def test_full_steps_1_and_2_call_count():
    """Each step-1 threat gets its own query_counters call (no pre-trim)."""
    threats = [_tc(f"Threat{i}", usage_rank=i + 1) for i in range(4)]
    counters_for = {
        "Threat0": [_tc("CandA", usage_rank=10)],
        "Threat1": [_tc("CandA", usage_rank=10), _tc("CandB", usage_rank=5)],
        "Threat2": [_tc("CandB", usage_rank=5)],
        "Threat3": [_tc("CandC", usage_rank=20)],
    }
    calls: list[str] = []

    def fake_qc(pokemon, n=20):
        sp = pokemon.get("species") or ""
        calls.append(sp)
        if sp == "Anchor":
            return list(threats)
        return list(counters_for.get(sp, []))

    with (
        patch("recommender.threat_counters.query_counters", side_effect=fake_qc),
        patch(
            "recommender.threat_counters.classify_matchup",
            return_value=MatchupResult(outcome="clean_kill", severity="decisive"),
        ),
    ):
        query_threat_counters({"species": "Anchor"}, n=10, verify_threats_n=5)

    assert calls[0] == "Anchor"
    assert calls[1:] == [f"Threat{i}" for i in range(4)]
    assert len(calls) == 1 + len(threats)


def test_merge_count_across_threats():
    threats = [_tc("T1", usage_rank=1), _tc("T2", usage_rank=2), _tc("T3", usage_rank=3)]

    def fake_qc(pokemon, n=20):
        sp = pokemon.get("species") or ""
        if sp == "Anchor":
            return list(threats)
        # CandA appears under all three threats
        return [_tc("CandA", usage_rank=10)]

    with (
        patch("recommender.threat_counters.query_counters", side_effect=fake_qc),
        patch(
            "recommender.threat_counters.classify_matchup",
            return_value=MatchupResult(outcome="clean_kill", severity="decisive"),
        ),
    ):
        out = query_threat_counters({"species": "Anchor"}, n=10, verify_threats_n=5)

    assert len(out) == 1
    assert out[0].threats_countered_count == 3
    assert set(out[0].threats_countered) == {"t1", "t2", "t3"}


def test_stage4_cuts_to_n_by_count():
    threats = [_tc("T1", usage_rank=1)]

    def fake_qc(pokemon, n=20):
        sp = pokemon.get("species") or ""
        if sp == "Anchor":
            return list(threats)
        # 12 candidates each counting 1
        return [_tc(f"Cand{i}", usage_rank=i + 1) for i in range(12)]

    with (
        patch("recommender.threat_counters.query_counters", side_effect=fake_qc),
        patch(
            "recommender.threat_counters.classify_matchup",
            return_value=MatchupResult(outcome="no_answer", severity="toss-up"),
        ),
    ):
        out = query_threat_counters({"species": "Anchor"}, n=10, verify_threats_n=5)

    assert len(out) == 10


def test_stage5_usage_order_differs_from_counters_order():
    """Usage-only re-select ≠ query_counters danger-first input order."""
    # Input order: low-usage dual-axis first, then high-usage singles (counters style).
    threats = [
        _tc("RareDanger", usage_rank=50, kinds=frozenset({"ko_threshold", "wall"}), ko_score=1.0),
        _tc("MidDanger", usage_rank=40, kinds=frozenset({"ko_threshold", "wall"}), ko_score=1.0),
        _tc("Popular", usage_rank=1, kinds=frozenset({"wall"}), ko_score=0.0),
        _tc("AlsoPopular", usage_rank=2, kinds=frozenset({"ko_threshold"}), ko_score=1.0),
        _tc("Third", usage_rank=3, kinds=frozenset({"wall"}), ko_score=0.0),
    ]
    counters_order = [t.form for t in threats]

    def fake_qc(pokemon, n=20):
        sp = pokemon.get("species") or ""
        if sp == "Anchor":
            return list(threats)
        return [_tc("Teammate", usage_rank=10)]

    with (
        patch("recommender.threat_counters.query_counters", side_effect=fake_qc),
        patch(
            "recommender.threat_counters.classify_matchup",
            return_value=MatchupResult(outcome="clean_kill", severity="decisive"),
        ),
    ):
        # Peek stage-5 via verifying which threats get classify calls
        classified: list[str] = []

        def fake_classify(a, b, field=None, client=None):
            classified.append(b.get("species") or "")
            return MatchupResult(outcome="clean_kill", severity="decisive")

        with patch(
            "recommender.threat_counters.classify_matchup", side_effect=fake_classify
        ):
            query_threat_counters({"species": "Anchor"}, n=10, verify_threats_n=3)

    # Usage-only top-3: Popular / AlsoPopular / Third — not RareDanger / MidDanger.
    assert set(classified) == {"Popular", "AlsoPopular", "Third"}
    assert set(classified) != set(counters_order[:3])


def test_verify_as_rank_strong_beats_high_static_count():
    """Lower static count + decisive verifies outranks higher count + weak verifies."""
    threats = [
        _tc("T1", usage_rank=1),
        _tc("T2", usage_rank=2),
        _tc("T3", usage_rank=3),
    ]

    def fake_qc(pokemon, n=20):
        sp = pokemon.get("species") or ""
        if sp == "Anchor":
            return list(threats)
        if sp == "T1":
            return [_tc("WideWeak", usage_rank=20), _tc("NarrowStrong", usage_rank=30)]
        if sp == "T2":
            return [_tc("WideWeak", usage_rank=20), _tc("NarrowStrong", usage_rank=30)]
        if sp == "T3":
            return [_tc("WideWeak", usage_rank=20)]
        return []

    def fake_classify(a, b, field=None, client=None):
        cand = a.get("species")
        if cand == "NarrowStrong":
            return MatchupResult(outcome="clean_kill", severity="decisive")
        # WideWeak: weak answers
        return MatchupResult(outcome="intentional_non_ko_answer", severity="toss-up")

    with (
        patch("recommender.threat_counters.query_counters", side_effect=fake_qc),
        patch(
            "recommender.threat_counters.classify_matchup", side_effect=fake_classify
        ),
    ):
        out = query_threat_counters({"species": "Anchor"}, n=10, verify_threats_n=5)

    names = [c.candidate.form for c in out]
    assert names[0] == "NarrowStrong"
    assert names.index("NarrowStrong") < names.index("WideWeak")
    strong = next(c for c in out if c.candidate.form == "NarrowStrong")
    weak = next(c for c in out if c.candidate.form == "WideWeak")
    assert strong.threats_countered_count == 2
    assert weak.threats_countered_count == 3
    assert strong.verified_score > weak.verified_score


def test_credit_outside_verify_set_is_neutral():
    """Threat credited in merge but outside usage top-N: not classified, not penalized."""
    threats = [
        _tc("Popular", usage_rank=1),
        _tc("Obscure", usage_rank=99),
    ]

    def fake_qc(pokemon, n=20):
        sp = pokemon.get("species") or ""
        if sp == "Anchor":
            return list(threats)
        # Cand only counters Obscure (outside top-1 verify set when verify_threats_n=1)
        if sp == "Obscure":
            return [_tc("OnlyObscure", usage_rank=10)]
        if sp == "Popular":
            return [_tc("CoversPopular", usage_rank=11)]
        return []

    classified_vs: list[str] = []

    def fake_classify(a, b, field=None, client=None):
        classified_vs.append(b.get("species") or "")
        return MatchupResult(outcome="clean_kill", severity="decisive")

    with (
        patch("recommender.threat_counters.query_counters", side_effect=fake_qc),
        patch(
            "recommender.threat_counters.classify_matchup", side_effect=fake_classify
        ),
    ):
        out = query_threat_counters({"species": "Anchor"}, n=10, verify_threats_n=1)

    assert "Obscure" not in classified_vs
    assert "Popular" in classified_vs
    only = next(c for c in out if c.candidate.form == "OnlyObscure")
    assert only.threats_countered_count == 1
    assert "obscure" in only.threats_countered
    assert only.verified_score == 0.0  # credit exists but not verified — neutral
    assert only.verified_vs == ()


def test_excludes_anchor_species_from_merge():
    threats = [_tc("T1", usage_rank=1)]

    def fake_qc(pokemon, n=20):
        sp = pokemon.get("species") or ""
        if sp == "Anchor":
            return list(threats)
        return [_tc("Anchor", usage_rank=1), _tc("Other", usage_rank=2)]

    with (
        patch("recommender.threat_counters.query_counters", side_effect=fake_qc),
        patch(
            "recommender.threat_counters.classify_matchup",
            return_value=MatchupResult(outcome="clean_kill", severity="decisive"),
        ),
    ):
        out = query_threat_counters({"species": "Anchor"}, n=10)

    assert all(c.candidate.form != "Anchor" for c in out)
    assert any(c.candidate.form == "Other" for c in out)


def test_candidate_pool_asymmetry_threat_id_unrestricted():
    """candidate_pool restricts step-2+ only; step-1 threats stay full-meta."""
    # ThreatOutside is NOT in the restrictive teammate pool — proves step 1 unrestricted.
    threats = [
        _tc("ThreatOutside", usage_rank=1),
        _tc("ThreatInPool", usage_rank=2),
    ]
    restrictive = [{"species": "CandA"}, {"species": "CandB"}]
    calls: list[tuple[str, object]] = []

    def fake_qc(pokemon, n=20, candidate_pool=None):
        sp = pokemon.get("species") or ""
        calls.append((sp, candidate_pool))
        if sp == "Anchor":
            return list(threats)
        # Step-2: only return candidates that are in the restrictive pool.
        if candidate_pool is not None:
            allowed = {p.get("species") for p in candidate_pool}
            return [
                _tc(name, usage_rank=i + 1)
                for i, name in enumerate(["CandA", "CandB", "CandOutside"])
                if name in allowed
            ]
        return [_tc("CandA", usage_rank=1), _tc("CandOutside", usage_rank=99)]

    with (
        patch("recommender.threat_counters.query_counters", side_effect=fake_qc),
        patch(
            "recommender.threat_counters.classify_matchup",
            return_value=MatchupResult(outcome="clean_kill", severity="decisive"),
        ),
    ):
        out = query_threat_counters(
            {"species": "Anchor"},
            n=10,
            verify_threats_n=5,
            candidate_pool=restrictive,
        )

    # Call 0 = step-1 anchor: no pool passed (None).
    assert calls[0] == ("Anchor", None)
    # Later calls receive the restrictive pool.
    assert all(c[1] is restrictive for c in calls[1:])
    # Step-1 threats include a species outside the teammate pool.
    step1_names = {t.form for t in threats}
    pool_names = {p["species"] for p in restrictive}
    assert step1_names - pool_names  # ThreatOutside ∉ restrictive
    assert "ThreatOutside" in step1_names
    # Final candidates ⊆ restrictive pool.
    assert out
    assert {c.candidate.form for c in out} <= pool_names


def test_most_common_verify_spec_cache_hit_and_usage_fallback():
    from recommender.threat_counters import _most_common_verify_spec

    usage = {
        "species": "Garchomp",
        "moves": ["Earthquake", "Dragon Claw", "Rock Slide", "Protect"],
        "item": "Life Orb",
        "ability": "Rough Skin",
        "evs": {"hp": 0, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 34},
    }
    cached_spread = {"hp": 4, "atk": 30, "def": 0, "spa": 0, "spd": 0, "spe": 32}

    with (
        patch(
            "recommender.threat_counters.featured_or_common_set",
            return_value=usage,
        ),
        patch(
            "recommender.threat_counters.get_resolved_build",
            return_value={"spread": cached_spread, "verified": True},
        ),
    ):
        hit = _most_common_verify_spec("Garchomp")
    assert hit["evs"] == cached_spread
    assert hit["moves"] == usage["moves"]
    assert hit["item"] == "Life Orb"

    with (
        patch(
            "recommender.threat_counters.featured_or_common_set",
            return_value=usage,
        ),
        patch("recommender.threat_counters.get_resolved_build", return_value=None),
    ):
        miss = _most_common_verify_spec("Garchomp")
    assert miss["evs"] == usage["evs"]  # usage-sourced, not cache

    with patch(
        "recommender.threat_counters.featured_or_common_set", return_value=None
    ):
        bare = _most_common_verify_spec("UnknownMon")
    assert bare == {"species": "UnknownMon"}


def test_classify_matchup_receives_most_common_verify_specs():
    """Stage-6 passes resolved specs, not raw query_counters specs."""
    threats = [_tc("Threat0", usage_rank=1)]
    seen: list[tuple[object, object]] = []

    def fake_qc(pokemon, n=20, candidate_pool=None):
        sp = pokemon.get("species") or ""
        if sp == "Anchor":
            return list(threats)
        return [_tc("CandA", usage_rank=5)]

    def fake_classify(a, b, field=None, client=None):
        seen.append((a, b))
        return MatchupResult(outcome="clean_kill", severity="decisive")

    with (
        patch("recommender.threat_counters.query_counters", side_effect=fake_qc),
        patch(
            "recommender.threat_counters.classify_matchup", side_effect=fake_classify
        ),
        patch(
            "recommender.threat_counters._most_common_verify_spec",
            side_effect=lambda sp, regulation="champions-reg-mb": {
                "species": sp,
                "item": f"{sp}-Item",
                "evs": {"hp": 1},
            },
        ),
    ):
        query_threat_counters({"species": "Anchor"}, n=10, verify_threats_n=5)

    assert seen
    a, b = seen[0]
    assert a.get("item") == "CandA-Item"
    assert b.get("item") == "Threat0-Item"
    assert a.get("evs") == {"hp": 1}
