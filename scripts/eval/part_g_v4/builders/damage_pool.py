#!/usr/bin/env python3
"""Build the calc-labeled damage pool for the claim battery (guaranteed-KO yes/no items).

A calc-free selector steers candidate draws (type chart plus the calc's own move and ability rules, base
stats, learnsets); EVERY candidate is then labeled through builders/calc_store.py (in-process @smogon/calc,
no HTTP service) and the calc result is the key. A candidate whose calc result does not satisfy the kind it
was drawn for is reassigned to another kind it satisfies (if that kind has room) or discarded; both are
counted in the pool metadata.

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
from _lib import load_legality  # noqa: E402

OUT = PKG / "key_artifacts" / "battery_damage_pool.json"
STONE_MAP = PKG / "key_artifacts" / "stone_map.v1.json"
TYPE_CHART = PKG / "key_artifacts" / "type_chart.v1.json"
CALC_RULES = PKG / "key_artifacts" / "calc_move_rules.v1.json"
CONDITIONALS = PKG / "key_artifacts" / "move_conditionals.v1.json"
PINS = PKG / "pins_manifest.json"
BLOBS = (
    "data/legality/champions.v1.json",
    "data/moves/static.v1.json",
    "data/moves/flags.v1.json",
    "data/moves/gen9_accuracy.v1.json",
)

SEED = 20261022
POOL_MULTIPLE = 4
# Battery quotas per kind (51 items: 25 True, 26 False). The pool holds POOL_MULTIPLE x each.
# T4 = low-defense target: 4 plain + "T4r" (resisted, still a guaranteed KO) + "T4e" (chart exception).
# T5 = chart exceptions: Freeze-Dry into a Water-type, Flying Press from Hawlucha (1 each).
# M1/M2 = twins on one (attacker, ability, move): conversion makes a guaranteed KO / ends up resisted or immune.
QUOTAS = {
    "T5fd": 1, "T5fp": 1,
    "T1": 8, "T2": 1, "T3": 8, "T4": 4, "T4r": 1, "T4e": 1, "M1": 1,
    "F1": 5, "F2": 5, "F2b": 4, "M2": 1,
    "F3r_low": 1, "F3r_mid": 1, "F3r_high": 1, "F3n": 2,
    "F5": 4, "F4": 3,
}
TRUE_KINDS = ("T1", "T2", "T3", "T4", "T4r", "T4e", "T5fd", "T5fp", "M1")
TWIN_KINDS = ("M1", "M2")  # an ability- or form-modified move: a True item and a False item on the same triple
MAX_ATTEMPTS_PER_KIND = 60000
# Defender abilities that change a first hit but that the calc's rolls do not model; excluded when the
# scan confirms the calc rolls ignore them and a legal species has them.
UNMODELED_WATCH = ("Sturdy", "Disguise", "Wonder Guard", "Ice Face", "Shadow Shield", "Tera Shell")

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
        self.chart = json.loads(TYPE_CHART.read_text())["effectiveness"]
        self.rules = json.loads(CALC_RULES.read_text())
        self.legal = sorted(k for k, v in self.sp.items() if v["is_nonstandard"] is None)
        # Moves with no calc type at all would be a silent zero-damage trap: assert none can be drawn.
        self.no_type_moves = {m["id"] for m in self.rules["calc_dex_gaps"]["moves"] if m["calc"][0] is None}
        self.gap_species = set(self.rules["calc_dex_gaps"]["species"])
        cond = json.loads(CONDITIONALS.read_text())
        self.conditional = set(cond["excluded"]) | {h["id"] for h in cond["hand_supplement"]}
        self.cond_doc = cond
        acc = json.loads((ROOT / "data/moves/gen9_accuracy.v1.json").read_text())
        self.accuracy = {m: acc[m]["accuracy"] for m in self.static if m in acc}

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

    def plain_eff(self, move_id: str, def_types: list[str]) -> float:
        """Plain type chart on the move's listed type (what a reader would assume)."""
        m = 1.0
        for t in def_types:
            m *= self.chart[self.moves[move_id]["type"]][t]
        return m

    def final_type(self, att: str, ability: str, move_id: str) -> str:
        return self.rules["type_changes"].get(f"{att}|{ability}|{move_id}", self.moves[move_id]["type"])

    def eff(self, att: str, ability: str, move_id: str, def_types: list[str]) -> float:
        """Effectiveness as the calc computes it: final move type, move rules, Scrappy."""
        name = self.moves[move_id]["name"]
        ft = self.final_type(att, ability, move_id)
        exc = self.rules["move_effectiveness_exceptions"].get(name, {})
        scrappy = ability in self.rules["ghost_revealing_abilities"]
        m = 1.0
        for t in def_types:
            v = exc[t] if t in exc else self.chart[ft][t]
            if scrappy and ft in ("Normal", "Fighting") and t == "Ghost":
                v = 1.0
            m *= v
        return m


