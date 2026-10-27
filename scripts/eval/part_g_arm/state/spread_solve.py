"""Arm spread solver: one 66-SP spread closest in L1 to filtered joint refs.

Monotone constraints only (survive / outspeed / KO). Uses in-process calc with
persist=False — never writes key_artifacts. Not the key builder's enumerator.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Callable

_BUILDERS = Path(__file__).resolve().parents[2] / "part_g_v4" / "builders"
if str(_BUILDERS) not in sys.path:
    sys.path.insert(0, str(_BUILDERS))

# Prefer in-process; probes never persist.
os.environ.setdefault("PART_G_V4_CALC_BACKEND", "inprocess")

from _lib import (  # noqa: E402
    champions_spe,
    load_legality,
    load_showdown,
    to_id,
)
from calc_store import calculate  # noqa: E402
from speed_grid import ALL_NATURES  # noqa: E402

STAT_KEYS = ("hp", "atk", "def", "spa", "spd", "spe")
SP_CAP = 32
SP_BUDGET = 66
MONOTONE_TYPES = frozenset({"survive", "outspeed", "ko"})
REFUSED_HINTS = frozenset({
    "underspeed", "under_speed", "trick_room", "trickroom", "exact", "exact_stat",
    "exact_stats", "max_speed_only", "slower", "speed_tie_lose",
})


def _sp_dict(raw: dict[str, Any] | None) -> dict[str, int]:
    raw = raw or {}
    return {k: int(raw.get(k) or 0) for k in STAT_KEYS}


def _l1(a: dict[str, int], b: dict[str, int]) -> int:
    return sum(abs(a[k] - b[k]) for k in STAT_KEYS)


def joint_refs_66(species: str) -> tuple[list[dict[str, Any]], int]:
    """All listed Showdown joints for species with SP sum exactly 66.

    Same accessor path as common_joint (top_spreads), full list not sliced.
    Returns (entries with filtered_rank 1..n, n_dropped).
    """
    sd = load_showdown()
    sid = to_id(species)
    rows = (sd["showdown_doubles"]["species"].get(sid) or {}).get("top_spreads") or []
    kept: list[dict[str, Any]] = []
    dropped = 0
    for i, r in enumerate(rows):
        evs = _sp_dict(r.get("evs"))
        if sum(evs.values()) != SP_BUDGET:
            dropped += 1
            continue
        kept.append(
            {
                "filtered_rank": len(kept) + 1,
                "file_rank": i + 1,
                "nature": r.get("nature") or "Serious",
                "sp": evs,
                "weight": float(r.get("chaos_weight", r.get("pct") or 0.0)),
            }
        )
    return kept, dropped


def list_mirror_speeds(species: str) -> dict[str, Any]:
    """Helper: Spe stats from 66-SP joints (for stating an outspeed target)."""
    snap = load_legality()
    entry = snap["species"].get(to_id(species))
    if not entry:
        return {"status": "not_found", "species": species}
    base = entry["base_stats"]["spe"]
    refs, dropped = joint_refs_66(species)
    cells = []
    for r in refs:
        cells.append(
            {
                "filtered_rank": r["filtered_rank"],
                "nature": r["nature"],
                "spe_sp": r["sp"]["spe"],
                "spe_stat": champions_spe(base, r["sp"]["spe"], r["nature"]),
                "weight": r["weight"],
            }
        )
    return {
        "status": "ok",
        "species": entry["name"],
        "base_spe": base,
        "dropped_non_66": dropped,
        "cells": cells,
        "note": (
            "Pass an explicit outspeed target_spe (integer Spe stat) to solve_spread; "
            "this helper only lists joint Spe cells."
        ),
    }


def _move_category(move: str) -> str | None:
    snap = load_legality()
    m = (snap.get("moves") or {}).get(to_id(move))
    if not m:
        return None
    return m.get("category")


def _calc_once(attacker: dict, defender: dict, move: str, field: dict | None) -> dict[str, Any]:
    req = {
        "attacker": attacker,
        "defender": defender,
        "move": move,
        "field": field or {"gameType": "Doubles"},
    }
    rec = calculate(req, "probe", persist=False)
    return rec.get("response") or {}


def _survives(attacker: dict, defender: dict, move: str, field: dict | None) -> bool:
    resp = _calc_once(attacker, defender, move, field)
    if "error" in resp:
        return False
    raw = resp.get("raw") or {}
    dmg = raw.get("damage") or []
    if not dmg:
        return True
    hp = (raw.get("stats") or {}).get("defender", {}).get("hp") or 0
    return max(dmg) < hp


def _ohkoes(attacker: dict, defender: dict, move: str, field: dict | None) -> bool:
    resp = _calc_once(attacker, defender, move, field)
    if "error" in resp:
        return False
    raw = resp.get("raw") or {}
    dmg = raw.get("damage") or []
    if not dmg:
        return False
    hp = (raw.get("stats") or {}).get("defender", {}).get("hp") or 0
    return min(dmg) >= hp


def _mon(
    species: str,
    nature: str,
    sp: dict[str, int],
    *,
    ability: str,
    item: str = "",
) -> dict[str, Any]:
    return {
        "species": species,
        "level": 50,
        "nature": nature,
        "ability": ability,
        "item": item or "",
        "evs": dict(sp),
    }


def _refuse_non_monotone(constraints: list[dict[str, Any]]) -> str | None:
    for c in constraints:
        if not isinstance(c, dict):
            return "each constraint must be an object"
        ctype = str(c.get("type") or "").strip().lower()
        if ctype in REFUSED_HINTS or ctype not in MONOTONE_TYPES:
            return (
                f"refused non-monotone or unknown constraint type {ctype!r}; "
                "v1 accepts only survive, outspeed, and ko"
            )
    return None


def _parse_constraints(
    species: str,
    ability: str,
    item: str,
    constraints: list[dict[str, Any]],
) -> tuple[list[Callable[[str, dict[str, int]], bool]], list[dict[str, Any]], str | None]:
    """Return (predicates, normalized_meta, error)."""
    preds: list[Callable[[str, dict[str, int]], bool]] = []
    meta: list[dict[str, Any]] = []
    snap = load_legality()
    base_spe = snap["species"][to_id(species)]["base_stats"]["spe"]

    for c in constraints:
        ctype = str(c.get("type") or "").strip().lower()
        if ctype == "outspeed":
            if "target_spe" in c:
                target = int(c["target_spe"])
            elif "species" in c:
                opp = snap["species"].get(to_id(str(c["species"])))
                if not opp:
                    return [], [], f"outspeed opponent species not found: {c.get('species')!r}"
                opp_nat = str(c.get("nature") or "Serious")
                opp_sp = int(c.get("spe_sp") or 0)
                target = champions_spe(opp["base_stats"]["spe"], opp_sp, opp_nat)
            else:
                return [], [], "outspeed needs target_spe or species (+ nature, spe_sp)"
            meta.append({"type": "outspeed", "target_spe": target})

            def pred(nature: str, sp: dict[str, int], _t=target, _b=base_spe) -> bool:
                return champions_spe(_b, sp["spe"], nature) >= _t

            preds.append(pred)
            continue

        if ctype == "survive":
            att = c.get("attacker")
            move = c.get("move")
            if not isinstance(att, dict) or not move:
                return [], [], "survive needs attacker object and move"
            for key in ("species", "ability"):
                if not att.get(key):
                    return [], [], f"survive attacker missing {key}"
            field = c.get("field") if isinstance(c.get("field"), dict) else {"gameType": "Doubles"}
            att_sp = _sp_dict(att.get("sp") or att.get("evs"))
            att_mon = _mon(
                str(att["species"]),
                str(att.get("nature") or "Serious"),
                att_sp,
                ability=str(att["ability"]),
                item=str(att.get("item") or ""),
            )
            meta.append(
                {
                    "type": "survive",
                    "move": move,
                    "attacker": att_mon["species"],
                    "attacker_nature": att_mon["nature"],
                }
            )

            def pred(
                nature: str,
                sp: dict[str, int],
                _att=att_mon,
                _move=str(move),
                _field=field,
                _ab=ability,
                _it=item,
                _spn=species,
            ) -> bool:
                defn = _mon(_spn, nature, sp, ability=_ab, item=_it)
                return _survives(_att, defn, _move, _field)

            preds.append(pred)
            continue

        if ctype == "ko":
            de = c.get("defender")
            move = c.get("move")
            if not isinstance(de, dict) or not move:
                return [], [], "ko needs defender object and move"
            for key in ("species", "ability"):
                if not de.get(key):
                    return [], [], f"ko defender missing {key}"
            field = c.get("field") if isinstance(c.get("field"), dict) else {"gameType": "Doubles"}
            de_sp = _sp_dict(de.get("sp") or de.get("evs"))
            de_mon = _mon(
                str(de["species"]),
                str(de.get("nature") or "Serious"),
                de_sp,
                ability=str(de["ability"]),
                item=str(de.get("item") or ""),
            )
            cat = _move_category(str(move))
            meta.append({"type": "ko", "move": move, "defender": de_mon["species"], "category": cat})

            def pred(
                nature: str,
                sp: dict[str, int],
                _de=de_mon,
                _move=str(move),
                _field=field,
                _ab=ability,
                _it=item,
                _spn=species,
            ) -> bool:
                att = _mon(_spn, nature, sp, ability=_ab, item=_it)
                return _ohkoes(att, _de, _move, _field)

            preds.append(pred)
            continue

        return [], [], f"unknown constraint type {ctype!r}"

    return preds, meta, None


def _feasible(preds: list[Callable[[str, dict[str, int]], bool]], nature: str, sp: dict[str, int]) -> bool:
    return all(p(nature, sp) for p in preds)


def _min_spe_for(preds_outspeed_targets: list[int], base_spe: int, nature: str) -> int | None:
    if not preds_outspeed_targets:
        return 0
    need = max(preds_outspeed_targets)
    for spe in range(SP_CAP + 1):
        if champions_spe(base_spe, spe, nature) >= need:
            return spe
    return None


def _outspeed_targets(meta: list[dict[str, Any]]) -> list[int]:
    return [int(m["target_spe"]) for m in meta if m.get("type") == "outspeed"]


def _fill_toward(
    frontier: dict[str, int],
    target: dict[str, int],
) -> dict[str, int] | None:
    """x >= frontier, sum 66, cap 32, minimize L1 to target."""
    x = dict(frontier)
    if any(x[k] > SP_CAP for k in STAT_KEYS):
        return None
    used = sum(x.values())
    if used > SP_BUDGET:
        return None
    rem = SP_BUDGET - used
    # Fill deficits first (reduces L1).
    while rem > 0:
        progressed = False
        # Prefer largest remaining deficit
        deficits = sorted(
            ((target[k] - x[k], k) for k in STAT_KEYS if x[k] < target[k] and x[k] < SP_CAP),
            reverse=True,
        )
        if deficits:
            _, k = deficits[0]
            x[k] += 1
            rem -= 1
            progressed = True
        if progressed:
            continue
        # Must overshoot: dump into any under-cap stat (L1 +1 each). Prefer target's
        # highest-weight-ish: higher target first, then STAT_KEYS order.
        cands = [k for k in sorted(STAT_KEYS, key=lambda s: (-target[s], STAT_KEYS.index(s))) if x[k] < SP_CAP]
        if not cands:
            return None
        x[cands[0]] += 1
        rem -= 1
    return x


def _frontier_for_nature(
    preds: list[Callable[[str, dict[str, int]], bool]],
    nature: str,
    base_spe: int,
    outspeed_tgts: list[int],
    *,
    budget_cells: int | None,
    t0: float,
    time_budget_s: float | None,
) -> tuple[list[dict[str, int]], str | None]:
    """Minimal feasible vectors (Spe fixed at outspeed min; Atk/SpA free only if needed).

    Mechanism: fewest total SP via binary SpD per (HP,Def) with Spe fixed, then
    keep Pareto-minimal among found feasible cells. Returns (frontier, stop_reason).
    """
    min_spe = _min_spe_for(outspeed_tgts, base_spe, nature)
    if min_spe is None:
        return [], None
    rem = SP_BUDGET - min_spe
    # Pure outspeed (and nothing else that needs bulk/offense): one minimal vector.
    zero = {
        "hp": 0,
        "atk": 0,
        "def": 0,
        "spa": 0,
        "spd": 0,
        "spe": min_spe,
    }
    if preds and _feasible(preds, nature, zero):
        return [zero], None

    # Does any constraint need Atk/SpA? Detect by testing all-zero offensive with max bulk.
    probe_bulk = {
        "hp": min(SP_CAP, rem),
        "atk": 0,
        "def": 0,
        "spa": 0,
        "spd": 0,
        "spe": min_spe,
    }
    left = rem - probe_bulk["hp"]
    probe_bulk["def"] = min(SP_CAP, left)
    left -= probe_bulk["def"]
    probe_bulk["spd"] = min(SP_CAP, left)

    needs_atk = False
    needs_spa = False
    if preds and not _feasible(preds, nature, probe_bulk):
        for off in ("atk", "spa"):
            trial = dict(probe_bulk)
            steal = min(SP_CAP, trial["hp"])
            trial[off] = steal
            trial["hp"] = 0
            if _feasible(preds, nature, trial):
                if off == "atk":
                    needs_atk = True
                else:
                    needs_spa = True

    found: list[dict[str, int]] = []
    cells = 0
    stop: str | None = None

    def timed_out() -> bool:
        return time_budget_s is not None and (time.perf_counter() - t0) > time_budget_s

    atk_range = range(SP_CAP + 1) if needs_atk else (0,)
    spa_range = range(SP_CAP + 1) if needs_spa else (0,)

    for atk in atk_range:
        for spa in spa_range:
            rem2 = rem - atk - spa
            if rem2 < 0:
                continue
            for hp in range(SP_CAP + 1):
                for df in range(SP_CAP + 1):
                    if hp + df > rem2:
                        continue
                    if timed_out():
                        return found, "time"
                    if budget_cells is not None and cells >= budget_cells:
                        return found, "budget"
                    cells += 1
                    spd_hi = min(SP_CAP, rem2 - hp - df)
                    lo, hi = 0, spd_hi + 1
                    best = None
                    while lo < hi:
                        mid = (lo + hi) // 2
                        sp = {
                            "hp": hp,
                            "atk": atk,
                            "def": df,
                            "spa": spa,
                            "spd": mid,
                            "spe": min_spe,
                        }
                        if _feasible(preds, nature, sp):
                            best = mid
                            hi = mid
                        else:
                            lo = mid + 1
                    if best is None:
                        continue
                    if best > 0:
                        sp_lo = {
                            "hp": hp,
                            "atk": atk,
                            "def": df,
                            "spa": spa,
                            "spd": best - 1,
                            "spe": min_spe,
                        }
                        if _feasible(preds, nature, sp_lo):
                            best = next(
                                (
                                    s
                                    for s in range(spd_hi + 1)
                                    if _feasible(
                                        preds,
                                        nature,
                                        {
                                            "hp": hp,
                                            "atk": atk,
                                            "def": df,
                                            "spa": spa,
                                            "spd": s,
                                            "spe": min_spe,
                                        },
                                    )
                                ),
                                None,
                            )
                            if best is None:
                                continue
                    found.append(
                        {
                            "hp": hp,
                            "atk": atk,
                            "def": df,
                            "spa": spa,
                            "spd": best,
                            "spe": min_spe,
                        }
                    )

    # Pareto-minimal under componentwise order
    minimal: list[dict[str, int]] = []
    for v in found:
        if any(
            all(u[k] <= v[k] for k in STAT_KEYS) and any(u[k] < v[k] for k in STAT_KEYS)
            for u in found
            if u is not v
        ):
            continue
        # also skip exact duplicates
        if any(all(u[k] == v[k] for k in STAT_KEYS) for u in minimal):
            continue
        minimal.append(v)
    return minimal, stop


def _verify_constraints(
    species: str,
    ability: str,
    item: str,
    nature: str,
    sp: dict[str, int],
    constraints: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    out = []
    for c in constraints:
        ctype = str(c.get("type") or "").strip().lower()
        if ctype == "outspeed":
            snap = load_legality()
            base = snap["species"][to_id(species)]["base_stats"]["spe"]
            got = champions_spe(base, sp["spe"], nature)
            target = None
            if "target_spe" in c:
                target = int(c["target_spe"])
            elif "species" in c:
                opp = snap["species"][to_id(str(c["species"]))]
                target = champions_spe(
                    opp["base_stats"]["spe"],
                    int(c.get("spe_sp") or 0),
                    str(c.get("nature") or "Serious"),
                )
            ok = target is not None and got >= target
            out.append({"type": "outspeed", "ok": ok, "spe_stat": got, "target_spe": target})
        elif ctype == "survive":
            att = c["attacker"]
            att_mon = _mon(
                str(att["species"]),
                str(att.get("nature") or "Serious"),
                _sp_dict(att.get("sp") or att.get("evs")),
                ability=str(att["ability"]),
                item=str(att.get("item") or ""),
            )
            defn = _mon(species, nature, sp, ability=ability, item=item)
            field = c.get("field") if isinstance(c.get("field"), dict) else {"gameType": "Doubles"}
            ok = _survives(att_mon, defn, str(c["move"]), field)
            out.append({"type": "survive", "ok": ok, "move": c["move"], "attacker": att_mon["species"]})
        elif ctype == "ko":
            de = c["defender"]
            de_mon = _mon(
                str(de["species"]),
                str(de.get("nature") or "Serious"),
                _sp_dict(de.get("sp") or de.get("evs")),
                ability=str(de["ability"]),
                item=str(de.get("item") or ""),
            )
            att = _mon(species, nature, sp, ability=ability, item=item)
            field = c.get("field") if isinstance(c.get("field"), dict) else {"gameType": "Doubles"}
            ok = _ohkoes(att, de_mon, str(c["move"]), field)
            out.append({"type": "ko", "ok": ok, "move": c["move"], "defender": de_mon["species"]})
    return out


def solve_spread(
    species: str,
    constraints: list[dict[str, Any]],
    *,
    ability: str | None = None,
    item: str = "Leftovers",
    time_budget_s: float | None = 30.0,
    cell_budget: int | None = None,
) -> dict[str, Any]:
    """Find one good 66-SP spread for monotone constraints.

    status: optimal | feasible | infeasible | unknown
    """
    if not isinstance(constraints, list) or not constraints:
        return {
            "status": "unknown",
            "error": "constraints must be a non-empty list",
            "no_reference": False,
        }
    refused = _refuse_non_monotone(constraints)
    if refused:
        return {"status": "unknown", "error": refused, "refused": True, "no_reference": False}

    snap = load_legality()
    sp_entry = snap["species"].get(to_id(species))
    if not sp_entry:
        return {"status": "unknown", "error": f"species not found: {species!r}", "no_reference": False}
    if ability is None:
        abs_ = sp_entry.get("abilities") or {}
        ability = abs_.get("0") or abs_.get("1") or abs_.get("H")
        if not ability:
            return {"status": "unknown", "error": "species has no ability in snapshot", "no_reference": False}
    ability = str(ability)
    item = str(item or "")

    preds, meta, err = _parse_constraints(species, ability, item, constraints)
    if err:
        return {"status": "unknown", "error": err, "no_reference": False}

    refs, n_dropped = joint_refs_66(species)
    no_reference = refs == []
    base_spe = sp_entry["base_stats"]["spe"]
    outspeed_tgts = _outspeed_targets(meta)
    t0 = time.perf_counter()
    objective = (
        "Among spreads that meet every stated constraint, use all 66 SP "
        "(max 32 per stat), minimize L1 distance to a 66-SP Showdown joint "
        "reference; ties prefer the higher-weight entry."
    )

    def _better(a: dict[str, Any], b: dict[str, Any]) -> bool:
        da, db = a.get("distance"), b.get("distance")
        if da is None and db is not None:
            return False
        if db is None and da is not None:
            return True
        if da is not None and db is not None:
            if da != db:
                return da < db
            wa = (a.get("matched_entry") or {}).get("weight") or 0.0
            wb = (b.get("matched_entry") or {}).get("weight") or 0.0
            if wa != wb:
                return wa > wb
            ra = (a.get("matched_entry") or {}).get("filtered_rank") or 999
            rb = (b.get("matched_entry") or {}).get("filtered_rank") or 999
            return ra < rb
        return sum(a["sp"].values()) < sum(b["sp"].values())

    def try_nature_set(
        natures: list[str],
        *,
        same_nature_refs_only: bool,
    ) -> dict[str, Any] | None:
        """Return best candidate dict or None if none feasible in this set."""
        best: dict[str, Any] | None = None
        any_feasible = False
        hit_limit = False
        for nature in natures:
            if same_nature_refs_only:
                ref_list = [r for r in refs if r["nature"] == nature]
                targets = ref_list
            else:
                ref_list = [r for r in refs if r["nature"] == nature]
                targets = refs  # L1 to any joint vector when nature is constraint-driven
            for r in ref_list:
                if _feasible(preds, nature, r["sp"]):
                    any_feasible = True
                    cand = {
                        "nature": nature,
                        "sp": dict(r["sp"]),
                        "distance": 0,
                        "matched_entry": r,
                        "unallocated": 0,
                    }
                    if best is None or _better(cand, best):
                        best = cand
            if best and best.get("distance") == 0 and best["nature"] == nature:
                continue

            frontier, stop = _frontier_for_nature(
                preds,
                nature,
                base_spe,
                outspeed_tgts,
                budget_cells=cell_budget,
                t0=t0,
                time_budget_s=time_budget_s,
            )
            if stop:
                hit_limit = True
            if not frontier:
                continue
            any_feasible = True
            if not targets:
                continue
            for fr in frontier:
                for r in targets:
                    filled = _fill_toward(fr, r["sp"])
                    if filled is None:
                        continue
                    if not _feasible(preds, nature, filled):
                        continue
                    dist = _l1(filled, r["sp"])
                    cand = {
                        "nature": nature,
                        "sp": filled,
                        "distance": dist,
                        "matched_entry": r,
                        "unallocated": 0,
                        "frontier": fr,
                    }
                    if best is None or _better(cand, best):
                        best = cand
        if best is None and not any_feasible and not hit_limit:
            return None
        if best is None and hit_limit:
            return {"_limit": True}
        if best is None:
            return None
        best["_limit"] = hit_limit
        return best

    # --- no reference: minimal feasible, leave remainder unallocated ---
    if no_reference:
        natures = list(ALL_NATURES)
        best_min: dict[str, Any] | None = None
        natures_tried = []
        hit_limit = False
        for nature in natures:
            natures_tried.append(nature)
            frontier, stop = _frontier_for_nature(
                preds,
                nature,
                base_spe,
                outspeed_tgts,
                budget_cells=cell_budget,
                t0=t0,
                time_budget_s=time_budget_s,
            )
            if stop:
                hit_limit = True
            for fr in frontier:
                total = sum(fr.values())
                cand = {
                    "nature": nature,
                    "sp": dict(fr),
                    "distance": None,
                    "matched_entry": None,
                    "unallocated": SP_BUDGET - total,
                    "total_sp": total,
                }
                if best_min is None or cand["total_sp"] < best_min["total_sp"]:
                    best_min = cand
                elif cand["total_sp"] == best_min["total_sp"]:
                    if natures.index(nature) < natures.index(best_min["nature"]):
                        best_min = cand
        if best_min is None:
            status = "unknown" if hit_limit else "infeasible"
            return {
                "status": status,
                "spread": None,
                "objective": objective,
                "no_reference": True,
                "dropped_non_66": n_dropped,
                "constraint_results": None,
                "natures_covered": natures_tried if status == "infeasible" else natures_tried,
                "nature_mismatch": False,
                "message": (
                    "no feasible spread under stated constraints"
                    if status == "infeasible"
                    else "search budget/time exhausted before proving infeasibility"
                ),
            }
        verified = _verify_constraints(
            species, ability, item, best_min["nature"], best_min["sp"], constraints
        )
        return {
            "status": "feasible" if hit_limit else "optimal",
            "spread": {"nature": best_min["nature"], **best_min["sp"]},
            "objective": objective,
            "matched_entry": None,
            "rank": None,
            "distance": None,
            "weight": None,
            "unallocated": best_min["unallocated"],
            "no_reference": True,
            "dropped_non_66": n_dropped,
            "constraint_results": verified,
            "nature_mismatch": False,
            "claim_wording": (
                f"minimal feasible spread ({best_min['total_sp']} SP); "
                "no 66-SP joint reference for this species in the pinned Showdown data"
            ),
        }

    # Reference natures first
    ref_natures = []
    for r in refs:
        if r["nature"] not in ref_natures:
            ref_natures.append(r["nature"])
    hit = try_nature_set(ref_natures, same_nature_refs_only=True)
    nature_mismatch = False
    if hit is None or (hit.get("_limit") and hit.get("sp") is None):
        all_hit = try_nature_set(list(ALL_NATURES), same_nature_refs_only=False)
        if all_hit and all_hit.get("sp") is not None:
            hit = all_hit
            nature_mismatch = hit["nature"] not in ref_natures
        elif all_hit and all_hit.get("_limit"):
            return {
                "status": "unknown",
                "spread": None,
                "objective": objective,
                "no_reference": False,
                "dropped_non_66": n_dropped,
                "message": "search budget/time exhausted before finding a feasible spread",
                "nature_mismatch": False,
            }
        else:
            return {
                "status": "infeasible",
                "spread": None,
                "objective": objective,
                "no_reference": False,
                "dropped_non_66": n_dropped,
                "constraint_results": None,
                "natures_covered": list(ALL_NATURES),
                "nature_mismatch": False,
                "message": "no feasible spread under stated constraints (all natures covered)",
            }

    assert hit is not None and hit.get("sp") is not None
    limit = bool(hit.get("_limit"))
    entry = hit.get("matched_entry")
    verified = _verify_constraints(species, ability, item, hit["nature"], hit["sp"], constraints)
    if not all(v.get("ok") for v in verified):
        return {
            "status": "unknown",
            "error": "final spread failed calc re-verify",
            "spread": {"nature": hit["nature"], **hit["sp"]},
            "constraint_results": verified,
            "no_reference": False,
        }
    rank = entry["filtered_rank"] if entry else None
    dist = hit.get("distance")
    claim = None
    if rank is not None and dist is not None:
        claim = (
            f"within {dist} SP of rank {rank} of the 66-SP joint spreads "
            "in the pinned Showdown data"
        )
    return {
        "status": "feasible" if limit else "optimal",
        "spread": {"nature": hit["nature"], **hit["sp"]},
        "objective": objective,
        "matched_entry": {
            "filtered_rank": rank,
            "file_rank": entry.get("file_rank") if entry else None,
            "nature": entry.get("nature") if entry else None,
            "sp": entry.get("sp") if entry else None,
            "weight": entry.get("weight") if entry else None,
        }
        if entry
        else None,
        "rank": rank,
        "distance": dist,
        "weight": entry.get("weight") if entry else None,
        "unallocated": 0,
        "no_reference": False,
        "dropped_non_66": n_dropped,
        "constraint_results": verified,
        "nature_mismatch": nature_mismatch,
        "claim_wording": claim,
    }
