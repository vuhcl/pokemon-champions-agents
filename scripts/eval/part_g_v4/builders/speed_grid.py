"""Part 0 speed grids, COMMON_SPEED grouping, inverse min-SP (ADR-060)."""
from __future__ import annotations

from collections import defaultdict

from _lib import (
    SPEED_MINUS,
    SPEED_PLUS,
    base_stats,
    champions_spe,
    common_joint,
    load_legality,
    load_showdown,
)

SPE_PLUS = SPEED_PLUS
SPE_MINUS = SPEED_MINUS
ALL_NATURES = [
    "Hardy",
    "Lonely",
    "Brave",
    "Adamant",
    "Naughty",
    "Bold",
    "Docile",
    "Relaxed",
    "Impish",
    "Lax",
    "Timid",
    "Hasty",
    "Serious",
    "Jolly",
    "Naive",
    "Modest",
    "Mild",
    "Quiet",
    "Bashful",
    "Rash",
    "Calm",
    "Gentle",
    "Sassy",
    "Careful",
    "Quirky",
]
DEF_PLUS = {"Bold", "Impish", "Lax", "Relaxed"}
SPD_PLUS = {"Calm", "Careful", "Gentle", "Sassy"}
ATK_PLUS = {"Lonely", "Adamant", "Naughty", "Brave"}
SPA_PLUS = {"Modest", "Mild", "Quiet", "Rash"}


def nature_class(nature: str) -> str:
    if nature in SPE_PLUS:
        return "+Spe"
    if nature in DEF_PLUS:
        return "+Def"
    if nature in SPD_PLUS:
        return "+SpD"
    if nature in ATK_PLUS:
        return "+Atk"
    if nature in SPA_PLUS:
        return "+SpA"
    if nature in SPE_MINUS:
        return "-Spe"
    return "neutral"


def common_speed_distinct(sd: dict, species: str, n: int = 3, joint_limit: int = 8) -> list[dict]:
    """Top n distinct final-Speed values from retained joints (group by Spe, sum chaos weight)."""
    from _lib import to_id

    spreads = (sd["showdown_doubles"]["species"].get(to_id(species)) or {}).get("top_spreads") or []
    spreads = spreads[:joint_limit]
    snap = load_legality()
    base = base_stats(snap, species)["spe"]
    by_spe: dict[int, float] = defaultdict(float)
    for row in spreads:
        nat = row.get("nature") or "Serious"
        spe_sp = int((row.get("evs") or {}).get("spe") or 0)
        s = champions_spe(base, spe_sp, nat)
        by_spe[s] += float(row.get("pct") or 0)
    ranked = sorted(by_spe.items(), key=lambda kv: (-kv[1], -kv[0]))
    out = []
    for spe, w in ranked[:n]:
        out.append({"final_spe": spe, "weight": w})
    return out


def beneficial_spe_nature(species: str) -> str:
    """First Spe+ nature in retained top joints, else Timid."""
    sd = load_showdown()
    from _lib import to_id

    spreads = (sd["showdown_doubles"]["species"].get(to_id(species)) or {}).get("top_spreads") or []
    for row in spreads[:8]:
        nat = row.get("nature") or "Serious"
        if nat in SPE_PLUS:
            return nat
    return "Timid"


def scarf_lines(base_spe: int, has_scarf: bool, species: str | None = None) -> list[dict]:
    """Part 0: only Spe-32 neutral (Serious) and beneficial Spe+ nature, with Scarf."""
    if not has_scarf:
        return []
    ben = beneficial_spe_nature(species) if species else "Timid"
    return [
        {"nature": "Serious", "spe_sp": 32, "spe": champions_spe(base_spe, 32, "Serious", scarf=True)},
        {
            "nature": ben,
            "spe_sp": 32,
            "spe": champions_spe(base_spe, 32, ben, scarf=True),
        },
    ]


