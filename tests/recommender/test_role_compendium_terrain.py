"""Terrain setter Role Compendium construction (mirror of weather)."""

from __future__ import annotations

from pathlib import Path

from recommender.ids import to_id
from recommender.legality import load_snapshot
from recommender.role_compendium import (
    ELECTRIC_TERRAIN_SETTER_CRITERIA,
    GRASSY_TERRAIN_SETTER_CRITERIA,
    PSYCHIC_TERRAIN_SETTER_CRITERIA,
    construct_role_category,
    critique_role_ranking,
    legal_species_pool,
)
from recommender.role_compendium_read import load_role_category
from recommender.slot_fill import _compendium_roles_for_need, resolve_need_candidates
from recommender.support_needs import SupportNeed
from recommender.state import RecommenderState


def _draft(criteria: dict, pool: list[str] | None = None):
    snap = load_snapshot()
    return construct_role_category(
        "terrain_setter",
        criteria,
        pool if pool is not None else legal_species_pool(snap),
        snap=snap,
        live_fetch=None,
    )


def _names(draft, tier: str) -> set[str]:
    return {c.species for c in draft.candidates if c.tier == tier}


def test_electric_surge_holders_excellent():
    draft = _draft(ELECTRIC_TERRAIN_SETTER_CRITERIA)
    assert _names(draft, "Excellent") == {"Pincurchin", "Raichu-Mega-X"}
    assert _names(draft, "Good") == set()
    assert critique_role_ranking(draft).approved


def test_grassy_surge_excellent_seed_sower_good():
    draft = _draft(GRASSY_TERRAIN_SETTER_CRITERIA)
    assert _names(draft, "Excellent") == {"Rillaboom"}
    assert _names(draft, "Good") == {"Arboliva"}
    rilla = next(c for c in draft.candidates if c.species == "Rillaboom")
    arbo = next(c for c in draft.candidates if c.species == "Arboliva")
    assert rilla.mechanism == "Grassy Surge"
    assert rilla.excellence_basis == "ability_delivery"
    assert arbo.mechanism == "Seed Sower"
    assert arbo.delivery_class == "ability"
    assert arbo.excellence_basis == "reactive_ability"
    assert critique_role_ranking(draft).approved


def test_psychic_surge_excellent():
    draft = _draft(PSYCHIC_TERRAIN_SETTER_CRITERIA)
    assert {"Indeedee", "Indeedee-F"} <= _names(draft, "Excellent")
    assert critique_role_ranking(draft).approved


def test_whimsicott_grassy_move_rejected_without_usage():
    draft = _draft(GRASSY_TERRAIN_SETTER_CRITERIA)
    members = {c.species for c in draft.candidates if c.tier}
    assert "Whimsicott" not in members
    rej = next(r for r in draft.considered_rejected if r.species == "Whimsicott")
    assert "no usage evidence" in rej.reason


def test_shipped_json_matches_construct():
    for cond, criteria in (
        ("Electric", ELECTRIC_TERRAIN_SETTER_CRITERIA),
        ("Grassy", GRASSY_TERRAIN_SETTER_CRITERIA),
        ("Psychic", PSYCHIC_TERRAIN_SETTER_CRITERIA),
    ):
        draft = _draft(criteria)
        shipped = load_role_category("terrain_setter", cond)
        assert shipped is not None, cond
        assert set(shipped.get("tiers", {}).get("Excellent") or []) == _names(
            draft, "Excellent"
        )
        assert set(shipped.get("tiers", {}).get("Good") or []) == _names(draft, "Good")


def test_compendium_roles_for_need_maps_terrain_labels():
    need = SupportNeed(
        category="condition_setter",
        name="Grassy setter",
        description="Needs Grassy",
        trigger="field_condition:any:grassy",
        notes="Requires Grassy",
    )
    assert _compendium_roles_for_need(need) == [("terrain_setter", "Grassy")]


def test_resolve_grassy_need_prefers_compendium_members():
    need = SupportNeed(
        category="condition_setter",
        name="Grassy setter",
        description="Needs Grassy",
        trigger="field_condition:any:grassy",
        notes="Requires Grassy",
    )
    rows = resolve_need_candidates(need, RecommenderState())
    ids = {to_id(r.species) for r in rows}
    assert {"rillaboom", "arboliva"} <= ids
    assert any("role:grassy_terrain_setter" in (r.evidence[0].evidence or ()) for r in rows)


def test_no_misty_compendium_file():
    assert load_role_category("terrain_setter", "Misty") is None
    misty = Path("data/roles/terrain_setter_misty.v1.json")
    assert not misty.exists()
