#!/usr/bin/env python3
"""AR3 Mega Charizard X Belly Drum chain — calc-backed keys (Tough Claws explicit)."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib import (
    SHOWDOWN_THREAT_USAGE_CUTOFF,
    champions_hp,
    champions_spe,
    common_joint,
    load_legality,
    load_showdown,
    showdown_threats_ge_cutoff,
    to_id,
)
from calc_store import calculate, health
from speed_grid import common_item_ingame  # pattern only; we need showdown cutoff

OUT = Path(__file__).resolve().parents[1] / "key_artifacts" / "derived_keys.json"

CX = "Charizard-Mega-X"
CX_ABILITY = "Tough Claws"
CX_ITEM = "Charizardite X"
PRIM = "Primarina"
THREAT_USAGE_CUTOFF = SHOWDOWN_THREAT_USAGE_CUTOFF


def common_item_part0(sd: dict, species: str, max_items: int = 5, cutoff: float = 0.90) -> dict:
    from _lib import common_item_showdown

    items = common_item_showdown(sd, species)
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
        "focus_sash_in_common_item": any(to_id(i["name"]) == "focussash" for i in out),
        "focus_sash_raw_pct": next(
            (float(r.get("pct") or 0) for r in items if to_id(r.get("name") or "") == "focussash"),
            None,
        ),
        "rule": "Part 0 COMMON_ITEM: descending until cumulative ≥90%, max 5; 'nothing' counts",
    }


def _cx(nature: str, spread: dict, boosts: dict | None = None) -> dict:
    mon = {
        "species": CX,
        "level": 50,
        "nature": nature,
        "ability": CX_ABILITY,
        "item": CX_ITEM,
        "evs": spread,
    }
    if boosts:
        mon["boosts"] = boosts
    return mon


def _prim(row: dict, item: str) -> dict:
    nat = row.get("nature") or "Modest"
    evs = row.get("evs") or {}
    spread = {k: min(32, int(evs.get(k) or 0)) for k in ("hp", "atk", "def", "spa", "spd", "spe")}
    # Ability: Torrent is slot 0; ASSUME-STATE default for unspecified
    return {
        "species": PRIM,
        "level": 50,
        "nature": nat,
        "ability": "Torrent",
        "item": item,
        "evs": spread,
    }


def min_atk_for_ohko(nature: str, move: str, prim: dict, field: dict) -> dict:
    """Binary search min Atk SP for guaranteed OHKO at +6 Atk under Tough Claws."""
    best = None
    best_rec = None
    for atk in range(33):
        spread = {"hp": 0, "atk": atk, "def": 0, "spa": 0, "spd": 0, "spe": 0}
        rec = calculate(
            {
                "attacker": _cx(nature, spread, {"atk": 6}),
                "defender": prim,
                "move": move,
                "field": field,
            },
            f"ar3_probe_{to_id(move)}_{nature}_{atk}",
            persist=False,
        )
        resp = rec.get("response") or {}
        if "error" in resp:
            return {"error": resp["error"], "move": move, "nature": nature}
        raw = resp.get("raw") or {}
        dmg = raw.get("damage") or []
        if not dmg:
            # immune / zero
            return {
                "move": move,
                "nature": nature,
                "guaranteed_ohko": False,
                "min_atk_sp": None,
                "reason": "zero_damage_or_immune",
                "desc": raw.get("desc"),
            }
        hp = (raw.get("stats") or {}).get("defender", {}).get("hp") or 0
        if min(dmg) >= hp:
            best = atk
            best_rec = rec
            break
    if best is None:
        # persist max attempt
        calculate(
            {
                "attacker": _cx(nature, {"hp": 0, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 0}, {"atk": 6}),
                "defender": prim,
                "move": move,
                "field": field,
            },
            f"ar3_no_ohko_{to_id(move)}_{nature}",
            persist=True,
        )
        return {
            "move": move,
            "nature": nature,
            "guaranteed_ohko": False,
            "min_atk_sp": None,
            "at_atk_32": (best_rec or {}).get("key") if best_rec else None,
            "note": "no guaranteed OHKO even at Atk-32",
        }
    # persist the min
    calculate(
        {
            "attacker": _cx(nature, {"hp": 0, "atk": best, "def": 0, "spa": 0, "spd": 0, "spe": 0}, {"atk": 6}),
            "defender": prim,
            "move": move,
            "field": field,
        },
        f"ar3_ohko_{to_id(move)}_{nature}_atk{best}",
        persist=True,
    )
    return {
        "move": move,
        "nature": nature,
        "guaranteed_ohko": True,
        "min_atk_sp": best,
        "key": best_rec.get("key") if best_rec else None,
        "ability": CX_ABILITY,
    }


def aqua_jet_survival(cx_nature: str, cx_spread: dict, prim: dict, field: dict) -> dict:
    """Two Aqua Jets before attack: AJ into full HP, then BD, then AJ. Prefer ar3_hp_fix for worst-joint."""
    snap = load_legality()
    base_hp = snap["species"][to_id(CX)]["base_stats"]["hp"]
    # Prefer calc defender HP; champions_hp = base + SP + 75
    aj1 = calculate(
        {
            "attacker": {
                "species": PRIM,
                "level": 50,
                "nature": prim["nature"],
                "ability": prim["ability"],
                "item": prim["item"],
                "evs": prim["evs"],
            },
            "defender": _cx(cx_nature, cx_spread),
            "move": "Aqua Jet",
            "field": field,
        },
        "ar3_aquajet_into_full",
        persist=True,
    )
    raw1 = (aj1.get("response") or {}).get("raw") or {}
    max_hp = (raw1.get("stats") or {}).get("defender", {}).get("hp") or champions_hp(
        base_hp, int(cx_spread.get("hp") or 0)
    )
    d1 = (aj1.get("key") or {}).get("max_damage") or 0
    after_aj1 = max_hp - d1
    bd_cost = max_hp // 2
    after_bd = after_aj1 - bd_cost
    remaining_from_full = max_hp - bd_cost
    aj2 = calculate(
        {
            "attacker": {
                "species": PRIM,
                "level": 50,
                "nature": prim["nature"],
                "ability": prim["ability"],
                "item": prim["item"],
                "evs": prim["evs"],
            },
            "defender": _cx(cx_nature, cx_spread),
            "move": "Aqua Jet",
            "field": field,
        },
        "ar3_aquajet_into_post_bd",
        persist=True,
    )
    d2 = (aj2.get("key") or {}).get("max_damage") or 0
    after_aj2 = after_bd - d2
    return {
        "model": "AJ(prio)+BD then AJ(prio) before attack; AJ damage from calc max roll",
        "cx_max_hp": max_hp,
        "aj1_max": d1,
        "after_aj1": after_aj1,
        "belly_drum_cost": bd_cost,
        "after_bd": after_bd,
        "post_belly_drum_remaining_from_full": remaining_from_full,
        "aj2_max": d2,
        "after_aj2": after_aj2,
        "survives_both_aj": after_aj2 > 0,
        "aj1_desc": (aj1.get("key") or {}).get("desc"),
        "aj2_desc": (aj2.get("key") or {}).get("desc"),
        "setup_turns_plus_one": 2,
    }


def flare_blitz_recoil(nature: str, spread: dict, prim: dict, field: dict) -> dict:
    rec = calculate(
        {
            "attacker": _cx(nature, spread, {"atk": 6}),
            "defender": prim,
            "move": "Flare Blitz",
            "field": field,
        },
        "ar3_flareblitz_plus6",
        persist=True,
    )
    raw = (rec.get("response") or {}).get("raw") or {}
    recoil = raw.get("recoil") or {}
    pct_range = recoil.get("recoil")
    if isinstance(pct_range, list):
        pct_lo, pct_hi = float(pct_range[0]), float(pct_range[1])
    elif isinstance(pct_range, (int, float)):
        pct_lo = pct_hi = float(pct_range)
    else:
        pct_lo = pct_hi = None
    atk_hp = (raw.get("stats") or {}).get("attacker", {}).get("hp")
    def_hp = (raw.get("stats") or {}).get("defender", {}).get("hp")
    dmg = raw.get("damage") or []
    max_dmg = max(dmg) if dmg else 0
    # points from % of attacker max HP; capped by damage dealt / target remaining (OHKO → def HP)
    points_lo = points_hi = None
    if pct_lo is not None and atk_hp:
        points_lo = math.floor(atk_hp * pct_lo / 100)
        points_hi = math.floor(atk_hp * pct_hi / 100)
        # cap by target HP on OHKO
        if def_hp:
            points_lo = min(points_lo, def_hp, max_dmg)
            points_hi = min(points_hi, def_hp, max_dmg)
    bd_cost = atk_hp // 2 if atk_hp else None
    remaining_from_full = (atk_hp - bd_cost) if atk_hp is not None and bd_cost is not None else None
    survives_recoil_from_half = (
        remaining_from_full - points_hi > 0
        if remaining_from_full is not None and points_hi is not None
        else None
    )
    return {
        "desc": raw.get("desc"),
        "ko_chance": (rec.get("key") or {}).get("ko_chance"),
        "damage_range": (rec.get("key") or {}).get("damage_range"),
        "recoil_text": recoil.get("text"),
        "recoil_pct_range": [pct_lo, pct_hi],
        "recoil_pct_is_share_of_attacker_max_hp": True,
        "attacker_max_hp": atk_hp,
        "defender_hp": def_hp,
        "recoil_hp_points_range": [points_lo, points_hi],
        "points_source": (
            f"floor(attacker_max_hp × pct/100); calc % is share of attacker max HP"
        ),
        "belly_drum_cost": bd_cost,
        "post_belly_drum_remaining_from_full": remaining_from_full,
        "survives_recoil_from_half_hp_alone": survives_recoil_from_half,
        "arm_must_state": (
            "Flare Blitz OHKOs Primarina at +6; under the AJ→BD→AJ setup path the remaining HP "
            "does not cover recoil — arm must state OHKO-but-dies-to-recoil for that path"
        ),
        "ability": CX_ABILITY,
    }


def speed_ladder(snap: dict, sd: dict, threats: list[dict]) -> dict:
    """Condition B: +1 Spe via locked move; Adamant vs Jolly Spe SP ladder."""
    base = snap["species"][to_id(CX)]["base_stats"]["spe"]
    # +1 stage multiplier on final Spe
    def spe_plus1(nature: str, spe_sp: int) -> int:
        return math.floor(champions_spe(base, spe_sp, nature) * 1.5)

    jolly_max = spe_plus1("Jolly", 32)
    adamant_max = spe_plus1("Adamant", 32)

    from speed_grid import common_speed_distinct, scarf_lines, beneficial_spe_nature

    cells = []
    unreachable = []
    for t in threats:
        name = t["name"]
        # skip self
        if to_id(name) in {to_id(CX), "charizard"}:
            continue
        distinct = common_speed_distinct(sd, name)
        items = (sd["showdown_doubles"]["species"].get(to_id(name)) or {}).get("common_items") or []
        has_scarf = any(to_id(i.get("name") or "") == "choicescarf" for i in items[:5])
        # Part 0 COMMON_ITEM cutoff for scarf presence
        cum = 0.0
        scarf_in_common = False
        for i, row in enumerate(items):
            if i >= 5:
                break
            cum += float(row.get("pct") or 0)
            if to_id(row.get("name") or "") == "choicescarf":
                scarf_in_common = True
            if cum >= 90:
                break
        opp_lines = [{"spe": c["final_spe"], "weight": c["weight"], "scarf": False} for c in distinct]
        if scarf_in_common:
            ob = snap["species"].get(to_id(name), {}).get("base_stats", {}).get("spe")
            if ob:
                for sl in scarf_lines(ob, True, name):
                    opp_lines.append({"spe": sl["spe"], "nature": sl["nature"], "scarf": True})
        beaten_j = []
        beaten_a = []
        for ol in opp_lines:
            o = ol["spe"]
            # min Spe SP for Jolly/Adamant at +1 to outspeed
            need_j = need_a = None
            for sp in range(33):
                if spe_plus1("Jolly", sp) > o and need_j is None:
                    need_j = sp
                if spe_plus1("Adamant", sp) > o and need_a is None:
                    need_a = sp
            entry = {**ol, "min_spe_sp_jolly_plus1": need_j, "min_spe_sp_adamant_plus1": need_a}
            if need_j is not None:
                beaten_j.append(entry)
            if need_a is not None:
                beaten_a.append(entry)
            if need_j is None and need_a is None:
                unreachable.append({"threat": name, "opp_spe": o, "scarf": ol.get("scarf"), "reason": f"exceeds +1 ceiling Jolly32={jolly_max}"})
        cells.append(
            {
                "threat": name,
                "usage": t["usage"],
                "opp_lines": opp_lines,
                "beaten_with_jolly": beaten_j,
                "beaten_with_adamant": beaten_a,
            }
        )

    # Unburden Sneasler note
    sneasler_note = (
        "Unburden Sneasler unreachable without Tailwind (Charizard-Mega-X has no Tailwind); "
        "Scarf+TW stacking excluded from forward Condition B."
    )
    partial = any(u.get("opp_spe", 0) > jolly_max for u in unreachable)
    return {
        "boost_stage": "+1 (Flame Charge / Scale Shot); key Spe values computed at +1",
        "jolly_plus1_max": jolly_max,
        "adamant_plus1_max": adamant_max,
        "hand_jolly_32_plus1": 250,
        "hand_vs_calc_jolly": jolly_max == 250,
        "threat_definition": (
            f"Showdown doubles usage ≥ {THREAT_USAGE_CUTOFF:.6f} "
            f"(1-0.5^(1/15)); every listed form is its own threat; ASSUME-STATE"
        ),
        "threat_count": len(threats),
        "per_threat": cells,
        "unreachable": unreachable,
        "partial": partial,
        "class_if_scarf_over_ceiling": "PARTIAL" if partial else "SERVED",
        "sneasler_unburden_note": sneasler_note,
        "no_scarf_tw_stack": True,
    }


def leftover_hp_table(ohko_table: list[dict], speed_needs: dict, *, exclude_moves: set[str] | None = None) -> dict:
    """t6: leftover SP = 66 - min(Atk SP + Spe SP) over nature×move; HP capped 32."""
    exclude_moves = exclude_moves or set()
    rows = []
    for row in ohko_table:
        if not row.get("guaranteed_ohko"):
            continue
        if row["move"] in exclude_moves:
            continue
        nature = row["nature"]
        move = row["move"]
        atk = row["min_atk_sp"]
        spe = 32  # max threats
        used = atk + spe
        leftover = 66 - used
        hp_sp = min(32, leftover)
        spill = leftover - hp_sp
        rows.append(
            {
                "nature": nature,
                "move": move,
                "min_atk_sp": atk,
                "spe_sp": spe,
                "used": used,
                "leftover": leftover,
                "hp_sp": hp_sp,
                "spill_above_32": spill,
            }
        )
    if not rows:
        return {"ties": [], "note": "no OHKO rows"}
    max_hp = max(r["hp_sp"] for r in rows)
    # Among max hp_sp, prefer higher leftover (same) — all ties at max
    ties = [r for r in rows if r["hp_sp"] == max_hp and r["leftover"] == max(x["leftover"] for x in rows if x["hp_sp"] == max_hp)]
    # Actually "most HP" = maximize leftover (= maximize hp_sp then leftover), so max leftover
    max_left = max(r["leftover"] for r in rows)
    ties = [r for r in rows if r["leftover"] == max_left]
    return {
        "rule": "leftover SP = 66 - (min Atk SP for OHKO + Spe SP for Condition B); Spe SP=32 for max threats",
        "hp_cap": 32,
        "spill_rule": "If leftover > 32, HP SP=32 and arm states ASSUME-STATE for remaining SP placement (no silent bulk math)",
        "all_rows": rows,
        "max_leftover": max_left,
        "tied_nature_move_pairs": ties,
        "offer_swap_note": (
            "If t4 draft used a costlier move (e.g. Fire Fang), arm offers Fire Punch/Temper Flare "
            "swap (exact-name confirm); no silent mutation"
        ),
    }


def main() -> None:
    if health().get("status") != "ok":
        raise SystemExit("calc not ok")
    snap = load_legality()
    sd = load_showdown()
    field = {"gameType": "Doubles"}

    # OPEN CHECK: Primarina COMMON_ITEM
    prim_items = common_item_part0(sd, PRIM)
    print("Primarina COMMON_ITEM:", prim_items)
    if prim_items["focus_sash_in_common_item"]:
        print("FOCUS SASH IN COMMON_ITEM — full-HP OHKO impossible by definition")
    else:
        print(
            f"Focus Sash NOT in COMMON_ITEM (raw pct={prim_items['focus_sash_raw_pct']}); "
            "OHKO keys vs common items are valid"
        )

    joints = common_joint(sd, PRIM)
    # Primary defender: top joint + top common item (Life Orb) — LO doesn't affect defensive calc
    # Use Leftovers as second? Part 0: group legal effect classes. For receiving damage, item rarely matters except sash/sitrus.
    # Use top item Life Orb (no defensive effect on Aqua Jet receive for Primarina as defender)
    prim_def = _prim(joints[0], prim_items["items"][0]["name"] if prim_items["items"] else "")
    # For Aqua Jet offense from Primarina, Life Orb boosts AJ — use it
    prim_atk = _prim(joints[0], "Life Orb")

    moves = ["Fire Punch", "Temper Flare", "Fire Fang", "Flame Charge", "Scale Shot", "Flare Blitz"]
    natures = ["Adamant", "Jolly"]
    ohko_table = []
    for move in moves:
        for nature in natures:
            print(f"  OHKO {move} {nature}...", flush=True)
            ohko_table.append(min_atk_for_ohko(nature, move, prim_def, field))

    # Aqua Jet survival on a representative bulk-ish spread (HP-32) and on min-spread
    print("  Aqua Jet survival...", flush=True)
    aj = aqua_jet_survival(
        "Adamant",
        {"hp": 32, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
        prim_atk,
        field,
    )

    print("  Flare Blitz recoil...", flush=True)
    fb_row = next(r for r in ohko_table if r["move"] == "Flare Blitz" and r["nature"] == "Adamant")
    fb_atk = fb_row.get("min_atk_sp") if fb_row.get("guaranteed_ohko") else 32
    recoil = flare_blitz_recoil(
        "Adamant",
        {"hp": 32, "atk": fb_atk or 32, "def": 0, "spa": 0, "spd": 0, "spe": 0},
        prim_def,
        field,
    )
    # Combine with AJ survival path
    if aj.get("after_aj2") is not None and recoil.get("recoil_hp_points_range"):
        pts = recoil["recoil_hp_points_range"][1]
        recoil["hp_after_aj_bd_aj"] = aj["after_aj2"]
        recoil["survives_recoil_after_aj_bd_aj"] = aj["after_aj2"] - pts > 0
        recoil["hand_disagreement"] = {
            "hand": "recoil kills Charizard after Belly Drum",
            "calc_half_alone": recoil["survives_recoil_from_half_hp_alone"],
            "calc_after_two_aj": recoil["survives_recoil_after_aj_bd_aj"],
            "note": (
                "Recoil alone from 50% max HP does NOT kill at HP-32 (calc); "
                "after two max-roll Aqua Jets on the setup path, recoil DOES kill. "
                "Condition A uses the setup path."
            ),
        }

    print("  Threat set...", flush=True)
    threats = showdown_threats_ge_cutoff(sd, THREAT_USAGE_CUTOFF)
    usage_field_ok = bool(threats)
    print(f"  threats={len(threats)} usage_field_ok={usage_field_ok}", flush=True)
    ladder = speed_ladder(snap, sd, threats)
    # Exclude Flare Blitz from t6 ties: Condition A fails (dies to recoil on AJ setup path)
    leftover = leftover_hp_table(ohko_table, ladder, exclude_moves={"Flare Blitz"})

    # Legality prereq record
    def learn(species, move):
        moveset = (snap.get("learnsets") or {}).get(to_id(species)) or {}
        mid = to_id(move)
        if isinstance(moveset, dict):
            return mid in {to_id(k) for k in moveset}
        return mid in {to_id(m) for m in moveset}

    legality = {
        "charizard_moves": {
            m: learn("charizard", m)
            for m in [
                "Belly Drum",
                "Flame Charge",
                "Scale Shot",
                "Fire Punch",
                "Temper Flare",
                "Fire Fang",
                "Flare Blitz",
                "Dragon Dance",
            ]
        },
        "charizard_mega_x_legal": snap["species"]["charizardmegax"].get("is_nonstandard") is None,
        "charizardite_x_legal": snap["items"]["charizarditex"].get("is_nonstandard") is None,
        "primarina_aqua_jet": learn("primarina", "Aqua Jet"),
        "temper_flare_contact": True,
        "scale_shot_contact": False,
        "scale_shot_type_dragon_fairy_immune": True,
    }

    t2 = {
        "valid_speed_moves": ["Flame Charge", "Scale Shot"],
        "invalid": ["Dragon Dance"],
        "dragon_dance_reason": "Atk boost redundant with Belly Drum; legal but must not suggest",
        "if_t1_already_has_speed_move": "state it and ASK whether user wants a different one (no silent swap)",
        "scale_shot_variant": "Flame Charge locked in prompt; Scale Shot same Condition B (+1 Spe) — key unchanged if Spe stage only",
    }

    ar3 = {
        "prereq_legality": legality,
        "primarina_common_item": prim_items,
        "primarina_common_joint": joints,
        "defender_assumption": {
            "ability": "Torrent (slot 0; ASSUME-STATE)",
            "item": prim_def["item"],
            "spread": prim_def["evs"],
            "nature": prim_def["nature"],
        },
        "attacker_ability_rule": "Tough Claws always explicit; key fails if desc lacks Tough Claws on contact rolls",
        "t2": t2,
        "t3_lock": "Flame Charge (exact name); Scale Shot alternate only if key identical for Spe (+1)",
        "t4_ohko_min_atk_sp": ohko_table,
        "t4_aqua_jet_survival": aj,
        "t4_flare_blitz_recoil": recoil,
        "haze_caveat": "Haze resets Belly Drum +6; OHKO lost. Known caveat; no claim required unless arm raises it.",
        "t5_speed_ladder": ladder,
        "t5_usage_field_ok": usage_field_ok,
        "t6_leftover_hp": leftover,
        "expected_classes": {
            "t1": "SERVED",
            "t2": "SERVED or ASK",
            "t3": "MUTATION-OK",
            "t4": "SERVED",
            "t5": ladder.get("class_if_scarf_over_ceiling") or "SERVED",
            "t6": "SERVED with offered swap",
        },
        "hand_disagreements": [],
    }
    if ladder["jolly_plus1_max"] != 250:
        ar3["hand_disagreements"].append(
            {"field": "jolly_32_plus1", "hand": 250, "calc_or_formula": ladder["jolly_plus1_max"]}
        )

    path = OUT
    artifacts = json.loads(path.read_text()) if path.exists() else {}
    artifacts["ar3"] = ar3
    path.write_text(json.dumps(artifacts, indent=2) + "\n")
    print(f"wrote ar3 → {path}")
    # summary table
    print("\n=== min Atk SP ===")
    for r in ohko_table:
        print(r["move"], r["nature"], r.get("min_atk_sp"), r.get("guaranteed_ohko"), r.get("reason") or r.get("note") or "")
    print("AJ survives", aj["survives_both_aj"], aj)
    print(
        "Recoil",
        recoil["recoil_pct_range"],
        recoil["recoil_hp_points_range"],
        "half_alone",
        recoil.get("survives_recoil_from_half_hp_alone"),
        "after_aj",
        recoil.get("survives_recoil_after_aj_bd_aj"),
    )
    print("Speed max J/A", ladder["jolly_plus1_max"], ladder["adamant_plus1_max"], "partial", ladder["partial"])
    print("Leftover ties", leftover["tied_nature_move_pairs"])


if __name__ == "__main__":
    main()
