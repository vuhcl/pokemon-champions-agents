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


# --- #372 -------------------------------------------------------------------


def test_372_edit_moveset_returns_value_from_state_when_flag_on():
    _enable_fixes()
    st = _tb2_partly_locked()
    legal = ["Flare Blitz", "Fake Out", "Parting Shot", "Will-O-Wisp"]
    after, res = edit_slot_field(st, 1, "moveset", legal)
    assert res.get("ok") is True
    assert res.get("value") == legal
    assert res["slot_after"]["moveset"] == after["team_draft"][0].moveset.value


def test_372_flag_off_edit_has_no_value_field():
    st = _tb2_partly_locked()
    legal = ["Flare Blitz", "Fake Out", "Parting Shot", "Will-O-Wisp"]
    _after, res = edit_slot_field(st, 1, "moveset", legal)
    assert "value" not in res
    assert "slot_after" not in res


# --- #364 -------------------------------------------------------------------


def test_364_find_species_competitive_omits_meowstic_f_when_flag_off():
    st = empty_team()
    res = find_species(st, ability="Competitive")
    names = {s if isinstance(s, str) else s.get("name") for s in (res.get("species") or [])}
    # result may be list of names or dicts
    flat = set()
    for s in res.get("species") or []:
        flat.add(s if isinstance(s, str) else (s.get("name") or s.get("species")))
    assert "Meowstic-F" not in flat


def test_364_find_species_competitive_includes_meowstic_f_when_flag_on():
    _enable_fixes()
    st = empty_team()
    res = find_species(st, ability="Competitive")
    flat = set()
    for s in res.get("species") or []:
        flat.add(s if isinstance(s, str) else (s.get("name") or s.get("species")))
    assert "Meowstic-F" in flat


def test_364_join_ts_six_predicate_matrix():
    from recommender.legality import load_snapshot
    from recommender.regulation_registry import active_regulation
    from recommender.slot_fill import (
        JOIN_TS_UNLISTED_OTHER_FORMES,
        _is_battle_only_transient_forme,
        set_keep_join_ts_unlisted_formes,
    )

    snap = load_snapshot()
    reg = active_regulation()
    set_keep_join_ts_unlisted_formes(False)
    off = {
        sid: _is_battle_only_transient_forme(sid, snap["species"][sid], reg)
        for sid in JOIN_TS_UNLISTED_OTHER_FORMES
    }
    set_keep_join_ts_unlisted_formes(True)
    on = {
        sid: _is_battle_only_transient_forme(sid, snap["species"][sid], reg)
        for sid in JOIN_TS_UNLISTED_OTHER_FORMES
    }
    set_keep_join_ts_unlisted_formes(False)
    assert all(off.values()), off  # heuristic still True without flag
    assert not any(on.values()), on  # flag clears all six
    # Castform weather still battle-only under flag
    set_keep_join_ts_unlisted_formes(True)
    assert _is_battle_only_transient_forme(
        "castformsunny", snap["species"]["castformsunny"], reg
    )
    set_keep_join_ts_unlisted_formes(False)


# --- #370 -------------------------------------------------------------------


def test_370_change_archetype_case_insensitive_when_flag_on():
    from scripts.eval.part_g_arm.state.pending import build_fully_locked_slot
    from scripts.eval.part_g_arm.state.tools import change_archetype

    _enable_fixes()
    st = build_fully_locked_slot("Pelipper", user_slot=1)
    _a1, r1 = change_archetype(st, ["rain", "offense"])
    _a2, r2 = change_archetype(st, ["Rain", "Offense"])
    assert r1.get("ok") and r2.get("ok")
    assert r1.get("pending_flags") == r2.get("pending_flags")
    assert r1.get("conflicts") == r2.get("conflicts")


# --- #371 -------------------------------------------------------------------


def test_371_pending_flags_carry_advisory_fields_when_flag_on():
    from scripts.eval.part_g_arm.state.tools import apply_mismatch_flag_kinds

    kinds = apply_mismatch_flag_kinds()
    assert kinds == {
        "flag_exempt_conflict",
        "judgment_mismatch",
        "sibling_mismatch",
        "severity_mismatch",
        "theme_mismatch",
    }


# --- item 7 calc_damage -----------------------------------------------------


def test_7a_calc_damage_requires_ability_when_flag_on():
    from recommender.arm_tools import ArmTools
    from recommender.calc_client import CalcClient
    from scripts.eval.part_g_arm.state.harness import dispatch

    _enable_fixes()
    arm = ArmTools(regulation="champions", allow_live=False, calc=CalcClient())
    st = empty_team()
    _after, res = dispatch(
        st,
        arm,
        "calc_damage",
        {
            "attacker": {"species": "Garchomp", "move": "Earthquake"},
            "defender": {"species": "Toxapex", "ability": "Regenerator"},
        },
    )
    assert res.get("error_kind") == "bad_arguments"
    assert res.get("field") == "attacker.ability"


def test_7b_sturdy_gets_calc_limitation():
    from recommender.arm_tools import ArmTools
    from recommender.calc_client import CalcClient
    from scripts.eval.part_g_arm.state.harness import dispatch

    _enable_fixes()
    arm = ArmTools(regulation="champions", allow_live=False, calc=CalcClient())
    st = empty_team()
    _after, res = dispatch(
        st,
        arm,
        "calc_damage",
        {
            "attacker": {
                "species": "Garchomp",
                "ability": "Rough Skin",
                "move": "Earthquake",
            },
            "defender": {"species": "Avalugg", "ability": "Sturdy"},
        },
    )
    assert "calc_limitation" in res
    assert "Sturdy" in res["calc_limitation"]


# --- item 8 hypothetical ----------------------------------------------------


def test_8_hypothetical_messages_do_not_claim_live_lock_when_flag_on():
    from scripts.eval.part_g_arm.state.tools import check_hypothetical

    _enable_fixes()
    st = empty_team()
    res = check_hypothetical(
        st,
        [
            {"species": "Garchomp", "item": "Choice Scarf"},
            {"species": "Jolteon", "item": "Choice Scarf"},
        ],
    )
    assert res.get("verdict") == "item_clause"
    assert res.get("hypothetical") is True
    assert res.get("applies_to_team") is False
    assert "Hypothetical only" in (res.get("message") or "")

    res2 = check_hypothetical(st, [{"species": "Water type"}])
    assert res2.get("verdict") == "unknown_species"
    assert "can't lock" not in (res2.get("message") or "").lower()
    assert "hypothetical" in (res2.get("message") or "").lower()
