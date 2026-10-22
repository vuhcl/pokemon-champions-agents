#!/usr/bin/env python3
"""Build the calc-labeled damage pool for the claim battery (guaranteed-KO yes/no items).

A calc-free selector steers candidate draws (type chart, base stats, learnsets); EVERY candidate is then
labeled through builders/calc_store.py (in-process @smogon/calc, no HTTP service) and the calc result is the
key. A candidate whose calc result does not satisfy the kind it was drawn for is reassigned to another kind
it satisfies (if that kind has room) or discarded; both are counted in the pool metadata.

Writes key_artifacts/battery_damage_pool.json. The battery generator stays calc-free and draws its damage
items from that file. `--check` rebuilds and fails if the committed file differs.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import math
import os
import random
import statistics
import sys
from pathlib import Path
from typing import Any

os.environ["PART_G_V4_CALC_BACKEND"] = "inprocess"  # same pinned @smogon/calc, no HTTP service
os.environ["PART_G_V4_CALC_IGNORE_DISK"] = "1"  # never answer from a stored artifact

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
ROOT = PKG.parents[2]
sys.path.insert(0, str(HERE))

import calc_store  # noqa: E402
from _lib import load_legality, to_id  # noqa: E402

OUT = PKG / "key_artifacts" / "battery_damage_pool.json"
STONE_MAP = PKG / "key_artifacts" / "stone_map.v1.json"
TYPE_CHART = PKG / "key_artifacts" / "type_chart.v1.json"
PINS = PKG / "pins_manifest.json"
BLOBS = (
    "data/legality/champions.v1.json",
    "data/moves/static.v1.json",
    "data/moves/flags.v1.json",
)

SEED = 20261022
POOL_MULTIPLE = 4
# Battery quotas per kind (51 items: 25 True, 26 False). The pool holds POOL_MULTIPLE x each.
QUOTAS = {
    "T1": 8, "T2": 3, "T3": 8, "T4": 6,
    "F1": 5, "F2": 5, "F2b": 4,
    "F3r_low": 1, "F3r_mid": 1, "F3r_high": 1, "F3n": 2,
    "F5": 4, "F4": 3,
}
TRUE_KINDS = ("T1", "T2", "T3", "T4")
MAX_ATTEMPTS_PER_KIND = 40000

# Fixed conditions (stated in every prompt).
LEVEL = 50
NATURE = {"Physical": "Adamant", "Special": "Modest"}
OFFENSE = {"Physical": "atk", "Special": "spa"}
DEFENSE = {"Physical": "def", "Special": "spd"}
ATTACKER_SP = 32
DEFENDER_NATURE = "Hardy"
DEFENDER_HP_SP = 32
FIELD = {"gameType": "Doubles"}
T1_MARGIN_MAX = 1.10  # min roll / HP: narrow margin is 1.0-1.1
T2_MARGIN_MIN = 1.25  # comfortable margin (a stated constant, not a quartile)
NEAR_MISS = (0.60, 0.95)  # max roll / HP
ROLLS_LOW_MAX, ROLLS_MID_MAX = 4, 11  # rolls that KO, out of 16: <=4 low, 5-11 mid, 12-15 high
ASSERT_ABILITIES = ("Tough Claws", "Huge Power", "Pure Power", "Parental Bond", "Tinted Lens")
# Steering only (the calc is authoritative): abilities that grant a type immunity.
STEERING_IMMUNITY = {
    "Ground": {"Levitate", "Earth Eater"},
    "Electric": {"Volt Absorb", "Lightning Rod", "Motor Drive"},
    "Water": {"Water Absorb", "Storm Drain", "Dry Skin"},
    "Fire": {"Flash Fire", "Well-Baked Body"},
    "Grass": {"Sap Sipper"},
}


def stat(base: int, sp: int, mult: float = 1.0) -> int:
    return math.floor(mult * (base + sp + 20))


def hp_stat(base: int, sp: int) -> int:
    return base + sp + 75


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


class Data:
    def __init__(self) -> None:
        snap = load_legality()
        self.sp = snap["species"]
        self.moves = snap["moves"]
        self.ls = snap["learnsets"]
        self.static = json.loads((ROOT / "data/moves/static.v1.json").read_text())["moves"]
        self.flags = json.loads((ROOT / "data/moves/flags.v1.json").read_text())["moves"]
        pairs = json.loads(STONE_MAP.read_text())["pairs"]
        self.holder = {p["mega"]: p["holder"] for p in pairs if p["mega"] in self.sp}
        chart = json.loads(TYPE_CHART.read_text())
        self.chart = chart["effectiveness"]
        self.legal = sorted(k for k, v in self.sp.items() if v["is_nonstandard"] is None)

    def ability_list(self, sid: str) -> list[str]:
        return [v for v in self.sp[sid]["abilities"].values() if v]

    def learnset_key(self, sid: str) -> str | None:
        if sid in self.ls:
            return sid
        h = self.holder.get(sid)
        if h and h in self.ls:
            return h
        b = self.sp[sid].get("base_species_id")
        return b if b in self.ls else None

    def eff(self, move_type: str, def_types: list[str]) -> float:
        m = 1.0
        for t in def_types:
            m *= self.chart[move_type][t]
        return m


def usable_moves(d: Data) -> list[str]:
    out = []
    for m in sorted(d.static):
        mv, st, fl = d.moves[m], d.static[m], d.flags[m]["flags"]
        if mv["category"] in ("Physical", "Special") and mv["basePower"] > 0 \
                and st["target"] in ("normal", "any") and not fl.get("charge") and not fl.get("recharge"):
            out.append(m)
    return out


def mon(sid_name: str, nature: str, ability: str, evs: dict) -> dict:
    return {"species": sid_name, "level": LEVEL, "nature": nature, "ability": ability, "evs": evs}


def zero_evs() -> dict:
    return {"hp": 0, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0}


def request(d: Data, att: str, att_ab: str, move: str, dfn: str, dfn_ab: str) -> dict:
    cat = d.moves[move]["category"]
    a_evs = zero_evs()
    a_evs[OFFENSE[cat]] = ATTACKER_SP
    d_evs = zero_evs()
    d_evs["hp"] = DEFENDER_HP_SP
    return {
        "attacker": mon(d.sp[att]["name"], NATURE[cat], att_ab, a_evs),
        "defender": mon(d.sp[dfn]["name"], DEFENDER_NATURE, dfn_ab, d_evs),
        "move": d.moves[move]["name"],
        "field": FIELD,
    }


def label(d: Data, req: dict) -> tuple[str, Any]:
    """Run one pair through calc_store; ('ok', result) or ('error', reason)."""
    try:
        rec = calc_store.calculate(req, "probe", persist=False)
    except RuntimeError as e:
        return "error", ("ability_assertion" if "desc lacks" in str(e) else str(e)[:80])
    resp = rec.get("response") or {}
    if "error" in resp:
        return "error", resp["error"][:80]
    raw = resp.get("raw") or {}
    dmg = raw.get("damage")
    if isinstance(dmg, (int, float)):
        dmg = [dmg] * 16  # immunity: the calc returns a scalar 0
    if not isinstance(dmg, list) or not dmg:
        return "error", "no damage field"
    if isinstance(dmg[0], list):
        return "error", "multi_hit"
    if len(dmg) != 16:
        return "error", f"{len(dmg)} rolls"
    return "ok", {"rolls": [int(x) for x in dmg], "hp": int(raw["stats"]["defender"]["hp"]), "desc": raw.get("desc") or ""}


def preflight(d: Data, usable: list[str]) -> dict[str, Any]:
    """Species the calc dex lacks, attacker (species, ability, category) triples assert_abilities rejects,
    and multi-hit moves (the calc returns one roll set per hit, so 'every roll' is not defined)."""
    ref = "garchomp"
    not_in_calc = []
    for sid in d.legal:
        ab = d.ability_list(sid)[0]
        bad = False
        for att, dfn in ((sid, ref), (ref, sid)):
            r = request(d, att, d.ability_list(att)[0], "tackle", dfn, d.ability_list(dfn)[0])
            k, info = label(d, r)
            if k == "error" and "unknown Champions species" in str(info):
                bad = True
        if bad:
            not_in_calc.append(sid)
    echo = []
    reps = {"Physical": "tackle", "Special": "psychic"}
    for sid in d.legal:
        if sid in not_in_calc:
            continue
        for ab in d.ability_list(sid):
            if ab not in ASSERT_ABILITIES:
                continue
            for cat, mv in reps.items():
                r = request(d, sid, ab, mv, "arcanine", d.ability_list("arcanine")[0])
                k, info = label(d, r)
                if k == "error" and info == "ability_assertion":
                    echo.append([sid, ab, cat])
    multi = []
    for m in usable:
        cat = d.moves[m]["category"]
        r = request(d, ref, "Rough Skin", m, "arcanine", d.ability_list("arcanine")[0])
        k, info = label(d, r)
        if k == "error" and info == "multi_hit":
            multi.append(m)
    return {"species_not_in_calc": sorted(not_in_calc), "ability_echo_rejected": sorted(echo), "multi_hit_moves": sorted(multi)}


def quartiles(vals: list[float]) -> list[float]:
    return statistics.quantiles(sorted(vals), n=4, method="inclusive")


def build() -> dict[str, Any]:
    d = Data()
    rng = random.Random(SEED)
    usable_all = usable_moves(d)
    pre = preflight(d, usable_all)
    multi = set(pre["multi_hit_moves"])
    usable = [m for m in usable_all if m not in multi]
    ok_species = [s for s in d.legal if s not in set(pre["species_not_in_calc"])]
    echo = {tuple(t) for t in pre["ability_echo_rejected"]}

    bp = [d.moves[m]["basePower"] for m in usable]
    bp_q1, _, bp_q3 = quartiles(bp)

    def bulk(sid: str, cat: str) -> int:
        b = d.sp[sid]["base_stats"]
        return hp_stat(b["hp"], DEFENDER_HP_SP) * stat(b[DEFENSE[cat]], 0)

    bulk_cut = {c: quartiles([bulk(s, c) for s in ok_species]) for c in ("Physical", "Special")}

    def bulk_quartile(sid: str, cat: str) -> int:
        v = bulk(sid, cat)
        q = bulk_cut[cat]
        return 1 + sum(v > c for c in q)

    def strong_cat(sid: str) -> str:
        b = d.sp[sid]["base_stats"]
        return "Physical" if b["atk"] >= b["spa"] else "Special"

    def est(att: str, dfn: str, m: str) -> tuple[float, float, int]:
        mv, b, c = d.moves[m], d.sp[att]["base_stats"], d.sp[dfn]["base_stats"]
        cat = mv["category"]
        a = stat(b[OFFENSE[cat]], ATTACKER_SP, 1.1)
        df = stat(c[DEFENSE[cat]], 0)
        hp = hp_stat(c["hp"], DEFENDER_HP_SP)
        base = math.floor(math.floor(22 * mv["basePower"] * a / df) / 50) + 2
        mult = (1.5 if mv["type"] in d.sp[att]["types"] else 1.0) * d.eff(mv["type"], d.sp[dfn]["types"])
        return math.floor(base * 0.85 * mult) / hp, math.floor(base * mult) / hp, hp

    learn = {s: sorted(set(d.ls[d.learnset_key(s)]) & set(usable)) if d.learnset_key(s) else [] for s in ok_species}

    def attrs(att: str, move: str, dfn: str, res: dict) -> dict[str, Any]:
        mv = d.moves[move]
        cat = mv["category"]
        rolls, hp = res["rolls"], res["hp"]
        b = d.sp[dfn]["base_stats"]
        other = "Special" if cat == "Physical" else "Physical"
        return {
            "effectiveness": d.eff(mv["type"], d.sp[dfn]["types"]),
            "high_power": mv["basePower"] >= bp_q3,
            "low_power": mv["basePower"] <= bp_q1,
            "stab": mv["type"] in d.sp[att]["types"],
            "category_match": cat == strong_cat(att),
            "defender_bulk_quartile": bulk_quartile(dfn, cat),
            "hits_stronger_defense": b[DEFENSE[cat]] > b[DEFENSE[other]],
            "margin": round(min(rolls) / hp, 4),
            "max_ratio": round(max(rolls) / hp, 4),
        }

    def satisfied(res: dict, a: dict) -> list[str]:
        rolls, hp = res["rolls"], res["hp"]
        g = min(rolls) >= hp
        ko = sum(r >= hp for r in rolls)
        eff, hi, lo = a["effectiveness"], a["high_power"], a["low_power"]
        out = []
        if g and eff >= 2 and hi and a["margin"] <= T1_MARGIN_MAX:
            out.append("T1")
        if g and eff >= 2 and hi and a["margin"] >= T2_MARGIN_MIN:
            out.append("T2")
        if g and eff == 1 and a["stab"] and hi and a["category_match"]:
            out.append("T3")
        if g and a["defender_bulk_quartile"] == 1:
            out.append("T4")
        if not g:
            if eff >= 2 and lo:
                out.append("F1")
            if eff == 1 and hi and not a["category_match"]:
                out.append("F2")
            if eff == 1 and hi and a["category_match"] and a["hits_stronger_defense"]:
                out.append("F2b")
            if eff == 1 and hi and 1 <= ko <= 15:
                out.append("F3r_low" if ko <= ROLLS_LOW_MAX else "F3r_mid" if ko <= ROLLS_MID_MAX else "F3r_high")
            if eff == 1 and hi and max(rolls) < hp and NEAR_MISS[0] <= max(rolls) / hp <= NEAR_MISS[1]:
                out.append("F3n")
            if hi and a["defender_bulk_quartile"] == 4 and eff >= 1:
                out.append("F5")
            if hi and eff <= 0.5:
                out.append("F4")
        return out

    def pick_pair(kind: str) -> tuple[str, str, str] | None:
        att = rng.choice(ok_species)
        sc = strong_cat(att)
        want = {"F2": "weak"}.get(kind, "strong")
        moves = [m for m in learn[att] if (d.moves[m]["category"] == sc) == (want == "strong")]
        if kind == "F1":
            moves = [m for m in moves if d.moves[m]["basePower"] <= bp_q1]
        elif kind != "T4":
            moves = [m for m in moves if d.moves[m]["basePower"] >= bp_q3]
        if kind == "T3":
            moves = [m for m in moves if d.moves[m]["type"] in d.sp[att]["types"]]
        if not moves:
            return None
        m = rng.choice(moves)
        cat = d.moves[m]["category"]
        dfn = rng.choice([s for s in ok_species if s != att])
        e = d.eff(d.moves[m]["type"], d.sp[dfn]["types"])
        lo_est, hi_est, _ = est(att, dfn, m)
        b = d.sp[dfn]["base_stats"]
        other = "Special" if cat == "Physical" else "Physical"
        if kind == "T1" and not (e >= 2 and 0.98 <= lo_est <= 1.20):
            return None
        if kind == "T2" and not (e >= 2 and lo_est >= 1.35):
            return None
        if kind == "T3" and not (e == 1 and lo_est >= 1.0):
            return None
        if kind == "T4" and not (bulk_quartile(dfn, cat) == 1 and lo_est >= 1.0):
            return None
        if kind == "F1" and not (e >= 2 and hi_est < 0.9):
            return None
        if kind == "F2" and not (e == 1 and lo_est < 1.0):
            return None
        if kind == "F2b" and not (e == 1 and b[DEFENSE[cat]] > b[DEFENSE[other]] and lo_est < 1.0):
            return None
        if kind.startswith("F3r") and not (e == 1 and 0.85 <= hi_est <= 1.6):
            return None
        if kind == "F3n" and not (e == 1 and NEAR_MISS[0] <= hi_est <= NEAR_MISS[1]):
            return None
        if kind == "F5" and not (bulk_quartile(dfn, cat) == 4 and e >= 1 and lo_est < 1.0):
            return None
        if kind == "F4" and not (e <= 0.5):
            return None
        return att, m, dfn

    pool: dict[str, list[dict]] = {k: [] for k in QUOTAS}
    keys: set[tuple[str, str, str]] = set()
    stats: dict[str, collections.Counter] = {k: collections.Counter() for k in QUOTAS}
    order = list(QUOTAS)
    for kind in order:
        target = QUOTAS[kind] * POOL_MULTIPLE
        while len(pool[kind]) < target and stats[kind]["attempts"] < MAX_ATTEMPTS_PER_KIND:
            stats[kind]["attempts"] += 1
            pr = pick_pair(kind)
            if pr is None:
                continue
            att, m, dfn = pr
            if (att, m, dfn) in keys:
                stats[kind]["duplicate"] += 1
                continue
            cat = d.moves[m]["category"]
            att_ab = rng.choice([a for a in d.ability_list(att) if (att, a, cat) not in echo] or [None])
            if att_ab is None:
                stats[kind]["attacker_ability_excluded"] += 1
                continue
            dfn_abs = d.ability_list(dfn)
            if kind in TRUE_KINDS + ("F1", "F2", "F2b", "F3n", "F5") or kind.startswith("F3r"):
                dfn_abs = [a for a in dfn_abs if a not in STEERING_IMMUNITY.get(d.moves[m]["type"], set())] or dfn_abs
            dfn_ab = rng.choice(dfn_abs)
            res_kind, res = label(d, request(d, att, att_ab, m, dfn, dfn_ab))
            stats[kind]["calc_calls"] += 1
            if res_kind == "error":
                stats[kind]["error:" + str(res)[:40]] += 1
                continue
            a = attrs(att, m, dfn, res)
            sat = satisfied(res, a)
            target_kind = kind if kind in sat and len(pool[kind]) < target else None
            if target_kind is None:
                for other in order:
                    if other in sat and len(pool[other]) < QUOTAS[other] * POOL_MULTIPLE:
                        target_kind = other
                        break
            if target_kind is None:
                stats[kind]["discarded"] += 1
                continue
            if target_kind != kind:
                stats[kind]["reassigned_to_" + target_kind] += 1
            rolls = res["rolls"]
            mv = d.moves[m]
            keys.add((att, m, dfn))
            pool[target_kind].append(
                {
                    "kind": target_kind,
                    "drawn_as": kind,
                    "attacker_id": att, "attacker": d.sp[att]["name"], "attacker_ability": att_ab,
                    "nature": NATURE[cat],
                    "move_id": m, "move": mv["name"], "move_category": cat, "move_basePower": mv["basePower"], "move_type": mv["type"],
                    "defender_id": dfn, "defender": d.sp[dfn]["name"], "defender_ability": dfn_ab,
                    "hp": res["hp"], "rolls": rolls, "min_roll": min(rolls), "max_roll": max(rolls),
                    "rolls_ko_of_16": sum(r >= res["hp"] for r in rolls),
                    "guaranteed_ko": min(rolls) >= res["hp"],
                    "desc": res["desc"],
                    "attrs": a,
                }
            )
    entries = sorted((e for lst in pool.values() for e in lst), key=lambda e: (e["kind"], e["attacker_id"], e["move_id"], e["defender_id"]))
    pins = json.loads(PINS.read_text())
    by_path = {p["path"]: p for p in pins["pins"]}
    return {
        "schema": "part_g_v4_damage_pool",
        "meta": {
            "calc_build": pins["calc_service"]["version"],
            "backend": "inprocess (builders/calc_store.py, PART_G_V4_CALC_BACKEND=inprocess)",
            "selector": "builders/damage_pool.py",
            "selector_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "rng_seed": SEED,
            "pool_multiple": POOL_MULTIPLE,
            "quotas_per_battery": QUOTAS,
            "fixed_conditions": {
                "level": LEVEL, "nature_by_category": NATURE, "attacker_sp": f"{ATTACKER_SP} in the offensive stat, 0 elsewhere",
                "defender": f"{DEFENDER_NATURE} nature, {DEFENDER_HP_SP} HP SP, 0 Def/SpD SP", "items": "none",
                "field": "no weather, terrain or screens; single target; no critical hit; full HP; no stat stages or status",
                "calc_field": FIELD,
            },
            "cutoffs": {
                "usable_move_basePower_q1_q3": [bp_q1, bp_q3],
                "usable_moves": len(usable),
                "bulk_quartile_cuts_hp_times_defense": {k: v for k, v in bulk_cut.items()},
                "t1_margin_max": T1_MARGIN_MAX, "t2_margin_min": T2_MARGIN_MIN, "near_miss_max_over_hp": list(NEAR_MISS),
                "rolls_ko_buckets": {"low": f"<={ROLLS_LOW_MAX}", "mid": f"{ROLLS_LOW_MAX + 1}-{ROLLS_MID_MAX}", "high": f"{ROLLS_MID_MAX + 1}-15"},
            },
            "exclusions": pre,
            "steering_immunity_abilities": {k: sorted(v) for k, v in STEERING_IMMUNITY.items()},
            "pins": [{"path": p, "git_blob_sha": by_path[p]["git_blob_sha"]} for p in BLOBS],
            "stone_map_sha256": hashlib.sha256(STONE_MAP.read_bytes()).hexdigest(),
            "type_chart_sha256": hashlib.sha256(TYPE_CHART.read_bytes()).hexdigest(),
            "build_stats": {k: dict(v) for k, v in stats.items()},
            "pool_sizes": {k: len(v) for k, v in pool.items()},
        },
        "entries": entries,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args()
    for rel in BLOBS:
        pin = next(p for p in json.loads(PINS.read_text())["pins"] if p["path"] == rel)
        if git_blob_sha(ROOT / rel) != pin["git_blob_sha"]:
            raise SystemExit(f"{rel} differs from its pin")
    text = json.dumps(build(), sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    if args.check:
        if OUT.read_text() != text:
            print("FAIL: battery_damage_pool.json differs from a rebuild")
            return 1
        print("PASS: battery_damage_pool.json matches a rebuild")
        return 0
    args.out.write_text(text)
    d = json.loads(text)
    print(f"wrote {args.out}: sizes {d['meta']['pool_sizes']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
