#!/usr/bin/env python3
"""AR3 Part 1 follow-ups — patch derived_keys.ar3 (calc-backed)."""
from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib import (
    champions_hp,
    champions_spe,
    common_joint,
    load_legality,
    load_showdown,
    to_id,
)
from calc_store import calculate, health

OUT = Path(__file__).resolve().parents[1] / "key_artifacts" / "derived_keys.json"
CX = "Charizard-Mega-X"
CX_ABILITY = "Tough Claws"
CX_ITEM = "Charizardite X"
PRIM = "Primarina"


def _cx(nature, spread, boosts=None):
    m = {
        "species": CX,
        "level": 50,
        "nature": nature,
        "ability": CX_ABILITY,
        "item": CX_ITEM,
        "evs": spread,
    }
    if boosts:
        m["boosts"] = boosts
    return m


def _prim(row, item):
    nat = row.get("nature") or "Modest"
    evs = row.get("evs") or {}
    spread = {k: min(32, int(evs.get(k) or 0)) for k in ("hp", "atk", "def", "spa", "spd", "spe")}
    return {
        "species": PRIM,
        "level": 50,
        "nature": nat,
        "ability": "Torrent",
        "item": item,
        "evs": spread,
    }


def spe_plus1(nature: str, spe_sp: int) -> int:
    return math.floor(champions_spe(100, spe_sp, nature) * 1.5)


def min_spe_to_outspeed(nature: str, target: int) -> int | None:
    for sp in range(33):
        if spe_plus1(nature, sp) > target:
            return sp
    return None


def _fu_ohko_at(nature, move, prim, field, atk: int, joint_i: int, *, persist: bool):
    rec = calculate(
        {
            "attacker": _cx(
                nature,
                {"hp": 0, "atk": atk, "def": 0, "spa": 0, "spd": 0, "spe": 0},
                {"atk": 6},
            ),
            "defender": prim,
            "move": move,
            "field": field,
        },
        f"ar3fu_ohko_{to_id(move)}_{nature}_j{joint_i}_{atk}",
        persist=persist,
    )
    raw = (rec.get("response") or {}).get("raw") or {}
    dmg = raw.get("damage") or []
    if not dmg:
        return None
    hp = (raw.get("stats") or {}).get("defender", {}).get("hp") or 0
    return min(dmg) >= hp


def ohko_min_atk(nature, move, prim, field, joint_i: int = 0) -> int | None:
    """Binary-search min Atk SP for OHKO; persist 0..min ladder; linear fallback on verify fail."""
    if os.environ.get("PART_G_V4_AR3_LINEAR", "").strip() in {"1", "true", "yes"}:
        for atk in range(33):
            ok = _fu_ohko_at(nature, move, prim, field, atk, joint_i, persist=True)
            if ok is None:
                return None
            if ok:
                return atk
        return None
    lo, hi = 0, 32
    best = None
    while lo <= hi:
        mid = (lo + hi) // 2
        ok = _fu_ohko_at(nature, move, prim, field, mid, joint_i, persist=False)
        if ok is None:
            return None
        if ok:
            best = mid
            hi = mid - 1
        else:
            lo = mid + 1
    if best is None:
        _fu_ohko_at(nature, move, prim, field, 32, joint_i, persist=True)
        return None
    ok_b = _fu_ohko_at(nature, move, prim, field, best, joint_i, persist=False)
    ok_m1 = (
        False
        if best == 0
        else _fu_ohko_at(nature, move, prim, field, best - 1, joint_i, persist=False)
    )
    if (not ok_b) or (best > 0 and ok_m1 is not False):
        print(
            f"    WARN monotone_fallback ar3fu {move} {nature} j{joint_i} best={best}",
            flush=True,
        )
        for atk in range(33):
            ok = _fu_ohko_at(nature, move, prim, field, atk, joint_i, persist=True)
            if ok is None:
                return None
            if ok:
                return atk
        return None
    for atk in range(0, best + 1):
        _fu_ohko_at(nature, move, prim, field, atk, joint_i, persist=True)
    return best


