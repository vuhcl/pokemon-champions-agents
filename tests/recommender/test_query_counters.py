"""Tests for recommender.counters.query_counters."""

from __future__ import annotations

from unittest.mock import patch

from recommender.counters import (
    ASSUMED_FAINTED_TEAMMATES,
    ASSUMED_HITS_TAKEN,
    KO_THRESHOLD_BP,
    QUERY_COUNTERS_SLACK,
    _dominant_mega_form,
    _ko_best_move,
    _mega_forms_by_base,
    _scaled_base_power,
    defensive_synergy_score,
    query_counters,
    threat_tier,
    type_effectiveness,
)
from recommender.usage_data import showdown_species_map
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
    assert abs(effective_accuracy(70, None) - 0.70) < 1e-9
    assert abs(effective_accuracy(80, None) - 0.80) < 1e-9
    assert abs(effective_accuracy(75, "Hustle", category="Physical") - 0.60) < 1e-9
    assert abs(effective_accuracy(75, "Hustle", category="Special") - 0.75) < 1e-9
    assert effective_accuracy(50, "No Guard") == 1.0
    assert abs(effective_accuracy(70, "Compound Eyes") - 0.91) < 1e-9
    assert effective_accuracy(80, None, defender_ability="No Guard") == 1.0
    assert effective_accuracy(100, "Hustle", defender_ability="No Guard", category="Physical") == 1.0


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
    # Usage-primary within-tier key admits wall-only Ceruledge near the default cut.
    # n=40: wall-only Ceruledge sits past the old n=20/25 boundary after acc-aware KO scores.
    out = query_counters({"species": "Blaziken-Mega"}, n=40)
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


def test_ownership_off_and_owned_first_with_duplicate_box_entries():
    full = query_counters({"species": "Blaziken-Mega"}, n=1000)
    by_tier: dict[int, list[ThreatCandidate]] = {}
    for candidate in full:
        by_tier.setdefault(threat_tier(candidate.threat_kinds), []).append(candidate)
    same_tier = next(group for group in by_tier.values() if len(group) >= 3)[:3]
    candidate_pool = [{"species": c.form} for c in same_tier]
    owned = same_tier[-1].form

    baseline = query_counters(
        {"species": "Blaziken-Mega"}, n=20, candidate_pool=candidate_pool
    )
    off = query_counters(
        {"species": "Blaziken-Mega"},
        n=20,
        candidate_pool=candidate_pool,
        available_pool=[owned],
        ownership_mode="off",
    )
    once = query_counters(
        {"species": "Blaziken-Mega"},
        n=20,
        candidate_pool=candidate_pool,
        available_pool=[owned],
        ownership_mode="owned_first",
    )
    duplicates = query_counters(
        {"species": "Blaziken-Mega"},
        n=20,
        candidate_pool=candidate_pool,
        available_pool=[owned, owned, owned],
        ownership_mode="owned_first",
    )

    assert off == baseline
    assert once == duplicates
    assert to_id(once[0].form) == to_id(owned)
    assert {to_id(c.form) for c in once} == {to_id(c.form) for c in baseline}


def test_owned_last_only_breaks_a_complete_query_key_tie():
    """Regression, updated 2026-08-23: this test used to mine the live
    snapshot for a coincidental usage_rank=None tie -- valid under the
    old bug (every usage_rank=None candidate sorted as float("-inf"),
    genuinely indistinguishable), but no longer findable now that real
    Showdown popularity differentiates almost every candidate (confirmed
    directly: zero candidates in this exact query lack both usage_rank
    AND showdown_usage_pct entirely). Constructs a deliberate, controlled
    tie instead -- two real candidates that already share threat_tier and
    ko_threshold_score, with their real showdown_usage_pct forced equal
    via a patched showdown_species_map -- rather than depending on
    real data happening to coincide, which the _key fix specifically
    made much less likely.
    """
    full = query_counters({"species": "Blaziken-Mega"}, n=1000)
    groups: dict[tuple, list[ThreatCandidate]] = {}
    for candidate in full:
        if candidate.usage_rank is not None:
            continue
        key = (threat_tier(candidate.threat_kinds), candidate.ko_threshold_score)
        groups.setdefault(key, []).append(candidate)
    pair = next(group for group in groups.values() if len(group) >= 2)[:2]
    a_id, b_id = to_id(pair[0].form), to_id(pair[1].form)

    real_sd = showdown_species_map("champions-reg-mb")
    forced_pct = real_sd.get(a_id, {}).get("usage_pct", 1.0)
    patched_sd = dict(real_sd)
    patched_sd[b_id] = {**patched_sd.get(b_id, {}), "usage_pct": forced_pct}
    patched_sd[a_id] = {**patched_sd.get(a_id, {}), "usage_pct": forced_pct}

    candidate_pool = [{"species": pair[0].form}, {"species": pair[1].form}]
    owned = pair[1].form

    with patch(
        "recommender.counters.showdown_species_map", return_value=patched_sd
    ):
        out = query_counters(
            {"species": "Blaziken-Mega"},
            n=20,
            candidate_pool=candidate_pool,
            available_pool=[owned],
            ownership_mode="owned_last",
        )
    assert to_id(out[0].form) == to_id(owned)
    assert {to_id(c.form) for c in out} == {
        to_id(p["species"]) for p in candidate_pool
    }


