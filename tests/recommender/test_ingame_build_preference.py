"""Default build synthesis prefers in-game CBD over Showdown when both exist."""

from __future__ import annotations

from recommender.anchor_roles import classify_anchor_role, resolve_anchor_build
from recommender.ids import to_id
from recommender.usage_data import (
    featured_or_common_set,
    pick_team_aware_usage_item,
    set_from_ingame,
    set_from_showdown,
)


def test_klefki_default_is_screens_build_from_ingame():
    built = featured_or_common_set("Klefki", regulation="champions-reg-mb")
    assert built is not None
    move_ids = {to_id(m) for m in built["moves"]}
    assert "lightscreen" in move_ids
    assert "reflect" in move_ids
    assert to_id(built["item"]) == "lightclay"
    role = classify_anchor_role(
        resolve_anchor_build(
            "Klefki",
            provisional={
                "moves": built["moves"],
                "item": built["item"],
                "ability": built.get("ability"),
            },
            regulation="champions-reg-mb",
        )
    ).role_id
    assert role == "screens_support"


def test_klefki_item_pick_uses_ingame_ranking():
    item = pick_team_aware_usage_item(
        "Klefki", regulation="champions-reg-mb", used=set()
    )
    assert item is not None
    assert to_id(item) == "lightclay"


def test_pelipper_moves_unchanged_when_sources_agree():
    built = featured_or_common_set("Pelipper", regulation="champions-reg-mb")
    assert built is not None
    assert {to_id(m) for m in built["moves"]} == {
        "hurricane",
        "tailwind",
        "weatherball",
        "wideguard",
    }


def test_mega_capable_charizard_still_showdown_sourced():
    assert set_from_ingame("Charizard") is None
    built = featured_or_common_set("Charizard", regulation="champions-reg-mb")
    sd = set_from_showdown("Charizard", regulation="champions-reg-mb")
    assert built is not None and sd is not None
    assert {to_id(m) for m in built["moves"]} == {to_id(m) for m in sd["moves"]}


def test_showdown_only_maushold_unchanged():
    built = featured_or_common_set("Maushold", regulation="champions-reg-mb")
    sd = set_from_showdown("Maushold", regulation="champions-reg-mb")
    assert built is not None and sd is not None
    assert {to_id(m) for m in built["moves"]} == {to_id(m) for m in sd["moves"]}
