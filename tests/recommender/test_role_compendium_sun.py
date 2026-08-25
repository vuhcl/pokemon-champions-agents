"""Sun Setter Role Compendium construction / critic pipeline (ADR-019)."""

from __future__ import annotations

from recommender.ids import to_id
from recommender.legality import load_snapshot
from recommender.role_compendium import SUN_SETTER_CRITERIA, construct_role_category, critique_role_ranking, legal_species_pool


def _sun_draft(pool: list[str] | None = None, showdown_fetch=None):
    snap = load_snapshot()
    return construct_role_category(
        "weather_setter",
        SUN_SETTER_CRITERIA,
        pool if pool is not None else legal_species_pool(snap),
        snap=snap,
        live_fetch=None,
        showdown_fetch=showdown_fetch,
    )


def _members(draft, tier: str) -> set[str]:
    return {c.species for c in draft.candidates if c.tier == tier}


def test_sun_excellent_ability_setters():
    draft = _sun_draft()
    excellent = _members(draft, "Excellent")
    assert {"Charizard-Mega-Y", "Ninetales", "Torkoal"} <= excellent, draft.tiers
    assert "Charizard" not in excellent
    assert all(
        c.delivery_class == "ability"
        for c in draft.candidates
        if c.species in ("Charizard-Mega-Y", "Ninetales", "Torkoal")
    )


def test_sun_base_charizard_not_drought_admitted():
    draft = _sun_draft()
    members = {c.species for c in draft.candidates if c.tier}
    assert "Charizard" not in members


def test_sun_prankster_sunny_day_rejected_without_usage():
    draft = _sun_draft()
    rejected = {r.species_id for r in draft.considered_rejected}
    # Banette-Mega: learnset-only without offline CBD Sunny Day %.
    assert "banettemega" in rejected, draft.considered_rejected
    banette = next(r for r in draft.considered_rejected if r.species_id == "banettemega")
    assert "no usage evidence" in banette.reason


def test_sun_legal_pool_bounds():
    snap = load_snapshot()
    pool = [n for n in legal_species_pool(snap) if to_id(n) != "torkoal"]
    draft = _sun_draft(pool=pool)
    assert "Torkoal" not in _members(draft, "Excellent")
    assert "Ninetales" in _members(draft, "Excellent")


def test_sun_critique_approves():
    draft = _sun_draft()
    result = critique_role_ranking(draft)
    assert result.approved, result.flags