def forward_grid(
    snap: dict,
    sd: dict,
    own_species: str,
    opp_species: str,
    own_locked: dict | None = None,
) -> dict:
    """Forward speed grid per Part 0 (no Scarf+TW stack; Scarf = 2 lines only)."""
    ob = base_stats(snap, own_species)["spe"]
    opp_distinct = common_speed_distinct(sd, opp_species)
    opp_max = max(c["final_spe"] for c in opp_distinct) if opp_distinct else 0
    opp_core = [c for c in opp_distinct if c["final_spe"] < opp_max]
    if not opp_core and opp_distinct:
        opp_core = opp_distinct[:]
    dropped_max_share = next((c["weight"] for c in opp_distinct if c["final_spe"] == opp_max), None)

    from _lib import common_item_showdown, to_id

    oitems = common_item_showdown(sd, own_species)
    has_scarf = any(to_id(i.get("name", "")) == "choicescarf" for i in oitems)

    if own_locked:
        own_spe = champions_spe(ob, own_locked["spe_sp"], own_locked["nature"])
        own_lines = [{"fixed": True, "spe": own_spe, **own_locked}]
    else:
        own_joints = common_joint(sd, own_species, 3)
        own_lines = []
        for row in own_joints:
            nat = row.get("nature") or "Serious"
            sp = int((row.get("evs") or {}).get("spe") or 0)
            own_lines.append(
                {
                    "nature": nat,
                    "spe_sp": sp,
                    "spe": champions_spe(ob, sp, nat),
                    "chaos_weight": row.get("chaos_weight", row.get("pct")),
                }
            )
        own_lines.extend(
            {"kind": "scarf", **x} for x in scarf_lines(ob, has_scarf, own_species)
        )
        # Tailwind extras on non-Scarf lines only (no Scarf+TW stack in forward grids)
        for line in own_lines:
            if line.get("kind") == "scarf":
                continue
            if "spe" in line and "spe_tw" not in line:
                line["spe_tw"] = line["spe"] * 2

    opp_lines = []
    for c in opp_distinct:
        role = "max_speed" if c["final_spe"] == opp_max else "core_non_max"
        opp_lines.append(
            {"final_spe": c["final_spe"], "weight": c["weight"], "role": role}
        )
    for c in opp_core:
        c["role"] = "core_non_max"

    # pairwise outcomes for core cells (max own vs each opp core)
    own_max = max(x.get("spe", 0) for x in own_lines if x.get("spe"))
    outcomes = {"outspeeds": [], "ties": [], "outsped": []}
    for oc in opp_core:
        o = oc["final_spe"]
        if own_max > o:
            outcomes["outspeeds"].append(o)
        elif own_max == o:
            outcomes["ties"].append(o)
        else:
            outcomes["outsped"].append(o)

    return {
        "own_species": own_species,
        "opp_species": opp_species,
        "opp_common_speed": opp_distinct,
        "opp_max_spe_dropped": opp_max,
        "opp_max_spe_weight": dropped_max_share,
        "opp_core_cells": opp_core,
        "own_lines": own_lines,
        "own_max_spe": own_max,
        "pairwise_vs_core_using_own_max": outcomes,
    }


