"""Arm tools: serializer, tie extension, snapshot lookups, dispatch errors; calc-backed ones need the service."""

from __future__ import annotations

import dataclasses
import json
import os

import pytest

from recommender.arm_tools import ArmTools, dumps, to_jsonable, top_n_with_ties


@dataclasses.dataclass(frozen=True)
class _Inner:
    b: int
    a: tuple[str, ...]


@dataclasses.dataclass(frozen=True)
class _Outer:
    z: _Inner | None
    y: float
    rows: tuple[_Inner, ...]


def test_serializer_nests_frozen_dataclasses_and_sorts_keys():
    obj = _Outer(z=_Inner(1, ("x", "y")), y=0.5, rows=(_Inner(2, ()),))
    assert to_jsonable(obj) == {"z": {"b": 1, "a": ["x", "y"]}, "y": 0.5, "rows": [{"b": 2, "a": []}]}
    assert dumps(obj) == '{"rows":[{"a":[],"b":2}],"y":0.5,"z":{"a":["x","y"],"b":1}}'
    assert dumps(_Outer(None, 1.0, ())) == '{"rows":[],"y":1.0,"z":null}'


def test_serializer_rejects_unknown_types():
    with pytest.raises(TypeError):
        to_jsonable({"k": {1, 2}})


def test_ties_extend_past_n():
    rows = [{"name": c, "pct": p} for c, p in zip("abcdefg", (50, 40, 30, 20, 10, 10, 10))]
    assert [r["name"] for r in top_n_with_ties(rows, 5)] == list("abcdefg")
    assert [r["name"] for r in top_n_with_ties(rows, 3)] == list("abc")
    assert len(top_n_with_ties(rows[:2], 5)) == 2


def test_offline_assertion():
    with pytest.raises(AssertionError):
        ArmTools(regulation="champions", allow_live=True)


@pytest.fixture(scope="module")
def tools():
    return ArmTools(regulation="champions", allow_live=False)


def test_snapshot_tools(tools):
    assert tools.get_typing("Charizard-Mega-X")["types"] == ["Fire", "Dragon"]
    assert tools.get_abilities("Charizard-Mega-X")["abilities"] == ["Tough Claws"]
    assert tools.get_typing("Notamon")["status"] == "not_found"
    assert tools.check_species_legal("Notamon") == {**tools.check_species_legal("Notamon"), "in_snapshot": False, "legal": False}
    assert tools.check_item_legal("Abomasite")["legal_as_held_item"] is True
    assert tools.get_move_static("Flamethrower")["base_power"] == 90


def test_dispatch_errors_are_results(tools):
    assert tools.call("nope", {})["error_kind"] == "unknown_tool"
    assert tools.call("get_typing", {"mon": "x"})["error_kind"] == "bad_arguments"
    assert tools.call("get_usage_items", {"species": "Hydreigon", "source": "web"})["error_kind"] == "invalid_source"
    assert tools.call("calc_damage", {"attacker": {"species": "A", "bogus": 1}, "defender": {"species": "B"}, "move": "M"})["error_kind"] == "bad_arguments"


def test_usage_items_labelled_and_tie_extended(tools):
    r = tools.get_usage_items("Hydreigon", "ingame", 5)
    assert r["source"].startswith("in-game") and len(r["items"]) >= 5
    assert json.loads(dumps(r)) == r
    assert tools.get_usage_items("Notamon", "ingame")["status"] == "not_found"


def test_teammates_offline_labelled(tools):
    r = tools.get_usage_teammates("Hydreigon", "ingame")
    assert r["used_source"] == "ingame" and r["method"] == "offline"
    assert all(row["conditional_pct"] is None for row in r["rows"])
    json.loads(dumps(r))


@pytest.mark.skipif(os.environ.get("CALC_LIVE") != "1", reason="needs live calc service")
def test_calc_backed_tools(tools):
    s = tools.get_speed("Garchomp", "Jolly", 32)
    assert s["status"] == "ok" and s["speed"] == 169
    d = tools.call("calc_damage", {"attacker": {"species": "Garchomp", "nature": "Jolly", "sp": {"atk": 32}},
                                   "defender": {"species": "Gengar", "sp": {"hp": 32}}, "move": "Earthquake"})
    assert d["status"] == "ok" and len(d["damage_rolls"]) == 16 and d["defender_hp"] == 167
    assert tools.get_speed("Aegislash", "Hardy", 0)["error_kind"] == "calc_error"


def test_field_defaults_to_doubles_and_validates():
    from recommender.arm_tools import _field

    assert _field(None) == {"gameType": "Doubles"} == _field({})
    assert _field({"weather": "Sun"}) == {"gameType": "Doubles", "weather": "Sun"}
    assert _field({"gameType": "Singles"}) == {"gameType": "Singles"}
    with pytest.raises(ValueError):
        _field({"crit": True})


