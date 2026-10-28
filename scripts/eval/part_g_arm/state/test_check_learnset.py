"""4e check_learnset — Champions learnset only (SC1/SC2)."""

from __future__ import annotations

from scripts.eval.part_g_arm.state.fixtures import empty_team
from scripts.eval.part_g_arm.state.tools import check_learnset, draft_signature


def test_archaludon_learns_snarl():
    st = empty_team()
    before = draft_signature(st)
    r = check_learnset(st, "Archaludon", "Snarl")
    assert r["status"] == "ok" and r["learns"] is True
    assert draft_signature(st) == before


def test_archaludon_does_not_learn_soak():
    st = empty_team()
    r = check_learnset(st, "Archaludon", "Soak")
    assert r["status"] == "ok" and r["learns"] is False


def test_venusaur_learns_sludge_bomb():
    r = check_learnset(empty_team(), "Venusaur", "Sludge Bomb")
    assert r["learns"] is True


def test_unknown_species():
    r = check_learnset(empty_team(), "NotAPokemon", "Tackle")
    assert r["status"] == "not_found" and r["learns"] is False