def test_owned_only_intersects_candidate_pool_and_handles_empty():
    full = query_counters({"species": "Blaziken-Mega"}, n=20)
    assert len(full) >= 3
    narrowed = [{"species": c.form} for c in full[:3]]
    owned = full[1].form

    one = query_counters(
        {"species": "Blaziken-Mega"},
        n=20,
        candidate_pool=narrowed,
        available_pool=[owned, owned, "NotInNarrowedPool"],
        ownership_mode="owned_only",
    )
    empty = query_counters(
        {"species": "Blaziken-Mega"},
        n=20,
        candidate_pool=narrowed,
        available_pool=[],
        ownership_mode="owned_only",
    )

    assert [to_id(c.form) for c in one] == [to_id(owned)]
    assert empty == []


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


def test_defensive_synergy_score_no_locked_team_returns_zero():
    assert defensive_synergy_score(["Water", "Ground"], []) == 0.0


def test_defensive_synergy_score_matches_validated_worked_examples():
    """Regression, confirmed against Vu's own worked examples and cross-
    checked directly against the real TYPE_CHART before being written as
    production code: for an Archaludon (Steel/Dragon) + Pelipper
    (Water/Flying) locked team, Swampert (a real teammate) should score
    clearly positive -- its one weakness (Grass) is shared by neither
    locked member, and it covers Pelipper's severe 4x Electric weakness
    via immunity. Kingambit (confirmed NOT purely explained by this
    signal alone -- it's a real teammate for reasons outside type-chart
    math, see the multi-signal design) should score clearly negative on
    THIS signal specifically -- its Fighting/Ground weaknesses directly
    compound with Archaludon's own.
    """
    locked = [["Steel", "Dragon"], ["Water", "Flying"]]
    swampert = defensive_synergy_score(["Water", "Ground"], locked)
    kingambit = defensive_synergy_score(["Dark", "Steel"], locked)
    assert swampert > 0
    assert kingambit < 0
    assert swampert > kingambit


def test_defensive_synergy_score_penalizes_weakness_severity_not_flat():
    """Regression for a real bug caught and fixed during validation: the
    baseline fragility penalty (for a weakness with zero team overlap)
    must scale with the weakness's own severity, not apply a flat
    penalty regardless of magnitude -- a candidate with a severe 4x
    weakness should score worse than one with only a 2x weakness in the
    same type, all else equal, even when neither weakness overlaps with
    the locked team at all (isolating severity from the compounding
    penalty entirely).
    """
    # Normal is genuinely neutral (1.0x) to Grass -- unlike an earlier
    # version of this test that used Fire, which actually resists Grass
    # (0.5x) and, after the backup-mitigation refinement, scaled both
    # cases down to the same value, masking the severity difference this
    # test exists to isolate. Confirmed directly before trusting it.
    locked = [["Normal"]]
    four_x_grass_weak = defensive_synergy_score(["Water", "Ground"], locked)
    two_x_grass_weak = defensive_synergy_score(["Water"], locked)
    assert four_x_grass_weak < two_x_grass_weak


