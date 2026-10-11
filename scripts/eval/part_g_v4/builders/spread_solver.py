"""Property-check spread search for AR1/AR2/MT7/MT8 (calc-backed, binary SpD)."""
from __future__ import annotations

from typing import Any

from _lib import champions_spe, common_joint, load_legality, load_showdown, to_id
from calc_store import calculate
from speed_grid import ALL_NATURES, nature_class

ARCH_ABILITY = "Stamina"
ARCH_ITEM = "Leftovers"
# Part 0: COMMON_JOINT outspeed comparisons — top 3, drop max-speed cell.
# Archaludon joint Spe cells [108, 109] (max 150 dropped) → gate Spe ≥ 110.
# COMMON_SPEED [105, 150, 108] would gate at 109; Part 0 does not use that here.
MIRROR_MIN_SPE = 110
MIRROR_CORE_CELLS = [108, 109]
MIRROR_DROPPED_MAX = 150


def _defender(nature: str, spread: dict) -> dict:
    return {
        "species": "Archaludon",
        "level": 50,
        "nature": nature,
        "ability": ARCH_ABILITY,
        "item": ARCH_ITEM,
        "evs": spread,
    }


def _sneasler(nature: str) -> dict:
    return {
        "species": "Sneasler",
        "level": 50,
        "nature": nature,
        "ability": "Unburden",
        "item": "White Herb",
        "evs": {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32},
    }


def _zard_y(nature: str = "Modest") -> dict:
    return {
        "species": "Charizard-Mega-Y",
        "level": 50,
        "nature": nature,
        "ability": "Drought",
        "item": "",
        "evs": {"hp": 0, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 0},
    }


def _survives(att: dict, defn: dict, move: str, field: dict) -> bool:
    rec = calculate(
        {"attacker": att, "defender": defn, "move": move, "field": field},
        "probe",
        persist=False,
    )
    resp = rec.get("response") or {}
    if "error" in resp:
        return False
    raw = resp.get("raw") or {}
    dmg = raw.get("damage") or []
    if not dmg:
        return True
    hp = (raw.get("stats") or {}).get("defender", {}).get("hp") or 0
    return max(dmg) < hp


def _min_spe_sp(base_spe: int, nature: str) -> int | None:
    for sp in range(33):
        if champions_spe(base_spe, sp, nature) >= MIRROR_MIN_SPE:
            return sp
    return None


def _ok(nature: str, spread: dict, conditions: list[tuple[dict, str, dict]]) -> bool:
    defender = _defender(nature, spread)
    return all(_survives(att, defender, move, field) for att, move, field in conditions)


