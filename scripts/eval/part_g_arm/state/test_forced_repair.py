"""Forced-repair checks: reference SP infeasible; solver fill vs brute L1 optimum.

Uses the shared _feasible predicate (same calc path as solve_spread) but does NOT
call _frontier_for_nature or _fill_toward — the enumeration is independent.
"""

from __future__ import annotations

import os

os.environ.setdefault("PART_G_V4_CALC_BACKEND", "inprocess")

from scripts.eval.part_g_arm.state.spread_solve import (
    STAT_KEYS,
    _feasible,
    _l1,
    _parse_constraints,
    joint_refs_66,
    solve_spread,
)

DOUBLES = {"gameType": "Doubles"}
SUN = {"gameType": "Doubles", "weather": "Sun"}


def _sneasler(nature: str) -> dict:
    return {
        "species": "Sneasler",
        "nature": nature,
        "ability": "Unburden",
        "item": "White Herb",
        "sp": {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32},
    }


def _zard(nature: str) -> dict:
    return {
        "species": "Charizard-Mega-Y",
        "nature": nature,
        "ability": "Drought",
        "item": "",
        "sp": {"hp": 0, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 0},
    }


def _brute_bold_spe5(preds, target_sp: dict) -> tuple[dict, int]:
    """Enumerate Bold Spe=5, Atk=SpA free only as remainder; minimize L1 to target."""
    best = None
    best_d = None
    for hp in range(33):
        for df in range(33):
            for spd in range(33):
                rem = 66 - (hp + df + spd + 5)
                if rem < 0 or rem > 64:
                    continue
                spa = min(32, rem)
                atk = rem - spa
                if atk < 0 or atk > 32:
                    continue
                sp = {"hp": hp, "atk": atk, "def": df, "spa": spa, "spd": spd, "spe": 5}
                if not _feasible(preds, "Bold", sp):
                    continue
                d = _l1(sp, target_sp)
                if best_d is None or d < best_d:
                    best_d = d
                    best = sp
                elif d == best_d and best is not None:
                    # stable tie: lower hp then def then spd
                    if (hp, df, spd) < (best["hp"], best["def"], best["spd"]):
                        best = sp
    assert best is not None and best_d is not None
    return best, best_d


def test_forced_repair_jolly_cc_gate():
    """All Bold 66-SP refs fail Spe gate; solver must repair toward rank-2."""
    constraints = [
        {
            "type": "survive",
            "attacker": _sneasler("Jolly"),
            "move": "Close Combat",
            "field": DOUBLES,
        },
        {"type": "outspeed", "target_spe": 110},
    ]
    preds, _, _, err = _parse_constraints("Archaludon", "Stamina", "Leftovers", constraints)
    assert err is None
    refs, _ = joint_refs_66("Archaludon")
    bold = [r for r in refs if r["nature"] == "Bold"]
    assert bold
    assert all(not _feasible(preds, "Bold", r["sp"]) for r in bold)
    target = bold[0]["sp"]  # highest-weight Bold = filtered rank among Bold
    # Prefer the Bold entry with highest weight overall
    target_entry = max(bold, key=lambda r: r["weight"])
    target = target_entry["sp"]

    brute, brute_d = _brute_bold_spe5(preds, target)
    out = solve_spread(
        "Archaludon", constraints, ability="Stamina", item="Leftovers", time_budget_s=60
    )
    assert out["status"] == "optimal"
    assert out["distance"] is not None and out["distance"] > 0
    assert out["spread"]["nature"] == "Bold"
    solver_sp = {k: out["spread"][k] for k in STAT_KEYS}
    assert out["distance"] == brute_d
    assert _l1(solver_sp, target) == brute_d
    # Report fields for the Part A3 table (asserted equality is the check).
    assert solver_sp == brute or _l1(solver_sp, target) == _l1(brute, target)


def test_forced_repair_adamant_cc_flamethrower_gate():
    """Dual survive + gate: Bold refs infeasible; brute L1 matches solver."""
    constraints = [
        {
            "type": "survive",
            "attacker": _sneasler("Adamant"),
            "move": "Close Combat",
            "field": DOUBLES,
        },
        {
            "type": "survive",
            "attacker": _zard("Modest"),
            "move": "Flamethrower",
            "field": SUN,
        },
        {"type": "outspeed", "target_spe": 110},
    ]
    preds, _, _, err = _parse_constraints("Archaludon", "Stamina", "Leftovers", constraints)
    assert err is None
    refs, _ = joint_refs_66("Archaludon")
    bold = [r for r in refs if r["nature"] == "Bold"]
    assert all(not _feasible(preds, "Bold", r["sp"]) for r in bold)
    target = max(bold, key=lambda r: r["weight"])["sp"]
    brute, brute_d = _brute_bold_spe5(preds, target)
    out = solve_spread(
        "Archaludon", constraints, ability="Stamina", item="Leftovers", time_budget_s=90
    )
    assert out["status"] == "optimal"
    assert out["distance"] > 0
    solver_sp = {k: out["spread"][k] for k in STAT_KEYS}
    assert out["spread"]["nature"] == "Bold"
    assert out["distance"] == brute_d == _l1(solver_sp, target)