def test_defensive_synergy_score_mitigates_baseline_penalty_when_team_has_real_backup():
    """Regression, confirmed live: a candidate adding a weakness the
    locked team already RESISTS or is IMMUNE to should not be penalized
    the same as adding a weakness with zero team backup at all -- the
    team as a whole isn't actually exposed there even though the
    candidate itself is. Real example: Sylveon (Fairy) adds Steel and
    Poison weaknesses to an Archaludon(Steel/Dragon)+Pelipper(Water/
    Flying) team where Archaludon is immune to Poison and both
    Archaludon and Pelipper resist Steel -- confirmed against the real
    type chart before writing this test. Deliberately separate from the
    compounding penalty and coverage bonus, which already handle "team
    also weak" and "candidate covers team's weakness" -- this is the
    third direction: "team already backs up the candidate's own
    weakness."
    """
    locked = [["Steel", "Dragon"], ["Water", "Flying"]]  # Archaludon, Pelipper
    sylveon_with_mitigation = defensive_synergy_score(["Fairy"], locked)
    # Same weaknesses (Steel, Poison, both 2x), but against a locked team
    # with genuinely zero relationship to either type -- confirms the
    # mitigated score is meaningfully higher than what an unmitigated
    # baseline penalty would have produced for the identical weaknesses.
    neutral_locked = [["Normal"]]
    sylveon_no_backup = defensive_synergy_score(["Fairy"], neutral_locked)
    assert sylveon_with_mitigation > sylveon_no_backup


def test_defensive_synergy_score_full_immunity_backs_up_more_than_partial_resist():
    """Confirms immunity (0x) backup mitigates the baseline weakness
    penalty more strongly than a plain resist (0.5x) does, for the same
    added weakness.

    Not a fully isolated single-effect test -- confirmed directly that
    no such pairing exists in the real type chart without also
    triggering some other real interaction (the compounding penalty or
    coverage bonus), since types are too interconnected for a pure
    single-effect example to exist. Ghost is immune to Fighting and
    Flying resists it; Normal (weak only to Fighting) against each
    isolates the weakness type itself even if other real terms also
    contribute -- the comparison (immune backup scoring meaningfully
    higher than resist backup) is what this test actually needs to hold,
    not a claim of zero other interaction.
    """
    resist_backup = defensive_synergy_score(["Normal"], [["Flying"]])
    immune_backup = defensive_synergy_score(["Normal"], [["Ghost"]])
    assert immune_backup > resist_backup


def test_dominant_mega_form_swampert_real_data():
    """Regression, confirmed live: "Swampert" in real in-game usage data
    is 95.5% Swampertite -- the usage_rank currently attributed to the
    base form (Torrent, base stats) actually belongs to the mega form
    (Swift Swim, boosted stats) in practice. Confirms the real, exact
    scenario that motivated this fix.
    """
    from recommender.legality import load_snapshot
    from recommender.usage_data import ingame_species_map

    snap = load_snapshot()
    ig = ingame_species_map("champions-reg-mb")
    mega_forms_by_base = _mega_forms_by_base(snap)
    ig_entry = ig.get("swampert") or {}
    result = _dominant_mega_form(snap, "swampert", ig_entry, mega_forms_by_base)
    assert result == "swampertmega"


def test_dominant_mega_form_handles_multi_form_species_charizard():
    """Charizard has two real mega forms (X/Y) -- confirms the dominant
    one (Y, per real in-game item share) is correctly identified, not
    just "some" mega form or the wrong one."""
    from recommender.legality import load_snapshot
    from recommender.usage_data import ingame_species_map

    snap = load_snapshot()
    ig = ingame_species_map("champions-reg-mb")
    mega_forms_by_base = _mega_forms_by_base(snap)
    ig_entry = ig.get("charizard") or {}
    result = _dominant_mega_form(snap, "charizard", ig_entry, mega_forms_by_base)
    assert result == "charizardmegay"


def test_dominant_mega_form_returns_none_below_threshold():
    """A species with no dominant mega-stone item share (or no mega form
    at all) must not be retargeted -- confirms this is a real, threshold-
    gated decision, not applied blanket to every species with a mega
    form available."""
    from recommender.legality import load_snapshot
    from recommender.usage_data import ingame_species_map

    snap = load_snapshot()
    ig = ingame_species_map("champions-reg-mb")
    mega_forms_by_base = _mega_forms_by_base(snap)
    # A species with no mega form at all
    ig_entry = ig.get("garchomp") or {}
    result = _dominant_mega_form(snap, "garchomp", ig_entry, mega_forms_by_base)
    assert result is None