def search_conditions(
    conditions: list[tuple[dict, str, dict]],
    speed_gate: bool,
    prefix: str,
) -> dict[str, Any]:
    """Return feasibility, min total SP, one example. Counts are diagnostic only."""
    snap = load_legality()
    base_spe = snap["species"][to_id("Archaludon")]["base_stats"]["spe"]
    # Diagnostic counts at minimal Spe (gate minimum) — not exhaustive totals.
    diag_counts: dict[str, int] = {}
    min_total: int | None = None
    example: dict | None = None
    any_ok = False

    for nature in ALL_NATURES:
        ncls = nature_class(nature)
        min_spe = _min_spe_sp(base_spe, nature) if speed_gate else 0
        if speed_gate and min_spe is None:
            continue
        spe = min_spe or 0
        rem = 66 - spe
        n_ok = 0
        for hp in range(33):
            for df in range(33):
                if hp + df > rem:
                    continue
                # Per-stat Champions SP max is 32 (budget rem may be larger when Spe ungated)
                spd_hi = min(32, rem - hp - df)
                lo, hi = 0, spd_hi
                best = None
                while lo <= hi:
                    mid = (lo + hi) // 2
                    spread = {"hp": hp, "atk": 0, "def": df, "spa": 0, "spd": mid, "spe": spe}
                    if _ok(nature, spread, conditions):
                        best = mid
                        hi = mid - 1
                    else:
                        lo = mid + 1
                if best is None:
                    continue
                n_ok += spd_hi - best + 1
                tot = hp + df + best + spe
                any_ok = True
                if min_total is None or tot < min_total:
                    min_total = tot
                    example = {
                        "nature": nature,
                        "nature_class": ncls,
                        "spread": {
                            "hp": hp,
                            "atk": 0,
                            "def": df,
                            "spa": 0,
                            "spd": best,
                            "spe": spe,
                        },
                        "spe": champions_spe(base_spe, spe, nature),
                        "total_sp": tot,
                    }
        if n_ok:
            diag_counts[ncls] = diag_counts.get(ncls, 0) + n_ok

    if example:
        for i, (att, move, field) in enumerate(conditions):
            calculate(
                {
                    "attacker": att,
                    "defender": _defender(example["nature"], example["spread"]),
                    "move": move,
                    "field": field,
                },
                f"{prefix}_ex_{i}",
                persist=True,
            )

    return {
        "feasible": any_ok,
        "min_total_sp": min_total,
        "example": example,
        "solutions_at_minimal_spe_by_class": diag_counts,
        "count_semantics": (
            "solutions at minimal Spe (gate minimum); Spe fixed at gate min; "
            "not exhaustive totals across Spe SP. Only feasible/infeasible is exact."
        ),
        "search_note": (
            "Spe fixed at min for gate; binary-search min SpD per (HP,Def); "
            "diagnostic SpD>=min counts summed per nature class (not key totals)."
        ),
        "class_count_note": (
            "Neutral count exceeds +Atk/+SpA/+SpD when HP/Def/Spe constraints match "
            "because neutral has 5 identical full-bulk natures while each +/- class "
            "mixes 2 full-bulk + 1 Def− + 1 Spe− nature (fewer sols). Not double-counting; "
            "Spe is fixed so natures that do not change Def/Spe share the same (HP,Def,SpD) set."
        ),
    }


def ar2_pareto() -> dict[str, list]:
    doubles = {"gameType": "Doubles"}
    class_natures = {
        "neutral": "Serious",
        "+Def": "Bold",
        "+SpD": "Calm",
        "+Spe": "Jolly",
        "+Atk": "Adamant",
        "+SpA": "Modest",
    }
    out: dict[str, list] = {}
    for ncls, nat in class_natures.items():
        pairs = []
        for hp in range(33):
            for df in range(33):
                rem = 66 - hp - df
                if rem < 0:
                    continue
                lo, hi = 0, rem
                best = None
                while lo <= hi:
                    mid = (lo + hi) // 2
                    spread = {"hp": hp, "atk": 0, "def": df, "spa": 0, "spd": mid, "spe": 0}
                    if _ok(nat, spread, [(_sneasler("Adamant"), "Close Combat", doubles)]):
                        best = mid
                        hi = mid - 1
                    else:
                        lo = mid + 1
                if best is not None:
                    pairs.append((hp, df))
        minimal = [
            p
            for p in pairs
            if not any(q[0] <= p[0] and q[1] <= p[1] and q != p for q in pairs)
        ]
        out[ncls] = sorted(set(minimal))
        if minimal:
            calculate(
                {
                    "attacker": _sneasler("Adamant"),
                    "defender": _defender(
                        nat,
                        {
                            "hp": minimal[0][0],
                            "atk": 0,
                            "def": minimal[0][1],
                            "spa": 0,
                            "spd": 0,
                            "spe": 0,
                        },
                    ),
                    "move": "Close Combat",
                    "field": doubles,
                },
                f"ar2_pareto_ex_{ncls.replace('+', 'p')}",
                persist=True,
            )
    return out


