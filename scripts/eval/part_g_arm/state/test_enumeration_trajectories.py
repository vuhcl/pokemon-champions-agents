"""Scripted find_species trajectories for H11 / H19 / H20 / HU1 (no model)."""

from __future__ import annotations

from scripts.eval.part_g_arm.state.fixtures import empty_team
from scripts.eval.part_g_arm.state.tools import find_species


def test_h11_water_hurricane_includes_core_and_reports_castform_drift():
    r = find_species(empty_team(), types=["Water"], learns_move="Hurricane")
    assert r["status"] == "ok"
    names = set(r["species"])
    # Acceptance core (request-set); Mega = deliberate FP in acceptance note.
    assert {"Gyarados", "Pelipper", "Quaquaval"} <= names
    assert "Gyarados-Mega" in names
    # Freeze finding: Castform-Rainy is legal Water+Hurricane but not in acceptance set.
    assert "Castform-Rainy" in names


def test_h19_trick_room_learners_nonempty():
    r = find_species(empty_team(), learns_move="Trick Room")
    assert r["status"] == "ok" and r["count"] > 0
    # Learnset half only — compendium-role TR setters stay hand/checklist.


def test_h20_monotype_water_pool_nonempty():
    r = find_species(empty_team(), types=["Water"], include_formes=False)
    assert r["status"] == "ok" and r["count"] > 0
    # Pool only — ranked offers still need show_candidates.


def test_hu1_fire_bulk_membership():
    r = find_species(
        empty_team(),
        types=["Fire"],
        stat_formula={"expr": "2*hp+def+spd", "op": ">=", "value": 350},
        include_formes=False,
    )
    assert r["status"] == "ok"
    names = set(r["species"])
    for want in ("Skeledirge", "Incineroar", "Arcanine-Hisui", "Armarouge", "Emboar", "Torkoal"):
        assert want in names, want
    assert not any("-Mega" in n for n in names)
