"""Sand Setter Role Compendium construction / critic pipeline (ADR-019)."""

from __future__ import annotations

from recommender.ids import to_id
from recommender.legality import load_snapshot
from recommender.role_compendium import (
    SAND_SETTER_CRITERIA,
    construct_role_category,
    critique_role_ranking,
    legal_species_pool,
)


def _sand_draft(pool: list[str] | None = None, showdown_fetch=...):
    snap = load_snapshot()
    kwargs = {
        "category": "weather_setter",
        "sub_criteria": SAND_SETTER_CRITERIA,
        "legal_pool": pool if pool is not None else legal_species_pool(snap),
        "snap": snap,
        "live_fetch": None,
    }
    if showdown_fetch is not ...:
        kwargs["showdown_fetch"] = showdown_fetch
    return construct_role_category(**kwargs)


def _members(draft, tier: str) -> set[str]:
    return {c.species for c in draft.candidates if c.tier == tier}


def test_sand_excellent_includes_tyranitar_pair_and_hippowdon():
    def sd_fetch(name: str):
        sid = to_id(name)
        if sid == "tyranitarmega":
            return {
                "name": "Tyranitar-Mega",
                "id": "tyranitarmega",
                "usage_pct": 3.602,
                "common_moves": [],
                "source": "munchstats-showdown",
            }
        if sid == "tyranitar":
            return {
                "name": "Tyranitar",
                "id": "tyranitar",
                "usage_pct": 1.759,
                "common_moves": [],
                "source": "munchstats-showdown",
            }
        return None

    draft = _sand_draft(showdown_fetch=sd_fetch)
    excellent = _members(draft, "Excellent")
    assert {"Tyranitar", "Tyranitar-Mega", "Hippowdon"} <= excellent, draft.tiers
    # Ratio 1.759/3.602 ≈ 0.49 ≥ 0.25 → both kept (not Scovillain-shaped).
    rejected_ids = {r.species_id for r in draft.considered_rejected}
    assert "tyranitar" not in rejected_ids
    assert any("both kept" in n for n in draft.notes)


def test_sand_discount_artifact_base(monkeypatch):
    monkeypatch.setattr("recommender.role_compendium.showdown_species_map", lambda: {})
    monkeypatch.setattr("recommender.role_compendium_usage.showdown_species_map", lambda: {})

    def sd_fetch(name: str):
        sid = to_id(name)
        if sid == "tyranitarmega":
            return {"name": "Tyranitar-Mega", "id": sid, "usage_pct": 4.0}
        if sid == "tyranitar":
            return {"name": "Tyranitar", "id": sid, "usage_pct": 0.5}  # < 0.25×4
        return None

    draft = _sand_draft(showdown_fetch=sd_fetch)
    assert "Tyranitar-Mega" in _members(draft, "Excellent")
    assert "Tyranitar" in _members(draft, "Acceptable")
    assert "Tyranitar" not in _members(draft, "Excellent")
    ttar = next(c for c in draft.candidates if c.species_id == "tyranitar")
    assert ttar.excellence_basis == "usage_discounted"
    assert ttar.criteria_notes.get("usage_proven") == "False"
    assert not any(r.species_id == "tyranitar" for r in draft.considered_rejected)


def test_sand_prankster_sandstorm_usage_proven_is_good():
    """July chaos: Klefki Sandstorm r11 / 4.0% + Prankster."""
    draft = _sand_draft(showdown_fetch=None)
    assert "Klefki" in _members(draft, "Good")
    klef = next(c for c in draft.candidates if c.species_id == "klefki")
    assert klef.criteria_notes.get("usage_proven") == "True"


def test_sand_critique_approves_with_independent_tyranitar():
    def sd_fetch(name: str):
        sid = to_id(name)
        if sid == "tyranitarmega":
            return {"name": "Tyranitar-Mega", "id": sid, "usage_pct": 3.602}
        if sid == "tyranitar":
            return {"name": "Tyranitar", "id": sid, "usage_pct": 1.759}
        return None

    draft = _sand_draft(showdown_fetch=sd_fetch)
    result = critique_role_ranking(draft)
    assert result.approved, result.flags
