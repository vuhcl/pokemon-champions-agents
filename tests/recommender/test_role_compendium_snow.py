"""Snow Setter Role Compendium construction / critic pipeline (ADR-019)."""

from __future__ import annotations

from recommender.ids import to_id
from recommender.legality import load_snapshot
from recommender.role_compendium import SNOW_SETTER_CRITERIA, construct_role_category, critique_role_ranking, legal_species_pool


def _snow_draft(pool: list[str] | None = None, showdown_fetch=None):
    snap = load_snapshot()
    return construct_role_category(
        "weather_setter",
        SNOW_SETTER_CRITERIA,
        pool if pool is not None else legal_species_pool(snap),
        snap=snap,
        live_fetch=None,
        showdown_fetch=showdown_fetch,
    )


def _members(draft, tier: str) -> set[str]:
    return {c.species for c in draft.candidates if c.tier == tier}


def test_snow_excellent_ability_setters():
    draft = _snow_draft()
    excellent = _members(draft, "Excellent")
    # Core ability setters (base Abomasnow may be Showdown-discounted when offline map has pair %).
    assert {
        "Abomasnow-Mega",
        "Aurorus",
        "Froslass-Mega",
        "Ninetales-Alola",
        "Vanilluxe",
    } <= excellent, draft.tiers
    assert "Froslass" not in excellent  # base lacks Snow Warning


def test_snow_legal_pool_bounds():
    snap = load_snapshot()
    pool = [n for n in legal_species_pool(snap) if to_id(n) != "ninetalesalola"]
    draft = _snow_draft(pool=pool)
    assert "Ninetales-Alola" not in _members(draft, "Excellent")
    # Base Abomasnow may be Excellent or Acceptable (Showdown mega-pair discount).
    assert "Abomasnow" in (
        _members(draft, "Excellent") | _members(draft, "Acceptable")
    )


def test_snow_critique_approves():
    draft = _snow_draft()
    result = critique_role_ranking(draft)
    assert result.approved, result.flags


def test_snow_abomasnow_discounted_acceptable(monkeypatch):
    monkeypatch.setattr(
        "recommender.role_compendium.showdown_species_map", lambda: {}
    )

    def sd_fetch(name: str):
        sid = to_id(name)
        if sid == "abomasnowmega":
            return {"name": "Abomasnow-Mega", "id": sid, "usage_pct": 0.525}
        if sid == "abomasnow":
            return {"name": "Abomasnow", "id": sid, "usage_pct": 0.083}
        return None

    draft = _snow_draft(showdown_fetch=sd_fetch)
    assert "Abomasnow-Mega" in _members(draft, "Excellent")
    assert "Abomasnow" in _members(draft, "Acceptable")
    assert "Abomasnow" not in _members(draft, "Excellent")
    abo = next(c for c in draft.candidates if c.species_id == "abomasnow")
    assert abo.excellence_basis == "usage_discounted"
    result = critique_role_ranking(draft)
    assert result.approved, result.flags
