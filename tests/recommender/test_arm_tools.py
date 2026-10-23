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
