"""Property-check spread search for AR1/AR2/MT7/MT8 (calc-backed, binary SpD)."""
from __future__ import annotations

import json
import os
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
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

# Monotone fallback log (stderr/print); also appended when checkpoint dir set.
_MONOTONE_FALLBACKS: list[str] = []


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


def _workers() -> int:
    raw = (os.environ.get("PART_G_V4_SOLVER_WORKERS") or "").strip()
    if raw:
        return max(1, int(raw))
    return max(1, min(8, (os.cpu_count() or 2) - 1))


def _checkpoint_path(prefix: str) -> Path | None:
    root = (os.environ.get("PART_G_V4_SOLVER_CHECKPOINT_DIR") or "").strip()
    if not root:
        return None
    p = Path(root)
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{prefix}_cells.jsonl"


def _load_checkpoint(path: Path | None) -> dict[str, dict]:
    if path is None or not path.is_file():
        return {}
    out: dict[str, dict] = {}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        cid = row.get("cell_id") or row.get("nature")
        if cid:
            out[str(cid)] = row
    return out


def _append_checkpoint(path: Path | None, row: dict) -> None:
    if path is None:
        return
    with path.open("a") as f:
        f.write(json.dumps(row, sort_keys=True) + "\n")


def _min_spd_linear(
    nature: str,
    hp: int,
    df: int,
    spe: int,
    spd_hi: int,
    conditions: list[tuple[dict, str, dict]],
) -> int | None:
    for spd in range(0, spd_hi + 1):
        spread = {"hp": hp, "atk": 0, "def": df, "spa": 0, "spd": spd, "spe": spe}
        if _ok(nature, spread, conditions):
            return spd
    return None


def _min_spd_binary_verified(
    nature: str,
    hp: int,
    df: int,
    spe: int,
    spd_hi: int,
    conditions: list[tuple[dict, str, dict]],
    *,
    cell_id: str,
) -> int | None:
    """Binary-search min SpD; verify boundary; fall back to linear on monotone fail."""
    lo, hi = 0, spd_hi
    best: int | None = None
    while lo <= hi:
        mid = (lo + hi) // 2
        spread = {"hp": hp, "atk": 0, "def": df, "spa": 0, "spd": mid, "spe": spe}
        if _ok(nature, spread, conditions):
            best = mid
            hi = mid - 1
        else:
            lo = mid + 1
    if best is None:
        return None
    # Boundary verify: best passes, best-1 fails (if best>0)
    spread_ok = {"hp": hp, "atk": 0, "def": df, "spa": 0, "spd": best, "spe": spe}
    if not _ok(nature, spread_ok, conditions):
        msg = f"monotone_fallback boundary_fail_pass {cell_id} spd={best}"
        _MONOTONE_FALLBACKS.append(msg)
        print(f"    WARN {msg}", flush=True)
        return _min_spd_linear(nature, hp, df, spe, spd_hi, conditions)
    if best > 0:
        spread_lo = {"hp": hp, "atk": 0, "def": df, "spa": 0, "spd": best - 1, "spe": spe}
        if _ok(nature, spread_lo, conditions):
            msg = f"monotone_fallback boundary_fail_min1 {cell_id} spd={best}"
            _MONOTONE_FALLBACKS.append(msg)
            print(f"    WARN {msg}", flush=True)
            return _min_spd_linear(nature, hp, df, spe, spd_hi, conditions)
    return best


