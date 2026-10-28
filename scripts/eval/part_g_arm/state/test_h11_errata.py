"""H11 set-answer errata: Gyarados-Mega allowed_not_required (no key/tool edit)."""

from scripts.eval.part_g_arm.state.errata_read import (
    allowed_not_required,
    set_answer_errata,
    set_answer_hand_note,
)
from scripts.eval.part_g_arm.state.fixtures import empty_team
from scripts.eval.part_g_arm.state.hand_audit_form import (
    _points_with_set_errata,
    split_acceptance_points,
)
from scripts.eval.part_g_arm.state.tools import check_learnset, find_species


def test_h11_errata_effective():
    e = set_answer_errata("H11")
    assert e is not None
    assert e["scoring_rule"] == "allowed_not_required"
    assert allowed_not_required("H11") == {"Gyarados-Mega"}
    assert "Gyarados-Mega" in (set_answer_hand_note("H11") or "")


def test_find_species_unchanged_includes_gyarados_mega():
    r = find_species(empty_team(), types=["Water"], learns_move="Hurricane")
    assert set(r["species"]) == {"Gyarados", "Gyarados-Mega", "Pelipper", "Quaquaval"}


def test_check_learnset_gyarados_mega_hurricane_true():
    r = check_learnset(empty_team(), "Gyarados-Mega", "Hurricane")
    assert r["learns"] is True


def test_hand_audit_gains_allowed_not_required_point():
    pts = _points_with_set_errata("H11", split_acceptance_points("a; b"))
    assert any(p["id"] == "set_errata_allowed_not_required" for p in pts)
