"""find_species — read-only legal species filters (H11 / HU1 / H19 / Prankster)."""

from __future__ import annotations

from scripts.eval.part_g_arm.state.fixtures import empty_team
from scripts.eval.part_g_arm.state.tools import draft_signature, find_species


def test_water_hurricane_includes_h11_core():
    st = empty_team()
    before = draft_signature(st)
    r = find_species(st, types=["Water"], learns_move="Hurricane")
    assert r["status"] == "ok"
    names = set(r["species"])
    assert {"Gyarados", "Pelipper", "Quaquaval"} <= names
    assert "Gyarados-Mega" in names  # include_formes default true
    assert draft_signature(st) == before


def test_water_hurricane_exclude_mega():
    r = find_species(empty_team(), types=["Water"], learns_move="Hurricane", include_formes=False)
    assert "Gyarados-Mega" not in r["species"]
    assert "Gyarados" in r["species"]


def test_fire_bulk_hu1_shape():
    r = find_species(
        empty_team(),
        types=["Fire"],
        stat_formula={"expr": "2*hp+def+spd", "op": ">=", "value": 350},
        include_formes=False,
    )
    assert r["status"] == "ok"
    names = set(r["species"])
    # Request-set HU1 membership (non-Mega); Arcanine-Hisui is a regional, not Mega.
    for want in ("Skeledirge", "Incineroar", "Arcanine-Hisui", "Armarouge", "Emboar", "Torkoal"):
        assert want in names, want
    assert not any("-Mega" in n for n in names)


def test_trick_room_learners_nonempty():
    r = find_species(empty_team(), learns_move="Trick Room")
    assert r["status"] == "ok" and r["count"] > 0


def test_prankster_sunny_day_subset():
    r = find_species(empty_team(), ability="Prankster", learns_move="Sunny Day")
    assert r["status"] == "ok" and r["count"] >= 1
    assert "Whimsicott" in r["species"] or "Sableye" in r["species"]


def test_no_filters_errors():
    r = find_species(empty_team())
    assert r["status"] == "error" and r["species"] == []


def test_bad_stat_formula_errors():
    r = find_species(
        empty_team(),
        types=["Fire"],
        stat_formula={"expr": "hp/spd", "op": ">=", "value": 1},
    )
    assert r["status"] == "error"
