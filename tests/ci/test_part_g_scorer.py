"""Part G scorer skeleton: CP bound table, R6 counting, set and guaranteed-KO rules. Synthetic answers only."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/eval/part_g_v4/scorer.py"
spec = importlib.util.spec_from_file_location("part_g_scorer", SCRIPT)
sc = importlib.util.module_from_spec(spec)
sys.modules["part_g_scorer"] = sc
spec.loader.exec_module(sc)
T, F, U = sc.Verdict.TRUE, sc.Verdict.FALSE, sc.Verdict.UNVERIFIABLE


@pytest.mark.parametrize("false,n", [(0, 149), (1, 236), (2, 313), (3, 386)])
def test_cp_table(false, n):
    assert sc.min_scored_for(false) == n
    assert sc.cp_upper(false, n) <= 0.02 < sc.cp_upper(false, n - 1)


def test_cp_edges():
    assert sc.cp_upper(0, 0) == 1.0 and sc.cp_upper(5, 5) == 1.0
    assert sc.cp_upper(0, 149) == pytest.approx(1 - 0.05 ** (1 / 149), abs=1e-9)  # closed form for 0 false


def C(v, line="gate", n=0):
    return sc.Claim("k", f"s{n}", "p", v, line)


def test_gate_excludes_unverifiable_and_no_verdict():
    cs = [C(T, n=i) for i in range(149)] + [C(U, n=i) for i in range(40)] + [C(None, n=i) for i in range(5)]
    s = sc.gate_summary(cs, slots=384)
    assert (s["scored"], s["false"], s["no_verdict"], s["unverifiable"]["count"]) == (149, 0, 5, 40)
    assert s["passes_gate"] and s["answer_rate"] == pytest.approx(149 / 384)
    assert s["unverifiable"]["share_of_typed"] == pytest.approx(40 / 189)
    assert not sc.gate_summary([C(T)] * 148, slots=384)["passes_gate"]
    assert not sc.gate_summary([C(T)] * 234 + [C(F)], slots=384)["passes_gate"]  # 235 scored, 1 false
    assert sc.gate_summary([C(T)] * 235 + [C(F)], slots=384)["passes_gate"]  # 236 scored, 1 false


def test_ko_number_line_gates_by_default_and_can_be_switched_off():
    cs = [C(T)] * 149 + [C(F, "ko_chance")]
    s = sc.gate_summary(cs, slots=384)
    assert s["ko_chance_line"]["gating"] and s["scored"] == 150 and s["false"] == 1 and not s["passes_gate"]  # gated by default
    off = sc.gate_summary(cs, slots=384, gate_ko_chance=False)
    assert off["passes_gate"] and off["scored"] == 149 and off["ko_chance_line"]["false"] == 1 and not off["ko_chance_line"]["gating"]


def test_per_type_false_rate_sits_beside_the_headline():
    cs = [sc.Claim("k", "a", "p", T, ctype="typing")] * 3 + [sc.Claim("k", "b", "p", F, ctype="damage"), sc.Claim("k", "c", "p", T, ctype="damage")]
    r = sc.gate_summary(cs, slots=5)["false_rate_by_type"]
    assert r == {"damage": {"false": 1, "scored": 2, "false_rate": 0.5}, "typing": {"false": 0, "scored": 3, "false_rate": 0.0}}


def test_dedupe_one_claim_per_kind_subject_proposition():
    a = sc.Claim("has_type", "Aromatisse", "Fairy", T)
    cs = sc.dedupe([a, sc.Claim("has_type", "aromatisse", "fairy", T), sc.Claim("has_type", "Aromatisse", "Steel", F)])
    assert len(cs) == 2  # a restated claim collapses; a different proposition is its own claim


def test_set_rule_from_ground_truth_shape():
    key = ["Choice Scarf", "Focus Sash", "Life Orb", "Haban Berry", "Chople Berry", "Sitrus Berry"]  # top 5 + a tie
    kw = dict(key_source="in-game")
    v = lambda cs: [c.verdict for c in cs]  # noqa: E731
    assert v(sc.score_set("common_items", "Hydreigon", ["choice scarf", "Life Orb"], key, **kw)) == [T, T]  # source inherited
    assert v(sc.score_set("common_items", "Hydreigon", ["Leftovers", "Life Orb"], key, **kw)) == [F, T]  # non-key FALSE
    assert v(sc.score_set("common_items", "Hydreigon", ["Life Orb"], key, stated_source="in-game", **kw)) == [T]
    assert v(sc.score_set("common_items", "Hydreigon", ["Life Orb"], key, stated_source="showdown", **kw)) == [U]
    assert sc.score_set("common_items", "Hydreigon", [], key, **kw) == []  # unstated key members: no claims
    assert len(sc.score_set("common_items", "Hydreigon", ["Life Orb", "life orb"], key, **kw)) == 1


def test_rank_assertions_and_key_ranks():
    items = [("A", 50.0), ("B", 20.0), ("C", 10.0), ("D", 10.0), ("E", 5.0)]
    kr = sc.ranks(items)
    assert kr == {"a": 1, "b": 2, "c": 3, "d": 3, "e": 5}  # ties share a rank
    assert sc.ranks([("X", None), ("Y", None)]) == {"x": 1, "y": 2}  # in-game teammates: list position
    cs = sc.score_set("common_items", "S", ["A", "D"], [n for n, _ in items], key_source="in-game",
                      asserted_ranks={"A": 1, "D": 4}, key_ranks=kr)
    assert [(c.kind, c.verdict) for c in cs] == [("common_items", T), ("common_items", T), ("common_items_rank", T), ("common_items_rank", F)]


ROLLS = [154, 156, 159, 160, 162, 163, 166, 168, 169, 171, 172, 175, 177, 178, 180, 183]  # built by hand, not arm output
GT = {"attacker": "Hydrapple", "defender": "Castform-Snowy", "move": "Draco Meteor", "guaranteed_ko": False,
      "rolls_ko_of_16": 4, "rolls": ROLLS, "hp": 177, "min_roll": 154, "max_roll": 183, "scoring": {"chance_tolerance_points": 3.125, "form_ability_used_by_key": {"attacker": None, "defender": None}}}
GT_MEGA = {**GT, "attacker": "Charizard-Mega-X", "scoring": {**GT["scoring"], "form_ability_used_by_key": {"attacker": "Tough Claws", "defender": None}}}


def by(cs):
    return {c.kind: c.verdict for c in cs}


def test_guaranteed_ko_rules():
    assert by(sc.score_guaranteed_ko(sc.KoAnswer(False, 25.0, True), GT)) == {"guaranteed_ko": T, "ko_chance": T}
    assert by(sc.score_guaranteed_ko(sc.KoAnswer(True, 28.125, True), GT)) == {"guaranteed_ko": F, "ko_chance": T}  # edge inclusive
    assert by(sc.score_guaranteed_ko(sc.KoAnswer(False, 28.2, True), GT))["ko_chance"] == F
    assert by(sc.score_guaranteed_ko(sc.KoAnswer(None, None, True), GT)) == {"guaranteed_ko": None, "ko_chance": None}  # hedge
    assert by(sc.score_guaranteed_ko(sc.KoAnswer(True, 50.0, False), GT)) == {"guaranteed_ko": U, "ko_chance": U}
    assert by(sc.score_guaranteed_ko(sc.KoAnswer(True, None, True), GT))["ko_chance"] is None


def test_mega_form_wrong_ability_is_false_ability_and_unverifiable_damage():
    cs = sc.score_guaranteed_ko(sc.KoAnswer(True, None, True, {"attacker": "Blaze"}), GT_MEGA)
    assert by(cs) == {"has_ability": F, "guaranteed_ko": U, "ko_chance": None}
    cs = sc.score_guaranteed_ko(sc.KoAnswer(True, None, True, {"attacker": "Tough Claws"}), GT_MEGA)
    assert "has_ability" not in by(cs) and by(cs)["guaranteed_ko"] == F


def test_score_equal_and_audit_sampler():
    assert sc.score_equal("has_type", "A", "Fairy", "fairy").verdict == T
    assert sc.score_equal("has_type", "A", False, True).verdict == F and sc.score_equal("has_type", "A", None, 1).verdict is None
    ids = [f"i{n}" for n in range(50)]
    assert sc.audit_sample(ids, 10, 7) == sc.audit_sample(list(reversed(ids)), 10, 7)
    assert sc.audit_sample(ids, 10, 7) != sc.audit_sample(ids, 10, 8) and len(sc.audit_sample(ids, 99, 0)) == 50


def test_extractors_are_stubs():
    with pytest.raises(NotImplementedError):
        sc.EXTRACTORS[("typing", "has_type")]({}, {})


def test_pilot_report_counts_and_different_source():
    by_item = {
        "a": sc.score_set("common_items", "S", ["Life Orb", "Leftovers"], ["Life Orb"], key_source="in-game"),  # T, F
        "b": sc.score_set("teammates", "S", ["X", "Y"], ["X"], key_source="in-game", stated_source="showdown"),  # U, U
        "c": [sc.Claim("has_type", "A", "Fairy", None)],  # hedge
        "d": [sc.Claim("ko_chance", "A", "25", T, line="ko_chance")],  # own line, not in the gate unit
    }
    r = sc.pilot_report(by_item, n_items=4, slots=10)
    assert (r["scored_claims_gate_unit"], r["items_with_scored_claim"], r["items"]) == (3, 2, 4)  # the KO line is in the gate unit by default
    off = sc.pilot_report(by_item, n_items=4, slots=10, gate_ko_chance=False)
    assert (off["scored_claims_gate_unit"], off["items_with_scored_claim"]) == (2, 1)
    assert r["answer_names_different_source"] == 2 and r["unverifiable_share_overall"] == pytest.approx(2 / 5)
    assert r["unverifiable_by_kind"]["teammates"] == {"unverifiable": 2, "typed": 2, "share": 1.0}
    assert r["unverifiable_by_kind"]["common_items"]["share"] == 0.0


def test_ko_count_is_exact_and_gated_with_the_chance_line():
    ok = by(sc.score_guaranteed_ko(sc.KoAnswer(False, None, True, ko_count=4), GT))
    assert ok == {"guaranteed_ko": T, "ko_chance": None, "ko_count": T}
    assert by(sc.score_guaranteed_ko(sc.KoAnswer(False, None, True, ko_count=5), GT))["ko_count"] == F  # not within one
    assert by(sc.score_guaranteed_ko(sc.KoAnswer(False, None, True, ko_count=3), GT))["ko_count"] == F
    cs = sc.score_guaranteed_ko(sc.KoAnswer(False, 25.0, True, ko_count=4), GT)
    assert {c.line for c in cs if c.kind in ("ko_count", "ko_chance")} == {"ko_chance"}
    assert by(sc.score_guaranteed_ko(sc.KoAnswer(False, 25.0, False, ko_count=4), GT))["ko_count"] == U  # conditions differ


def test_ko_threshold_uses_the_roll_list_and_hp():
    hp186 = {**GT, "hp": 186, "rolls": [84, 85, 87, 87, 88, 90, 90, 91, 93, 93, 94, 96, 96, 97, 99, 100], "rolls_ko_of_16": 0}
    assert sc.score_ko_threshold(hp186, 93).verdict == F  # "93 or higher KO" while HP is 186
    assert sc.score_ko_threshold(hp186, 186).verdict == T
    assert sc.score_ko_threshold(hp186, 101).verdict == T  # same (empty) set of rolls as at HP 186: nothing reaches either bound
    hp197 = {**GT, "hp": 197, "rolls": [182, 186, 194, 198, 200, 216]}
    assert sc.score_ko_threshold(hp197, 198).verdict == T  # no roll equals 197, so "198 or more" names the same rolls
    assert sc.score_ko_threshold(hp197, 194).verdict == F
    nokey = sc.score_ko_threshold({"attacker": "A", "move": "M", "defender": "D"}, 93)
    assert nokey.verdict == U and nokey.line == "threshold_arith_unverifiable"


def test_hp_arithmetic_claims():
    assert sc.score_hp_arithmetic(GT, ("max_roll", 183), "<", ("hp", 177)).verdict == F  # "183 less than 177"
    assert sc.score_hp_arithmetic(GT, ("max_roll", 183), ">", ("hp", 177)).verdict == T
    wrong = sc.score_hp_arithmetic(GT, ("max_roll", 150), "<", ("hp", 177))  # true comparison, wrong labelled value
    assert wrong.verdict == F and "max_roll 150 vs key 183" in wrong.reason
    other = sc.score_hp_arithmetic(GT, ("hp", 177), ">", ("sp_cap", 32))
    assert other.verdict == U and other.line == "threshold_arith_unverifiable"
    assert sc.score_hp_arithmetic({"attacker": "A", "move": "M", "defender": "D"}, ("hp", 1), ">", ("min_roll", 0)).verdict == U
    s = sc.gate_summary([sc.score_hp_arithmetic(GT, ("hp", 177), ">", ("sp_cap", 32)), sc.score_ko_threshold(GT, 177)], slots=2)
    assert s["threshold_arith_unverifiable_line"]["count"] == 1 and s["scored"] == 1


TRANSCRIPT = [  # synthetic tool results shaped like the arm's usage tools (built by hand, not arm output)
    {"name": "get_usage_teammates", "result": {"status": "served", "rows": [
        {"name": "Farigiraf", "conditional_pct": 30.171, "rank": 1}, {"name": "Rillaboom", "conditional_pct": 19.11, "rank": 2},
        {"name": "Indeedee-F", "conditional_pct": 17.906, "rank": 3}, {"name": "Whimsicott", "conditional_pct": 17.749, "rank": 4},
        {"name": "Sneasler", "conditional_pct": None, "rank": 5}]}},
    {"name": "get_usage_items", "result": {"status": "ok", "items": [{"name": "Choice Scarf", "pct": 48.9}, {"name": "Life Orb", "pct": 15.4}]}},
    {"name": "calc_damage", "result": {"status": "ok", "damage_range": [1, 2]}},
]


def test_usage_pct_scored_against_the_items_own_tool_results():
    stated = {"Farigiraf": 30.17, "Indeedee-F": 17.75, "Whimsicott": 17.91, "Choice Scarf": 48.9, "Empoleon": 13.2, "Sneasler": 5.0}
    cs = {c.proposition.split("=")[0]: c for c in sc.score_usage_pct("teammates", "Golurk", stated, TRANSCRIPT)}
    assert cs["Farigiraf"].verdict == T and cs["Choice Scarf"].verdict == T  # rows from both result shapes
    assert cs["Indeedee-F"].verdict == F and cs["Indeedee-F"].reason == "stated 17.75 vs tool 17.906"  # swapped pair
    assert cs["Whimsicott"].verdict == F and cs["Whimsicott"].reason == "stated 17.91 vs tool 17.749"
    assert cs["Empoleon"].verdict == F and cs["Empoleon"].reason == "no row for this name in the tool results"
    assert cs["Sneasler"].verdict == F  # a row without a percentage (in-game teammates) gives nothing to match
    assert all(c.line == "usage_pct" and c.ctype == "usage" for c in cs.values())


def test_usage_pct_tolerance_edge_and_duplicate_rows():
    edge = lambda v: sc.score_usage_pct("t", "S", {"Farigiraf": v}, TRANSCRIPT)[0].verdict  # noqa: E731
    assert edge(30.171 + 0.05) == T and edge(30.171 - 0.05) == T and edge(30.171 + 0.06) == F
    twice = TRANSCRIPT + [{"name": "get_usage_teammates", "result": {"rows": [{"name": "Farigiraf", "conditional_pct": 12.0}]}}]
    assert sc.score_usage_pct("t", "S", {"Farigiraf": 12.0}, twice)[0].verdict == T  # any row for the name within tolerance
    assert sc.score_usage_pct("t", "S", {"Farigiraf": 1.0}, twice)[0].reason == "stated 1 vs tool 30.171, 12"
    assert sc.score_usage_pct("t", "S", {"Farigiraf": 1.0}, [{"name": "x", "result": None}])[0].verdict == F  # no usable result


def test_usage_pct_line_is_off_by_default_lists_every_mismatch_and_switches_on():
    cs = sc.score_usage_pct("teammates", "Golurk", {"Farigiraf": 30.17, "Indeedee-F": 17.75, "Whimsicott": 17.91}, TRANSCRIPT)
    off = sc.gate_summary(cs, slots=3)
    assert off["scored"] == 0 and off["usage_pct_line"]["false"] == 2 and not off["usage_pct_line"]["gating"]
    assert [m[2:] for m in off["usage_pct_line"]["mismatches"]] == [("Indeedee-F=17.75", "stated 17.75 vs tool 17.906"),
                                                                    ("Whimsicott=17.91", "stated 17.91 vs tool 17.749")]
    on = sc.gate_summary(cs, slots=3, gate_usage_pct=True)
    assert on["scored"] == 3 and on["false"] == 2 and on["usage_pct_line"]["gating"]


def test_scorer_source_does_not_import_the_recommender_or_compute_percentages():
    src = SCRIPT.read_text()
    assert "from recommender" not in src and "import recommender" not in src and "chaos_weight" not in src


# Ground-truth-shaped keys built by hand (never arm output).
DMG = {"attacker": "Thievul", "defender": "Typhlosion-Hisui", "move": "Psychic", "hp": 196, "min_roll": 54, "max_roll": 64,
       "rolls": [54, 55, 56, 58, 59, 60, 60, 61, 62, 62, 63, 63, 64, 64, 64, 64], "rolls_ko_of_16": 0, "guaranteed_ko": False,
       "scoring": {"chance_tolerance_points": 3.125}}
SPD = {"s1": "Ninetales-Alola", "s2": "Sylveon", "spe1_jolly32": 177, "spe2_timid32": 123}


def test_labelled_value_unit_slips_are_false():
    assert sc.score_labelled(DMG, "hp", 196).verdict == T
    slip = sc.score_labelled(DMG, "hp", 32)  # "the defender has 32 HP"
    assert slip.verdict == F and slip.reason == "labelled hp 32 vs key 196"
    assert sc.score_labelled(DMG, "hp", 608).verdict == F  # "32 SP out of 608 total HP"
    assert sc.score_labelled(DMG, "max_roll", 64).verdict == T and sc.score_labelled(DMG, "max_roll", 63).verdict == F
    other = sc.score_labelled(DMG, "sp_cap", 32)
    assert other.verdict == U and other.line == "threshold_arith_unverifiable"


def test_ko_needed_must_equal_hp_and_roll_threshold_uses_the_roll_list():
    assert sc.score_ko_needed(DMG, 196).verdict == T
    assert sc.score_ko_needed(DMG, 197).verdict == F  # "197 needed" for HP 196
    assert sc.score_ko_needed(DMG, 98).verdict == F  # "half of HP"
    assert sc.score_ko_threshold(DMG, 197).verdict == T  # "rolls at or above 197 KO": no roll reaches 196 either
    assert sc.score_ko_threshold({**DMG, "rolls": [190, 196, 200], "hp": 196}, 197).verdict == F  # 196 itself KOs
    assert sc.score_ko_needed({"attacker": "A", "move": "M", "defender": "D"}, 5).verdict == U


def test_speed_stat_and_margin_are_exact_against_the_key():
    assert sc.score_speed_stat(SPD, "Ninetales-Alola", 177).verdict == T and sc.score_speed_stat(SPD, "sylveon", 123).verdict == T
    bad = sc.score_speed_stat(SPD, "Sylveon", 124)
    assert bad.verdict == F and bad.reason == "stated 124 vs key 123"
    assert sc.score_speed_stat(SPD, "Garchomp", 169).verdict == U
    assert sc.score_speed_margin(SPD, "Ninetales-Alola", "Sylveon", 54).verdict == T  # 177 - 123
    assert sc.score_speed_margin(SPD, "Sylveon", "Ninetales-Alola", 54).verdict == T  # an absolute margin
    assert sc.score_speed_margin(SPD, "Ninetales-Alola", "Sylveon", 53).verdict == F
    assert sc.score_speed_margin(SPD, "Ninetales-Alola", "Garchomp", 8).verdict == U


def test_damage_range_and_percent_of_hp():
    assert sc.score_damage_range(DMG, 54, 64).verdict == T and sc.score_damage_range(DMG, 54, 65).verdict == F
    # 54/196 = 27.55 and 64/196 = 32.65: the calc truncates, so 27.5 and 32.6 are within rounding
    assert sc.score_percent_of_hp(DMG, 27.5, 32.6).verdict == T
    assert sc.score_percent_of_hp(DMG, 27.6, 32.7).verdict == T
    assert sc.score_percent_of_hp(DMG, 27.8, 32.6).verdict == F
    gt = {**DMG, "hp": 177, "min_roll": 154, "max_roll": 183}  # the calc text "87 - 103.3%"
    assert sc.score_percent_of_hp(gt, 87, 103.3).verdict == T


def test_nhko_guaranteed_and_possible_from_min_and_max_roll():
    gt = {**DMG, "hp": 162, "min_roll": 106, "max_roll": 126}  # calc: "guaranteed 2HKO"
    assert sc.score_nhko(gt, "guaranteed", 2).verdict == T and sc.score_nhko(gt, "guaranteed", 3).verdict == F
    assert sc.score_nhko(gt, "possible", 2).verdict == T  # ceil(162 / 126)
    gt2 = {**DMG, "hp": 217, "min_roll": 22, "max_roll": 26}  # calc: "possible 9HKO"
    assert sc.score_nhko(gt2, "possible", 9).verdict == T and sc.score_nhko(gt2, "possible", 8).verdict == F
    assert sc.score_nhko(gt2, "guaranteed", 10).verdict == T  # ceil(217 / 22)
    assert sc.score_nhko(gt2, "sometimes", 9).verdict == U


def test_chance_based_nhko_is_unverifiable_on_its_own_line():
    c = sc.score_chance_nhko(DMG, 99.8, 3)
    assert c.verdict == U and c.line == "chance_nhko_unverifiable"
    s = sc.gate_summary([c, sc.score_labelled(DMG, "hp", 196)], slots=2)
    assert s["chance_nhko_unverifiable_line"]["count"] == 1 and s["scored"] == 1


def test_ko_ratio_tied_to_an_hko_chance_is_scored_against_rolls_ko_of_16():
    # "about 6 out of 10 rolls would KO" read off "59.4% chance to 4HKO"; the key has 0 of 16 KO rolls
    assert sc.score_ko_ratio(DMG, 6, 10).verdict == F
    assert sc.score_ko_ratio(DMG, 0, 10).verdict == T
    assert sc.score_ko_ratio({**DMG, "rolls_ko_of_16": 4}, 25, 100).verdict == T  # 25% of rolls = 4 of 16
    assert sc.score_ko_ratio({**DMG, "rolls_ko_of_16": 4}, 4, 16).verdict == T and sc.score_ko_ratio({**DMG, "rolls_ko_of_16": 4}, 5, 16).verdict == F
    assert sc.score_ko_ratio(DMG, 6, 10).line == "ko_chance"  # gated with the KO numbers by default


def test_sensitivity_line_excludes_copied_unchanged_claims_and_never_decides():
    cs = [sc.Claim("k", f"s{i}", "p", T, copied_unchanged=True, ctype="usage") for i in range(149)]
    cs += [sc.Claim("k", "x", "p", F, ctype="usage")]
    s = sc.gate_summary(cs, slots=150)
    sens = s["sensitivity_excluding_copied_unchanged"]
    assert (sens["scored"], sens["false"], sens["claims_excluded"], sens["decides_pass_fail"]) == (1, 1, 149, False)
    assert sens["cp_upper_bound"] == 1.0 and s["scored"] == 150 and s["false"] == 1
    assert s["passes_gate"] is False  # the headline decides: 150 scored with 1 false


def _mk(kind, prop, v, ctype="usage", line="gate"):
    return sc.Claim(kind, "S", prop, v, line=line, ctype=ctype)


def test_list_as_one_aggregation_on_synthetic_verdicts():
    by_item = {
        "u1": [_mk("teammates", f"m{i}", T) for i in range(5)] + [_mk("common_items", "a", T), _mk("common_items", "b", F)],
        "u2": [_mk("teammates", "x", None), _mk("common_items", "y", U)],  # no member stated -> no verdict (and no claim counted)
        "t1": [_mk("has_type", "True", T, "typing"), _mk("type_list_member", "Fire", T, "typing"), _mk("type_list_member", "Ice", T, "typing")],
        "d1": [_mk("guaranteed_ko", "no", F, "damage"), _mk("ko_count", "4 of 16", T, "damage", line="ko_chance"), _mk("usage_pct_x", "p", F, "usage", line="usage_pct")],
    }
    one = sc.list_as_one(by_item)
    by = {(c.ctype, c.kind, c.subject): c.verdict for c in one}
    assert by[("usage", "set:teammates", "u1")] == T and by[("usage", "set:common_items", "u1")] == F  # any FALSE member makes the list FALSE
    assert by[("usage", "set:teammates", "u2")] is None and by[("usage", "set:common_items", "u2")] is None
    assert by[("typing", "set:type_list_member", "t1")] == T and ("typing", "has_type", "S") in by  # a non-set claim stays individual
    assert by[("damage", "ko_count", "S")] == T and not any(c.line == "usage_pct" for c in one)  # the KO line stays in; the usage_pct line stays out
    d = sc.dev_headline(by_item, slots=10)
    assert d["list_members_as_claims"]["claims"] == 5 + 2 + 3 + 2 and d["list_members_as_claims"]["false"] == 1 + 1
    assert d["list_as_one"]["claims"] == 6 and d["list_as_one"]["false"] == 2  # u1 teammates and items, t1 set, t1 has_type, d1 verdict and KO count
    assert d["list_as_one"]["false_rate_by_type"]["usage"] == {"claims": 2, "false": 1, "false_rate": 0.5}
    assert d["list_as_one"]["min_claims_for_this_many_false"] == 313 and d["list_members_as_claims"]["min_claims_for_this_many_false"] == 313  # the same CP table


def test_list_as_one_leaves_every_verdict_rule_alone():
    members = [_mk("teammates", f"m{i}", T) for i in range(4)] + [_mk("teammates", "bad", F)]
    flat = [c.verdict for c in members]
    sc.list_as_one({"i": members})
    assert [c.verdict for c in members] == flat  # inputs are not modified
    assert sc.list_as_one({"i": []}) == []


def test_dev_headline_refusals(tmp_path):
    import hashlib

    def record(**over):
        rec = {"schema": "run_parameter_record_v1", "allow_live": False, "arm_config": {"allow_live": False}, **over}
        rec["record_sha256"] = hashlib.sha256(json.dumps({k: v for k, v in rec.items() if k != "record_sha256"}, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
        return rec

    bat = tmp_path / "dev.json"
    bat.write_text(json.dumps({"seed": 1, "items": []}))
    rp = tmp_path / "run_params.json"
    rp.write_text(json.dumps(record()))
    assert sc.dev_headline_allowed(bat, "P", rp) == (True, "ok")
    assert "held out" in sc.dev_headline_allowed(_write(tmp_path / "s0.json", {"seed": 0, "items": []}), "P", rp)[1]
    assert "half P only" in sc.dev_headline_allowed(bat, "T", rp)[1] and "half P only" in sc.dev_headline_allowed(bat, None, rp)[1]
    assert "no run_params" in sc.dev_headline_allowed(bat, "P", None)[1] and "no run_params" in sc.dev_headline_allowed(bat, "P", tmp_path / "missing.json")[1]
    tampered = json.loads(rp.read_text())
    tampered["allow_live"] = True
    rp.write_text(json.dumps(tampered))
    assert "edited" in sc.dev_headline_allowed(bat, "P", rp)[1]
    rp.write_text(json.dumps(record(allow_live=True)))
    assert "offline arm run" in sc.dev_headline_allowed(bat, "P", rp)[1]
    assert "held out" in sc.dev_headline_allowed(Path(sc.__file__).resolve().parent / "battery" / "claim_battery_v4.json", "P", rp)[1]


def _write(path, doc):
    path.write_text(json.dumps(doc))
    return path