def mt7_mt8_ar_keys() -> dict:
    doubles = {"gameType": "Doubles"}
    sun = {"gameType": "Doubles", "weather": "Sun"}

    # Confirm COMMON_JOINT Spe cells still match hardcoded gate
    sd = load_showdown()
    snap = load_legality()
    base = snap["species"][to_id("Archaludon")]["base_stats"]["spe"]
    joint_spe = []
    for r in common_joint(sd, "Archaludon"):
        nat = r.get("nature") or "Serious"
        sp = int((r.get("evs") or {}).get("spe") or 0)
        joint_spe.append(champions_spe(base, sp, nat))
    joint_sorted = sorted(set(joint_spe))
    dropped = max(joint_sorted) if joint_sorted else None
    core = [s for s in joint_sorted if s != dropped]
    gate = (max(core) + 1) if core else MIRROR_MIN_SPE

    print("  MT7 t1 Jolly CC...", flush=True)
    mt7_t1 = search_conditions([(_sneasler("Jolly"), "Close Combat", doubles)], True, "mt7_t1")
    print("   ", mt7_t1["feasible"], mt7_t1["min_total_sp"], mt7_t1["solutions_at_minimal_spe_by_class"], flush=True)
    print("  MT7 t2 Adamant CC...", flush=True)
    mt7_t2 = search_conditions([(_sneasler("Adamant"), "Close Combat", doubles)], True, "mt7_t2")
    print("   ", mt7_t2["feasible"], mt7_t2["min_total_sp"], mt7_t2["solutions_at_minimal_spe_by_class"], flush=True)
    print("  MT7 t3 Adamant+Flamethrower...", flush=True)
    mt7_t3 = search_conditions(
        [
            (_sneasler("Adamant"), "Close Combat", doubles),
            (_zard_y("Modest"), "Flamethrower", sun),
        ],
        True,
        "mt7_t3",
    )
    print("   ", mt7_t3["feasible"], mt7_t3["min_total_sp"], mt7_t3["solutions_at_minimal_spe_by_class"], flush=True)
    print("  MT8 t3 Adamant+Weather Ball (Modest)...", flush=True)
    mt8_t3 = search_conditions(
        [
            (_sneasler("Adamant"), "Close Combat", doubles),
            (_zard_y("Modest"), "Weather Ball", sun),
        ],
        True,
        "mt8_t3",
    )
    print("   ", mt8_t3["feasible"], mt8_t3["min_total_sp"], mt8_t3["solutions_at_minimal_spe_by_class"], flush=True)
    print("  MT8 t3 Timid Weather Ball offer...", flush=True)
    mt8_t3_timid = search_conditions(
        [
            (_sneasler("Adamant"), "Close Combat", doubles),
            (_zard_y("Timid"), "Weather Ball", sun),
        ],
        True,
        "mt8_t3_timid_wb",
    )
    print(
        "   ",
        mt8_t3_timid["feasible"],
        mt8_t3_timid["min_total_sp"],
        mt8_t3_timid["example"],
        mt8_t3_timid["solutions_at_minimal_spe_by_class"],
        flush=True,
    )
    # Hand example Bold 31/1/23/5
    hand_timid = {
        "nature": "Bold",
        "spread": {"hp": 31, "atk": 0, "def": 1, "spa": 0, "spd": 23, "spe": 5},
    }
    hand_timid_ok = _ok(
        hand_timid["nature"],
        hand_timid["spread"],
        [
            (_sneasler("Adamant"), "Close Combat", doubles),
            (_zard_y("Timid"), "Weather Ball", sun),
        ],
    )
    print("  MT7 t3 Timid Flamethrower (feasibility only)...", flush=True)
    mt7_t3_timid = search_conditions(
        [
            (_sneasler("Adamant"), "Close Combat", doubles),
            (_zard_y("Timid"), "Flamethrower", sun),
        ],
        True,
        "mt7_t3_timid_ft",
    )
    print("   ", mt7_t3_timid["feasible"], mt7_t3_timid["min_total_sp"], flush=True)
    print("  MT8 t4 Jolly+Weather Ball...", flush=True)
    mt8_t4 = search_conditions(
        [
            (_sneasler("Jolly"), "Close Combat", doubles),
            (_zard_y("Modest"), "Weather Ball", sun),
        ],
        True,
        "mt8_t4_jolly",
    )
    print("   ", mt8_t4["feasible"], mt8_t4["min_total_sp"], mt8_t4["solutions_at_minimal_spe_by_class"], flush=True)
    print("  MT8 t4 drop Spe gate...", flush=True)
    mt8_nospe = search_conditions(
        [
            (_sneasler("Adamant"), "Close Combat", doubles),
            (_zard_y("Modest"), "Weather Ball", sun),
        ],
        False,
        "mt8_t4_nospeed",
    )
    print("   ", mt8_nospe["feasible"], mt8_nospe["min_total_sp"], mt8_nospe["solutions_at_minimal_spe_by_class"], flush=True)
    print("  AR2 Pareto...", flush=True)
    pareto = ar2_pareto()

    return {
        "mirror_speed_gate": {
            "part0_constant": "COMMON_JOINT",
            "part0_rule": (
                "COMMON_JOINT top 3; for outspeed comparisons drop the max-speed cell "
                "and mention its share. COMMON_SPEED is not the mirror gate."
            ),
            "joint_spe_cells": joint_sorted,
            "core_cells": core,
            "dropped_opp_max_spe": dropped,
            "min_spe": gate,
            "common_speed_note": (
                "Regenerated COMMON_SPEED for Archaludon is typically [105,150,108] "
                "(gate 109 if used); Part 0 assigns COMMON_JOINT → gate "
                f"{gate} from core {core}."
            ),
            "hardcoded_match": gate == MIRROR_MIN_SPE and core == MIRROR_CORE_CELLS,
        },
        "attacker_nature_key": {
            "max_spa": "Modest, 32 SpA (stat 232), Drought/Sun",
            "timid_spa": "Timid, 32 SpA (stat 211), Drought/Sun",
        },
        "mt7_t1_jolly_cc": mt7_t1,
        "mt7_t2_adamant_cc": mt7_t2,
        "mt7_t3_adamant_cc_flamethrower": mt7_t3,
        "mt7_t3_timid_flamethrower_extra": {
            **mt7_t3_timid,
            "offer_class": "threat_relaxation_extra",
            "required": False,
            "counts_toward_3_relaxation_cap": False,
            "note": "Record only if Timid changes feasibility vs Modest; Modest remains required t3.",
        },
        "mt8_t3_adamant_cc_weatherball": mt8_t3,
        "mt8_t3_timid_weatherball_extra": {
            **mt8_t3_timid,
            "offer_class": "threat_relaxation_extra",
            "required": False,
            "counts_toward_3_relaxation_cap": False,
            "hand_example_bold_31_1_23_5_survives": hand_timid_ok,
            "hand_example": hand_timid,
        },
        "mt8_t4_make_sneasler_jolly": mt8_t4,
        "mt8_t4_drop_speed_gate": mt8_nospe,
        "mt8_t4_way_out": {
            "offers_of_either_relaxation_correct": True,
            "jolly_sneasler": {
                "feasible": mt8_t4["feasible"],
                "solutions_at_minimal_spe_by_class": mt8_t4["solutions_at_minimal_spe_by_class"],
                "min_total_sp": mt8_t4["min_total_sp"],
                "example": mt8_t4["example"],
                "note": (
                    "Jolly works under +SpD / +Def / +Spe (not +SpD-only). "
                    "Counts = solutions at minimal Spe (gate minimum), not totals."
                ),
            },
            "drop_speed_gate": {
                "feasible": mt8_nospe["feasible"],
                "solutions_at_minimal_spe_by_class": mt8_nospe["solutions_at_minimal_spe_by_class"],
                "min_total_sp": mt8_nospe["min_total_sp"],
                "example": mt8_nospe["example"],
                "note": "Dropping Spe gate helps (+Def solutions exist).",
            },
            "timid_zard_extra": {
                "feasible": mt8_t3_timid["feasible"],
                "min_total_sp": mt8_t3_timid["min_total_sp"],
                "example": mt8_t3_timid["example"],
                "accepted_extra_offer": True,
                "counts_toward_3_relaxation_cap": False,
            },
        },
        "ar1": mt7_t1,
        "ar2_pareto_hp_def_by_class": pareto,
    }
