"""FU70 tool_fixes_v2: each fix gated; flag default off reproduces a393ae91."""

from __future__ import annotations

from dataclasses import replace

import pytest

from recommender.state import Attr, all_locked
from scripts.eval.part_g_arm.state.fixtures import empty_team
from scripts.eval.part_g_arm.state.tools import (
    edit_slot_field,
    find_species,
    set_draft,
    set_tool_fields,
    set_tool_fixes_v2,
    set_wrapper,
    tool_fixes_v2_enabled,
)


TB2_ILLEGAL_MOVESET = ["Flare Blitz", "Knock Off", "U-turn", "Protect"]


@pytest.fixture(autouse=True)
def _flags_off():
    set_tool_fields(False)
    set_wrapper(False)
    set_draft(False)
    set_tool_fixes_v2(False)
    yield
    set_tool_fields(False)
    set_wrapper(False)
    set_draft(False)
    set_tool_fixes_v2(False)


def _enable_fixes(*, draft: bool = False) -> None:
    set_tool_fixes_v2(True)
    if draft:
        set_tool_fields(True)
        set_wrapper(True)
        set_draft(True)


def _tb2_partly_locked() -> dict:
    """TB2 Incineroar: species/ability/item/moveset/nature locked; role+spread open."""
    st = empty_team()
    st["team_draft"][0] = replace(
        st["team_draft"][0],
        species=Attr("Incineroar", locked=True),
        ability=Attr("Intimidate", locked=True),
        item=Attr("Charcoal", locked=True),
        moveset=Attr(["Flare Blitz", "Fake Out", "Parting Shot", "Will-O-Wisp"], locked=True),
        nature=Attr("Adamant", locked=True),
        # role + spread remain unlocked → all_locked False
    )
    assert not all_locked(st["team_draft"][0])
    return st


def _fully_locked_incineroar() -> dict:
    st = _tb2_partly_locked()
    st["team_draft"][0] = replace(
        st["team_draft"][0],
        role=Attr("standard_physical_attacker", locked=True),
        spread=Attr(
            {"hp": 0, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 0},
            locked=True,
        ),
    )
    assert all_locked(st["team_draft"][0])
    return st


# --- #369 -------------------------------------------------------------------


def test_flag_defaults_off():
    assert tool_fixes_v2_enabled() is False


def test_369_partly_locked_moveset_accepted_when_flag_off():
    """a393ae91: partly locked path skips check_set → illegal moveset ok."""
    st = _tb2_partly_locked()
    after, res = edit_slot_field(st, 1, "moveset", TB2_ILLEGAL_MOVESET)
    assert res.get("ok") is True
    assert after["team_draft"][0].moveset.value == TB2_ILLEGAL_MOVESET


def test_369_fully_locked_moveset_refused_learnset_message():
    st = _fully_locked_incineroar()
    before = list(st["team_draft"][0].moveset.value)
    after, res = edit_slot_field(st, 1, "moveset", TB2_ILLEGAL_MOVESET)
    assert res.get("ok") is not True
    err = str(res.get("slot_commit_error") or res)
    assert "learnset:Knock Off" in err
    assert "learnset:U-turn" in err
    assert after["team_draft"][0].moveset.value == before


def test_369_partly_locked_moveset_refused_when_flag_on():
    _enable_fixes()
    st = _tb2_partly_locked()
    before = list(st["team_draft"][0].moveset.value)
    after, res = edit_slot_field(st, 1, "moveset", TB2_ILLEGAL_MOVESET)
    assert res.get("ok") is not True
    err = str(res.get("slot_commit_error") or res)
    assert "learnset:Knock Off" in err
    assert "learnset:U-turn" in err
    assert after["team_draft"][0].moveset.value == before


def test_369_draft_set_slot_refuses_illegal_moveset_when_flag_on():
    from recommender.arm_tools import ArmTools
    from recommender.calc_client import CalcClient
    from scripts.eval.part_g_arm.state.harness import dispatch

    _enable_fixes(draft=True)
    st = empty_team()
    arm = ArmTools(regulation="champions", allow_live=False, calc=CalcClient())
    after, res = dispatch(
        st,
        arm,
        "set_slot",
        {
            "slot": 1,
            "species": "Incineroar",
            "item": "Charcoal",
            "moves": TB2_ILLEGAL_MOVESET,
        },
    )
    assert res.get("ok") is not True
    err = str(res.get("slot_commit_error") or res)
    assert "learnset:Knock Off" in err
    assert "learnset:U-turn" in err
    assert after["team_draft"][0].moveset.value is None


# --- #384 -------------------------------------------------------------------


def test_384_mega_plus_stone_refused_when_flag_off():
    from scripts.eval.part_g_arm.state.set_slot_tool import set_slot

    set_tool_fields(True)
    set_wrapper(True)
    st = empty_team()
    _after, res = set_slot(
        st, {"slot": 1, "species": "Salamence-Mega", "item": "Salamencite"}
    )
    assert res.get("ok") is False
    assert "Mega forme must hold Salamencite" in (res.get("slot_commit_error") or "")


def test_384_mega_plus_stone_accepted_when_flag_on():
    from scripts.eval.part_g_arm.state.set_slot_tool import set_slot

    _enable_fixes()
    set_tool_fields(True)
    set_wrapper(True)
    st = empty_team()
    after, res = set_slot(
        st, {"slot": 1, "species": "Salamence-Mega", "item": "Salamencite"}
    )
    assert res.get("ok") is True, res
    assert after["team_draft"][0].species.value == "Salamence-Mega"
    assert after["team_draft"][0].item.value == "Salamencite"


def test_384_mega_alone_and_wrong_item_still_mega_stone_refusal():
    from scripts.eval.part_g_arm.state.set_slot_tool import set_slot

    _enable_fixes()
    set_tool_fields(True)
    set_wrapper(True)
    for kwargs in (
        {"slot": 1, "species": "Salamence-Mega"},
        {"slot": 1, "species": "Salamence-Mega", "item": "Leftovers"},
    ):
        st = empty_team()
        _after, res = set_slot(st, kwargs)
        assert res.get("ok") is False, kwargs
        assert "Mega forme must hold Salamencite" in (res.get("slot_commit_error") or "")