def test_unknown_weather_is_a_tool_error_listing_valid_values(tools):
    r = tools.call("calc_damage", {"attacker": {"species": "A"}, "defender": {"species": "B"}, "move": "M", "field": {"weather": "Drizzle"}})
    assert r["error_kind"] == "bad_arguments" and "'Rain'" in r["message"] and "Drizzle" in r["message"]
    from recommender.arm_tools import _field

    assert _field({"weather": "Rain"})["weather"] == "Rain"


class _FailingCalc:
    def __init__(self, species):
        self.species = species

    def calculate(self, *a, **k):
        from recommender.calc_client import CalcClientError

        raise CalcClientError(400, {"error": f"unknown Champions species: {self.species}"})


def _speed_error(name):
    return ArmTools(regulation="champions", allow_live=False, calc=_FailingCalc(name)).get_speed(name, "Hardy", 0)


@pytest.mark.parametrize("name,base", [("Goodra-Gooey", "Goodra"), ("Typhlosion-Flash Fire", "Typhlosion"),
                                       ("Slowbro-Galar-Own Tempo", "Slowbro-Galar")])
def test_ability_suffix_suggests_the_species(name, base):
    r = _speed_error(name)
    assert r["error_kind"] == "calc_error" and r["calc_message"] == f"unknown Champions species: {name}"
    assert f"Did you mean the species '{base}'" in r["message"] and "never include an ability" in r["message"]


@pytest.mark.parametrize("name", ["Pikachu-Gooey", "Goodra-Blaze", "Notamon"])
def test_other_unknown_names_suggest_nothing(name):
    r = _speed_error(name)  # suffix is not an ability of that species, or there is no such species
    assert "Did you mean" not in r["message"] and f"{name!r} is not a species name" in r["message"]


def test_name_in_snapshot_but_rejected_by_calc_is_reported_as_such():
    r = _speed_error("Aegislash")
    assert "does not recognise the species name" in r["message"] and "Did you mean" not in r["message"]


def test_no_lookup_needed_records_reason_and_category(tools):
    r = tools.call("no_lookup_needed", {"reason": "asks about strategy", "category": "conceptual"})
    assert r["status"] == "ok" and r["recorded"] and r["category"] == "conceptual" and r["reason"] == "asks about strategy"
    assert tools.call("no_lookup_needed", {"reason": "x", "category": "other"})["error_kind"] == "bad_arguments"


def test_check_species_ability(tools):
    r = tools.call("check_species_ability", {"species": "Dragapult", "ability": "Clear Body"})
    assert r["status"] == "ok" and r["species_can_have_ability"] is True
    assert r["species_abilities"] == ["Clear Body", "Infiltrator", "Cursed Body"] and r["source"].startswith("legality snapshot")
    assert tools.call("check_species_ability", {"species": "Dragapult", "ability": "clear body"})["species_can_have_ability"] is True
    assert tools.call("check_species_ability", {"species": "Dragapult", "ability": "Libero"})["species_can_have_ability"] is False
    assert tools.call("check_species_ability", {"species": "Gardevoir-Mega", "ability": "Pixilate"})["species_abilities"] == ["Pixilate"]
    assert tools.call("check_species_ability", {"species": "Notamon", "ability": "Static"})["status"] == "not_found"
    assert json.loads(dumps(r)) == r  # serializer: plain JSON with sorted keys survives a round trip
    assert dumps(r) == json.dumps(r, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    assert tools.call("get_abilities", {"species": "Dragapult"})["abilities"] == r["species_abilities"]  # get_abilities is kept


def test_unknown_item_name_notes_where_to_look_but_stays_illegal(tools):
    r = tools.check_item_legal("Weak Armor")
    assert r["in_snapshot"] is False and r["legal_as_held_item"] is False
    assert "use the matching tool" in r["note"] and "check_species_ability" in r["note"]
    known = tools.check_item_legal("Heat Rock")
    assert known["in_snapshot"] is True and "note" not in known


@pytest.mark.skipif(os.environ.get("CALC_LIVE") != "1", reason="needs live calc service")
def test_damage_rolls_can_be_left_out_of_the_result_keeping_the_derived_fields():
    args = {"attacker": {"species": "Garchomp", "nature": "Jolly", "sp": {"atk": 32}}, "defender": {"species": "Gengar", "sp": {"hp": 32}},
            "move": "Earthquake"}
    full = ArmTools(regulation="champions", allow_live=False).call("calc_damage", args)
    lean = ArmTools(regulation="champions", allow_live=False, include_damage_rolls=False).call("calc_damage", args)
    assert "damage_rolls" in full and "damage_rolls" not in lean
    assert {k: v for k, v in full.items() if k != "damage_rolls"} == lean
    assert lean["rolls_that_ko"] == sum(x >= lean["defender_hp"] for x in full["damage_rolls"])