def test_dominant_mega_form_handles_shortened_stone_names():
    """Regression, confirmed live (2026-08-23): several real mega stones
    trim or alter the base species name's ending before appending "ite"
    rather than cleanly appending it -- "staraptor" -> "staraptite" (not
    "staraptorite"), "mawile" -> "mawilite", "floette" -> "floettite",
    "sceptile" -> "sceptilite", "blastoise" -> "blastoisinite". The
    original substring check ("base_name_id in item_id") required an
    exact containment match and missed every one of these, despite each
    having genuine, dominant real mega-stone usage (55-99%, checked
    directly against real in-game data) -- silently evaluating the
    weaker base form indefinitely instead, with no visible sign anything
    was wrong. Confirmed via a direct before/after comparison that this
    fix strictly adds these cases without removing any of the
    previously-correct ones (Blaziken, Charizard, Delphox, Froslass,
    Gardevoir, Metagross, Raichu, Swampert all still retarget exactly as
    before).
    """
    from recommender.legality import load_snapshot
    from recommender.usage_data import ingame_species_map

    snap = load_snapshot()
    ig = ingame_species_map("champions-reg-mb")
    mega_forms_by_base = _mega_forms_by_base(snap)
    expected = {
        "staraptor": "staraptormega",
        "mawile": "mawilemega",
        "sceptile": "sceptilemega",
    }
    for base_sid, expected_mega in expected.items():
        ig_entry = ig.get(base_sid) or {}
        result = _dominant_mega_form(snap, base_sid, ig_entry, mega_forms_by_base)
        assert result == expected_mega, base_sid


def test_dominant_mega_form_prefers_true_mega_over_non_mega_alternate():
    """Regression, confirmed live (2026-08-23): Blastoise and Floette
    each have TWO real alternate forms in this snapshot -- Blastoise has
    ['blastoisemega', 'blastoisegmax'], Floette has ['floetteeternal',
    'floettemega'] -- and the multi-form disambiguation logic only ever
    handled Charizard-style X/Y suffixes, so a matched "-ite" item (which
    is specifically a mega-evolution mechanic, never a Gmax or other
    alternate-forme trigger) fell through to None for both, despite
    Blastoise showing 95.0% real Blastoisinite usage and Floette showing
    99.0% real Floettite usage. When exactly one of the multiple
    alternates actually contains "mega", that's now treated as an
    unambiguous match regardless of naming, without needing the narrower
    X/Y-suffix path at all.
    """
    from recommender.legality import load_snapshot
    from recommender.usage_data import ingame_species_map

    snap = load_snapshot()
    ig = ingame_species_map("champions-reg-mb")
    mega_forms_by_base = _mega_forms_by_base(snap)
    for base_sid, expected_mega in [
        ("blastoise", "blastoisemega"),
        ("floette", "floettemega"),
    ]:
        ig_entry = ig.get(base_sid) or {}
        result = _dominant_mega_form(snap, base_sid, ig_entry, mega_forms_by_base)
        assert result == expected_mega, base_sid


def test_dominant_mega_form_still_respects_dominance_threshold_for_shortened_names():
    """The shortened-name matching fix must not bypass the real 80%
    dominance threshold -- confirmed directly: Dragonite's real
    Dragoninite usage is 55.4%, genuinely below the threshold, and must
    still correctly return None, not get swept in just because the name-
    matching heuristic is now more permissive.
    """
    from recommender.legality import load_snapshot
    from recommender.usage_data import ingame_species_map

    snap = load_snapshot()
    ig = ingame_species_map("champions-reg-mb")
    mega_forms_by_base = _mega_forms_by_base(snap)
    ig_entry = ig.get("dragonite") or {}
    result = _dominant_mega_form(snap, "dragonite", ig_entry, mega_forms_by_base)
    assert result is None


