"""Screens Support Role Compendium (ADR-019, TW-shaped move-only setter)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from recommender.ability_classification import load_abilities
from recommender.ids import to_id
from recommender.legality import load_snapshot
from recommender.role_compendium import (
    SCREENS_SUPPORT_CRITERIA,
    CandidateEval,
    construct_role_category,
    critique_role_ranking,
    legal_species_pool,
    rebuild_role_category,
    _SCREENS_SPE_FLOOR,
    _screens_learnset_complete,
    _screens_wanted,
)


def _screens_draft(
    *,
    live_fetch: Any = None,
    showdown_fetch: Any = None,
    pool: list[str] | None = None,
) -> Any:
    snap = load_snapshot()
    return construct_role_category(
        "screens_support",
        SCREENS_SUPPORT_CRITERIA,
        pool if pool is not None else legal_species_pool(snap),
        snap=snap,
        live_fetch=live_fetch,
        showdown_fetch=showdown_fetch,
    )


def _members(draft, tier: str) -> set[str]:
    return {c.species for c in draft.candidates if c.tier == tier}


def _find(draft, species_id: str) -> CandidateEval:
    return next(c for c in draft.candidates if c.species_id == species_id)


def test_wanted_threshold_helpers():
    assert _screens_learnset_complete({"auroraveil"})
    assert _screens_learnset_complete({"lightscreen", "reflect"})
    assert not _screens_learnset_complete({"lightscreen"})
    assert _screens_wanted(usage_mids={"auroraveil"}, has_clay=False)
    assert _screens_wanted(usage_mids={"lightscreen", "reflect"}, has_clay=False)
    assert _screens_wanted(usage_mids={"lightscreen"}, has_clay=True)
    assert not _screens_wanted(usage_mids={"lightscreen"}, has_clay=False)


def test_no_ability_sets_screens():
    """Nothing Drizzle-shaped exists for screens, so delivery cannot rank."""
    setters = []
    for aid, entry in (load_abilities().get("abilities") or {}).items():
        desc = str(entry.get("description") or "").lower()
        if "set" in desc and any(
            w in desc for w in ("light screen", "aurora veil")
        ):
            setters.append(aid)
        if "summon" in desc and "reflect" in desc:
            setters.append(aid)
    assert setters == [], setters


def test_delivery_class_identical():
    draft = _screens_draft()
    members = [c for c in draft.candidates if c.tier]
    assert members
    assert {c.delivery_class for c in members} == {"move_screens"}


def test_prankster_dual_screens_excellent():
    draft = _screens_draft()
    assert {"Grimmsnarl", "Sableye"} <= _members(draft, "Excellent"), draft.tiers
    grim = _find(draft, "grimmsnarl")
    assert grim.excellence_basis == "prankster_priority"
    assert grim.reinforce_class == "prankster"
    assert grim.criteria_notes["light_clay"] == "True"


def test_veil_natural_speed_is_good():
    draft = _screens_draft()
    good = _members(draft, "Good")
    assert "Ninetales-Alola" in good or "Froslass-Mega" in good, draft.tiers
    for sid in ("ninetalesalola", "froslassmega"):
        try:
            c = _find(draft, sid)
        except StopIteration:
            continue
        if c.tier == "Good":
            assert int(c.criteria_notes["spe"]) >= _SCREENS_SPE_FLOOR
            assert c.excellence_basis == "natural_speed"
            assert "snow-gated" in c.criteria_notes["execution"]


def test_rotom_wash_light_screen_with_clay_is_admitted():
    """July chaos: Light Screen 3.6% + Light Clay 0.25%."""
    draft = _screens_draft()
    assert "Rotom-Wash" in {c.species for c in draft.candidates if c.tier}


def test_whimsicott_prankster_screen_with_clay_is_excellent():
    """July chaos: Light Screen 2.32% + Light Clay 0.19% + Prankster."""
    draft = _screens_draft()
    whim = _find(draft, "whimsicott")
    assert whim.tier == "Excellent"
    assert whim.excellence_basis == "prankster_priority"
    assert whim.criteria_notes["usage_proven"] == "True"


def test_prankster_dual_usage_proven_is_excellent():
    draft = _screens_draft()
    exc = _members(draft, "Excellent")
    assert {"Grimmsnarl", "Sableye", "Klefki", "Meowstic"} <= exc, draft.tiers
    klef = _find(draft, "klefki")
    assert klef.excellence_basis == "prankster_priority"
    assert klef.criteria_notes["usage_proven"] == "True"


def test_degrees_differ_across_tiers():
    draft = _screens_draft()
    by_tier: dict[str, set[tuple[str, str, str]]] = {}
    for c in draft.candidates:
        if not c.tier:
            continue
        key = (c.delivery_class, c.reinforce_class or "", c.excellence_basis or "")
        by_tier.setdefault(c.tier, set()).add(key)
    tiers = list(by_tier)
    for i, a in enumerate(tiers):
        for b in tiers[i + 1 :]:
            assert not (by_tier[a] & by_tier[b]), (a, b, by_tier[a] & by_tier[b])


def test_critique_approves():
    draft = _screens_draft()
    result = critique_role_ranking(draft)
    assert result.approved, result.flags


def test_rebuild_tmp(tmp_path: Path):
    r = rebuild_role_category(
        "screens_support",
        SCREENS_SUPPORT_CRITERIA,
        roles_dir=tmp_path,
        live_fetch=lambda n: {
            "name": n,
            "id": to_id(n),
            "common_moves": [
                {"name": "Light Screen", "pct": 40},
                {"name": "Reflect", "pct": 40},
            ],
            "common_items": [{"name": "Light Clay", "pct": 50}],
        }
        if to_id(n) == "grimmsnarl"
        else None,
        showdown_fetch=lambda _n: None,
    )
    assert r.status == "approved", r.critique.flags
    assert Path(r.path or "").exists()
