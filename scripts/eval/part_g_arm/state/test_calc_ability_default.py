"""tool_fields: calc_damage requires ability; get_usage_stats top_ability (FU14)."""

from __future__ import annotations

import pytest

from recommender.arm_tools import ArmTools
from recommender.calc_client import CalcClient
from scripts.eval.part_g_arm.state import ability_default as ad
from scripts.eval.part_g_arm.state.ability_default import (
    prepare_calc_damage_args,
    preferred_ability_source,
)
from scripts.eval.part_g_arm.state.fixtures import empty_team
from scripts.eval.part_g_arm.state.harness import dispatch
from scripts.eval.part_g_arm.state.tools import (
    combined_specs,
    set_tool_fields,
    set_wrapper,
)
from scripts.eval.part_g_arm.state.usage_meta_tools import get_usage_stats


@pytest.fixture(autouse=True)
def _flags_off():
    set_tool_fields(False)
    set_wrapper(False)
    yield
    set_tool_fields(False)
    set_wrapper(False)


@pytest.fixture
def arm():
    return ArmTools(regulation="champions", allow_live=False, calc=CalcClient())


def test_missing_ability_refused_with_legal_list(arm):
    set_tool_fields(True)
    state = empty_team()
    _, res = dispatch(
        state,
        arm,
        "calc_damage",
        {
            "attacker": {
                "species": "Annihilape",
                "nature": "Adamant",
                "sp": {"hp": 0, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 0},
            },
            "defender": {
                "species": "Incineroar",
                "nature": "Adamant",
                "ability": "Intimidate",
                "sp": {"hp": 32, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
            },
            "move": "Close Combat",
            "field": {"gameType": "Doubles"},
        },
    )
    assert res.get("error_kind") == "missing_ability"
    assert res.get("side") == "attacker"
    assert "Defiant" in (res.get("legal_abilities") or [])
    assert "get_usage_stats" in (res.get("message") or "")


def test_single_ability_autofill_mega(arm):
    set_tool_fields(True)
    state = empty_team()
    _, res = dispatch(
        state,
        arm,
        "calc_damage",
        {
            "attacker": {
                "species": "Gallade-Mega",
                "nature": "Jolly",
                "item": "Galladite",
                "sp": {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32},
            },
            "defender": {
                "species": "Incineroar",
                "nature": "Adamant",
                "ability": "Intimidate",
                "item": "Sitrus Berry",
                "sp": {"hp": 32, "atk": 32, "def": 0, "spa": 0, "spd": 2, "spe": 0},
            },
            "move": "Close Combat",
            "field": {"gameType": "Doubles"},
        },
    )
    assert res.get("status") == "ok"
    assert res.get("ability_source") == {
        "attacker": "auto_single",
        "defender": "stated",
    }
    assert (res.get("request") or {}).get("attacker", {}).get("ability") == "Inner Focus"
    assert res.get("damage_range") == [270, 318]


def test_stated_ability_echo(arm):
    set_tool_fields(True)
    state = empty_team()
    _, res = dispatch(
        state,
        arm,
        "calc_damage",
        {
            "attacker": {
                "species": "Annihilape",
                "nature": "Adamant",
                "ability": "Defiant",
                "sp": {"hp": 0, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 0},
            },
            "defender": {
                "species": "Incineroar",
                "nature": "Adamant",
                "ability": "Intimidate",
                "sp": {"hp": 32, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
            },
            "move": "Close Combat",
            "field": {"gameType": "Doubles"},
        },
    )
    assert res.get("status") == "ok"
    assert res.get("ability_source") == {
        "attacker": "stated",
        "defender": "stated",
    }


def test_default_source_non_mega_ingame():
    assert preferred_ability_source("Incineroar") == "ingame"
    out = get_usage_stats("Incineroar", "abilities")
    assert out["default_source"] == "ingame"
    assert out["default_source_missing"] is False
    assert out["top_ability"]["name"] == "Intimidate"
    assert out["top_ability"]["source"] == "ingame"


def test_default_source_mega_capable_base_showdown():
    # Floette-Eternal is the MEGA_STONES base (arm_teammates), not floette.
    assert preferred_ability_source("Floette-Eternal") == "showdown"
    out = get_usage_stats("Floette-Eternal", "abilities")
    assert out["default_source"] == "showdown"


def test_default_source_mega_forme_showdown():
    assert preferred_ability_source("Gallade-Mega") == "showdown"
    out = get_usage_stats("Gallade-Mega", "abilities")
    assert out["default_source"] == "showdown"


def test_default_source_missing_meowstic_f():
    # Meowstic-F is itself a mega-capable base (Meowsticite-F); preferred=Showdown
    # but Showdown has no meowsticf ability rows (#303).
    out = get_usage_stats("Meowstic-F", "abilities")
    assert out["default_source"] == "showdown"
    assert out["default_source_missing"] is True
    assert out["top_ability"]["name"] == "Competitive"
    assert out["top_ability"]["source"] == "ingame"


def test_showdown_everywhere_constant(monkeypatch):
    monkeypatch.setattr(ad, "ABILITY_DEFAULT_SOURCE_MODE", "showdown")
    assert preferred_ability_source("Incineroar") == "showdown"
    assert preferred_ability_source("Annihilape") == "showdown"


def test_flags_off_calc_damage_still_allows_omit(arm):
    """Flags off: no prep gate; PRE-RS-ARM behavior (omit still reaches calc)."""
    set_tool_fields(False)
    state = empty_team()
    _, res = dispatch(
        state,
        arm,
        "calc_damage",
        {
            "attacker": {
                "species": "Annihilape",
                "nature": "Adamant",
                "sp": {"hp": 0, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 0},
            },
            "defender": {
                "species": "Incineroar",
                "nature": "Adamant",
                "ability": "Intimidate",
                "sp": {"hp": 32, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
            },
            "move": "Close Combat",
            "field": {"gameType": "Doubles"},
        },
    )
    assert res.get("status") == "ok"
    assert "ability_source" not in res


def test_flags_off_usage_stats_not_in_schema():
    set_tool_fields(False)
    names = [s["function"]["name"] for s in combined_specs(tool_fields=False)]
    assert "get_usage_stats" not in names


def test_prepare_args_helper_unit():
    args, refusal = prepare_calc_damage_args(
        {
            "attacker": {"species": "Annihilape", "nature": "Adamant"},
            "defender": {"species": "Incineroar", "ability": "Intimidate"},
            "move": "Close Combat",
        }
    )
    assert refusal is not None and refusal["error_kind"] == "missing_ability"
    assert args is None
