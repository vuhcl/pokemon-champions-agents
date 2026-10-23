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


def test_ko_chance_line_is_non_gating_by_default_and_switchable():
    cs = [C(T)] * 149 + [C(F, "ko_chance")]
    s = sc.gate_summary(cs, slots=384)
    assert s["passes_gate"] and s["scored"] == 149 and s["ko_chance_line"]["false"] == 1 and not s["ko_chance_line"]["gating"]
    assert not sc.gate_summary(cs, slots=384, gate_ko_chance=True)["passes_gate"]  # 150 scored, 1 false


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


GT = {"attacker": "Hydrapple", "defender": "Castform-Snowy", "move": "Draco Meteor", "guaranteed_ko": False,
      "rolls_ko_of_16": 4, "scoring": {"chance_tolerance_points": 3.125, "form_ability_used_by_key": {"attacker": None, "defender": None}}}
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
