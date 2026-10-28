"""4h — get_move_static returns priority from data/moves/static.v1.json (MV1)."""

from __future__ import annotations

from recommender.arm_tools import ArmTools

from scripts.eval.part_g_arm.state.harness import dispatch
from scripts.eval.part_g_arm.state.fixtures import empty_team
from scripts.eval.part_g_arm.state.tools import with_move_priority


def _arm() -> ArmTools:
    return ArmTools(regulation="champions", allow_live=False)


def test_follow_me_priority_is_2():
    """MV1: Follow Me priority = 2 in Champions static."""
    st = empty_team()
    _, r = dispatch(st, _arm(), "get_move_static", {"move": "Follow Me"})
    assert r["status"] == "ok"
    assert r["priority"] == 2
    assert r["move"] == "Follow Me"


def test_extreme_speed_priority_is_2():
    st = empty_team()
    _, r = dispatch(st, _arm(), "get_move_static", {"move": "Extreme Speed"})
    assert r["status"] == "ok" and r["priority"] == 2


def test_aqua_jet_priority_is_1():
    st = empty_team()
    _, r = dispatch(st, _arm(), "get_move_static", {"move": "Aqua Jet"})
    assert r["status"] == "ok" and r["priority"] == 1


def test_raw_arm_omits_priority_enrichment_adds_it():
    raw = _arm().get_move_static("Follow Me")
    assert "priority" not in raw
    enriched = with_move_priority(raw)
    assert enriched["priority"] == 2


def test_not_found_unchanged():
    st = empty_team()
    _, r = dispatch(st, _arm(), "get_move_static", {"move": "NotARealMoveXYZ"})
    assert r["status"] == "not_found"
    assert "priority" not in r