def aj_damage(prim, cx_spread, field, aid):
    rec = calculate(
        {
            "attacker": {
                "species": PRIM,
                "level": 50,
                "nature": prim["nature"],
                "ability": prim["ability"],
                "item": prim["item"],
                "evs": prim["evs"],
            },
            "defender": _cx("Adamant", cx_spread),
            "move": "Aqua Jet",
            "field": field,
        },
        aid,
        persist=True,
    )
    return (rec.get("key") or {}).get("max_damage") or 0, rec


def main() -> None:
    assert health().get("status") == "ok"
    snap = load_legality()
    sd = load_showdown()
    field = {"gameType": "Doubles"}
    d = json.loads(OUT.read_text())
    ar = d["ar3"]
    ladder = ar["t5_speed_ladder"]

    # --- Part 1.2: cells in 229-250 ---
    cells_229_250 = []
    all_opp = []
    for t in ladder.get("per_threat") or []:
        for ol in t.get("opp_lines") or []:
            spe = ol.get("spe") or 0
            all_opp.append({"threat": t["threat"], **ol})
            if 229 <= spe <= 250:
                cells_229_250.append({"threat": t["threat"], **ol})
    jolly_max = ladder["jolly_plus1_max"]
    adamant_max = ladder["adamant_plus1_max"]
    reachable_229_250 = [c for c in cells_229_250 if c["spe"] <= jolly_max]
    t5_selects_jolly = bool(reachable_229_250)

    # Unreachable scarf lines (>250)
    unreachable_scarf = [
        c for c in all_opp if c.get("scarf") and c.get("spe", 0) > jolly_max
    ]
    # Also any non-scarf > 250
    unreachable_other = [
        c for c in all_opp if not c.get("scarf") and c.get("spe", 0) > jolly_max
    ]

    # Spe SP needed for each unique opp spe cell (reachable)
    unique_spe = sorted({c["spe"] for c in all_opp if c["spe"] <= jolly_max})
    spe_sp_table = []
    for tgt in unique_spe:
        spe_sp_table.append(
            {
                "target_spe": tgt,
                "jolly_min_spe_sp": min_spe_to_outspeed("Jolly", tgt),
                "adamant_min_spe_sp": min_spe_to_outspeed("Adamant", tgt),
                "jolly_final": spe_plus1("Jolly", min_spe_to_outspeed("Jolly", tgt) or 32)
                if min_spe_to_outspeed("Jolly", tgt) is not None
                else None,
                "adamant_final": spe_plus1("Adamant", min_spe_to_outspeed("Adamant", tgt) or 32)
                if min_spe_to_outspeed("Adamant", tgt) is not None
                else None,
            }
        )

    # Max Spe SP needed for full reachable coverage
    max_reachable = max(unique_spe) if unique_spe else 0
    jolly_spe_for_all = min_spe_to_outspeed("Jolly", max_reachable)
    adamant_spe_for_all = min_spe_to_outspeed("Adamant", max_reachable)

    # --- Part 1.4: OHKO across all 3 joints ---
    joints = common_joint(sd, PRIM)
    moves = ["Fire Punch", "Temper Flare", "Fire Fang", "Flame Charge", "Flare Blitz"]
    natures = ["Adamant", "Jolly"]
    per_joint = []
    cover_all = []
    for move in moves:
        for nature in natures:
            row = {"move": move, "nature": nature, "per_joint": []}
            mins = []
            for i, j in enumerate(joints):
                prim = _prim(j, "Life Orb")
                m = ohko_min_atk(nature, move, prim, field, joint_i=i)
                def_hp = champions_hp(80, int((j.get("evs") or {}).get("hp") or 0))
                row["per_joint"].append(
                    {
                        "joint_i": i,
                        "nature": j.get("nature"),
                        "spread": {k: min(32, int((j.get("evs") or {}).get(k) or 0)) for k in ("hp", "atk", "def", "spa", "spd", "spe")},
                        "def_hp": def_hp,
                        "def_hp_source": "champions_hp = base + SP + 75",
                        "min_atk_sp": m,
                    }
                )
                if m is not None:
                    mins.append(m)
            cover = max(mins) if len(mins) == 3 else None
            row["min_atk_sp_covers_all_joints"] = cover
            row["guaranteed_ohko_all_joints"] = cover is not None and len(mins) == 3
            per_joint.append(row)
            if row["guaranteed_ohko_all_joints"] and move in ("Fire Punch", "Temper Flare", "Fire Fang"):
                cover_all.append(row)

    # --- Part 1.3: min HP for AJ survival (worst joint + LO) ---
    # Worst AJ = max damage across joints with Life Orb
    worst_aj = 0
    worst_prim = None
    for i, j in enumerate(joints):
        prim = _prim(j, "Life Orb")
        # probe at HP-0 def-0 to get AJ damage (absolute)
        dmg, _ = aj_damage(prim, {"hp": 0, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0}, field, f"ar3fu_aj_probe_{i}")
        if dmg >= worst_aj:
            worst_aj = dmg
            worst_prim = prim
    # Also compare Mystic Water vs LO for label
    mw_dmg, _ = aj_damage(
        _prim(joints[0], "Mystic Water"),
        {"hp": 0, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
        field,
        "ar3fu_aj_mystic",
    )
    lo_dmg, _ = aj_damage(
        _prim(joints[0], "Life Orb"),
        {"hp": 0, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
        field,
        "ar3fu_aj_lo",
    )

    base_hp = snap["species"][to_id(CX)]["base_stats"]["hp"]
    min_hp_sp = None
    survival_rows = []
    for hp_sp in range(33):
        max_hp = champions_hp(base_hp, hp_sp)
        # AJ into full, BD cost floor(max/2), AJ into post-BD
        after_aj1 = max_hp - worst_aj
        after_bd = after_aj1 - (max_hp // 2)
        after_aj2 = after_bd - worst_aj
        ok = after_aj2 > 0
        survival_rows.append(
            {
                "hp_sp": hp_sp,
                "max_hp": max_hp,
                "aj_max": worst_aj,
                "after_aj2": after_aj2,
                "survives": ok,
            }
        )
        if ok and min_hp_sp is None:
            min_hp_sp = hp_sp

    # Joint feasibility: min_hp + atk + spe <= 66
    # Nature for Condition B
    if t5_selects_jolly:
        cov_nature = "Jolly"
        cov_spe = jolly_spe_for_all
        atk_move = "Fire Punch"
        atk_need = next(
            r["min_atk_sp_covers_all_joints"]
            for r in per_joint
            if r["move"] == atk_move and r["nature"] == "Jolly"
        )
    else:
        cov_nature = "Adamant"
        cov_spe = adamant_spe_for_all
        atk_move = "Fire Punch"
        atk_need = next(
            r["min_atk_sp_covers_all_joints"]
            for r in per_joint
            if r["move"] == atk_move and r["nature"] == "Adamant"
        )

    joint_budget = {
        "t5_selects_jolly": t5_selects_jolly,
        "reason": (
            f"Reachable threat cells in 229–250: {reachable_229_250}. "
            + (
                "Jolly required for max coverage."
                if t5_selects_jolly
                else "No reachable cell in 229–250; Adamant +1 max 228 covers all reachable cells."
            )
        ),
        "coverage_nature": cov_nature,
        "min_spe_sp": cov_spe,
        "min_atk_sp": atk_need,
        "min_hp_sp": min_hp_sp,
        # ponytail: 0 is valid SP — only None means missing (never `x or 99`)
        "sum": (
            (99 if min_hp_sp is None else min_hp_sp)
            + (99 if atk_need is None else atk_need)
            + (99 if cov_spe is None else cov_spe)
        ),
        "fits_budget_66": (
            (99 if min_hp_sp is None else min_hp_sp)
            + (99 if atk_need is None else atk_need)
            + (99 if cov_spe is None else cov_spe)
        )
        <= 66,
        "assume_state_t4_spread": {
            "nature": cov_nature,
            "hp": min_hp_sp,
            "atk": atk_need,
            "def": 0,
            "spa": 0,
            "spd": 0,
            "spe": cov_spe,
            "note": "t4 survival rests on this unstated ASSUME-STATE spread",
        },
    }

    # --- leftover table with correct Spe SP ---
    leftover_rows = []
    for move in ("Fire Punch", "Temper Flare", "Fire Fang"):
        for nature in ("Adamant", "Jolly"):
            r = next(x for x in per_joint if x["move"] == move and x["nature"] == nature)
            atk = r["min_atk_sp_covers_all_joints"]
            if atk is None:
                continue
            spe = jolly_spe_for_all if nature == "Jolly" else adamant_spe_for_all
            if spe is None:
                continue
            # If t5 selects jolly-only coverage, Adamant rows are partial-coverage
            used = atk + spe
            left = 66 - used
            leftover_rows.append(
                {
                    "nature": nature,
                    "move": move,
                    "min_atk_sp": atk,
                    "spe_sp": spe,
                    "max_reachable_opp_spe": max_reachable,
                    "covers_all_reachable_threats": (
                        (nature == "Jolly" and t5_selects_jolly)
                        or (nature == "Adamant" and not t5_selects_jolly)
                        or (nature == "Jolly" and not t5_selects_jolly)  # jolly also covers if adamant does
                    ),
                    "used": used,
                    "leftover": left,
                    "hp_sp": min(32, left),
                    "spill_above_32": max(0, left - 32),
                }
            )

    # True optimum for t6 among rows that cover all reachable threats
    covering = [r for r in leftover_rows if r["covers_all_reachable_threats"]]
    if t5_selects_jolly:
        covering = [r for r in leftover_rows if r["nature"] == "Jolly"]
    else:
        # both natures cover; max leftover wins
        covering = leftover_rows[:]
    max_left = max(r["leftover"] for r in covering) if covering else None
    ties = [r for r in covering if r["leftover"] == max_left] if covering else []

    # --- Recoil per Primarina joint at +6 ---
    recoil_rows = []
    for i, j in enumerate(joints):
        prim = _prim(j, "Life Orb")
        # use Adamant atk 0 +6 for FB
        rec = calculate(
            {
                "attacker": _cx("Adamant", {"hp": 32, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0}, {"atk": 6}),
                "defender": prim,
                "move": "Flare Blitz",
                "field": field,
            },
            f"ar3fu_fb_recoil_j{i}",
            persist=True,
        )
        raw = (rec.get("response") or {}).get("raw") or {}
        recoil = raw.get("recoil") or {}
        pct = recoil.get("recoil")
        atk_hp = (raw.get("stats") or {}).get("attacker", {}).get("hp")
        def_hp = (raw.get("stats") or {}).get("defender", {}).get("hp")
        dmg = raw.get("damage") or []
        if isinstance(pct, list):
            pct_lo, pct_hi = float(pct[0]), float(pct[1])
        else:
            pct_lo = pct_hi = float(pct or 0)
        from _lib import flare_blitz_recoil_basis

        basis = flare_blitz_recoil_basis(
            def_hp=def_hp,
            atk_hp=atk_hp,
            damage=dmg,
            calc_display_pct=[pct_lo, pct_hi],
        )
        recoil_rows.append(
            {
                "joint_i": i,
                "def_hp": def_hp,
                "damage_range": (rec.get("key") or {}).get("damage_range"),
                "recoil_text": recoil.get("text"),
                "recoil_pct": [pct_lo, pct_hi],
                "recoil_hp_points": basis["recoil_hp_range"],
                "attacker_max_hp": atk_hp,
                "desc": raw.get("desc"),
                **basis,
            }
        )

    followup = {
        "t5_cells_229_250": cells_229_250,
        "reachable_cells_229_250": reachable_229_250,
        "t5_selects_jolly_for_max_coverage": t5_selects_jolly,
        "jolly_plus1_max": jolly_max,
        "adamant_plus1_max": adamant_max,
        "max_reachable_opp_spe": max_reachable,
        "spe_sp_for_full_reachable_coverage": {
            "jolly": jolly_spe_for_all,
            "adamant": adamant_spe_for_all,
        },
        "spe_sp_table_by_target": spe_sp_table,
        "unreachable_scarf_lines": unreachable_scarf,
        "unreachable_other": unreachable_other,
        "t4_ohko_per_joint": per_joint,
        "t4_aqua_jet_worst_case": {
            "item": "Life Orb",
            "item_note": "Life Orb (1.3x) is worst-case among COMMON_ITEM for AJ offense vs Mystic Water (1.2x)",
            "lo_dmg_joint0": lo_dmg,
            "mystic_water_dmg_joint0": mw_dmg,
            "worst_aj_max": worst_aj,
            "worst_prim": {k: worst_prim[k] for k in ("nature", "item", "evs")} if worst_prim else None,
        },
        "t4_min_hp_sp_survival": {
            "min_hp_sp": min_hp_sp,
            "rows": survival_rows,
            "model": "AJ(max)+BD(half max)+AJ(max); worst Primarina joint + Life Orb",
        },
        "t4_t5_joint_feasible": joint_budget,
        "t6_leftover_corrected": {
            "all_rows": leftover_rows,
            "covering_rows": covering,
            "max_leftover": max_left,
            "tied_nature_move_pairs": ties,
            "prior_error": (
                "Prior leftover 34 used Spe=32 for Adamant without checking whether any "
                "reachable threat cell lies in 229–250 (Jolly-only band)."
            ),
            "adamant_x_firepunch_is_optimum": (
                (not t5_selects_jolly)
                and any(t["nature"] == "Adamant" and t["move"] == "Fire Punch" for t in ties)
            ),
        },
        "t4_flare_blitz_recoil_per_joint": recoil_rows,
    }

    ar["part1_followup"] = followup
    # Replace t6 with corrected
    ar["t6_leftover_hp"] = followup["t6_leftover_corrected"]
    ar["t4_ohko_min_atk_sp"] = [
        {
            "move": r["move"],
            "nature": r["nature"],
            "min_atk_sp": r["min_atk_sp_covers_all_joints"],
            "guaranteed_ohko": r["guaranteed_ohko_all_joints"],
            "per_joint": r["per_joint"],
            "note": "min Atk SP = max across three COMMON_JOINT Primarina spreads",
        }
        for r in per_joint
    ]
    d["ar3"] = ar
    OUT.write_text(json.dumps(d, indent=2) + "\n")
    print("t5_selects_jolly", t5_selects_jolly)
    print("reachable_229_250", reachable_229_250)
    print("max_reachable", max_reachable, "jolly_spe", jolly_spe_for_all, "adamant_spe", adamant_spe_for_all)
    print("min_hp", min_hp_sp, "joint", joint_budget)
    print("ties", ties)
    print("unreachable_scarf", unreachable_scarf)
    print("ohko cover", [(r["move"], r["nature"], r["min_atk_sp_covers_all_joints"]) for r in per_joint if r["move"] in ("Fire Punch", "Temper Flare", "Fire Fang")])
    print("recoil", [(r["def_hp"], r["recoil_pct"], r["recoil_hp_points"]) for r in recoil_rows])
    print("LO vs MW", lo_dmg, mw_dmg)


if __name__ == "__main__":
    main()
