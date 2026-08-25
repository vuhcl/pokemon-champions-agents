"""Screens Support Role Compendium — dual/Prankster/2.3% redesign."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from recommender.ability_classification import load_abilities
from recommender.ids import to_id
from recommender.legality import load_snapshot
from recommender.role_compendium_support import _screens_mech_dual
from recommender.role_compendium import SCREENS_SUPPORT_CRITERIA, CandidateEval, construct_role_category, critique_role_ranking, legal_species_pool, rebuild_role_category, _SCREENS_SPE_FLOOR, _USAGE_SET_PCT_FLOOR


LOCKED_EXCELLENT = {"Grimmsnarl", "Klefki", "Meowstic", "Sableye"}
LOCKED_GOOD = {"Dragapult", "Serperior", "Ninetales-Alola", "Froslass-Mega"}
LOCKED_ACCEPTABLE = {
    "Whimsicott",
    "Abomasnow",
    "Abomasnow-Mega",
    "Aurorus",
    "Vanilluxe",
}
LOCKED_EXCLUDED = {
    "Florges",
    "Avalugg",
    "Gardevoir-Mega",
    "Gardevoir",
    "Alakazam",
    "Espeon",
    "Musharna",
    "Rotom-Wash",
    "Meowstic-M-Mega",
}


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


def test_mech_dual_requires_snow_warning_for_veil():
    assert _screens_mech_dual({"lightscreen", "reflect"}, {})
    assert _screens_mech_dual({"auroraveil"}, {"snowwarning": "Snow Warning"})
    assert not _screens_mech_dual({"auroraveil"}, {})
    assert not _screens_mech_dual({"lightscreen"}, {"prankster": "Prankster"})
    assert _USAGE_SET_PCT_FLOOR == 2.3


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


def test_locked_13_tiers():
    draft = _screens_draft()
    assert _members(draft, "Excellent") == LOCKED_EXCELLENT, draft.tiers
    assert _members(draft, "Good") == LOCKED_GOOD, draft.tiers
    assert _members(draft, "Acceptable") == LOCKED_ACCEPTABLE, draft.tiers
    admitted = {c.species for c in draft.candidates if c.tier}
    assert admitted & LOCKED_EXCLUDED == set(), admitted & LOCKED_EXCLUDED
    assert "Meowstic-F" not in admitted


def test_prankster_dual_screens_excellent():
    draft = _screens_draft()
    grim = _find(draft, "grimmsnarl")
    assert grim.excellence_basis == "prankster_priority"
    assert grim.reinforce_class == "prankster"


def test_veil_natural_speed_is_good():
    draft = _screens_draft()
    for sid in ("ninetalesalola", "froslassmega"):
        c = _find(draft, sid)
        assert c.tier == "Good"
        assert int(c.criteria_notes["spe"]) >= _SCREENS_SPE_FLOOR
        assert c.excellence_basis == "natural_speed"
        assert "Snow Warning" in c.criteria_notes["execution"]


def test_rotom_wash_lone_screen_excluded():
    draft = _screens_draft()
    admitted = {c.species for c in draft.candidates if c.tier}
    assert "Rotom-Wash" not in admitted
    assert any(r.species == "Rotom-Wash" for r in draft.considered_rejected)


def test_whimsicott_single_prankster_is_acceptable():
    draft = _screens_draft()
    whim = _find(draft, "whimsicott")
    assert whim.tier == "Acceptable"
    assert whim.excellence_basis == "prankster_single_screen"
    assert whim.criteria_notes["usage_proven"] == "True"


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
