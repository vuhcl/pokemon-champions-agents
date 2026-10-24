"""Part G extractors on hand-written answers (never arm output): polarity, extras, numbers, spans, and the copied_unchanged flag."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts/eval/part_g_v4"))
import extractors as ex  # noqa: E402
import scorer as sc  # noqa: E402

T, F, U = sc.Verdict.TRUE, sc.Verdict.FALSE, sc.Verdict.UNVERIFIABLE


def item(ctype, kind, gt, template=""):
    return {"id": "x", "claim_type": ctype, "template": template, "claims": [{"kind": kind, "ground_truth": gt}]}


def run(it, text, calls=None):
    return ex.extract_item(it, {"final_text": text, "tool_calls": calls or []})


def by(cs):
    return {(c.kind, c.proposition): c.verdict for c in cs}


def test_typing_negation_extras_and_exact():
    it = item("typing", "has_type", {"species": "Slowbro-Galar", "asked_type": "Fire", "has_type": False, "types": ["Poison", "Psychic"]})
    cs = run(it, "No, Slowbro-Galar does not have Fire typing. It has Poison and Psychic typing.")
    assert by(cs) == {("has_type", "False"): T, ("type_list_member", "Poison"): T, ("type_list_member", "Psychic"): T}
    wrong = run(it, "No, Slowbro-Galar is not a Fire type. It is a Water/Psychic type Pokémon.")
    assert by(wrong)[("type_list_member", "Water")] == F and by(wrong)[("type_list_member", "Psychic")] == T
    pure = run(item("typing", "has_type", {"species": "Musharna", "asked_type": "Fire", "has_type": False, "types": ["Psychic"]}),
               "No, Musharna does not have Fire typing. It is a pure Psychic type.")
    assert by(pure)[("type_list_member_exact", "Psychic")] == T
    assert by(run(it, "Yes, Slowbro-Galar has Fire typing."))[("has_type", "True")] == F  # a wrong asked proposition


def test_ability_lists_and_the_asked_ability_polarity():
    it = item("ability", "has_ability", {"species": "Dragapult", "asked_ability": "Clear Body", "has_ability": True,
                                         "abilities": ["Clear Body", "Infiltrator", "Cursed Body"]})
    cs = run(it, "Yes, Dragapult has Clear Body. According to the data, Dragapult's abilities are Infiltrator, Cursed Body and Telepathy.")
    assert by(cs)[("has_ability", "True")] == T and by(cs)[("ability_list_member", "Telepathy")] == F
    assert by(cs)[("ability_list_member", "Infiltrator")] == T and ("ability_list_member", "Clear Body") not in by(cs)
    form = item("ability_form", "has_ability", {"form": "Gardevoir-Mega", "form_id": "gardevoirmega", "asked_ability": "Pixilate",
                                                "form_abilities": ["Pixilate"], "has_ability": True})
    wrong = by(run(form, "No, Gardevoir-Mega does not have Pixilate. Its only ability is Telepathy."))
    assert wrong[("has_ability", "False")] == F and wrong[("ability_list_member", "Telepathy")] == F and wrong[("ability_list_member_exact", "Telepathy")] == F


def test_item_and_legality_polarity():
    assert by(run(item("item", "item_legal", {"item": "Heat Rock", "legal": True}), "Yes, Heat Rock is legal as a held item."))[("item_legal", "True")] == T
    leg = item("legality", "species_legal", {"species": "Kyogre", "legal": False})
    assert by(run(leg, "Kyogre is legal in Champions VGC."))[("species_legal", "True")] == F
    assert by(run(leg, "No, you cannot use Kyogre in Champions VGC."))[("species_legal", "False")] == T
    assert by(run(leg, "Kyogre is not legal."))[("species_legal", "False")] == T


SPD = {"s1": "Ninetales-Alola", "s2": "Sylveon", "spe1_jolly32": 177, "spe2_timid32": 123, "s1_outspeeds": True}


def test_speed_verdict_stats_margin_and_the_sp_echo():
    it = item("speed", "outspeed", SPD)
    txt = ("Yes, Ninetales-Alola (Jolly, 32 Spe SP) outspeeds Sylveon (Timid, 32 Spe SP).\n- Ninetales-Alola has a final Speed stat of 177.\n"
           "- Sylveon has a final Speed stat of 123.\nNinetales-Alola is faster by 54 points.")
    b = by(run(it, txt))
    assert b[("outspeed", "True")] == T and b[("speed_stat", "Ninetales-Alola speed=177")] == T and b[("speed_stat", "Sylveon speed=123")] == T
    assert b[("speed_margin", "|Ninetales-Alola - Sylveon| speed margin=54")] == T
    assert not any("speed=32" in k[1] for k in b)  # the "32 Spe SP" echo is not a Speed stat
    bad = by(run(item("speed", "faster", SPD), "Sylveon (Timid, 32 Spe SP) is faster with a final Speed stat of 130, compared to Ninetales-Alola, which has 177 Speed."))
    assert bad[("faster", "False")] == F and bad[("speed_stat", "Sylveon speed=130")] == F


def test_move_static_values_and_non_answers():
    gt = {"move": "Life Dew", "basePower": 0, "category": "Status", "type": "Water"}
    b = by(run(item("move_static", "base_power", gt), "Life Dew is a status move with no base power. It is a Water-type move."))
    assert b == {("category", "Status"): T, ("move_type", "Water"): T, ("base_power", "0"): T}
    wrong = by(run(item("move_static", "move_type", {"move": "Boomburst", "type": "Normal", "category": "Special", "basePower": 140}), "Boomburst is a Fairy-type move."))
    assert wrong[("move_type", "Fairy")] == F
    nonanswer = run(item("move_static", "category", gt), "Life Dew is a held item, not a move.")
    assert [(c.kind, c.verdict) for c in nonanswer] == [("category", None)]  # hedge: no verdict


DMG = {"attacker": "Hydrapple", "defender": "Castform-Snowy", "move": "Draco Meteor", "hp": 177, "min_roll": 154, "max_roll": 183, "guaranteed_ko": False,
       "rolls": [154, 156, 159, 160, 162, 163, 166, 168, 169, 171, 172, 175, 177, 178, 180, 183], "rolls_ko_of_16": 4, "scoring": {"chance_tolerance_points": 3.125}}


def test_damage_counts_percent_thresholds_and_labelled_values():
    it = item("damage", "guaranteed_ko", DMG)
    ok = by(run(it, "No, this does not guarantee a KO. It deals 154-183 damage (87 - 103.3%). Only 4 of the 16 rolls KO, a 25% chance to OHKO."))
    assert ok[("guaranteed_ko", "no")] == T and ok[("damage_range", "damage range 154-183")] == T and ok[("percent_of_hp", "percent of HP 87-103.3")] == T
    assert ok[("ko_count", "4 of 16 rolls KO")] == T and ok[("ko_chance", "25%")] == T
    bad = by(run(it, "No. Since the maximum damage (183) is less than the defender's full HP (177), some rolls fail. The defender has 32 HP. "
                     "It needs at least 197 damage; only one roll would knock out the defender; about 6 out of 10 rolls would KO."))
    assert bad[("labelled_value", "hp=32")] == F and bad[("ko_needed", "damage needed to KO = 197")] == F
    assert bad[("ko_count", "1 of 16 rolls KO")] == F and bad[("ko_count", "6 of 10 rolls KO")] == F
    assert any(k[0] == "hp_arithmetic" and v == F for k, v in bad.items())
    every = by(run(it, "Yes, every one of the 16 rolls knocks the defender out."))
    assert every == {("guaranteed_ko", "yes"): F}  # "16 of 16" collapses onto the guaranteed_ko claim, which is wrong against this key


def test_damage_nhko_statements():
    it = item("damage", "guaranteed_ko", {**DMG, "hp": 162, "min_roll": 106, "max_roll": 126, "rolls_ko_of_16": 0})
    cs = run(it, "No, this does not guarantee a KO. The result shows a guaranteed 2HKO, and a 99.8% chance to 3HKO.")
    b = by(cs)
    assert b[("nhko", "guaranteed 2HKO")] == T and b[("chance_nhko", "99.8% chance to 3HKO")] == U
    assert [c.line for c in cs if c.kind == "chance_nhko"] == ["chance_nhko_unverifiable"]


def test_usage_lists_percentages_ranks_and_other_source():
    gt = {"species": "Golurk", "teammates": ["Farigiraf", "Rillaboom", "Indeedee-F"], "source": "showdown"}
    it = item("usage_showdown", "teammates", gt)
    calls = [{"name": "get_usage_teammates", "result": {"rows": [{"name": "Farigiraf", "conditional_pct": 30.171}, {"name": "Rillaboom", "conditional_pct": 19.11},
                                                                 {"name": "Indeedee-F", "conditional_pct": 17.906}]}}]
    txt = "Showdown teammates for Golurk:\n1. Farigiraf - 30.17%\n2. Rillaboom - 19.11%\n3. Indeedee-F - 17.75%\n4. Empoleon - 13.2%"
    b = by(run(it, txt, calls))
    assert b[("teammates", "Farigiraf")] == T and b[("teammates", "Empoleon")] == F
    assert b[("teammates", "Indeedee-F=17.75")] == F and b[("teammates", "Farigiraf=30.17")] == T and b[("teammates", "Empoleon=13.2")] == F
    other = run(it, "In-game usage:\n1. Farigiraf\n2. Rillaboom", calls)  # names a different source than the prompt's
    assert all(c.verdict == U and c.reason == "different_source" for c in other)
    inh = item("usage", "teammates", {"species": "H", "common_items": ["Choice Scarf"], "teammates": ["Sneasler", "Rillaboom"], "source": "in-game"})
    cs = run(inh, "Top 5 Held Items:\n1. Choice Scarf (48.9%)\nTop 5 Teammates:\n1. Sneasler (rank 1)\n2. Rillaboom (rank 3)")
    b = by(cs)
    assert b[("common_items", "Choice Scarf")] == T and b[("teammates_rank", "Sneasler=1")] == T and b[("teammates_rank", "Rillaboom=3")] == F


def test_copied_unchanged_means_the_whole_carrier_line_is_in_the_final_text():
    calls = [{"name": "get_move_static", "result": {"base_power": 75, "category": "Physical", "type": "Fighting"}},
             {"name": "get_usage_items", "result": {"items": [{"name": "Choice Scarf", "pct": 48.9}, {"name": "Life Orb", "pct": 15.4}]}}]
    ms = run(item("move_static", "base_power", {"move": "Brick Break", "basePower": 75, "category": "Physical", "type": "Fighting"}),
             "Brick Break has a base power of 75 and is a Physical, Fighting-type move.", calls)
    flags = {c.kind: c.copied_unchanged for c in ms}
    assert flags == {"category": True, "move_type": True, "base_power": False}  # category and type are string lines; base power is an integer
    it = item("usage", "common_items", {"species": "H", "common_items": ["Choice Scarf", "Life Orb"], "teammates": [], "source": "in-game"})
    verbatim = {c.proposition: c.copied_unchanged for c in run(it, "Top 5 Held Items:\n1. Choice Scarf (48.9%)\n2. Life Orb (15.4%)\nNote: choice scarf   48.9 is the top row.", calls)}
    assert verbatim["Choice Scarf=48.9"] is True and verbatim["Life Orb=15.4"] is False  # the whole line "choice scarf 48.9" is in the text; "life orb 15.4" is not
    spd = run(item("speed", "outspeed", SPD), "Yes, Ninetales-Alola outspeeds Sylveon. Ninetales-Alola has a Speed stat of 177.", [{"name": "get_speed", "result": {"speed": 177}}])
    assert not any(c.copied_unchanged for c in spd)  # the stat is an integer field; the verdict has no value string
    dmg = run(item("damage", "guaranteed_ko", DMG), "No. Only 4 of the 16 rolls KO.", [{"name": "calc_damage", "result": {"rolls_that_ko": 4}}])
    assert not any(c.copied_unchanged for c in dmg)  # counts and verdicts are never carried by a line


@pytest.mark.parametrize("text,kind", [("Yes, Aromatisse has Fairy typing. It is a Fairy type.", "typing"), ("No, Pinsir has Bug typing? no", "typing")])
def test_every_claim_has_a_span_inside_the_text(text, kind):
    it = item("typing", "has_type", {"species": "Aromatisse", "asked_type": "Fairy", "has_type": True, "types": ["Fairy"]})
    for c in run(it, text):
        assert c.span is not None and 0 <= c.span[0] < c.span[1] <= len(text)


def test_audit_view_highlights_spans_writes_the_csv_columns_and_prints_no_rate(tmp_path):
    import csv
    import json
    import subprocess

    import audit_view as av

    it = {"id": "typing_x", "claim_type": "typing", "prompt": "Does Aromatisse have Fairy typing?",
          "claims": [{"kind": "has_type", "ground_truth": {"species": "Aromatisse", "asked_type": "Fairy", "has_type": True, "types": ["Fairy"]}}], "n_claims": 1}
    ans = {"id": "typing_x", "final_text": "Yes, Aromatisse has Fairy typing.", "tool_calls": [{"name": "get_typing", "args": {"species": "Aromatisse"}, "result": {"types": ["Fairy"]}}]}
    bat, answers = tmp_path / "b.json", tmp_path / "a.jsonl"
    bat.write_text(json.dumps({"items": [it]}))
    answers.write_text(json.dumps(ans) + "\n")
    cp = subprocess.run([sys.executable, str(Path(av.__file__)), "--answers", str(answers), "--battery", str(bat), "--out", str(tmp_path / "o"), "--size", "5"],
                        capture_output=True, text=True)
    assert cp.returncode == 0 and "false rate" not in cp.stdout.lower()
    page = (tmp_path / "o/audit.html").read_text()
    assert '<mark class="hl" style="background:#cfe8cf"' in page and ">Yes, Aromatisse has Fairy typing.</mark>" in page  # the TRUE verdict colours the span
    assert "<details><summary>get_typing" in page and "key values" in page and "false rate" not in page.lower()
    assert list(csv.reader((tmp_path / "o/audit.csv").open()))[0] == av.CSV_COLUMNS
    assert av.EXCEPTION_TYPES == ("missed_claim", "wrong_extraction", "wrong_verdict", "other")


def test_headline_is_withheld_until_the_exception_log_is_committed_and_hashed(tmp_path):
    import hashlib
    import subprocess

    repo = tmp_path / "r"
    repo.mkdir()
    git = lambda *a: subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *a], check=True, capture_output=True)  # noqa: E731
    git("init", "-q")
    log = repo / "exceptions.csv"
    log.write_text("item_id,reviewed\nx,y\n")
    sha = hashlib.sha256(log.read_bytes()).hexdigest()
    ok = lambda p, h: sc.exception_log_verified(p, h, repo)[0]  # noqa: E731
    assert not ok(None, None) and not ok(log, None)  # nothing given
    assert not ok(log, sha)  # exists and hashes right, but git does not track it
    git("add", "exceptions.csv")
    assert not ok(log, sha)  # staged is not committed
    git("commit", "-qm", "log")
    assert ok(log, sha)
    assert not ok(log, "0" * 64)  # wrong hash
    log.write_text("changed\n")
    assert not ok(log, hashlib.sha256(log.read_bytes()).hexdigest())  # an uncommitted edit
    assert not ok(repo / "missing.csv", sha)


def test_audit_view_takes_a_committed_id_list_and_refuses_ids_outside_the_answers(tmp_path):
    import json
    import subprocess

    it = {"id": "typing_x", "claim_type": "typing", "prompt": "q", "n_claims": 1,
          "claims": [{"kind": "has_type", "ground_truth": {"species": "A", "asked_type": "Fairy", "has_type": True, "types": ["Fairy"]}}]}
    bat, ans, ids = tmp_path / "b.json", tmp_path / "a.jsonl", tmp_path / "ids.json"
    bat.write_text(json.dumps({"items": [it]}))
    ans.write_text(json.dumps({"id": "typing_x", "final_text": "Yes, A is Fairy type.", "tool_calls": []}) + "\n")
    ids.write_text(json.dumps({"ids": ["typing_x"]}))
    run = lambda f: subprocess.run([sys.executable, str(Path(__file__).resolve().parents[2] / "scripts/eval/part_g_v4/audit_view.py"), "--answers", str(ans),  # noqa: E731
                                    "--battery", str(bat), "--out", str(tmp_path / "o"), "--ids-file", str(f)], capture_output=True, text=True)
    assert run(ids).returncode == 0 and (tmp_path / "o/audit.html").read_text().count("<section") == 1
    ids.write_text(json.dumps({"ids": ["typing_nope"]}))
    assert run(ids).returncode != 0


def test_ability_list_leads_has_n_abilities_and_along_with_parenthetical():
    gt = {"species": "Pikachu", "asked_ability": "Static", "has_ability": True, "abilities": ["Static", "Lightning Rod", "Surge Surfer"]}
    it = item("ability", "has_ability", gt)
    b = by(run(it, "Yes, Pikachu has Static. According to the data, Pikachu has three abilities: Static, Lightning Rod and Levitate."))
    assert b[("ability_list_member", "Lightning Rod")] == T and b[("ability_list_member", "Levitate")] == F
    two = by(run(item("ability", "has_ability", {"species": "Eevee", "asked_ability": "Run Away", "has_ability": True, "abilities": ["Run Away", "Adaptability", "Anticipation"]}),
                 "Yes, Eevee has Run Away. According to the data, Eevee can have Run Away as one of its abilities (along with Adaptability and Anticipation)."))
    assert two[("ability_list_member", "Adaptability")] == T and two[("ability_list_member", "Anticipation")] == T
    assert not any(k[1].lower().startswith("along") for k in two)  # the connective is not part of a name
    mixed = by(run(item("ability", "has_ability", {"species": "Eevee", "asked_ability": "Run Away", "has_ability": True, "abilities": ["Run Away", "Adaptability"]}),
                   "Yes, Eevee has Run Away. Eevee can have Run Away (plus Adaptability and Guts)."))
    assert mixed[("ability_list_member", "Guts")] == F and mixed[("ability_list_member", "Adaptability")] == T


DMG2 = {"attacker": "A", "defender": "D", "move": "M", "hp": 182, "min_roll": 186, "max_roll": 218, "guaranteed_ko": True, "rolls_ko_of_16": 16,
        "rolls": [186] * 16, "scoring": {"chance_tolerance_points": 3.125}}


def test_ohko_and_digit_hko_forms_and_hp_in_parentheses():
    it = item("damage", "guaranteed_ko", DMG2)
    b = by(run(it, "Yes. It is a guaranteed OHKO against a target with full HP (182)."))
    assert b[("guaranteed_ko", "yes")] == T and ("nhko", "guaranteed 1HKO") not in b and b[("labelled_value", "hp=182")] == T  # OHKO collapses onto "yes"
    wrong = by(run(it, "Yes. It is a possible 2HKO and a guaranteed 3hko. The defender's HP (150) is low."))
    assert wrong[("nhko", "possible 2HKO")] == F and wrong[("nhko", "guaranteed 3HKO")] == F and wrong[("labelled_value", "hp=150")] == F
    low = item("damage", "guaranteed_ko", {**DMG2, "min_roll": 100, "max_roll": 190, "guaranteed_ko": False, "rolls_ko_of_16": 3})
    assert by(run(low, "No. It is a possible OHKO."))[("nhko", "possible 1HKO")] == T  # max roll 190 >= HP 182
    assert by(run(low, "No. It is a guaranteed OHKO."))[("nhko", "guaranteed 1HKO")] == F  # min roll 100 < HP 182


def test_label_lines_are_not_list_entries_but_real_entries_are():
    gt = {"species": "S", "common_items": ["Leftovers"], "teammates": ["Rillaboom", "Garchomp"], "source": "in-game"}
    it = item("usage", "teammates", gt)
    txt = ("Top 5 teammates:\n1. Rillaboom (rank 1)\n2. Garchomp (rank 2)\n\n"
           "Note: the teammate list carries rank only, without percentages.\nCaveat: attribution may be ambiguous for some rows.\n"
           "Source: in-game usage ladder\nSummary - these are the most common partners\nWarning:")
    b = by(run(it, txt))
    assert b[("teammates", "Rillaboom")] == T and b[("teammates", "Garchomp")] == T
    assert not any(k[1].startswith(("Note", "Caveat", "Source", "Summary", "Warning")) for k in b)  # no claim from a label line
    assert [k for k in b if k[0] == "teammates"] == [("teammates", "Rillaboom"), ("teammates", "Garchomp")]
    unmarked = by(run(it, "Teammates:\nRillaboom: 31.5%\nSomeone Else: 12.0%"))  # short "Name: value" lines are entries
    assert unmarked[("teammates", "Someone Else")] == F  # a real list entry that is not in the key still scores FALSE


def test_trailing_as_an_ability_is_not_part_of_a_list_member_name():
    gt = {"species": "Mimikyu-Mega", "form": "Mimikyu-Mega", "form_id": "mimikyumega", "asked_ability": "Disguise", "has_ability": True, "form_abilities": ["Disguise"]}
    it = item("ability_form", "has_ability", gt)
    b = by(run(it, "Yes, Mimikyu-Mega has Disguise. According to the data, Mimikyu-Mega can have Disguise as an ability and Pressure as one of its abilities."))
    assert ("ability_list_member", "Pressure") in b and b[("ability_list_member", "Pressure")] == F
    assert not any(k[1].lower().endswith(("as an ability", "as one of its abilities")) for k in b)
    only = by(run(item("ability", "has_ability", {"species": "X", "asked_ability": "Static", "has_ability": False, "abilities": ["Keen Eye"]}),
                  "No, X does not have Static. According to the data, X can have Keen Eye as its ability."))
    assert only[("ability_list_member", "Keen Eye")] == T  # "as its ability" is trimmed too


GK = {"attacker": "A", "defender": "D", "move": "M", "hp": 186, "min_roll": 84, "max_roll": 100, "guaranteed_ko": False, "rolls_ko_of_16": 0,
      "rolls": [84] * 15 + [100], "scoring": {"chance_tolerance_points": 3.125}}


def test_half_of_n_uses_the_figure_the_arm_stated_and_never_halves_it_itself():
    it = item("damage", "guaranteed_ko", GK)
    stated = [(k, v) for k, v in by(run(it, "No. Since the defender has 186 HP, the move would need to deal at least 94 damage (half of 186) to KO it.")).items() if k[0] == "ko_needed"]
    assert stated == [(("ko_needed", "damage needed to KO = 94"), F)]  # one claim, the arm's 94; no 93
    bare = [(k, v) for k, v in by(run(it, "No. A KO needs half of 186 HP.")).items() if k[0] == "ko_needed"]
    assert bare == [(("ko_needed", "damage needed to KO = 93"), F)]  # no stated figure: the half-of-HP claim itself
    split = by(run(it, "No. The move would need at least 186 damage to KO. Separately, half of 186 is a common benchmark; a KO needs half of 186 HP."))
    assert split[("ko_needed", "damage needed to KO = 186")] == T and split[("ko_needed", "damage needed to KO = 93")] == F  # a later sentence with no figure keeps its claim


def test_guaranteed_one_hko_and_sixteen_of_sixteen_collapse_onto_guaranteed_ko_yes():
    full = {**GK, "guaranteed_ko": True, "rolls_ko_of_16": 16, "min_roll": 190, "max_roll": 220, "rolls": [190] * 16}
    it = item("damage", "guaranteed_ko", full)
    cs = run(it, "Yes, this guarantees a KO. Every one of the 16 damage rolls knocks the defender out, a guaranteed OHKO.")
    assert [(c.kind, c.proposition) for c in cs] == [("guaranteed_ko", "yes")]  # three statements, one claim; guaranteed_ko is the one kept
    part = item("damage", "guaranteed_ko", {**full, "guaranteed_ko": False, "rolls_ko_of_16": 12, "min_roll": 150})
    cs = run(part, "No. 12 of the 16 rolls knock it out, with a 75% chance to OHKO and a possible OHKO.")
    kinds = [(c.kind, c.proposition) for c in cs]
    assert ("ko_count", "12 of 16 rolls KO") in kinds and ("ko_chance", "75%") in kinds and ("nhko", "possible 1HKO") in kinds  # partial counts, chances and possible OHKO stay
    contradict = [(c.kind, c.proposition) for c in run(it, "No, this does not guarantee a KO. Every one of the 16 rolls knocks it out.")]
    assert ("guaranteed_ko", "no") in contradict and ("ko_count", "16 of 16 rolls KO") in contradict  # a contradiction is not collapsed


def test_dedupe_equivalence_prefers_the_guaranteed_ko_claim_in_any_order():
    g = sc.Claim("guaranteed_ko", "A M D", "yes", T, ctype="damage")
    n = sc.Claim("nhko", "A M D", "guaranteed 1HKO", T, ctype="damage")
    k = sc.Claim("ko_count", "a m d", "16 of 16 rolls KO", T, line="ko_chance", ctype="damage")
    for order in ([g, n, k], [n, k, g], [k, g, n]):
        assert sc.dedupe(order) == [g]
    other = sc.Claim("ko_count", "A M D", "15 of 16 rolls KO", T, line="ko_chance", ctype="damage")
    assert len(sc.dedupe([g, n, other])) == 2 and len(sc.dedupe([n, k])) == 1  # without a guaranteed_ko claim the first equivalent one stands


# --- audit view input controls -------------------------------------------------------------------

def _node(js: str) -> str:
    import shutil
    import subprocess

    if shutil.which("node") is None:
        pytest.skip("node is not installed")
    return subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout


def test_audit_csv_export_logic_matches_python_csv_for_awkward_fields():
    import csv
    import io
    import json

    import audit_view as av

    ids = ["a_1", "a_2", "a_3", "a_4", "a_5"]
    state = {"reviewed": {"a_1": True, "a_2": True, "a_3": False, "a_5": True},
             "exceptions": {"a_2": [{"type": "missed_claim", "claim": 'He said "Yes", then left', "note": "line one\nline two, with comma"},
                                    {"type": "wrong_verdict", "claim": "Rillaboom 32.411%", "note": ""}],
                            "a_3": [{"type": "other", "claim": "Pokémon ✓", "note": "unreviewed answer with an exception"}],
                            "a_4": []}}
    out = _node(av.EXPORT_JS + f"process.stdout.write(JSON.stringify(toCsv(buildRows({json.dumps(ids)}, {json.dumps(state)}))));")
    got = json.loads(out)
    rows = [["a_1", "y", "", "", ""],  # reviewed and clean: one row
            ["a_2", "y", "missed_claim", 'He said "Yes", then left', "line one\nline two, with comma"],  # one row per exception
            ["a_2", "y", "wrong_verdict", "Rillaboom 32.411%", ""],
            ["a_3", "n", "other", "Pokémon ✓", "unreviewed answer with an exception"],  # an exception is exported even if the box is unchecked
            ["a_5", "y", "", "", ""]]  # a_4 is not reviewed and has no exception: no row
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(av.CSV_COLUMNS)
    w.writerows(rows)
    assert got == buf.getvalue()  # byte-for-byte what Python's csv module writes (CRLF, RFC 4180 quoting)
    parsed = list(csv.reader(io.StringIO(got, newline="")))
    assert parsed[0] == av.CSV_COLUMNS and parsed[1:] == rows  # and it round-trips, newline inside a field included
    empty = _node(av.EXPORT_JS + "process.stdout.write(JSON.stringify(toCsv(buildRows(['x'], {}))));")
    assert json.loads(empty) == ",".join(av.CSV_COLUMNS) + "\r\n"  # nothing reviewed: header only


def test_audit_page_has_the_input_controls_autosave_key_and_no_figure(tmp_path):
    import hashlib
    import json
    import re
    import subprocess

    import audit_view as av

    items = [{"id": f"typing_{n}", "claim_type": "typing", "prompt": "q", "n_claims": 1,
              "claims": [{"kind": "has_type", "ground_truth": {"species": "A", "asked_type": "Fairy", "has_type": True, "types": ["Fairy"]}}]} for n in (1, 2)]
    bat, ans, ids = tmp_path / "b.json", tmp_path / "a.jsonl", tmp_path / "ids.json"
    bat.write_text(json.dumps({"items": items}))
    ans.write_text("".join(json.dumps({"id": i["id"], "final_text": "Yes, A has Fairy typing. It is a Fairy type.", "tool_calls": []}) + "\n" for i in items))
    ids.write_text(json.dumps({"ids": ["typing_1", "typing_2"]}))
    cp = subprocess.run([sys.executable, str(Path(av.__file__)), "--answers", str(ans), "--battery", str(bat), "--out", str(tmp_path / "o"), "--ids-file", str(ids)],
                        capture_output=True, text=True)
    assert cp.returncode == 0
    page = (tmp_path / "o/audit.html").read_text()
    assert page.count('<input type="checkbox" class="rev">') == 2 and page.count('class="addex"') == 2 and page.count('class="exlist"') == 2
    assert all(f'"{t}"' in page for t in av.EXCEPTION_TYPES) and 'id="exportcsv"' in page and 'id="clearall"' in page and "confirm(" in page  # Clear asks first
    assert json.dumps(hashlib.sha256("typing_1\ntyping_2".encode()).hexdigest()) in page  # the autosave key is the sample id list's sha256
    for m in re.finditer(r"localStorage\.(?:getItem|setItem)", page):  # every storage call sits inside a try block
        assert "try {" in page[max(0, m.start() - 200):m.start()]
    assert 'id="status"' in page and "'unsaved'" in page and "'saved'" in page
    low = page.lower()
    assert "false rate" not in low and "passes" not in low and "cp_upper" not in low and "headline figure" in low  # only the sentence saying none is shown
    assert page.count('<mark class="hl"') >= 2  # the highlight layout is unchanged and clickable
