"""Tests for recommender.threat_counters.query_threat_counters."""

from __future__ import annotations

from unittest.mock import patch

from recommender.matchup import MatchupEvidenceError, MatchupResult
from recommender.state import (
    TeamThreatObjectiveRow,
    ThreatCandidate,
    ThreatCounterCandidate,
)
from recommender.threat_counters import (
    _best_matchup_with_forced_fields,
    aggregate_verified,
    pair_score,
    query_candidates_for_threats,
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
    empty = query_threat_counters({})
    assert empty.status == "available"
    assert empty.candidates == ()
    with patch(
        "recommender.threat_counters.query_counters", return_value=[]
    ) as qc:
        empty2 = query_threat_counters({"species": "Blaziken-Mega"})
        assert empty2.status == "available"
        assert empty2.candidates == ()
        assert qc.call_count == 1


def test_explicit_team_objective_verifies_every_admitted_candidate_against_all_rows():
    objective = (
        TeamThreatObjectiveRow(_tc("T1"), frozenset({"uncovered"})),
        TeamThreatObjectiveRow(_tc("T2"), frozenset({"spof"})),
    )

    def fake_qc(pokemon, **_kwargs):
        return [_tc("Cand")] if pokemon["species"] == "T1" else []

    with (
        patch("recommender.threat_counters.query_counters", side_effect=fake_qc),
        patch(
            "recommender.threat_counters.classify_matchup",
            return_value=MatchupResult("clean_kill", "costly"),
        ),
    ):
        result = query_candidates_for_threats(objective)

    assert result.status == "available"
    assert [threat_id for threat_id, _ in result.candidates[0].verified_vs] == [
        "t1",
        "t2",
    ]


def test_explicit_team_objective_reports_incomplete_calc_evidence():
    objective = (TeamThreatObjectiveRow(_tc("T1"), frozenset({"uncovered"})),)
    with (
        patch("recommender.threat_counters.query_counters", return_value=[_tc("Cand")]),
        patch(
            "recommender.threat_counters.classify_matchup",
            side_effect=MatchupEvidenceError("bad row"),
        ),
    ):
        result = query_candidates_for_threats(objective)
    assert result.status == "unavailable"
    assert result.error is not None
    assert result.error.kind == "calc_incomplete"


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
        result = query_threat_counters({"species": "Anchor"}, n=10, verify_threats_n=5)
        out = result.candidates

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
        result = query_threat_counters({"species": "Anchor"}, n=10, verify_threats_n=5)
        out = result.candidates

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
        result = query_threat_counters({"species": "Anchor"}, n=10, verify_threats_n=5)
        out = result.candidates

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
        result = query_threat_counters({"species": "Anchor"}, n=10, verify_threats_n=1)
        out = result.candidates

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
        result = query_threat_counters({"species": "Anchor"}, n=10)
        out = result.candidates

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
        result = query_threat_counters(
            {"species": "Anchor"},
            n=10,
            verify_threats_n=5,
            candidate_pool=restrictive,
        )
        out = result.candidates

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


def test_owned_first_reaches_candidate_stages_but_not_threat_stages():
    threats = [_tc("ThreatOutsideBox", usage_rank=1)]
    calls: list[tuple[str, dict]] = []
    classified_threats: list[str] = []

    def fake_qc(pokemon, n=20, **kwargs):
        species = pokemon.get("species") or ""
        calls.append((species, kwargs))
        if species == "Anchor":
            return list(threats)
        return [
            _tc("PopularUnowned", usage_rank=1),
            _tc("RareOwned", usage_rank=99),
        ]

    def fake_classify(a, b, field=None, client=None):
        classified_threats.append(b.get("species") or "")
        return MatchupResult(outcome="clean_kill", severity="decisive")

    with (
        patch("recommender.threat_counters.query_counters", side_effect=fake_qc),
        patch(
            "recommender.threat_counters.classify_matchup",
            side_effect=fake_classify,
        ),
    ):
        result = query_threat_counters(
            {"species": "Anchor"},
            n=1,
            available_pool=["RareOwned", "RareOwned"],
            ownership_mode="owned_first",
        )
        out = result.candidates

    assert [c.candidate.form for c in out] == ["RareOwned"]
    assert calls[0] == ("Anchor", {})
    assert all(
        kwargs == {
            "available_pool": ["RareOwned", "RareOwned"],
            "ownership_mode": "owned_first",
        }
        for _, kwargs in calls[1:]
    )
    assert classified_threats == ["ThreatOutsideBox"]


def test_owned_last_breaks_final_candidate_tie():
    threats = [_tc("Threat", usage_rank=1)]

    def fake_qc(pokemon, n=20, **kwargs):
        if pokemon.get("species") == "Anchor":
            return list(threats)
        return [_tc("Unowned", usage_rank=5), _tc("Owned", usage_rank=5)]

    with (
        patch("recommender.threat_counters.query_counters", side_effect=fake_qc),
        patch(
            "recommender.threat_counters.classify_matchup",
            return_value=MatchupResult(outcome="clean_kill", severity="decisive"),
        ),
    ):
        result = query_threat_counters(
            {"species": "Anchor"},
            n=2,
            available_pool=["Owned"],
            ownership_mode="owned_last",
        )
        out = result.candidates

    assert [c.candidate.form for c in out] == ["Owned", "Unowned"]


def test_owned_only_empty_pool_returns_empty_without_verification():
    threats = [_tc("Threat", usage_rank=1)]
    candidate_calls: list[dict] = []

    def fake_qc(pokemon, n=20, **kwargs):
        if pokemon.get("species") == "Anchor":
            return list(threats)
        candidate_calls.append(kwargs)
        return []

    with (
        patch("recommender.threat_counters.query_counters", side_effect=fake_qc),
        patch("recommender.threat_counters.classify_matchup") as classify,
    ):
        result = query_threat_counters(
            {"species": "Anchor"},
            available_pool=[],
            ownership_mode="owned_only",
        )
        out = result.candidates

    assert out == ()
    assert candidate_calls == [
        {"available_pool": [], "ownership_mode": "owned_only"}
    ]
    classify.assert_not_called()


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


def test_query_threat_counters_degraded_on_calc_failure():
    from recommender.calc_client import CalcClientError

    threats = [_tc("T1", usage_rank=1)]

    def fake_qc(pokemon, n=20, **kwargs):
        sp = pokemon.get("species") or ""
        if sp == "Anchor":
            return list(threats)
        return [_tc("CandA", usage_rank=10, kinds=frozenset({"wall"}))]

    with (
        patch("recommender.threat_counters.query_counters", side_effect=fake_qc),
        patch(
            "recommender.threat_counters.classify_matchup",
            side_effect=CalcClientError(503, {"error": "down"}),
        ),
    ):
        result = query_threat_counters({"species": "Anchor"}, n=10, verify_threats_n=5)

    assert result.status == "degraded"
    assert result.error is not None
    assert result.error.kind == "calc_unavailable"
    assert result.candidates
    for row in result.candidates:
        assert row.estimate_kind == "static"
        assert row.verified_vs == ()
        assert row.verified_score == 0.0


def test_best_matchup_with_forced_fields_neutral_answers_skips_field_check():
    """If the neutral matchup already answers the threat, forced fields
    are never even tried -- confirms the fallback only fires when
    genuinely needed, not on every call."""
    with patch(
        "recommender.threat_counters.classify_matchup",
        return_value=MatchupResult("clean_kill", "decisive"),
    ) as cm:
        result = _best_matchup_with_forced_fields(
            {"species": "Garchomp"},
            {"species": "SomeThreat"},
            [{"weather": "Rain"}],
            client=None,
        )
    assert result.outcome == "clean_kill"
    assert cm.call_count == 1  # only the neutral call, forced field never tried


def test_best_matchup_with_forced_fields_falls_back_when_neutral_fails():
    """Regression for the confirmed root-cause bug: a candidate that only
    answers a threat under a real, team-provided field (e.g. a Water-type
    that only threatens a Fire-type target once Rain actually boosts its
    offense) must be credited for that -- not evaluated as if the team's
    real Rain were never in play."""
    def fake_classify(cand, threat, field, *, client=None):
        if field is None:
            return MatchupResult("no_answer", "toss-up")
        assert field == {"weather": "Rain"}
        return MatchupResult("clean_kill", "decisive")

    with patch(
        "recommender.threat_counters.classify_matchup", side_effect=fake_classify
    ):
        result = _best_matchup_with_forced_fields(
            {"species": "Swampert-Mega"},
            {"species": "SomeFireThreat"},
            [{"weather": "Rain"}],
            client=None,
        )
    assert result.outcome == "clean_kill"


def test_best_matchup_with_forced_fields_no_forced_fields_returns_neutral():
    """No locked field providers at all -- falls through to the neutral
    result unchanged, same as before this fix existed."""
    with patch(
        "recommender.threat_counters.classify_matchup",
        return_value=MatchupResult("no_answer", "toss-up"),
    ) as cm:
        result = _best_matchup_with_forced_fields(
            {"species": "Delphox"}, {"species": "SomeThreat"}, [], client=None
        )
    assert result.outcome == "no_answer"
    assert cm.call_count == 1


def test_query_candidates_for_threats_credits_field_dependent_answer():
    """Full end-to-end regression, exact shape of the confirmed live bug:
    a candidate that only counters the threat once the team's real,
    locked field state (Rain) is accounted for must show up as
    'verified' against that threat -- previously this was structurally
    impossible, since every classify_matchup call in this function
    passed field=None unconditionally."""
    objective = (TeamThreatObjectiveRow(_tc("FireThreat"), frozenset({"uncovered"})),)

    def fake_classify(cand, threat, field, *, client=None):
        if field is None:
            return MatchupResult("no_answer", "toss-up")
        return MatchupResult("clean_kill", "decisive")

    with (
        patch(
            "recommender.threat_counters.query_counters",
            return_value=[_tc("Swampert-Mega")],
        ),
        patch(
            "recommender.threat_counters.classify_matchup", side_effect=fake_classify
        ),
    ):
        result = query_candidates_for_threats(
            objective, locked_contexts=(), exclude_slot=None
        )
    # With no locked_contexts (no team-provided field), the candidate
    # correctly does NOT get credited -- confirms the baseline behavior
    # (no forced fields available) is unchanged before testing the fix.
    assert result.candidates[0].verified_score == 0.0

    class _FakeMechanism:
        def __init__(self):
            self.present = True
            self.relation = "provides"
            self.mechanic = "Drizzle"
            self.evidence = ("condition:Rain",)

    class _FakeRoleDecision:
        mechanisms = (_FakeMechanism(),)

    class _FakeContext:
        slot_index = 0
        role_decision = _FakeRoleDecision()

    with (
        patch(
            "recommender.threat_counters.query_counters",
            return_value=[_tc("Swampert-Mega")],
        ),
        patch(
            "recommender.threat_counters.classify_matchup", side_effect=fake_classify
        ),
    ):
        result_with_rain = query_candidates_for_threats(
            objective, locked_contexts=(_FakeContext(),)
        )
    assert result_with_rain.candidates[0].verified_score > 0.0


def test_best_matchup_with_forced_fields_upgrades_already_answered_but_improvable_result():
    """Regression for a real, confirmed gap found live: a Steel-type
    candidate already 'answers' a Fire-type threat neutrally (surviving
    via bulk despite Steel's real 2x Fire weakness) but only at 'costly'
    severity -- the original fix's short-circuit ('return neutral
    whenever it isn't a hard no_answer') would never have re-checked
    whether Rain (halving Fire's power) makes that matchup meaningfully
    safer. Severity feeds directly into the real ranking score via
    pair_score/aggregate_verified, so this is a ranking-correctness gap,
    not cosmetic. Confirms the fix now correctly checks and upgrades.
    """
    def fake_classify(cand, threat, field, *, client=None):
        if field is None:
            return MatchupResult("intentional_non_ko_answer", "costly")
        assert field == {"weather": "Rain"}
        return MatchupResult("intentional_non_ko_answer", "decisive")

    with patch(
        "recommender.threat_counters.classify_matchup", side_effect=fake_classify
    ):
        result = _best_matchup_with_forced_fields(
            {"species": "Kingambit"},
            {"species": "SomeFireThreat"},
            [{"weather": "Rain"}],
            client=None,
        )
    assert result.outcome == "intentional_non_ko_answer"
    assert result.severity == "decisive"


def test_best_matchup_with_forced_fields_skips_check_only_at_absolute_ceiling():
    """The one legitimate short-circuit: neutral is already clean_kill +
    decisive (pair_score 4.0, the real maximum per _OUTCOME_POINTS/
    _SEVERITY_POINTS) -- nothing can improve on that, so the forced-field
    check is correctly skipped, confirmed against the real point tables
    rather than assumed."""
    with patch(
        "recommender.threat_counters.classify_matchup",
        return_value=MatchupResult("clean_kill", "decisive"),
    ) as cm:
        result = _best_matchup_with_forced_fields(
            {"species": "Garchomp"},
            {"species": "SomeThreat"},
            [{"weather": "Rain"}],
            client=None,
        )
    assert result.outcome == "clean_kill"
    assert result.severity == "decisive"
    assert cm.call_count == 1


def test_best_matchup_with_forced_fields_does_not_downgrade_when_field_is_worse():
    """A candidate that answers well neutrally but WORSE under a forced
    field (e.g. a matchup that's actually harder under Rain for some
    other reason) must not be downgraded -- the best result across all
    evaluated states wins, not just the last one checked."""
    def fake_classify(cand, threat, field, *, client=None):
        if field is None:
            return MatchupResult("clean_kill", "costly")
        return MatchupResult("intentional_non_ko_answer", "toss-up")

    with patch(
        "recommender.threat_counters.classify_matchup", side_effect=fake_classify
    ):
        result = _best_matchup_with_forced_fields(
            {"species": "Kingambit"},
            {"species": "SomeThreat"},
            [{"weather": "Rain"}],
            client=None,
        )
    assert result.outcome == "clean_kill"
    assert result.severity == "costly"
