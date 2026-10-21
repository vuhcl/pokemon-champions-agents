#!/usr/bin/env python3
"""AR3 HP-formula + worst-joint AJ + recoil store fixes (eval-only)."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib import (
    champions_hp,
    common_joint,
    flare_blitz_recoil_basis,
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


def aj_into(prim, cx_nature, cx_spread, aid):
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
            "defender": _cx(cx_nature, cx_spread),
            "move": "Aqua Jet",
            "field": {"gameType": "Doubles"},
        },
        aid,
        persist=True,
    )
    raw = (rec.get("response") or {}).get("raw") or {}
    stats = raw.get("stats") or {}
    return {
        "max_damage": (rec.get("key") or {}).get("max_damage") or 0,
        "damage_range": (rec.get("key") or {}).get("damage_range"),
        "desc": raw.get("desc"),
        "defender_hp_from_calc": (stats.get("defender") or {}).get("hp"),
        "attacker_stats": stats.get("attacker"),
        "calc_id": aid,
        "request": {
            "nature": prim["nature"],
            "item": prim["item"],
            "evs": prim["evs"],
        },
    }


def chain(max_hp: int, aj_max: int) -> dict:
    bd_cost = max_hp // 2
    after_aj1 = max_hp - aj_max
    after_bd = after_aj1 - bd_cost
    after_aj2 = after_bd - aj_max
    remaining_after_bd_from_full = max_hp - bd_cost
    return {
        "cx_max_hp": max_hp,
        "aj_max": aj_max,
        "after_aj1": after_aj1,
        "belly_drum_cost": bd_cost,
        "after_bd": after_bd,
        "post_belly_drum_remaining_from_full": remaining_after_bd_from_full,
        "aj2_max": aj_max,
        "after_aj2": after_aj2,
        "survives_both_aj": after_aj2 > 0,
        "recoil_margin_from_full_bd_only": remaining_after_bd_from_full,  # compare to recoil pts separately
    }


def fb_recoil(nature, spread, prim, aid):
    rec = calculate(
        {
            "attacker": _cx(nature, spread, {"atk": 6}),
            "defender": prim,
            "move": "Flare Blitz",
            "field": {"gameType": "Doubles"},
        },
        aid,
        persist=True,
    )
    raw = (rec.get("response") or {}).get("raw") or {}
    recoil = raw.get("recoil") or {}
    pct = recoil.get("recoil")
    if isinstance(pct, list):
        pct_lo, pct_hi = float(pct[0]), float(pct[1])
    else:
        pct_lo = pct_hi = float(pct or 0)
    atk_hp = (raw.get("stats") or {}).get("attacker", {}).get("hp")
    def_hp = (raw.get("stats") or {}).get("defender", {}).get("hp")
    dmg = raw.get("damage") or []
    basis = flare_blitz_recoil_basis(
        def_hp=def_hp,
        atk_hp=atk_hp,
        damage=dmg,
        calc_display_pct=[pct_lo, pct_hi],
    )
    return {
        "desc": raw.get("desc"),
        "damage_range": (rec.get("key") or {}).get("damage_range"),
        "recoil_text": recoil.get("text"),
        "attacker_max_hp": atk_hp,
        "attacker_hp_sp": spread.get("hp"),
        "defender_hp": def_hp,
        "calc_id": aid,
        "ability": CX_ABILITY,
        **basis,
        # compat aliases used by survival margins
        "recoil_hp_points_range": basis["recoil_hp_range"],
        "recoil_pct_range": [pct_lo, pct_hi],
    }


def main() -> None:
    assert health().get("status") == "ok"
    snap = load_legality()
    sd = load_showdown()
    d = json.loads(OUT.read_text())
    ar = d["ar3"]
    joints = common_joint(sd, PRIM)
    base_hp = snap["species"][to_id(CX)]["base_stats"]["hp"]
    assert champions_hp(base_hp, 32) == 185
    assert champions_hp(base_hp, 0) == 153
    assert champions_hp(80, 32) == 187

    # Snapshot old values for report
    old = {
        "cx_max_hp": ar["t4_aqua_jet_survival"].get("cx_max_hp"),
        "aj1_max": ar["t4_aqua_jet_survival"].get("aj1_max"),
        "belly_drum_cost": ar["t4_aqua_jet_survival"].get("belly_drum_cost"),
        "after_aj1": ar["t4_aqua_jet_survival"].get("after_aj1"),
        "after_bd": ar["t4_aqua_jet_survival"].get("after_bd"),
        "after_aj2": ar["t4_aqua_jet_survival"].get("after_aj2"),
        "post_belly_drum_hp": ar["t4_flare_blitz_recoil"].get("post_belly_drum_hp"),
        "hp_after_aj_bd_aj": ar["t4_flare_blitz_recoil"].get("hp_after_aj_bd_aj"),
        "def_hp_sample": (ar.get("t4_ohko_min_atk_sp") or [{}])[0]
        .get("per_joint", [{}])[0]
        .get("def_hp"),
        "min_hp_sp": (ar.get("part1_followup") or {})
        .get("t4_min_hp_sp_survival", {})
        .get("min_hp_sp"),
        "atk_mins": [
            (r["move"], r["nature"], r["min_atk_sp"])
            for r in (ar.get("t4_ohko_min_atk_sp") or [])
            if r["move"] in ("Fire Punch", "Temper Flare", "Fire Fang")
        ],
        "leftover_max": (ar.get("t6_leftover_hp") or {}).get("max_leftover"),
    }

    # --- AJ all three joints vs HP-32 CX ---
    cx32 = {"hp": 32, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0}
    per_joint_aj = []
    for i, j in enumerate(joints):
        prim = _prim(j, "Life Orb")
        hit = aj_into(prim, "Adamant", cx32, f"ar3_aquajet_joint{i}_lo_hp32")
        per_joint_aj.append(
            {
                "joint_i": i,
                "joint_nature": j.get("nature"),
                "joint_evs": hit["request"]["evs"],
                **hit,
            }
        )
    worst = max(per_joint_aj, key=lambda r: r["max_damage"])
    # MW vs LO on worst joint nature for label
    mw = aj_into(_prim(joints[worst["joint_i"]], "Mystic Water"), "Adamant", cx32, "ar3_aquajet_worstjoint_mystic")
    lo = aj_into(_prim(joints[worst["joint_i"]], "Life Orb"), "Adamant", cx32, "ar3_aquajet_worstjoint_lo")

    # Use calc defender HP (must be 185 at HP-32)
    cx_hp_calc = worst["defender_hp_from_calc"]
    assert cx_hp_calc == champions_hp(base_hp, 32) == 185, (cx_hp_calc, champions_hp(base_hp, 32))
    ch = chain(cx_hp_calc, worst["max_damage"])

    # Also store HP-0 chain for confirm
    cx0 = {"hp": 0, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0}
    # AJ damage is absolute — re-probe worst joint into HP-0 for desc/HP echo
    aj0 = aj_into(_prim(joints[worst["joint_i"]], "Life Orb"), "Adamant", cx0, "ar3_aquajet_worstjoint_lo_hp0")
    assert aj0["defender_hp_from_calc"] == 153
    # Damage may be identical absolute; use worst max from HP-32 run (same absolute dmg)
    ch0 = chain(153, worst["max_damage"])

    survival_rows = []
    min_hp_sp = None
    for hp_sp in range(33):
        mh = champions_hp(base_hp, hp_sp)
        c = chain(mh, worst["max_damage"])
        survival_rows.append(
            {
                "hp_sp": hp_sp,
                "max_hp": mh,
                "aj_max": worst["max_damage"],
                "after_aj2": c["after_aj2"],
                "survives": c["survives_both_aj"],
            }
        )
        if c["survives_both_aj"] and min_hp_sp is None:
            min_hp_sp = hp_sp

    # Fix def_hp on ohko tables (display only; mins from calc unchanged)
    for block_key in ("t4_ohko_min_atk_sp",):
        for row in ar.get(block_key) or []:
            for pj in row.get("per_joint") or []:
                hp_sp = int((pj.get("spread") or {}).get("hp") or 0)
                pj["def_hp"] = champions_hp(80, hp_sp)
                pj["def_hp_source"] = "champions_hp = base + SP + 75"

    fu = ar.setdefault("part1_followup", {})
    for row in fu.get("t4_ohko_per_joint") or []:
        for pj in row.get("per_joint") or []:
            hp_sp = int((pj.get("spread") or {}).get("hp") or 0)
            pj["def_hp"] = champions_hp(80, hp_sp)
            pj["def_hp_source"] = "champions_hp = base + SP + 75"

    # Atk mins unchanged check
    new_atk = [
        (r["move"], r["nature"], r["min_atk_sp"])
        for r in (ar.get("t4_ohko_min_atk_sp") or [])
        if r["move"] in ("Fire Punch", "Temper Flare", "Fire Fang")
    ]

    # Recoil at HP-32 and ASSUME-STATE HP-0
    prim0 = _prim(joints[0], "Life Orb")
    recoil_hp32 = fb_recoil(
        "Adamant",
        {"hp": 32, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
        prim0,
        "ar3_flareblitz_plus6_hp32",
    )
    # Also Jolly assume-state HP0 Atk14 Spe28 for t4
    assume = (fu.get("t4_t5_joint_feasible") or {}).get("assume_state_t4_spread") or {
        "nature": "Jolly",
        "hp": 0,
        "atk": 14,
        "spe": 28,
    }
    recoil_hp0 = fb_recoil(
        assume.get("nature") or "Jolly",
        {
            "hp": int(assume.get("hp") or 0),
            "atk": int(assume.get("atk") or 0),
            "def": 0,
            "spa": 0,
            "spd": 0,
            "spe": int(assume.get("spe") or 0),
        },
        prim0,
        "ar3_flareblitz_plus6_hp0_assume",
    )
    # Per-joint recoil at HP-32 Adamant Atk-0 (replace followup rows)
    recoil_joints = []
    for i, j in enumerate(joints):
        recoil_joints.append(
            fb_recoil(
                "Adamant",
                {"hp": 32, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
                _prim(j, "Life Orb"),
                f"ar3_flareblitz_recoil_j{i}_hp32",
            )
            | {"joint_i": i, "joint_nature": j.get("nature")}
        )

    # Survival margins use in-game value_hp only (62)
    pts = (recoil_hp32.get("recoil_basis") or {}).get("value_hp")
    if pts is None:
        pts = recoil_hp32.get("recoil_hp")
    pts_hi = pts_lo = pts
    margin_full_bd = ch["post_belly_drum_remaining_from_full"] - pts_hi

    ar["t4_aqua_jet_survival"] = {
        "model": "AJ(prio)+BD then AJ(prio) before attack; AJ max = worst COMMON_JOINT × Life Orb",
        "hp_formula": "champions_hp = base + SP + 75 (fixed; was half-SP formula → −16)",
        "cx_max_hp": ch["cx_max_hp"],
        "cx_max_hp_source": "calc defender.stats.hp (matches champions_hp)",
        "worst_joint": {
            "joint_i": worst["joint_i"],
            "nature": worst["joint_nature"],
            "evs": worst["joint_evs"],
            "item": "Life Orb",
            "aj_max": worst["max_damage"],
            "desc": worst["desc"],
            "calc_id": worst["calc_id"],
            "label": "worst joint by calc (max Aqua Jet damage across 3 COMMON_JOINT)",
        },
        "per_joint_aqua_jet": per_joint_aj,
        "item_worst_case": {
            "Life Orb": lo["max_damage"],
            "Mystic Water": mw["max_damage"],
            "note": "Life Orb (1.3x) > Mystic Water (1.2x) on the worst joint",
        },
        "aj1_max": ch["aj_max"],
        "after_aj1": ch["after_aj1"],
        "belly_drum_cost": ch["belly_drum_cost"],
        "after_bd": ch["after_bd"],
        "post_belly_drum_remaining_from_full": ch["post_belly_drum_remaining_from_full"],
        "aj2_max": ch["aj2_max"],
        "after_aj2": ch["after_aj2"],
        "survives_both_aj": ch["survives_both_aj"],
        "aj1_desc": worst["desc"],
        "aj2_desc": worst["desc"],
        "setup_turns_plus_one": 2,
        "hp0_confirm": {
            **ch0,
            "aj_desc": aj0["desc"],
            "note": "min HP SP survival uses absolute AJ max; HP-0 leaves after_aj2>0",
        },
    }

    ar["t4_flare_blitz_recoil"] = {
        "by_attacker_spread": {
            "hp_sp_32": recoil_hp32,
            "hp_sp_0_assume_state": recoil_hp0,
        },
        # flat fields: HP-32 reference + corrected basis
        **{
            k: recoil_hp32[k]
            for k in (
                "desc",
                "damage_range",
                "recoil_text",
                "recoil_pct_range",
                "attacker_max_hp",
                "defender_hp",
                "recoil_hp_points_range",
                "recoil_hp_range",
                "recoil_hp",
                "scope",
                "recoil_basis",
                "scoring",
                "calc_recoil_text_is_display_pct_of_attacker_max_hp",
                "ability",
            )
            if k in recoil_hp32
        },
        "belly_drum_cost": ch["belly_drum_cost"],
        "post_belly_drum_remaining_from_full": ch["post_belly_drum_remaining_from_full"],
        "recoil_margin_from_full_bd_only": margin_full_bd,
        "hp_after_aj_bd_aj": ch["after_aj2"],
        "survives_recoil_from_half_hp_alone": ch["post_belly_drum_remaining_from_full"] > pts_hi,
        "survives_recoil_after_aj_bd_aj": ch["after_aj2"] > pts_hi,
        "arm_must_state": (
            "Flare Blitz OHKOs Primarina at +6; under the AJ→BD→AJ setup path the remaining HP "
            "does not cover recoil — arm must state OHKO-but-dies-to-recoil for that path"
        ),
        "hand_disagreement": {
            "hand": "recoil kills Charizard after Belly Drum on the AJ→BD→AJ path",
            "calc_half_alone": ch["post_belly_drum_remaining_from_full"] > pts_hi,
            "calc_after_two_aj": ch["after_aj2"] > pts_hi,
            "note": (
                f"At HP-32 (185): BD remaining from full={ch['post_belly_drum_remaining_from_full']}; "
                f"in-game recoil value_hp={pts} (ADR-079 operator); "
                f"calc exposes only % of attacker HP (33.3% here), not HP points; "
                f"after AJ→BD→AJ remaining={ch['after_aj2']} < {pts}. "
                f"Showdown sim Math.round(187*33/100)=62 cross-checks."
            ),
        },
    }

    # Update joint feasible min_hp (should stay 0)
    jf = fu.get("t4_t5_joint_feasible") or ar.get("t4_t5_joint_feasible") or {}
    if jf:
        jf["min_hp_sp"] = min_hp_sp
        jf["sum"] = (min_hp_sp or 0) + (jf.get("min_atk_sp") or 0) + (jf.get("min_spe_sp") or 0)
        jf["fits_budget_66"] = jf["sum"] <= 66
        if jf.get("assume_state_t4_spread"):
            jf["assume_state_t4_spread"]["hp"] = min_hp_sp
            jf["assume_state_t4_spread"]["attacker_max_hp"] = champions_hp(base_hp, min_hp_sp or 0)
        fu["t4_t5_joint_feasible"] = jf
        ar["t4_t5_joint_feasible"] = jf

    fu["t4_aqua_jet_worst_case"] = {
        "item": "Life Orb",
        "item_note": "Life Orb (1.3x) is worst-case among COMMON_ITEM for AJ offense vs Mystic Water (1.2x)",
        "worst_joint_by_calc": {
            "joint_i": worst["joint_i"],
            "nature": worst["joint_nature"],
            "aj_max": worst["max_damage"],
            "desc": worst["desc"],
        },
        "per_joint": [
            {"joint_i": r["joint_i"], "nature": r["joint_nature"], "aj_max": r["max_damage"], "desc": r["desc"]}
            for r in per_joint_aj
        ],
        "lo_dmg_worst_joint": lo["max_damage"],
        "mystic_water_dmg_worst_joint": mw["max_damage"],
        "worst_aj_max": worst["max_damage"],
    }
    fu["t4_min_hp_sp_survival"] = {
        "min_hp_sp": min_hp_sp,
        "rows": survival_rows,
        "model": "AJ(max)+BD(half max)+AJ(max); worst Primarina COMMON_JOINT + Life Orb; HP=base+SP+75",
        "hp0_after_aj2": ch0["after_aj2"],
    }
    fu["t4_flare_blitz_recoil_per_joint"] = recoil_joints
    fu["t4_flare_blitz_recoil_by_attacker_hp"] = {
        "hp_sp_32": recoil_hp32,
        "hp_sp_0_assume_state": recoil_hp0,
    }

    # hand_disagreements update
    hd = [
        h
        for h in (ar.get("hand_disagreements") or [])
        if h.get("field") not in ("flare_blitz_recoil_path", "cx_max_hp", "def_hp", "aqua_jet_joint")
    ]
    hd.append(
        {
            "field": "cx_max_hp / primarina_def_hp",
            "old": "169 / 171 (half-SP formula)",
            "new": "185 / 187 (base + SP + 75; matches calc stats)",
        }
    )
    hd.append(
        {
            "field": "aqua_jet_joint",
            "old": "Modest joint (0- Atk) max 25",
            "new": f"Quiet joint (Atk-neutral) max {worst['max_damage']} — worst of 3 COMMON_JOINT",
        }
    )
    hd.append(
        {
            "field": "flare_blitz_recoil_path",
            "hand": "recoil kills after Belly Drum on setup path",
            "calc": (
                f"HP-32: after AJ→BD→AJ remaining {ch['after_aj2']} < recoil value_hp {pts} "
                f"(ADR-079 operator on damage dealt; calc exposes % of attacker HP only); "
                f"BD-from-full remaining {ch['post_belly_drum_remaining_from_full']} − {pts} = {margin_full_bd} margin. "
                f"Prior key used wrong HP 169 → after_aj2 35 / post_bd cost 84."
            ),
        }
    )
    ar["hand_disagreements"] = hd
    fu["hand_disagreements"] = [
        h
        for h in (fu.get("hand_disagreements") or [])
        if h.get("field")
        not in ("flare_blitz_recoil_path", "cx_max_hp", "jolly_spe_atk_for_max_coverage", "adamant_optimum")
    ] + [
        h
        for h in (fu.get("hand_disagreements") or [])
        if h.get("field") in ("jolly_spe_atk_for_max_coverage", "adamant_optimum")
    ] + [
        {
            "field": "hp_formula",
            "old": "floor((2*base+31+SP)*50/100)+60 → cx 169 / prim 171",
            "new": "base+SP+75 → cx 185 / prim 187",
        },
        {
            "field": "aqua_jet_worst_joint",
            "old": "Modest LO 25",
            "new": f"{worst['joint_nature']} LO {worst['max_damage']}",
        },
    ]

    d["ar3"] = ar
    OUT.write_text(json.dumps(d, indent=2) + "\n")

    report = {
        "old": old,
        "new": {
            "cx_max_hp": ch["cx_max_hp"],
            "aj1_max": ch["aj_max"],
            "belly_drum_cost": ch["belly_drum_cost"],
            "after_aj1": ch["after_aj1"],
            "after_bd": ch["after_bd"],
            "after_aj2": ch["after_aj2"],
            "post_belly_drum_remaining_from_full": ch["post_belly_drum_remaining_from_full"],
            "worst_joint": worst["joint_nature"],
            "worst_aj": worst["max_damage"],
            "min_hp_sp": min_hp_sp,
            "def_hp": 187,
            "recoil_value_hp_32": pts,
            "recoil_value_hp_0": (recoil_hp0.get("recoil_basis") or {}).get("value_hp")
            or recoil_hp0.get("recoil_hp"),
            "recoil_pct_hp0": recoil_hp0.get("recoil_pct_range"),
            "atk_mins": new_atk,
            "atk_mins_unchanged": new_atk == old["atk_mins"],
            "leftover_unchanged": (ar.get("t6_leftover_hp") or {}).get("max_leftover") == old["leftover_max"],
            "hp0_after_aj2": ch0["after_aj2"],
        },
    }
    Path(__file__).resolve().parents[1].joinpath("key_artifacts/ar3_hp_fix_report.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
