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
    assert by(run(it, "Yes, every one of the 16 rolls knocks the defender out."))[("ko_count", "16 of 16 rolls KO")] == F  # and the verdict is wrong too


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


def test_copied_unchanged_needs_verbatim_values_and_no_relation():
    calls = [{"name": "get_move_static", "result": {"base_power": 75, "category": "Physical", "type": "Fighting"}},
             {"name": "get_usage_items", "result": {"items": [{"name": "Choice Scarf", "pct": 48.9}, {"name": "Life Orb", "pct": 15.4}]}}]
    ms = run(item("move_static", "base_power", {"move": "Brick Break", "basePower": 75, "category": "Physical", "type": "Fighting"}),
             "Brick Break has a base power of 75 and is a Physical, Fighting-type move.", calls)
    assert all(c.copied_unchanged for c in ms)
    us = run(item("usage", "common_items", {"species": "H", "common_items": ["Choice Scarf", "Life Orb"], "teammates": [], "source": "in-game"}),
             "Top 5 Held Items:\n1. Choice Scarf (48.9%)\n2. Life Orb (15.0%)", calls)
    flags = {c.proposition: c.copied_unchanged for c in us}
    assert flags["Choice Scarf=48.9"] is True and flags["Life Orb=15"] is False and flags["Choice Scarf"] is True  # 15.0 is not the tool's 15.4
    spd = run(item("speed", "outspeed", SPD), "Yes, Ninetales-Alola outspeeds Sylveon. Ninetales-Alola has a Speed stat of 177.",
              [{"name": "get_speed", "result": {"speed": 177}}])
    flg = {(c.kind): c.copied_unchanged for c in spd}
    assert flg["outspeed"] is False and flg["speed_stat"] is True  # a verdict is a relation; the stat is copied
    dmg = run(item("damage", "guaranteed_ko", DMG), "No. Only 4 of the 16 rolls KO.", [{"name": "calc_damage", "result": {"rolls_that_ko": 4}}])
    assert not any(c.copied_unchanged for c in dmg)  # counts and verdicts state a relation even when the number is in the result


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
    assert '<mark style="background:#cfe8cf"' in page and ">Yes, Aromatisse has Fairy typing.</mark>" in page  # the TRUE verdict colours the span
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