def _search_one_nature(
    nature: str,
    conditions: list[tuple[dict, str, dict]],
    spe: int,
    base_spe: int,
    *,
    use_staircase: bool,
) -> dict[str, Any]:
    """Per-nature HP×Def search. Staircase skips infeasible HP below frontier."""
    ncls = nature_class(nature)
    rem = 66 - spe
    n_ok = 0
    min_total: int | None = None
    example: dict | None = None
    fallbacks_before = len(_MONOTONE_FALLBACKS)

    def handle_cell(hp: int, df: int) -> None:
        nonlocal n_ok, min_total, example
        spd_hi = min(32, rem - hp - df)
        cid = f"{nature}|hp={hp}|def={df}|spe={spe}"
        best = _min_spd_binary_verified(
            nature, hp, df, spe, spd_hi, conditions, cell_id=cid
        )
        if best is None:
            return
        n_ok += spd_hi - best + 1
        tot = hp + df + best + spe
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

    if use_staircase:
        # Damage non-increasing in defender HP/Def/SpD → feasible region is a staircase:
        # for each Def, binary-search min HP that admits some SpD, then fill HP≥min.
        # If frontier verify fails, fall back to full HP scan for that Def column.
        for df in range(33):
            if df > rem:
                continue
            # Per-stat SP max 32 (budget rem may exceed 32 when Spe is low).
            hp_hi = min(32, rem - df)
            lo, hi = 0, hp_hi
            min_hp: int | None = None
            while lo <= hi:
                mid = (lo + hi) // 2
                spd_hi = min(32, rem - mid - df)
                cid = f"{nature}|frontier|hp={mid}|def={df}|spe={spe}"
                if (
                    _min_spd_binary_verified(
                        nature, mid, df, spe, spd_hi, conditions, cell_id=cid
                    )
                    is not None
                ):
                    min_hp = mid
                    hi = mid - 1
                else:
                    lo = mid + 1
            if min_hp is None:
                continue
            # Frontier verify: min_hp-1 must be infeasible even at max SpD
            if min_hp > 0:
                spd_hi_lo = min(32, rem - (min_hp - 1) - df)
                spread_lo = {
                    "hp": min_hp - 1,
                    "atk": 0,
                    "def": df,
                    "spa": 0,
                    "spd": spd_hi_lo,
                    "spe": spe,
                }
                if _ok(nature, spread_lo, conditions):
                    msg = (
                        f"monotone_fallback frontier_hp {nature}|def={df} "
                        f"min_hp={min_hp} but hp-1 ok at spd={spd_hi_lo}"
                    )
                    _MONOTONE_FALLBACKS.append(msg)
                    print(f"    WARN {msg}", flush=True)
                    for hp in range(0, hp_hi + 1):
                        handle_cell(hp, df)
                    continue
            for hp in range(min_hp, hp_hi + 1):
                handle_cell(hp, df)
    else:
        for hp in range(33):
            for df in range(33):
                if hp + df > rem:
                    continue
                handle_cell(hp, df)

    return {
        "cell_id": nature,
        "nature": nature,
        "nature_class": ncls,
        "n_ok": n_ok,
        "min_total": min_total,
        "example": example,
        "monotone_fallbacks": len(_MONOTONE_FALLBACKS) - fallbacks_before,
    }


def _nature_job(args: tuple) -> dict[str, Any]:
    nature, conditions, spe, base_spe, use_staircase = args
    return _search_one_nature(
        nature, conditions, spe, base_spe, use_staircase=use_staircase
    )