def test_query_counters_showdown_only_candidates_ranked_by_real_popularity():
    """Regression, confirmed live (2026-08-23): candidates with no real
    in-game usage_rank (every mega form without a dominant base-form
    item redirect) were all sorted as the single worst possible value,
    genuinely indistinguishable from each other regardless of real
    Showdown popularity -- the code's own prior comment claimed a
    fallback function used showdown_usage_pct for exactly this case, but
    that function never actually existed anywhere in this codebase.

    End-to-end against the real query_counters (not a re-implementation
    of its internal _key) -- two real candidates that already share
    threat_tier and ko_threshold_score (found the same way the tie-break
    test above finds its pair), with one candidate's real Showdown
    percentage patched higher than the other's. The higher-percentage
    one must now rank first; under the pre-fix behavior both were tied
    at float("-inf") and ownership_mode/pool order would have decided
    it, not real popularity.
    """
    full = query_counters({"species": "Blaziken-Mega"}, n=1000)
    groups: dict[tuple, list[ThreatCandidate]] = {}
    for candidate in full:
        if candidate.usage_rank is not None:
            continue
        key = (threat_tier(candidate.threat_kinds), candidate.ko_threshold_score)
        groups.setdefault(key, []).append(candidate)
    pair = next(group for group in groups.values() if len(group) >= 2)[:2]
    a_id, b_id = to_id(pair[0].form), to_id(pair[1].form)

    real_sd = showdown_species_map("champions-reg-mb")
    patched_sd = dict(real_sd)
    # Assign the LOWER percentage to whichever of the two comes first in
    # the raw snapshot's own species dict ordering, and the HIGHER
    # percentage to whichever comes second -- candidate_pool only
    # filters which species are allowed, it does not control iteration
    # order (confirmed directly: reordering candidate_pool alone did not
    # change output order, since the actual stable-tie order comes from
    # snap["species"].items()'s own fixed ordering). This guarantees a
    # real discriminating test regardless of what that raw order happens
    # to be: under the pre-fix bug (both tied at float("-inf")), a
    # stable sort would preserve raw-snapshot order, putting the LOWER-
    # percentage one first (wrong); the fix must reorder them by real
    # percentage regardless of raw snapshot order.
    from recommender.legality import load_snapshot

    snap_order = list(load_snapshot()["species"].keys())
    first_id, second_id = sorted((a_id, b_id), key=snap_order.index)
    patched_sd[first_id] = {**patched_sd.get(first_id, {}), "usage_pct": 0.01}
    patched_sd[second_id] = {**patched_sd.get(second_id, {}), "usage_pct": 50.0}

    candidate_pool = [{"species": pair[0].form}, {"species": pair[1].form}]
    with patch(
        "recommender.counters.showdown_species_map", return_value=patched_sd
    ):
        out = query_counters(
            {"species": "Blaziken-Mega"}, n=20, candidate_pool=candidate_pool
        )
    assert to_id(out[0].form) == second_id
    assert to_id(out[1].form) == first_id


def test_query_counters_reports_mega_form_directly_not_base():
    """End-to-end confirmation against real data: querying for threats to
    Archaludon now correctly surfaces "Swampert-Mega" directly (Swift
    Swim, Swampertite, real usage_rank retargeted from the base entry's
    real popularity), not "Swampert" (Torrent, base stats) -- the exact
    live scenario that motivated this whole investigation.
    """
    counters = query_counters({"species": "Archaludon"})
    swampert_related = [c for c in counters if "swampert" in c.ladder_species.lower()]
    assert len(swampert_related) == 1
    candidate = swampert_related[0]
    assert candidate.ladder_species == "Swampert-Mega"
    assert candidate.usage_rank == 20
    assert candidate.spec.get("ability") == "Swift Swim"


def test_query_counters_candidate_pool_matches_retargeted_mega_name():
    """Regression, a real bug found while verifying this fix: a
    candidate_pool/available_pool filter naturally references a
    retargeted mega form's real name (e.g. "Delphox-Mega", once
    query_counters correctly reports it as such) -- confirms this is
    matched correctly against the base species actually being iterated
    internally, not incorrectly excluded because the base id itself
    isn't literally in the allowed set.
    """
    result = query_counters(
        {"species": "Archaludon"}, candidate_pool=[{"species": "Swampert-Mega"}]
    )
    assert any(c.ladder_species == "Swampert-Mega" for c in result)