def usable_moves(d: Data) -> list[str]:
    out = []
    for m in sorted(d.static):
        mv, st, fl = d.moves[m], d.static[m], d.flags[m]["flags"]
        if m in d.conditional:
            continue
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
    """Attacker (species, ability, category) triples assert_abilities rejects, and multi-hit moves (the calc
    returns one roll set per hit, so 'every roll' is not defined)."""
    ref = "garchomp"
    ok_species = [s for s in d.legal if s not in d.gap_species]
    echo = []
    reps = {"Physical": "tackle", "Special": "psychic"}
    for sid in ok_species:
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
        r = request(d, ref, "Rough Skin", m, "arcanine", d.ability_list("arcanine")[0])
        k, info = label(d, r)
        if k == "error" and info == "multi_hit":
            multi.append(m)
    return {"ability_echo_rejected": sorted(echo), "multi_hit_moves": sorted(multi)}


def quartiles(vals: list[float]) -> list[float]:
    return statistics.quantiles(sorted(vals), n=4, method="inclusive")


def build() -> dict[str, Any]:
    d = Data()
    rng = random.Random(SEED)
    usable_all = usable_moves(d)
    pre = preflight(d, usable_all)
    multi = set(pre["multi_hit_moves"])
    usable = [m for m in usable_all if m not in multi]
    ok_species = [s for s in d.legal if s not in d.gap_species]
    echo = {tuple(t) for t in pre["ability_echo_rejected"]}

    # Defender abilities whose first-hit effect the calc rolls do not model: excluded from the pool.
    no_effect = set(d.rules["defender_abilities_without_effect_on_probe_rolls"])
    legal_abilities = {a for s in ok_species for a in d.ability_list(s)}
    unmodeled = sorted(a for a in UNMODELED_WATCH if a in no_effect and a in legal_abilities)
    unmodeled_species = {a: sorted(s for s in ok_species if a in d.ability_list(s)) for a in unmodeled}

    def defender_abilities(sid: str) -> list[str]:
        return [a for a in d.ability_list(sid) if a not in unmodeled]

    def_species = [s for s in ok_species if defender_abilities(s)]
    excluded_defenders = sorted(set(ok_species) - set(def_species))

    bp = [d.moves[m]["basePower"] for m in usable]
    bp_q1, _, bp_q3 = quartiles(bp)

    def bulk(sid: str, cat: str) -> int:
        b = d.sp[sid]["base_stats"]
        return hp_stat(b["hp"], DEFENDER_HP_SP) * stat(b[DEFENSE[cat]], 0)

    bulk_cut = {c: quartiles([bulk(s, c) for s in def_species]) for c in ("Physical", "Special")}

    def bulk_quartile(sid: str, cat: str) -> int:
        v = bulk(sid, cat)
        return 1 + sum(v > c for c in bulk_cut[cat])

    def strong_cat(sid: str) -> str:
        b = d.sp[sid]["base_stats"]
        return "Physical" if b["atk"] >= b["spa"] else "Special"

    def est(att: str, att_ab: str, dfn: str, m: str) -> tuple[float, float]:
        mv, b, c = d.moves[m], d.sp[att]["base_stats"], d.sp[dfn]["base_stats"]
        cat = mv["category"]
        a = stat(b[OFFENSE[cat]], ATTACKER_SP, 1.1)
        df = stat(c[DEFENSE[cat]], 0)
        hp = hp_stat(c["hp"], DEFENDER_HP_SP)
        base = math.floor(math.floor(22 * mv["basePower"] * a / df) / 50) + 2
        mult = (1.5 if d.final_type(att, att_ab, m) in d.sp[att]["types"] else 1.0) * d.eff(att, att_ab, m, d.sp[dfn]["types"])
        return math.floor(base * 0.85 * mult) / hp, math.floor(base * mult) / hp

    learn = {s: sorted(set(d.ls[d.learnset_key(s)]) & set(usable)) if d.learnset_key(s) else [] for s in ok_species}
    for s_ in ok_species:
        assert not (set(learn[s_]) & d.no_type_moves), "a drawable move has no calc type"

    def est_plain(att: str, att_ab: str, dfn: str, m: str) -> float:
        """Estimated min roll / HP as if the move kept its listed type and the plain chart applied."""
        mv, b, c = d.moves[m], d.sp[att]["base_stats"], d.sp[dfn]["base_stats"]
        cat = mv["category"]
        a = stat(b[OFFENSE[cat]], ATTACKER_SP, 1.1)
        df = stat(c[DEFENSE[cat]], 0)
        hp = hp_stat(c["hp"], DEFENDER_HP_SP)
        base = math.floor(math.floor(22 * mv["basePower"] * a / df) / 50) + 2
        mult = (1.5 if mv["type"] in d.sp[att]["types"] else 1.0) * d.plain_eff(m, d.sp[dfn]["types"])
        return math.floor(base * 0.85 * mult) / hp

    def attrs(att: str, att_ab: str, move: str, dfn: str, res: dict) -> dict[str, Any]:
        mv = d.moves[move]
        cat = mv["category"]
        rolls, hp = res["rolls"], res["hp"]
        b = d.sp[dfn]["base_stats"]
        other = "Special" if cat == "Physical" else "Physical"
        e = d.eff(att, att_ab, move, d.sp[dfn]["types"])
        plain = d.plain_eff(move, d.sp[dfn]["types"])
        return {
            "type_changed": d.final_type(att, att_ab, move) != mv["type"],
            "accuracy": d.accuracy.get(move),
            "plain_est_min_ratio": round(est_plain(att, att_ab, dfn, move), 4),
            "effectiveness": e,
            "chart_effectiveness": plain,
            "chart_exception": e != plain,
            "high_power": mv["basePower"] >= bp_q3,
            "low_power": mv["basePower"] <= bp_q1,
            "stab": d.final_type(att, att_ab, move) in d.sp[att]["types"],
            "category_match": cat == strong_cat(att),
            "defender_bulk_quartile": bulk_quartile(dfn, cat),
            "hits_stronger_defense": b[DEFENSE[cat]] > b[DEFENSE[other]],
            "margin": round(min(rolls) / hp, 4),
            "max_ratio": round(max(rolls) / hp, 4),
        }

    def satisfied(move: str, res: dict, a: dict) -> list[str]:
        rolls, hp = res["rolls"], res["hp"]
        g = min(rolls) >= hp
        ko = sum(r >= hp for r in rolls)
        eff, hi, lo = a["effectiveness"], a["high_power"], a["low_power"]
        name = d.moves[move]["name"]
        out = []
        if g:
            if name == "Freeze-Dry" and eff >= 2 and a["chart_exception"]:
                out.append("T5fd")
            if name == "Flying Press" and eff >= 2 and a["chart_exception"]:
                out.append("T5fp")
            if a["defender_bulk_quartile"] == 1 and 0 < eff <= 0.5:
                out.append("T4r")
            if a["defender_bulk_quartile"] == 1 and a["chart_exception"]:
                out.append("T4e")
            if eff >= 2 and hi and a["margin"] <= T1_MARGIN_MAX:
                out.append("T1")
            if eff >= 2 and hi and a["margin"] >= T2_MARGIN_MIN:
                out.append("T2")
            if eff == 1 and a["stab"] and hi and a["category_match"]:
                out.append("T3")
            if a["defender_bulk_quartile"] == 1:
                out.append("T4")
        else:
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
            if hi and 0 < eff <= 0.5:
                out.append("F4")
            elif hi and eff == 0:
                out.append("F4")
        return out

    learners = {name: [s for s in ok_species if mid in learn[s]] for name, mid in (("freezedry", "freezedry"), ("flyingpress", "flyingpress"))}

    # Resisted pairs that still KO are rare, so T4r enumerates them (estimate prefilter) instead of sampling.
    resisted: list[tuple[str, str, str, str]] = []
    for x in ok_species:
        for xab in d.ability_list(x):
            for m in learn[x]:
                if (x, xab, d.moves[m]["category"]) in echo:
                    continue
                for y in def_species:
                    if y == x:
                        continue
                    e = d.eff(x, xab, m, d.sp[y]["types"])
                    if 0 < e <= 0.5 and bulk_quartile(y, d.moves[m]["category"]) == 1 and est(x, xab, y, m)[0] >= 0.55:
                        resisted.append((x, xab, m, y))
    rng.shuffle(resisted)

    def pick_pair(kind: str) -> tuple[str, str, str, str] | None:
        if kind == "T4r":
            return resisted.pop() if resisted else None
        if kind == "T5fd":
            if not learners["freezedry"]:
                return None
            att = rng.choice(learners["freezedry"])
        elif kind == "T5fp":
            if not learners["flyingpress"]:
                return None
            att = rng.choice(learners["flyingpress"])
        else:
            att = rng.choice(ok_species)
        att_ab = rng.choice([a for a in d.ability_list(att)])
        sc = strong_cat(att)
        want_strong = kind != "F2"
        moves = [m for m in learn[att] if (d.moves[m]["category"] == sc) == want_strong]
        if kind == "F1":
            moves = [m for m in moves if d.moves[m]["basePower"] <= bp_q1]
        elif kind in ("T5fd", "T5fp"):
            moves = [m for m in learn[att] if d.moves[m]["name"] == ("Freeze-Dry" if kind == "T5fd" else "Flying Press")]
        elif kind not in ("T4", "T4e"):
            moves = [m for m in moves if d.moves[m]["basePower"] >= bp_q3]
        if kind == "T3":
            moves = [m for m in moves if d.final_type(att, att_ab, m) in d.sp[att]["types"]]
        if not moves:
            return None
        m = rng.choice(moves)
        cat = d.moves[m]["category"]
        dfn = rng.choice([s for s in def_species if s != att])
        e = d.eff(att, att_ab, m, d.sp[dfn]["types"])
        lo_est, hi_est = est(att, att_ab, dfn, m)
        b = d.sp[dfn]["base_stats"]
        other = "Special" if cat == "Physical" else "Physical"
        bq = bulk_quartile(dfn, cat)
        if kind == "T5fd" and not (e >= 2 and lo_est >= 0.9):
            return None
        if kind == "T5fp" and not (e >= 2 and lo_est >= 0.9):
            return None
        if kind == "T1" and not (e >= 2 and 0.98 <= lo_est <= 1.20):
            return None
        if kind == "T2" and not (e >= 2 and lo_est >= 1.35):
            return None
        if kind == "T3" and not (e == 1 and lo_est >= 1.0):
            return None
        if kind == "T4" and not (bq == 1 and lo_est >= 1.0):
            return None
        if kind == "T4e" and not (bq == 1 and e > 0 and e != d.plain_eff(m, d.sp[dfn]["types"]) and lo_est >= 0.9):
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
        if kind == "F5" and not (bq == 4 and e >= 1 and lo_est < 1.0):
            return None
        if kind == "F4" and not (e <= 0.5):
            return None
        return att, att_ab, m, dfn

    def make_entry(kind: str, drawn_as: str, att: str, att_ab: str, m: str, dfn: str, dfn_ab: str, res: dict, a: dict) -> dict:
        rolls = res["rolls"]
        mv = d.moves[m]
        cat = mv["category"]
        return {
            "kind": kind,
            "drawn_as": drawn_as,
            "attacker_id": att, "attacker": d.sp[att]["name"], "attacker_ability": att_ab,
            "attacker_is_mega": att in d.holder,
            "nature": NATURE[cat],
            "move_id": m, "move": mv["name"], "move_category": cat, "move_basePower": mv["basePower"], "move_type": mv["type"],
            "move_final_type": d.final_type(att, att_ab, m),
            "defender_id": dfn, "defender": d.sp[dfn]["name"], "defender_ability": dfn_ab,
            "defender_is_mega": dfn in d.holder,
            "hp": res["hp"], "rolls": rolls, "min_roll": min(rolls), "max_roll": max(rolls),
            "rolls_ko_of_16": sum(r >= res["hp"] for r in rolls),
            "guaranteed_ko": min(rolls) >= res["hp"],
            "desc": res["desc"],
            "attrs": a,
        }

    pool: dict[str, list[dict]] = {k: [] for k in QUOTAS}
    keys: set[tuple[str, str, str]] = set()
    stats: dict[str, collections.Counter] = {k: collections.Counter() for k in QUOTAS}
    order = [k for k in QUOTAS if k not in TWIN_KINDS]
    for kind in order:
        target = QUOTAS[kind] * POOL_MULTIPLE
        while len(pool[kind]) < target and stats[kind]["attempts"] < MAX_ATTEMPTS_PER_KIND:
            stats[kind]["attempts"] += 1
            pr = pick_pair(kind)
            if pr is None:
                continue
            att, att_ab, m, dfn = pr
            cat = d.moves[m]["category"]
            if (att, att_ab, cat) in echo:
                stats[kind]["attacker_ability_excluded"] += 1
                continue
            if (att, m, dfn) in keys:
                stats[kind]["duplicate"] += 1
                continue
            dfn_abs = defender_abilities(dfn)
            if kind in TRUE_KINDS + ("F1", "F2", "F2b", "F3n", "F5") or kind.startswith("F3r"):
                dfn_abs = [a for a in dfn_abs if a not in STEERING_IMMUNITY.get(d.final_type(att, att_ab, m), set())] or dfn_abs
            dfn_ab = rng.choice(dfn_abs)
            res_kind, res = label(d, request(d, att, att_ab, m, dfn, dfn_ab))
            stats[kind]["calc_calls"] += 1
            if res_kind == "error":
                stats[kind]["error:" + str(res)[:40]] += 1
                continue
            a = attrs(att, att_ab, m, dfn, res)
            sat = satisfied(m, res, a)
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
            keys.add((att, m, dfn))
            pool[target_kind].append(make_entry(target_kind, kind, att, att_ab, m, dfn, dfn_ab, res, a))

    # Count every resisted-but-guaranteed-KO pair the enumeration can reach (the pool keeps only a few).
    survivors = [e for e in pool["T4r"]]
    extra = 0
    for x, xab, m, y in resisted:
        yab = rng.choice(defender_abilities(y))
        k_, res = label(d, request(d, x, xab, m, y, yab))
        if k_ == "ok" and min(res["rolls"]) >= res["hp"] and (x, m, y) not in keys:
            extra += 1
    resisted_ko_found = len(survivors) + extra

    # --- twins M1/M2: ability- or form-modified moves; one True and one False item on the same triple ---
    scrappy = d.rules["ghost_revealing_abilities"]

    def converting(att: str, ab: str, m: str) -> bool:
        ft = d.final_type(att, ab, m)
        return ft != d.moves[m]["type"] or (ab in scrappy and ft in ("Normal", "Fighting"))

    triples = [
        (x, ab, m)
        for x in ok_species for ab in d.ability_list(x) for m in learn[x]
        if converting(x, ab, m) and (x, ab, d.moves[m]["category"]) not in echo and d.moves[m]["basePower"] >= bp_q3
    ]
    def family(ab: str, m: str) -> str:
        if ab in scrappy and d.final_type("", ab, m) == d.moves[m]["type"]:
            return "Scrappy"
        return "Raging Bull" if m == "ragingbull" else ab

    # metadata only: where each conversion family dropped out (counts of attacker/ability/move triples)
    family_funnel: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for x in ok_species:
        for ab in d.ability_list(x):
            for m in learn[x]:
                if not converting(x, ab, m):
                    continue
                c_ = family_funnel[family(ab, m)]
                c_["converting_triples"] += 1
                if (x, ab, d.moves[m]["category"]) in echo:
                    c_["rejected_ability_echo"] += 1
                elif d.moves[m]["basePower"] < bp_q3:
                    c_["rejected_base_power_below_q3"] += 1
                else:
                    c_["passed_filters"] += 1

    by_family: dict[str, list[tuple[str, str, str]]] = collections.defaultdict(list)
    for t_ in triples:
        by_family[family(t_[1], t_[2])].append(t_)
    families = sorted(by_family)
    rng.shuffle(families)
    for f_ in families:
        rng.shuffle(by_family[f_])
    # one twin per conversion family, so the pool is not four copies of the same mechanism
    ordered_triples = [t_ for f_ in families for t_ in by_family[f_]]
    twin_log = []
    twin_stats = collections.Counter()
    target_pairs = QUOTAS["M1"] * POOL_MULTIPLE
    done_families: set[str] = set()
    tried_families: set[str] = set()
    for att, ab, m in ordered_triples:
        if len(twin_log) >= target_pairs:
            break
        if family(ab, m) in done_families:
            continue
        twin_stats["triples_tried"] += 1
        tried_families.add(family(ab, m))
        cat = d.moves[m]["category"]
        up, down = [], []
        for y in def_species:
            if y == att or (att, m, y) in keys:
                continue
            e = d.eff(att, ab, m, d.sp[y]["types"])
            plain = d.plain_eff(m, d.sp[y]["types"])
            lo_est, hi_est = est(att, ab, y, m)
            if e > plain and e >= 1 and lo_est >= 0.9 and est_plain(att, ab, y, m) < 0.95:
                up.append(y)
            elif e <= 0.5 and hi_est < 1.1:
                down.append(y)
        if not up or not down:
            continue
        rng.shuffle(up)
        rng.shuffle(down)

        def first(cands: list[str], want_ko: bool):
            for y in cands[:10]:
                abs_ = [x_ for x_ in defender_abilities(y) if x_ not in STEERING_IMMUNITY.get(d.final_type(att, ab, m), set())] or defender_abilities(y)
                yab = rng.choice(abs_)
                kind_, res = label(d, request(d, att, ab, m, y, yab))
                twin_stats["calc_calls"] += 1
                if kind_ != "ok":
                    continue
                at = attrs(att, ab, m, y, res)
                if want_ko and min(res["rolls"]) >= res["hp"] and at["effectiveness"] > at["chart_effectiveness"] and at["plain_est_min_ratio"] < 0.95:
                    return y, yab, res, at
                if not want_ko and min(res["rolls"]) < res["hp"] and at["effectiveness"] <= 0.5:
                    return y, yab, res, at
            return None

        g1, g2 = first(up, True), first(down, False)
        if g1 is None or g2 is None:
            twin_stats["no_twin_found"] += 1
            continue
        for kd, g in (("M1", g1), ("M2", g2)):
            y, yab, res, at = g
            keys.add((att, m, y))
            e = make_entry(kd, kd, att, ab, m, y, yab, res, at)
            e["twin"] = f"{att}|{ab}|{m}"
            pool[kd].append(e)
        done_families.add(family(ab, m))
        twin_log.append({"family": family(ab, m), "attacker": d.sp[att]["name"], "ability": ab, "move": d.moves[m]["name"],
                         "listed_type": d.moves[m]["type"], "final_type": d.final_type(att, ab, m)})
    twin_stats["families_available"] = len(families)

    def family_status(f_: str) -> str:
        if f_ in done_families:
            return "built"
        if f_ in tried_families:
            return "tried_no_twin_found"
        if f_ in by_family:
            return "passed_filters_not_tried_pair_target_reached"
        return "dropped_by_filters"

    twin_families = {f_: {**dict(c_), "status": family_status(f_)} for f_, c_ in sorted(family_funnel.items())}

    entries = sorted((e for lst in pool.values() for e in lst), key=lambda e: (e["kind"], e["attacker_id"], e["move_id"], e["defender_id"]))
    shortfalls = {k: QUOTAS[k] * POOL_MULTIPLE - len(v) for k, v in pool.items() if len(v) < QUOTAS[k] * POOL_MULTIPLE}
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
            "shortfalls": shortfalls,
            "fixed_conditions": {
                "level": LEVEL, "nature_by_category": NATURE, "attacker_sp": f"{ATTACKER_SP} in the offensive stat, 0 elsewhere",
                "defender": f"{DEFENDER_NATURE} nature, {DEFENDER_HP_SP} HP SP, 0 Def/SpD SP", "items": "none",
                "field": "no weather, terrain, screens or other field effects; single target; no critical hit; full HP; no stat stages or status",
                "calc_field": FIELD,
            },
            "cutoffs": {
                "usable_move_basePower_q1_q3": [bp_q1, bp_q3],
                "usable_moves": len(usable),
                "bulk_quartile_cuts_hp_times_defense": {k: v for k, v in bulk_cut.items()},
                "t1_margin_max": T1_MARGIN_MAX, "t2_margin_min": T2_MARGIN_MIN, "near_miss_max_over_hp": list(NEAR_MISS),
                "rolls_ko_buckets": {"low": f"<={ROLLS_LOW_MAX}", "mid": f"{ROLLS_LOW_MAX + 1}-{ROLLS_MID_MAX}", "high": f"{ROLLS_MID_MAX + 1}-15"},
            },
            "exclusions": {
                **pre,
                "species_not_in_calc": sorted(d.gap_species),
                "conditional_success_moves": {k: {"name": v["name"], "because": v["because"], "depends_on": v["depends_on"]} for k, v in sorted(d.cond_doc["excluded"].items())},
                "calc_dex_gap_moves_note": "Pound and Struggle have no learners and Growth is Status, so none can be drawn; a drawable move with no calc type fails the build",
                "defender_abilities_unmodeled_by_calc_rolls": unmodeled_species,
                "defenders_left_without_a_usable_ability": excluded_defenders,
            },
            "steering_immunity_abilities": {k: sorted(v) for k, v in STEERING_IMMUNITY.items()},
            "pins": [{"path": p, "git_blob_sha": by_path[p]["git_blob_sha"]} for p in BLOBS],
            "stone_map_sha256": hashlib.sha256(STONE_MAP.read_bytes()).hexdigest(),
            "type_chart_sha256": hashlib.sha256(TYPE_CHART.read_bytes()).hexdigest(),
            "calc_rules_sha256": hashlib.sha256(CALC_RULES.read_bytes()).hexdigest(),
            "build_stats": {**{k: dict(v) for k, v in stats.items()}, "M1_M2_twins": dict(twin_stats)},
            "twins": twin_log,
            "twin_families": twin_families,
            "resisted_but_guaranteed_ko_pairs_found": resisted_ko_found,
            "usable_moves_below_100_accuracy": {d.moves[m]["name"]: d.accuracy[m] for m in usable if d.accuracy.get(m) is not True and (d.accuracy.get(m) or 100) < 100},
            "move_conditionals_sha256": hashlib.sha256(CONDITIONALS.read_bytes()).hexdigest(),
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
    print(f"wrote {args.out}: sizes {d['meta']['pool_sizes']}; shortfalls {d['meta']['shortfalls']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