def search_conditions(
    conditions: list[tuple[dict, str, dict]],
    speed_gate: bool,
    prefix: str,
) -> dict[str, Any]:
    """Return feasibility, min total SP, one example. Counts are diagnostic only.

    Fast path (default): full HP×Def grid + binary SpD with boundary verify;
    parallel over natures; optional JSONL checkpoint resume.
    PART_G_V4_SOLVER_STAIRCASE=1 enables experimental HP frontier (unsound under
    SP budget — see search_note); linear SpD fallback on monotone fail.
    """
    snap = load_legality()
    base_spe = snap["species"][to_id("Archaludon")]["base_stats"]["spe"]
    # Default: full HP×Def grid + binary SpD (with boundary verify).
    # Opt-in staircase is UNSOUND under Champions SP budget: raising HP/Def
    # lowers spd_hi=min(32,rem-hp-df), so feasibility is not monotone in HP
    # for fixed Def — holes exist (validated vs linear on MT7 t3 Bold).
    # Atk-SP OHKO binary search (ar3) remains valid (no bulk tradeoff).
    use_staircase = os.environ.get("PART_G_V4_SOLVER_STAIRCASE", "").strip() in {
        "1",
        "true",
        "yes",
    }
    if os.environ.get("PART_G_V4_SOLVER_LINEAR", "").strip() in {"1", "true", "yes"}:
        use_staircase = False
    ck_path = _checkpoint_path(prefix)
    done = _load_checkpoint(ck_path)

    jobs: list[tuple] = []
    nature_order: list[str] = []
    for nature in ALL_NATURES:
        min_spe = _min_spe_sp(base_spe, nature) if speed_gate else 0
        if speed_gate and min_spe is None:
            continue
        spe = min_spe or 0
        nature_order.append(nature)
        if nature in done and done[nature].get("n_ok") is not None:
            continue
        jobs.append((nature, conditions, spe, base_spe, use_staircase))

    results_by_nat: dict[str, dict] = {
        n: done[n] for n in nature_order if n in done and done[n].get("n_ok") is not None
    }
    workers = _workers() if jobs else 1
    if jobs and workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futs = [pool.submit(_nature_job, j) for j in jobs]
            for fut in as_completed(futs):
                row = fut.result()
                results_by_nat[row["nature"]] = row
                _append_checkpoint(ck_path, row)
    else:
        for j in jobs:
            row = _nature_job(j)
            results_by_nat[row["nature"]] = row
            _append_checkpoint(ck_path, row)

    # Deterministic merge: ALL_NATURES order (not completion order / worker count).
    diag_counts: dict[str, int] = {}
    min_total: int | None = None
    example: dict | None = None
    any_ok = False
    monotone_fallbacks = 0
    for nature in nature_order:
        row = results_by_nat[nature]
        n_ok = int(row.get("n_ok") or 0)
        ncls = row.get("nature_class") or nature_class(nature)
        monotone_fallbacks += int(row.get("monotone_fallbacks") or 0)
        if n_ok:
            diag_counts[ncls] = diag_counts.get(ncls, 0) + n_ok
            any_ok = True
        mt = row.get("min_total")
        ex = row.get("example")
        if mt is not None and (min_total is None or int(mt) < min_total):
            min_total = int(mt)
            example = ex
        elif (
            mt is not None
            and min_total is not None
            and int(mt) == min_total
            and example is not None
            and ex is not None
        ):
            # Tie-break: earliest nature in ALL_NATURES (already iterating that order).
            pass

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

    # search_note must not mention worker count (byte-identity across PART_G_V4_SOLVER_WORKERS).
    note_extra = (
        "staircase HP×Def + binary SpD with boundary verify; "
        "linear SpD fallback on monotone fail."
        if use_staircase
        else "full HP×Def grid; binary SpD with boundary verify; "
        "linear SpD fallback on monotone fail."
    )
    # Stable class-key order for readers that don't sort_keys.
    diag_sorted = {k: diag_counts[k] for k in sorted(diag_counts)}
    return {
        "feasible": any_ok,
        "min_total_sp": min_total,
        "example": example,
        "solutions_at_minimal_spe_by_class": diag_sorted,
        "count_semantics": (
            "solutions at minimal Spe (gate minimum); Spe fixed at gate min; "
            "not exhaustive totals across Spe SP. Only feasible/infeasible is exact."
        ),
        "search_note": (
            "Spe fixed at min for gate; binary-search min SpD per (HP,Def); "
            "diagnostic SpD>=min counts summed per nature class (not key totals). "
            + note_extra
        ),
        "class_count_note": (
            "Neutral count exceeds +Atk/+SpA/+SpD when HP/Def/Spe constraints match "
            "because neutral has 5 identical full-bulk natures while each +/- class "
            "mixes 2 full-bulk + 1 Def− + 1 Spe− nature (fewer sols). Not double-counting; "
            "Spe is fixed so natures that do not change Def/Spe share the same (HP,Def,SpD) set."
        ),
        "monotone_fallback_count": monotone_fallbacks,
    }


