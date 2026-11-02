"""tool_fields: base+own Mega stone maps to Mega forme for calc_damage."""

from __future__ import annotations

from recommender.arm_tools import ArmTools
from recommender.calc_client import CalcClient
from scripts.eval.part_g_arm.state.fixtures import empty_team
from scripts.eval.part_g_arm.state.harness import dispatch
from scripts.eval.part_g_arm.state.mega_stone_calc import mega_forme_for_base_holding_stone
from scripts.eval.part_g_arm.state.tools import set_tool_fields, set_wrapper


def setup_function() -> None:
    set_tool_fields(False)
    set_wrapper(False)


def teardown_function() -> None:
    set_tool_fields(False)
    set_wrapper(False)


def test_helper_aggronite_maps() -> None:
    assert mega_forme_for_base_holding_stone("Aggron", "Aggronite") == "Aggron-Mega"
    assert mega_forme_for_base_holding_stone("Aggron", "Leftovers") is None
    assert mega_forme_for_base_holding_stone("Aggron-Mega", "Aggronite") is None


def test_calc_damage_maps_base_plus_stone() -> None:
    set_tool_fields(True)
    arm = ArmTools(regulation="champions", allow_live=False, calc=CalcClient())
    _, res = dispatch(
        empty_team(),
        arm,
        "calc_damage",
        {
            "attacker": {
                "species": "Aggron",
                "nature": "Adamant",
                "item": "Aggronite",
                "sp": {"hp": 0, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 0},
            },
            "defender": {
                "species": "Volcarona",
                "nature": "Modest",
                "ability": "Flame Body",
                "sp": {"hp": 32, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
            },
            "move": "Earthquake",
            "field": {"gameType": "Doubles"},
        },
    )
    assert res.get("status") == "ok"
    fr = res.get("forme_resolution") or {}
    assert fr["attacker"]["forme_used"] == "Aggron-Mega"
    assert fr["attacker"]["mapped_via"] == "mega_stone"
    assert fr["defender"]["forme_used"] == "Volcarona"
    assert fr["defender"]["mapped_via"] is None
    assert (res.get("request") or {}).get("attacker", {}).get("species") == "Aggron-Mega"
    assert res.get("ability_source", {}).get("attacker") == "auto_single"
    assert (res.get("request") or {}).get("attacker", {}).get("ability") == "Filter"


def test_calc_damage_no_map_without_stone() -> None:
    set_tool_fields(True)
    arm = ArmTools(regulation="champions", allow_live=False, calc=CalcClient())
    _, res = dispatch(
        empty_team(),
        arm,
        "calc_damage",
        {
            "attacker": {
                "species": "Aggron",
                "nature": "Adamant",
                "item": "Leftovers",
                "ability": "Sturdy",
                "sp": {"hp": 0, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 0},
            },
            "defender": {
                "species": "Volcarona",
                "nature": "Modest",
                "ability": "Flame Body",
                "sp": {"hp": 32, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
            },
            "move": "Earthquake",
            "field": {"gameType": "Doubles"},
        },
    )
    assert res.get("status") == "ok"
    fr = res.get("forme_resolution") or {}
    assert fr["attacker"]["forme_used"] == "Aggron"
    assert fr["attacker"]["mapped_via"] is None
    assert (res.get("request") or {}).get("attacker", {}).get("species") == "Aggron"


def test_check_species_legal_cause_mythical() -> None:
    set_tool_fields(True)
    arm = ArmTools(regulation="champions", allow_live=False, calc=CalcClient())
    _, res = dispatch(empty_team(), arm, "check_species_legal", {"species": "Darkrai"})
    assert res.get("legal") is False
    assert res.get("cause") == "Mythical"


def test_flags_off_no_mapping() -> None:
    set_tool_fields(False)
    arm = ArmTools(regulation="champions", allow_live=False, calc=CalcClient())
    _, res = dispatch(
        empty_team(),
        arm,
        "calc_damage",
        {
            "attacker": {
                "species": "Aggron",
                "nature": "Adamant",
                "item": "Aggronite",
                "ability": "Sturdy",
                "sp": {"hp": 0, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 0},
            },
            "defender": {
                "species": "Volcarona",
                "nature": "Modest",
                "ability": "Flame Body",
                "sp": {"hp": 32, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
            },
            "move": "Earthquake",
            "field": {"gameType": "Doubles"},
        },
    )
    assert res.get("status") == "ok"
    assert "forme_resolution" not in res
    assert (res.get("request") or {}).get("attacker", {}).get("species") == "Aggron"
