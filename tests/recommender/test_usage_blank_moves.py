"""Blank chaos move names must not occupy a stamped kit slot."""

from __future__ import annotations

from recommender.coverage import get_relevant_threats
from recommender.ids import to_id
from recommender.usage_data import (
    _nonempty_moves,
    featured_or_common_set,
    set_from_showdown,
)

_KANGASKHAN_FOUR = ["Fake Out", "Last Resort", "Double-Edge", "Sucker Punch"]


def test_nonempty_moves_skips_leading_blank_and_backfills():
    names = ["", "Fake Out", "Last Resort", "Double-Edge", "Sucker Punch"]
    assert _nonempty_moves(names) == _KANGASKHAN_FOUR
    assert "" not in _nonempty_moves(names)


def test_nonempty_moves_skips_late_blank_like_mega_staraptor_mawile():
    names = [
        "Fake Out",
        "Sucker Punch",
        "Power-Up Punch",
        "Double-Edge",
        "Crunch",
        "Earthquake",
        "",
        "Protect",
    ]
    out = _nonempty_moves(names)
    assert len(out) == 4
    assert "" not in out
    assert out == ["Fake Out", "Sucker Punch", "Power-Up Punch", "Double-Edge"]


def test_kangaskhan_stamps_four_real_moves():
    for built in (
        set_from_showdown("kangaskhan"),
        featured_or_common_set("kangaskhan"),
    ):
        assert built is not None
        assert "" not in built["moves"]
        assert len(built["moves"]) == 4
        assert built["moves"][0] == "Fake Out"


def test_showdown_species_with_late_blanks_stamp_four_real_moves():
    for sid in ("kangaskhanmega", "staraptor", "mawilemega"):
        built = set_from_showdown(sid)
        assert built is not None, sid
        assert "" not in built["moves"], sid
        assert len(built["moves"]) == 4, sid


def test_relevant_threats_kangaskhan_has_no_blank_move():
    threats = get_relevant_threats({"regulation_mod": "champions"})
    kangs = [t for t in threats if to_id(t.spec["species"]) == "kangaskhan"]
    assert kangs
    for t in kangs:
        assert "" not in (t.spec.get("moves") or [])
        assert len(t.spec.get("moves") or []) == 4
