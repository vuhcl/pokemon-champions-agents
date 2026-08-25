"""Item 7 Part B: ally-damage risk display note (allAdjacent payoffs)."""

from __future__ import annotations

from recommender.legality import load_snapshot
from recommender.role_compendium_setup_constants import _ALLY_HIT_DAMAGE_MOVE_IDS
from recommender.role_compendium_setup import _ally_damage_risk_note


def test_ally_hit_subset_matches_calc_all_adjacent():
    expected = frozenset(
        {
            "boomburst",
            "brutalswing",
            "bulldoze",
            "discharge",
            "earthquake",
            "explosion",
            "lavaplume",
            "mistyexplosion",
            "paraboliccharge",
            "petalblizzard",
            "selfdestruct",
            "sludgewave",
            "sparklingaria",
            "surf",
        }
    )
    assert _ALLY_HIT_DAMAGE_MOVE_IDS == expected
    assert "rockslide" not in _ALLY_HIT_DAMAGE_MOVE_IDS
    assert "muddywater" not in _ALLY_HIT_DAMAGE_MOVE_IDS
    assert "heatwave" not in _ALLY_HIT_DAMAGE_MOVE_IDS


def test_earthquake_note_lists_ground_protections():
    snap = load_snapshot()
    note = _ally_damage_risk_note(["earthquake"], snap)
    assert note is not None
    assert "Earthquake" in note
    for token in (
        "Flying",
        "Levitate",
        "Earth Eater",
        "Telepathy",
        "Friend Guard",
        "Gravity",
        "Iron Ball",
    ):
        assert token in note, token


def test_surf_note_is_water_not_ground():
    snap = load_snapshot()
    note = _ally_damage_risk_note(["surf"], snap)
    assert note is not None
    assert "Surf" in note
    assert "Water Absorb" in note or "Storm Drain" in note or "Dry Skin" in note
    assert "Levitate" not in note
    assert "Flying-type" not in note
    assert "Telepathy" in note
    assert "Friend Guard" in note


def test_boomburst_note_includes_soundproof_and_ghost():
    snap = load_snapshot()
    note = _ally_damage_risk_note(["boomburst"], snap)
    assert note is not None
    assert "Boomburst" in note
    assert "Soundproof" in note
    assert "Ghost" in note
    assert "Telepathy" in note
    assert "Friend Guard" in note


def test_rockslide_foes_only_no_note():
    snap = load_snapshot()
    assert _ally_damage_risk_note(["rockslide"], snap) is None
    assert _ally_damage_risk_note(["muddywater", "heatwave"], snap) is None
    assert _ally_damage_risk_note([], snap) is None
