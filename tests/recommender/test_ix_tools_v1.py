"""FU73 / #367+#368: find_by_effect + get_type_effectiveness behind ix_tools_v1."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.eval.part_g_arm.state import ix_tools as ix
from scripts.eval.part_g_arm.state.tools import (
    combined_specs,
    ix_tools_v1_enabled,
    set_ix_tools_v1,
    set_tool_fields,
    set_tool_fixes_v2,
    set_wrapper,
    set_draft,
)

ROOT = Path(__file__).resolve().parents[2]
TYPE_CHART = ROOT / "scripts/eval/part_g_v4/key_artifacts/type_chart.v1.json"


@pytest.fixture(autouse=True)
def _ix_on():
    set_ix_tools_v1(True)
    yield
    set_ix_tools_v1(False)


# --- #367 acceptance 1 ---


def test_redirection_flag_returns_follow_me_and_rage_powder_only():
    r = ix.find_by_effect("move", flag="redirection")
    assert r["status"] == "ok"
    names = {m["name"] for m in r["matches"]}
    assert names == {"Follow Me", "Rage Powder"}
    assert all(m["matched_by"] in ("flag", "both") for m in r["matches"])
    assert "Dragon Darts" not in names
    assert "Snipe Shot" not in names


def test_redirection_alias_matches_flag_set():
    by_flag = {m["name"] for m in ix.find_by_effect("move", flag="redirection")["matches"]}
    by_alias = {m["name"] for m in ix.find_by_effect("move", flag="redirect")["matches"]}
    assert by_flag == by_alias == {"Follow Me", "Rage Powder"}


def test_phazing_drag_alias_equals_flag():
    a = {m["name"] for m in ix.find_by_effect("move", flag="phazing")["matches"]}
    b = {m["name"] for m in ix.find_by_effect("move", flag="drag")["matches"]}
    assert a == b
    assert a == {"Circle Throw", "Dragon Tail", "Roar", "Whirlwind"}


def test_flag_members_appear_in_canonical_keyword_results():
    for flag, phrase in ix.FLAG_CANONICAL_PHRASE.items():
        flag_names = {m["name"] for m in ix.find_by_effect("move", flag=flag)["matches"]}
        kw_names = {
            m["name"]
            for m in ix.find_by_effect("move", keyword=phrase)["matches"]
        }
        missing = flag_names - kw_names
        assert not missing, f"{flag!r} phrase {phrase!r} missing {missing}"


def test_keyword_near_miss_does_not_match_unrelated_substring():
    # "coat" is inside Magic Coat; word-boundary must not hit "redirected" rows via "red".
    r = ix.find_by_effect("move", keyword="red")
    names = {m["name"] for m in r["matches"]}
    assert "Follow Me" not in names
    assert "Rage Powder" not in names


def test_intimidate_keyword_on_abilities_is_kind_scoped():
    r = ix.find_by_effect("ability", keyword="Intimidate")
    assert r["status"] == "ok"
    assert r["count"] >= 1
    names = {m["name"] for m in r["matches"]}
    assert "Inner Focus" in names or "Guard Dog" in names
    # Near-miss: must not return moves when kind=ability.
    assert all(m["matched_by"] == "description" for m in r["matches"])


def test_matched_by_both_when_flag_and_keyword_agree():
    r = ix.find_by_effect("move", flag="redirection", keyword="redirected")
    by = {m["name"]: m["matched_by"] for m in r["matches"]}
    assert by["Follow Me"] == "both"
    assert by["Rage Powder"] == "both"
    # Description-only near-misses ranked after flag hits.
    assert by.get("Dragon Darts") == "description" or "Dragon Darts" in by


def test_ground_keyword_distinguishes_levitate_from_sand_force():
    r = ix.find_by_effect("ability", keyword="Ground")
    by_name = {m["name"]: m for m in r["matches"]}
    assert "Levitate" in by_name and "Sand Force" in by_name
    lev, sand = by_name["Levitate"], by_name["Sand Force"]
    assert lev["matched_span"].casefold() == "ground"
    assert sand["matched_span"].casefold() == "ground"
    # Window / description must let the arm tell immunity from a Ground boost
    # without a follow-up describe call.
    lev_text = f"{lev.get('matched_window', '')} {lev.get('description', '')}".casefold()
    sand_text = f"{sand.get('matched_window', '')} {sand.get('description', '')}".casefold()
    assert "immune" in lev_text
    assert "immune" not in sand_text or "sandstorm" in sand_text
    assert "1.3" in sand_text or "power" in sand_text
    assert lev.get("matched_window") != sand.get("matched_window")


def test_allies_keyword_returns_telepathy_with_description():
    r = ix.find_by_effect("ability", keyword="allies")
    tele = next(m for m in r["matches"] if m["name"] == "Telepathy")
    assert "allies" in (tele.get("matched_window") or "").casefold()
    assert "allies" in (tele.get("description") or "").casefold()
    assert "damage" in (tele.get("description") or "").casefold()


def test_flag_matches_include_full_description():
    r = ix.find_by_effect("move", flag="redirection")
    for m in r["matches"]:
        assert m["matched_by"] in ("flag", "both")
        assert isinstance(m.get("description"), str) and len(m["description"]) > 20


# --- #368 acceptance 1–2 ---


def test_ground_attack_returns_chart_buckets():
    chart = json.loads(TYPE_CHART.read_text())["effectiveness"]["Ground"]
    r = ix.get_type_effectiveness(attack_type="Ground")
    assert r["status"] == "ok"
    assert r["no_damage"] == sorted(d for d, m in chart.items() if m == 0)
    assert r["no_damage"] == ["Flying"]
    assert r["super_effective"] == sorted(d for d, m in chart.items() if m > 1)
    assert r["resisted"] == sorted(d for d, m in chart.items() if 0 < m < 1)
    assert set(r) <= {
        "status",
        "source",
        "attack_type",
        "super_effective",
        "resisted",
        "no_damage",
    }


def test_type_chart_is_eval_extract_identity():
    disk = json.loads(TYPE_CHART.read_text())
    tool_doc = ix._type_chart_doc()
    assert tool_doc == disk
    r = ix.get_type_effectiveness(attack_type="Fire")
    assert "type_chart.v1.json" in r["source"]["path"]


# --- flag gate / schema ---


def test_flag_off_omits_ix_tools_from_schema():
    set_ix_tools_v1(False)
    set_tool_fixes_v2(False)
    set_tool_fields(False)
    set_wrapper(False)
    set_draft(False)
    names = {s["function"]["name"] for s in combined_specs()}
    assert "find_by_effect" not in names
    assert "get_type_effectiveness" not in names
    assert not ix_tools_v1_enabled()


def test_flag_on_adds_ix_tools_to_schema():
    set_ix_tools_v1(True)
    names = {s["function"]["name"] for s in combined_specs()}
    assert "find_by_effect" in names
    assert "get_type_effectiveness" in names
