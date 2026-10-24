"""Part G scorer skeleton: CP bound table, R6 counting, set and guaranteed-KO rules. Synthetic answers only."""

from __future__ import annotations

import importlib.util
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
    assert (r["scored_claims_gate_unit"], r["items_with_scored_claim"], r["items"]) == (2, 1, 4)
    assert r["answer_names_different_source"] == 2 and r["unverifiable_share_overall"] == pytest.approx(2 / 4)
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