def min_spe_four_part(
    snap: dict,
    sd: dict,
    own_species: str,
    opp_species: str,
    locked: dict | None = None,
) -> dict:
    """Inverse min-SP: N / N−1 for neutral + beneficial; reachability allows Scarf+TW stack."""
    from _lib import common_item_showdown, to_id

    base = base_stats(snap, own_species)["spe"]
    opp_cells = common_speed_distinct(sd, opp_species)
    beneficial = beneficial_spe_nature(own_species)
    items = common_item_showdown(sd, own_species)
    has_scarf = any(to_id(i.get("name", "")) == "choicescarf" for i in items)

    def spe_at(nature: str, sp: int, scarf: bool = False, tw: bool = False) -> int:
        s = champions_spe(base, sp, nature, scarf=scarf)
        return s * 2 if tw else s

    def search_mode(nature: str, target_spe: int, budget: int, scarf: bool, tw: bool, label: str) -> dict:
        found = None
        for sp in range(33):
            if spe_at(nature, sp, scarf, tw) > target_spe:
                found = sp
                break
        if found is None:
            return {
                "outcome": "unreachable",
                "n_suffices": None,
                "investment": None,
                "n_minus_1_fails": None,
                "mode": label,
                "final_spe_at_n": None,
                "recorded_scarf_in_common_item": has_scarf,
            }
        if found == 0:
            investment, n_m1 = "no investment needed", None
        else:
            n_m1 = spe_at(nature, found - 1, scarf, tw) <= target_spe
            investment = (
                f"N={found} suffices and N−1 does not" if n_m1 else f"N={found} suffices"
            )
        return {
            "outcome": "shortfall" if found > budget else "fits",
            "n_suffices": found,
            "investment": investment,
            "n_minus_1_fails": n_m1,
            "mode": label,
            "final_spe_at_n": spe_at(nature, found, scarf, tw),
            "recorded_scarf_in_common_item": has_scarf,
        }

    def search_best(nature: str, target_spe: int, budget: int) -> dict:
        # Reachability order: bare → Scarf → TW → Scarf+TW (stack allowed in inverse only)
        modes = [(False, False, "bare")]
        if has_scarf:
            modes.append((True, False, "scarf"))
        modes.append((False, True, "tw"))
        if has_scarf:
            modes.append((True, True, "scarf_tw"))
        for scarf, tw, label in modes:
            r = search_mode(nature, target_spe, budget, scarf, tw, label)
            if r["outcome"] != "unreachable":
                return r
        return {
            "outcome": "unreachable",
            "n_suffices": None,
            "investment": None,
            "n_minus_1_fails": None,
            "mode": "scarf_tw" if has_scarf else "tw",
            "recorded_scarf_in_common_item": has_scarf,
        }

    budget = 66
    if locked:
        budget = 66 - locked.get("other_sp_sum", 0)

    # Own bare max (no item): Spe-32 beneficial
    bare_max = champions_spe(base, 32, beneficial)

    per_cell = []
    for cell in opp_cells:
        tgt = cell["final_spe"]
        bare_n = search_mode("Serious", tgt, budget, False, False, "bare")
        bare_b = search_mode(beneficial, tgt, budget, False, False, "bare")
        scarf_n = (
            search_mode("Serious", tgt, budget, True, False, "scarf") if has_scarf else None
        )
        scarf_b = (
            search_mode(beneficial, tgt, budget, True, False, "scarf") if has_scarf else None
        )
        neutral = search_best("Serious", tgt, budget)
        beneficial_result = None
        need_ben = (
            neutral["outcome"] != "fits"
            or (neutral.get("n_suffices") or 0) > 32
            or beneficial in {row.get("nature") for row in common_joint(sd, own_species)}
        )
        if need_ben:
            beneficial_result = search_best(beneficial, tgt, budget)
        per_cell.append(
            {
                "opp_final_spe": tgt,
                "opp_weight": cell["weight"],
                "bare_max_own_spe": bare_max,
                "bare_unreachable_vs_cell": bare_max <= tgt,
                "bare_neutral": bare_n,
                "bare_beneficial": bare_b,
                "scarf_neutral": scarf_n,
                "scarf_beneficial": scarf_b,
                "neutral": neutral,
                "beneficial": beneficial_result,
            }
        )
    return {
        "own_species": own_species,
        "opp_species": opp_species,
        "budget_R": budget,
        "beneficial_nature": beneficial,
        "has_scarf_in_common_item": has_scarf,
        "bare_max_spe": bare_max,
        "note": (
            f"Bare (no-item) max Spe={bare_max} with {beneficial} Spe-32; "
            "unreachable against every opp cell when bare_unreachable_vs_cell is true for all. "
            "IS Scarf+TW stack is reachability-only (not forward grids)."
        ),
        "per_cell": per_cell,
    }


def common_item_ingame(ing: dict, species: str, max_items: int = 5, cutoff: float = 0.90) -> dict:
    """In-game COMMON_ITEM: descending pct until cumulative >= cutoff, max max_items."""
    from _lib import to_id

    sid = to_id(species)
    items = (ing["ingame_doubles"]["species"].get(sid) or {}).get("common_items") or []
    out = []
    cum = 0.0
    for row in items:
        if len(out) >= max_items:
            break
        name = row.get("name") or ""
        pct = float(row.get("pct") or 0)
        out.append({"name": name, "pct": pct})
        cum += pct
        if cum >= cutoff * 100:
            break
    return {
        "items": out,
        "cumulative_pct": cum,
        "cutoff_rule": "include entries until cumulative >= 90%; max 5 slots; 'nothing' counts as a slot and toward cumulative",
        "source": "ingame_doubles",
    }