def _timid_zard_extra_key(mt8_t3_timid: dict) -> dict:
    """Verified Timid Mega-Y WB + Adamant Sneasler CC branch (not in 3-cap)."""
    raw = dict(mt8_t3_timid.get("solutions_at_minimal_spe_by_class") or {})
    # Explicit zeros for classes the scorer / readers may check; +Spe:2 was never legal.
    counts = {
        "+Def": int(raw.get("+Def") or 0),
        "+Spe": int(raw.get("+Spe") or 0),
        "+SpD": int(raw.get("+SpD") or 0),
    }
    ex = mt8_t3_timid.get("example")
    spare = None
    if ex and ex.get("total_sp") is not None:
        spare = 66 - int(ex["total_sp"])
    return {
        "scenario": (
            "Adamant Sneasler Close Combat + Timid Mega Charizard Y Weather Ball "
            "(Sun), Spe≥110; Archaludon Stamina Leftovers"
        ),
        "feasible": mt8_t3_timid["feasible"],
        "solutions_at_minimal_spe_by_class": counts,
        "min_total_sp": mt8_t3_timid["min_total_sp"],
        "example": ex,
        "spare_sp": spare,
        "accepted_extra_offer": True,
        "counts_toward_3_relaxation_cap": False,
        "note": (
            "VERIFIED solver counts under legal SP≤32. Example Bold 31/1/23/5 "
            "(total 60, spare 6). Owner hand build 32 HP/1 Def/21 SpD/Spe 4 fails "
            "Timid Weather Ball (169–199 into 197 HP); Bold Spe gate is 5. "
            "+Spe:2 was never legal on this branch (0 cells) and is not stored. "
            "Direct-calc evidence: key_artifacts/mt8_correction_analysis.json."
        ),
        "direct_calc": {
            "timid_wb_vs_example": "survives (solver-verified Bold 31/1/23/5)",
            "adamant_cc_vs_example": "survives (solver-verified Bold 31/1/23/5)",
            "timid_wb_vs_owner_hand_32_1_21_4": {
                "damage_range": [169, 199],
                "defender_hp": 197,
                "survives_max": False,
            },
        },
        "count_semantics": mt8_t3_timid.get("count_semantics"),
        "search_note": mt8_t3_timid.get("search_note"),
        "class_count_note": mt8_t3_timid.get("class_count_note"),
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
            "valid_relaxations": [
                "make Sneasler Jolly (solutions at minimal Spe: +SpD only under legal SP≤32)",
                "drop Weather Ball (equals MT7 t2)",
                "Timid Zard WB extra (not in 3-cap; see timid_zard_extra)",
            ],
            "invalid_relaxation": "drop Spe gate (0 legal SP≤32 solutions)",
            "jolly_sneasler": {
                "feasible": mt8_t4["feasible"],
                "solutions_at_minimal_spe_by_class": mt8_t4["solutions_at_minimal_spe_by_class"],
                "min_total_sp": mt8_t4["min_total_sp"],
                "example": mt8_t4["example"],
                "note": (
                    "Jolly Sneasler + Modest Mega-Y Weather Ball (Sun), Spe≥110: "
                    "feasible under legal SP≤32 with +SpD only. +Def and +Spe have "
                    "zero feasible cells. Binding threat is special (Weather Ball); "
                    "neutral-SpD 32 HP/32 SpD takes 169–199 into 197 HP and does not "
                    "guarantee survival — see key_artifacts/mt8_correction_analysis.json. "
                    "Prior committed +Def:20/+Spe:2 were illegal-SpD>32 artifacts "
                    "(cap-less spd_hi=rem-hp-df); +Spe cells needed SpD=34. "
                    "Counts = solutions at minimal Spe (gate minimum), not totals."
                ),
                "count_semantics": mt8_t4.get("count_semantics"),
                "search_note": mt8_t4.get("search_note"),
                "class_count_note": (
                    "Under legal SP≤32, only the +SpD class is non-zero for this "
                    "fixture. +Def/+Spe/neutral have no feasible cells."
                ),
            },
            "drop_speed_gate": {
                "feasible": mt8_nospe["feasible"],
                "solutions_at_minimal_spe_by_class": mt8_nospe["solutions_at_minimal_spe_by_class"],
                "min_total_sp": mt8_nospe["min_total_sp"],
                "example": mt8_nospe["example"],
                "note": (
                    "With per-stat SP≤32 enforced, dropping Spe gate is INFEASIBLE vs "
                    "Adamant CC + Modest WB. Prior +Def 3 at SP 66 used SpD=34 "
                    "(illegal Champions SP). Not a valid way out."
                ),
                "prior_illegal_spd34_note": (
                    "Pre-fix solver allowed SpD>32 when rem>32; those 3 sols were invalid."
                ),
                "count_semantics": mt8_nospe.get("count_semantics"),
                "search_note": mt8_nospe.get("search_note"),
                "class_count_note": mt8_nospe.get("class_count_note"),
            },
            "timid_zard_extra": _timid_zard_extra_key(mt8_t3_timid),
        },
        "ar1": mt7_t1,
        "ar2_pareto_hp_def_by_class": pareto,
    }
