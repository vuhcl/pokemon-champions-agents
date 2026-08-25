"""Swords Dance setup-attacker tests — shared helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from recommender.ids import to_id
from recommender.legality import load_snapshot
from recommender.role_compendium import (
    SWORDS_DANCE_ATTACKER_CRITERIA,
    construct_role_category,
    legal_species_pool,
)

def _mock_calc(requests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Spe-path calibrators = 1.0. Incoming OHKO reqs have no attacker.boosts."""
    out: list[dict[str, Any]] = []
    for req in requests:
        atk = req.get("attacker") or {}
        if not atk.get("boosts"):
            # Panel hitting candidate: not OHKO (frac 0.2).
            frac = 0.2
            atk_spe = 100
        else:
            sp = to_id(atk.get("species") or "")
            if sp in {"blazikenmega", "blaziken"}:
                frac = 1.0
                atk_spe = 200
            elif sp in {"kingambit", "scizor", "scizormega", "mawilemega"}:
                frac = 0.35
                atk_spe = 50
            else:
                frac = 0.2
                atk_spe = 100
        dmg = int(200 * frac)
        out.append(
            {
                "damageRange": [dmg - 10, dmg],
                "koChance": "guaranteed OHKO" if frac >= 1.0 else "possibly 3HKO",
                "raw": {
                    "stats": {
                        "defender": {"hp": 200, "spe": 80},
                        "attacker": {"atk": 200, "spe": atk_spe},
                    }
                },
            }
        )
    return out

def _panel_result(
    *,
    dmg: int,
    hp: int = 200,
    atk_spe: int = 100,
    def_spe: int = 80,
    recoil_pct: float | None = None,
    recovery_hp: int | None = None,
    atk_hp: int | None = None,
) -> dict[str, Any]:
    attacker_hp = 159 if atk_hp is None else atk_hp
    raw: dict[str, Any] = {
        "stats": {
            "attacker": {"spe": atk_spe, "hp": attacker_hp},
            "defender": {"hp": hp, "spe": def_spe},
        }
    }
    if recoil_pct is not None:
        raw["recoil"] = {
            "recoil": [recoil_pct, recoil_pct],
            "text": f"{recoil_pct}% recoil damage",
        }
    if recovery_hp is not None:
        raw["recovery"] = {
            "recovery": [recovery_hp, recovery_hp],
            "text": f"{recovery_hp} HP recovered",
        }
    return {
        "damageRange": [dmg, dmg],
        "koChance": "2HKO",
        "raw": raw,
    }

def _sd_criteria_for_mock() -> dict[str, Any]:
    """Mock calcs score far below the locked live admission floor — strip it."""
    crit = dict(SWORDS_DANCE_ATTACKER_CRITERIA)
    crit.pop("damage_admission_floor", None)
    crit.pop("acceptable_floor_mult", None)
    return crit

def _sd_draft(*, pool: list[str] | None = None, live_fetch=None):
    snap = load_snapshot()
    proven = {
        "blazikenmega",
        "blaziken",
        "kingambit",
        "scizor",
        "scizormega",
        "mawilemega",
        "aegislash",
        "ceruledge",
        "lucariomega",
    }

    def _usage(name: str) -> dict[str, Any] | None:
        sid = to_id(name)
        if sid not in proven:
            return None
        return {
            "name": name,
            "id": sid,
            "common_moves": [{"name": "Swords Dance", "pct": 40.0}],
            "common_items": [{"name": "Life Orb", "pct": 20.0}],
        }

    default_pool = [n for n in legal_species_pool(snap) if to_id(n) in proven]
    return construct_role_category(
        "swords_dance_attacker",
        _sd_criteria_for_mock(),
        pool if pool is not None else default_pool,
        snap=snap,
        live_fetch=live_fetch if live_fetch is not None else _usage,
        showdown_fetch=lambda _n: None,
        calculate_batch=_mock_calc,
    )

def _members(draft, tier: str) -> set[str]:
    return {c.species for c in draft.candidates if c.tier == tier}

