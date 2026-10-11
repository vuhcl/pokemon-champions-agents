#!/usr/bin/env python3
"""H12 Calm vs Bold Sinistcha — best-of-top-4 + attacker-own-field (ADR-060)."""
from __future__ import annotations

import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib import (
    ROOT,
    SHOWDOWN_THREAT_USAGE_CUTOFF,
    common_joint,
    load_legality,
    load_showdown,
    showdown_threats_ge_cutoff,
    to_id,
)
from calc_store import calculate, health

OUT = Path(__file__).resolve().parents[1] / "key_artifacts" / "derived_keys.json"

# Fixed / level / OHKO / reciprocal — need state the key does not set.
NON_CALCABLE_MOVE_IDS = frozenset(
    {
        "seismictoss",
        "nightshade",
        "psywave",
        "superfang",
        "naturesmadness",
        "guardianofalola",
        "finalgambit",
        "endeavor",
        "counter",
        "mirrorcoat",
        "metalburst",
        "bide",
        "sonicboom",
        "dragonrage",
        "fissure",
        "horndrill",
        "guillotine",
        "sheercold",
        "climacticcrash",
    }
)

# Damaging moves that need status / boosts / current HP / hit counts / prior-turn info.
NEEDS_UNSET_STATE = {
    # status condition
    "facade": "needs_status_condition",
    "hex": "needs_status_condition",
    "infernalparade": "needs_status_condition",
    "smellingsalts": "needs_status_condition",
    "wakeupslap": "needs_status_condition",
    "dreameater": "needs_sleep",
    # boosts
    "storedpower": "needs_stat_boosts",
    "powertrip": "needs_stat_boosts",
    "punishment": "needs_foe_stat_boosts",
    # current HP
    "eruption": "needs_current_hp",
    "waterspout": "needs_current_hp",
    "flail": "needs_current_hp",
    "reversal": "needs_current_hp",
    "wringout": "needs_foe_current_hp",
    "crushgrip": "needs_foe_current_hp",
    "hardpress": "needs_foe_current_hp",
    # hit counts / prior-turn
    "ragefist": "needs_hit_count",
    "lastrespects": "needs_faint_count",
    "payback": "needs_prior_turn_order",
    "assurance": "needs_prior_turn_damage",
    "avalanche": "needs_prior_turn_damage",
    "retaliate": "needs_prior_turn_faint",
    "focuspunch": "needs_focus_setup",
    "belch": "needs_berry_consumed",
}

ABILITY_FIELD = {
    "Drizzle": {"weather": "Rain"},
    "Drought": {"weather": "Sun"},
    "Sand Stream": {"weather": "Sand"},
    "Snow Warning": {"weather": "Snow"},
    "Desolate Land": {"weather": "Harsh Sunshine"},
    "Primordial Sea": {"weather": "Heavy Rain"},
    "Delta Stream": {"weather": "Strong Winds"},
    "Orichalcum Pulse": {"weather": "Sun"},
    "Psychic Surge": {"terrain": "Psychic"},
    "Electric Surge": {"terrain": "Electric"},
    "Grassy Surge": {"terrain": "Grassy"},
    "Misty Surge": {"terrain": "Misty"},
    "Hadron Engine": {"terrain": "Electric"},
}


def clamp_evs(evs: dict) -> dict:
    return {k: min(32, int((evs or {}).get(k) or 0)) for k in ("hp", "atk", "def", "spa", "spd", "spe")}


def guaranteed_hko_hits(min_dmg: int, hp: int) -> int | None:
    if min_dmg <= 0 or hp <= 0:
        return None
    return int(math.ceil(hp / min_dmg))


def field_for_ability(ability: str) -> dict:
    base = {"gameType": "Doubles"}
    extra = ABILITY_FIELD.get(ability) or {}
    return {**base, **extra}


def normalize_damage(raw_dmg):
    if isinstance(raw_dmg, list):
        # Parental Bond etc. may nest
        flat = []
        for x in raw_dmg:
            if isinstance(x, list):
                flat.extend(x)
            else:
                flat.append(x)
        return [int(x) for x in flat]
    if isinstance(raw_dmg, (int, float)):
        return [int(raw_dmg)]
    return []


def parse_desc_move_meta(desc: str) -> dict:
    """Pull resolved BP / type hints from calc desc when present."""
    out = {}
    if not desc:
        return out
    # e.g. "Weather Ball (100 BP Water)" or "Expanding Force (120 BP)"
    m = re.search(r"\((\d+)\s*BP(?:\s+(\w+))?\)", desc)
    if m:
        out["resolved_bp"] = int(m.group(1))
        if m.group(2):
            out["resolved_type"] = m.group(2)
    if "in Psychic Terrain" in desc:
        out["terrain_noted"] = "Psychic"
    if " in Rain" in desc:
        out["weather_noted"] = "Rain"
    if " in Sun" in desc or "in harsh sunlight" in desc.lower():
        out["weather_noted"] = "Sun"
    return out


def run_hit(attacker: dict, defender: dict, move: str, field: dict, aid: str, persist: bool = True) -> dict:
    rec = calculate(
        {
            "attacker": attacker,
            "defender": defender,
            "move": move,
            "field": field,
        },
        aid,
        persist=persist,
    )
    raw = (rec.get("response") or {}).get("raw") or {}
    key = rec.get("key") or {}
    dmg = normalize_damage(raw.get("damage"))
    def_hp = (raw.get("stats") or {}).get("defender", {}).get("hp")
    min_d = min(dmg) if dmg else None
    max_d = max(dmg) if dmg else None
    hko = guaranteed_hko_hits(min_d, def_hp) if min_d is not None and def_hp else None
    desc = key.get("desc") or raw.get("desc") or ""
    return {
        "calc_id": aid,
        "move": move,
        "field": field,
        "damage_range": key.get("damage_range") or ([min_d, max_d] if min_d is not None else None),
        "min_damage": min_d,
        "max_damage": max_d,
        "defender_hp": def_hp,
        "pct_of_hp_min": (
            round(100.0 * min_d / def_hp, 2) if min_d is not None and def_hp else None
        ),
        "pct_of_hp_max": (
            round(100.0 * max_d / def_hp, 2) if max_d is not None and def_hp else None
        ),
        "guaranteed_hko_hits": hko,
        "desc": desc,
        "desc_meta": parse_desc_move_meta(desc),
        "ability_assert": rec.get("ability_assert"),
    }


def classify_move(name: str, moves_blob: dict, flags: dict, static: dict) -> dict:
    mid = to_id(name)
    ent = moves_blob.get(mid) or {}
    fl = flags.get(mid) or {}
    st = static.get(mid) or {}
    cat = ent.get("category") or fl.get("category")
    bp = ent.get("basePower")
    if bp is None:
        bp = fl.get("basePower")
    mtype = ent.get("type") or fl.get("type")
    target = st.get("target") or ent.get("target") or fl.get("target")
    info = {
        "name": name,
        "id": mid,
        "category": cat,
        "basePower": bp,
        "type": mtype,
        "target": target,
    }
    if cat == "Status" or cat not in ("Physical", "Special"):
        info["drop_reason"] = "status"
        return info
    if mid in NON_CALCABLE_MOVE_IDS:
        info["drop_reason"] = "fixed_or_level_or_reciprocal_damage"
        return info
    if mid in NEEDS_UNSET_STATE:
        info["drop_reason"] = NEEDS_UNSET_STATE[mid]
        return info
    if bp is not None and bp <= 0:
        info["drop_reason"] = "basePower_0_or_missing"
        return info
    info["drop_reason"] = None
    return info


def nature_winner(calm_hko, bold_hko, calm_max=None, bold_max=None) -> str:
    if (calm_max or 0) <= 0 and (bold_max or 0) <= 0:
        return "tie"
    if calm_hko is None or bold_hko is None:
        return "unknown"
    if calm_hko > bold_hko:
        return "Calm"
    if bold_hko > calm_hko:
        return "Bold"
    return "tie"


def aggregate(rows: list[dict], usage_by_id: dict) -> dict:
    calm_wins = bold_wins = ties = 0
    calm_w = bold_w = tie_w = 0.0
    calm_uncapped, bold_uncapped, calm_capped, bold_capped = [], [], [], []
    flips = []
    per_threat_weights = []
    for r in rows:
        w = nature_winner(
            r["calm"]["guaranteed_hko_hits"],
            r["bold"]["guaranteed_hko_hits"],
            r["calm"].get("max_damage"),
            r["bold"].get("max_damage"),
        )
        u = float(usage_by_id.get(r["threat_id"], 0.0))
        per_threat_weights.append(
            {"threat_id": r["threat_id"], "threat": r["threat"], "usage_fraction": u, "hko_winner": w}
        )
        if w == "Calm":
            calm_wins += 1
            calm_w += u
            flips.append(
                {
                    "threat": r["threat"],
                    "winner": "Calm",
                    "calm_hko": r["calm"]["guaranteed_hko_hits"],
                    "bold_hko": r["bold"]["guaranteed_hko_hits"],
                    "calm_move": r["calm"].get("move"),
                    "bold_move": r["bold"].get("move"),
                }
            )
        elif w == "Bold":
            bold_wins += 1
            bold_w += u
            flips.append(
                {
                    "threat": r["threat"],
                    "winner": "Bold",
                    "calm_hko": r["calm"]["guaranteed_hko_hits"],
                    "bold_hko": r["bold"]["guaranteed_hko_hits"],
                    "calm_move": r["calm"].get("move"),
                    "bold_move": r["bold"].get("move"),
                }
            )
        else:
            ties += 1
            tie_w += u
        for side, unc, cap in (
            ("calm", calm_uncapped, calm_capped),
            ("bold", bold_uncapped, bold_capped),
        ):
            pct = r[side].get("pct_of_hp_max")
            if pct is not None:
                unc.append(pct)
                cap.append(min(100.0, pct))

    def mean(xs):
        return round(sum(xs) / len(xs), 3) if xs else None

    overall = "Bold" if bold_wins > calm_wins else ("Calm" if calm_wins > bold_wins else "tie")
    overall_weighted = "Bold" if bold_w > calm_w else ("Calm" if calm_w > bold_w else "tie")
    return {
        "n_threats": len(rows),
        "margin": {
            "calm_strictly_better_hko_count": calm_wins,
            "bold_strictly_better_hko_count": bold_wins,
            "ties_hko_count": ties,
            "of_n": len(rows),
            "usage_weighted_calm": round(calm_w, 6),
            "usage_weighted_bold": round(bold_w, 6),
            "usage_weighted_difference_calm_minus_bold": round(calm_w - bold_w, 6),
            "note": (
                "Mixed-metric key. A claim tied to a stated metric is scored against that metric's "
                "winner. 'Mixed'/'depends on the metric' with numbers = pass. Unqualified "
                "'Calm/Bold is better' with no metric = unsupported (does not pass). "
                "Adjectives unscored; do not present the ~0.64 pp capped mean gap as meaningful."
            ),
        },
        "calm_strictly_better_hko_count": calm_wins,
        "bold_strictly_better_hko_count": bold_wins,
        "ties_hko_count": ties,
        "overall_winner_by_hko_win_counts": overall,
        "mean_pct_damage_max_roll": {
            "capped_at_100": {"Calm": mean(calm_capped), "Bold": mean(bold_capped)},
            "uncapped": {"Calm": mean(calm_uncapped), "Bold": mean(bold_uncapped)},
            "headline_uses": "capped_at_100",
            "gaps_calm_minus_bold": {
                "capped_at_100": (
                    round(mean(calm_capped) - mean(bold_capped), 3)
                    if calm_capped and bold_capped
                    else None
                ),
                "uncapped": (
                    round(mean(calm_uncapped) - mean(bold_uncapped), 3)
                    if calm_uncapped and bold_uncapped
                    else None
                ),
                "note": (
                    "gap = Calm_mean − Bold_mean. Negative ⇒ Calm takes less mean max-roll % "
                    "(Calm better for Sinistcha on this metric); positive ⇒ Bold better. "
                    "Score arm mean-damage claims against capped; uncapped accepted only if "
                    "arm labels it uncapped and matches stored uncapped."
                ),
            },
        },
        "usage_weighted_hko_wins": {
            "Calm": round(calm_w, 6),
            "Bold": round(bold_w, 6),
            "tie": round(tie_w, 6),
            "overall_winner": overall_weighted,
            "unit": "raw Showdown usage fraction (usage_pct/100)",
            "denominator": (
                "sum of raw Showdown usage fractions of the threats where the nature is "
                "strictly better; not normalized to 1"
            ),
            "per_threat_weights": per_threat_weights,
        },
        "threats_where_nature_changes_hko": flips,
        "metrics_for_scoring": [
            "hko_win_counts",
            "mean_pct_damage_max_roll",
            "usage_weighted_hko_wins",
        ],
    }


def category_split(rows: list[dict]) -> dict:
    """Physical/special split from each threat's chosen best-move category."""

    def mean(xs):
        return round(sum(xs) / len(xs), 3) if xs else None

    buckets = {"Physical": [], "Special": [], "other": []}
    cross_nature_notes = []
    for r in rows:
        calm_cat = r.get("chosen_move_category_calm")
        bold_cat = r.get("chosen_move_category_bold")
        if calm_cat != bold_cat:
            cross_nature_notes.append(
                {
                    "threat_id": r["threat_id"],
                    "threat": r["threat"],
                    "calm_move": r.get("chosen_move_calm"),
                    "calm_category": calm_cat,
                    "bold_move": r.get("chosen_move_bold"),
                    "bold_category": bold_cat,
                }
            )
        # When natures agree (current key: all), use that category; else note and skip bucket
        if calm_cat == bold_cat and calm_cat in ("Physical", "Special"):
            buckets[calm_cat].append(r)
        elif calm_cat in ("Physical", "Special") and bold_cat in ("Physical", "Special"):
            # different categories — do not double-count; leave in other with note
            buckets["other"].append(r)
        else:
            buckets["other"].append(r)

    out = {
        "rule": (
            "Category of a threat = category of its chosen best move (per nature). "
            "When natures agree on the move/category, the threat is counted once in that bucket."
        ),
        "natures_disagree_on_category": cross_nature_notes,
        "expected_reading_not_scored_as_insight": (
            "Calm takes less from special attackers and Bold less from physical ones; "
            "aggregate remains close to a wash. Must match stored figures if stated."
        ),
        "categories": {},
    }
    for cat in ("Physical", "Special"):
        rs = buckets[cat]
        calm_wins = bold_wins = ties = 0
        calm_cap, bold_cap, calm_unc, bold_unc = [], [], [], []
        ids = []
        for r in rs:
            ids.append(r["threat_id"])
            w = r.get("hko_winner")
            if w == "Calm":
                calm_wins += 1
            elif w == "Bold":
                bold_wins += 1
            else:
                ties += 1
            for side, cap_l, unc_l in (
                ("calm", calm_cap, calm_unc),
                ("bold", bold_cap, bold_unc),
            ):
                pct = r[side].get("pct_of_hp_max")
                if pct is not None:
                    unc_l.append(pct)
                    cap_l.append(min(100.0, pct))
        out["categories"][cat] = {
            "n_threats": len(rs),
            "threat_ids": ids,
            "calm_strictly_better_hko_count": calm_wins,
            "bold_strictly_better_hko_count": bold_wins,
            "ties_hko_count": ties,
            "mean_pct_damage_max_roll": {
                "capped_at_100": {"Calm": mean(calm_cap), "Bold": mean(bold_cap)},
                "uncapped": {"Calm": mean(calm_unc), "Bold": mean(bold_unc)},
                "headline_uses": "capped_at_100",
                "gaps_calm_minus_bold": {
                    "capped_at_100": (
                        round(mean(calm_cap) - mean(bold_cap), 3)
                        if calm_cap and bold_cap
                        else None
                    ),
                    "uncapped": (
                        round(mean(calm_unc) - mean(bold_unc), 3)
                        if calm_unc and bold_unc
                        else None
                    ),
                },
            },
            "which_nature_takes_less_mean_capped": (
                "Calm"
                if calm_cap and bold_cap and mean(calm_cap) < mean(bold_cap)
                else (
                    "Bold"
                    if calm_cap and bold_cap and mean(bold_cap) < mean(calm_cap)
                    else "tie"
                )
            ),
        }
    if buckets["other"]:
        out["uncategorized"] = [
            {"threat_id": r["threat_id"], "threat": r["threat"]} for r in buckets["other"]
        ]
    return out


def pick_best_move(candidates: list[dict], calm_hits: dict, bold_hits: dict, nature: str) -> dict | None:
    """Highest max-roll into that nature's Sinistcha; ties → higher usage pct."""
    hits = calm_hits if nature == "Calm" else bold_hits
    best = None
    best_key = None
    for c in candidates:
        h = hits.get(c["id"])
        if h is None:
            continue
        max_d = h.get("max_damage")
        if max_d is None:
            continue
        key = (max_d, float(c.get("pct") or 0))
        if best is None or key > best_key:
            best = c
            best_key = key
    return best


def main() -> None:
    assert health().get("status") == "ok"
    snap = load_legality()
    sd = load_showdown()
    flags = json.loads((ROOT / "data/moves/flags.v1.json").read_text())["moves"]
    static = json.loads((ROOT / "data/moves/static.v1.json").read_text())["moves"]
    moves_blob = snap.get("moves") or {}
    d = json.loads(OUT.read_text())

    threats = [t for t in showdown_threats_ge_cutoff(sd) if t["id"] != "sinistcha"]
    usage_by_id = {t["id"]: t["usage"] for t in threats}

    si = sd["showdown_doubles"]["species"]["sinistcha"]
    all_joints = si.get("top_spreads") or []
    common3 = common_joint(sd, "Sinistcha", n=3)
    top_joint = common3[0]
    top_item = ((si.get("common_items") or [{}])[0].get("name")) or "Sitrus Berry"
    top_ability = ((si.get("common_abilities") or [{}])[0].get("name")) or "Hospitality"
    base_evs = clamp_evs(top_joint.get("evs") or {})

    calm_in_top3 = [j for j in common3 if (j.get("nature") or "") == "Calm"]
    bold_in_top3 = [j for j in common3 if (j.get("nature") or "") == "Bold"]
    variant_b = None
    variant_b_drop = None
    if calm_in_top3 and bold_in_top3:
        variant_b = {
            "Calm": {
                "nature": "Calm",
                "evs": clamp_evs(calm_in_top3[0].get("evs")),
                "chaos_weight": calm_in_top3[0].get("pct"),
            },
            "Bold": {
                "nature": "Bold",
                "evs": clamp_evs(bold_in_top3[0].get("evs")),
                "chaos_weight": bold_in_top3[0].get("pct"),
            },
            "item": top_item,
            "ability": top_ability,
        }
    else:
        calm_rank = next(
            (i + 1 for i, j in enumerate(all_joints) if j.get("nature") == "Calm"), None
        )
        calm_joint = next((j for j in all_joints if j.get("nature") == "Calm"), None)
        bold_retained = [
            {
                "rank": i + 1,
                "nature": j.get("nature"),
                "evs": clamp_evs(j.get("evs")),
                "chaos_weight": j.get("pct"),
            }
            for i, j in enumerate(all_joints)
            if j.get("nature") == "Bold"
        ]
        variant_b_drop = {
            "reason": (
                "Variant B not constructible: COMMON_JOINT top-3 is Relaxed / Bold / Bold; "
                f"Calm's first joint is rank {calm_rank}"
            ),
            "top3": [
                {
                    "nature": j.get("nature"),
                    "evs": clamp_evs(j.get("evs")),
                    "chaos_weight": j.get("pct"),
                }
                for j in common3
            ],
            "calm_first_retained": (
                {
                    "rank": calm_rank,
                    "nature": "Calm",
                    "evs": clamp_evs(calm_joint.get("evs")),
                    "chaos_weight": calm_joint.get("pct"),
                }
                if calm_joint
                else None
            ),
            "bold_retained_joints": bold_retained,
            "usage_remark_scoreable": (
                "If arm remarks that Bold is retained in top-3 and Calm is not, "
                "score against top3 + calm_first_retained (not required)."
            ),
        }

    # Expanding Force + Weather Ball probes (hosted calc — not assumed)
    ef_probe = {}
    wb_probe = {}
    try:
        ef_atk = {
            "species": "Indeedee-F",
            "level": 50,
            "nature": "Modest",
            "ability": "Psychic Surge",
            "item": "Life Orb",
            "evs": {"hp": 0, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 32},
        }
        ef_def = {
            "species": "Sinistcha",
            "level": 50,
            "nature": "Calm",
            "ability": top_ability,
            "item": top_item,
            "evs": base_evs,
        }
        ef_d = run_hit(
            ef_atk,
            ef_def,
            "Expanding Force",
            {"gameType": "Doubles", "terrain": "Psychic"},
            "h12_probe_ef_doubles_pt",
            persist=True,
        )
        ef_s = run_hit(
            ef_atk,
            ef_def,
            "Expanding Force",
            {"gameType": "Singles", "terrain": "Psychic"},
            "h12_probe_ef_singles_pt",
            persist=True,
        )
        ef_probe = {
            "move": "Expanding Force",
            "static_target": (static.get("expandingforce") or {}).get("target"),
            "resolved_type": "Psychic",
            "base_bp_pinned": 80,
            "resolved_bp_under_psychic_terrain": 120,
            "resolved_target_under_pt_doubles": (
                "allAdjacentFoes (inferred): calc applies 0.75 in Doubles vs Singles"
            ),
            "under_psychic_terrain_doubles": {
                "damage_range": ef_d["damage_range"],
                "desc": ef_d["desc"],
                "desc_meta": ef_d["desc_meta"],
            },
            "under_psychic_terrain_singles": {
                "damage_range": ef_s["damage_range"],
                "desc": ef_s["desc"],
                "desc_meta": ef_s["desc_meta"],
            },
            "observed": (
                "Calc desc shows (120 BP) under Psychic Terrain (= 80 × 1.5). "
                f"Doubles range {ef_d['damage_range']} vs Singles {ef_s['damage_range']} "
                "≈ 0.75 ratio → hosted calc applies multi-target 0.75 in Doubles under PT "
                "even though static.v1 target is 'normal'."
            ),
        }
    except Exception as e:
        ef_probe = {"error": f"{type(e).__name__}: {e}"}

    try:
        # Politoed top joint for a faithful Weather Ball resolve under Drizzle→Rain
        po = sd["showdown_doubles"]["species"]["politoed"]
        pj = (po.get("top_spreads") or [{}])[0]
        pi = ((po.get("common_items") or [{}])[0].get("name")) or ""
        wb_atk = {
            "species": "Politoed",
            "level": 50,
            "nature": pj.get("nature"),
            "ability": "Drizzle",
            "evs": clamp_evs(pj.get("evs")),
        }
        if pi and to_id(pi) != "nothing":
            wb_atk["item"] = pi
        wb_def = {
            "species": "Sinistcha",
            "level": 50,
            "nature": "Calm",
            "ability": top_ability,
            "item": top_item,
            "evs": base_evs,
        }
        wb_rain = run_hit(
            wb_atk,
            wb_def,
            "Weather Ball",
            {"gameType": "Doubles", "weather": "Rain"},
            "h12_probe_wb_politoed_rain",
            persist=True,
        )
        wb_dry = run_hit(
            wb_atk,
            wb_def,
            "Weather Ball",
            {"gameType": "Doubles"},
            "h12_probe_wb_politoed_dry",
            persist=True,
        )
        wb_probe = {
            "move": "Weather Ball",
            "attacker": "Politoed",
            "ability": "Drizzle",
            "static_target": (static.get("weatherball") or {}).get("target"),
            "pinned_base": {"type": "Normal", "bp": 50},
            "under_rain_setter": {
                "field": {"gameType": "Doubles", "weather": "Rain"},
                "resolved_type": (wb_rain.get("desc_meta") or {}).get("resolved_type") or "Water",
                "resolved_bp": (wb_rain.get("desc_meta") or {}).get("resolved_bp") or 100,
                "damage_range": wb_rain["damage_range"],
                "desc": wb_rain["desc"],
                "desc_meta": wb_rain["desc_meta"],
            },
            "dry_baseline_no_weather": {
                "field": {"gameType": "Doubles"},
                "damage_range": wb_dry["damage_range"],
                "desc": wb_dry["desc"] or "(0 — Normal into Ghost)",
                "note": "Normal 50 BP into Ghost/Grass = 0 without rain",
            },
            "chosen_in_key": (
                "Ice Beam wins best-of-top-4 max-roll for Politoed; Weather Ball retained as "
                "candidate under Rain but not selected"
            ),
        }
    except Exception as e:
        wb_probe = {"error": f"{type(e).__name__}: {e}"}

    multi_move_probe = {
        "supported": False,
        "note": (
            "Hosted /calculate accepts a single `move` string only (CalcRequest.move). "
            "Passing `moves`/`moveList` returns HTTP 400. Key built with one request per "
            "candidate move × nature. Tool-surface item: a moves list per request would "
            "cut the arm's per-threat calc count."
        ),
    }

    excluded = []
    rows_a = []
    different_move_threats = []
    zero_ties = []
    setter_cases = []

    for t in threats:
        sp = sd["showdown_doubles"]["species"][t["id"]]
        joint = common_joint(sd, t["name"], n=1)
        if not joint:
            excluded.append({"threat": t["name"], "id": t["id"], "reason": "no_top_joint"})
            continue
        j0 = joint[0]
        items = sp.get("common_items") or []
        item = (items[0].get("name") if items else "") or ""
        if to_id(item) == "nothing":
            item = (items[1].get("name") if len(items) > 1 else "") or ""
        abs_ = sp.get("common_abilities") or []
        if abs_:
            ability = abs_[0]["name"]
        else:
            ab_map = (snap["species"].get(t["id"]) or {}).get("abilities") or {}
            ability = next(iter(ab_map.values()), None)
        if not ability:
            excluded.append({"threat": t["name"], "id": t["id"], "reason": "no_ability"})
            continue

        top4_raw = (sp.get("common_moves") or [])[:4]
        top4 = []
        dropped = []
        candidates = []
        for m in top4_raw:
            name = m.get("name") or ""
            info = classify_move(name, moves_blob, flags, static)
            entry = {**info, "pct": m.get("pct")}
            top4.append({"name": name, "pct": m.get("pct"), "category": info.get("category")})
            if info.get("drop_reason"):
                dropped.append({"name": name, "pct": m.get("pct"), "reason": info["drop_reason"]})
            else:
                candidates.append(entry)

        if not candidates:
            excluded.append(
                {
                    "threat": t["name"],
                    "id": t["id"],
                    "reason": "no_usable_damaging_move_in_top4",
                    "top4": top4,
                    "dropped": dropped,
                }
            )
            continue

        field = field_for_ability(ability)
        atk = {
            "species": t["name"],
            "level": 50,
            "nature": j0.get("nature"),
            "ability": ability,
            "evs": clamp_evs(j0.get("evs")),
        }
        if item:
            atk["item"] = item

        calm_def = {
            "species": "Sinistcha",
            "level": 50,
            "nature": "Calm",
            "ability": top_ability,
            "item": top_item,
            "evs": base_evs,
        }
        bold_def = {
            "species": "Sinistcha",
            "level": 50,
            "nature": "Bold",
            "ability": top_ability,
            "item": top_item,
            "evs": base_evs,
        }

        calm_hits = {}
        bold_hits = {}
        for c in candidates:
            aid = f"h12_A_{t['id']}_{c['id']}"
            calm_hits[c["id"]] = run_hit(
                atk, calm_def, c["name"], field, f"{aid}_calm", persist=True
            )
            bold_hits[c["id"]] = run_hit(
                atk, bold_def, c["name"], field, f"{aid}_bold", persist=True
            )

        best_calm = pick_best_move(candidates, calm_hits, bold_hits, "Calm")
        best_bold = pick_best_move(candidates, calm_hits, bold_hits, "Bold")
        if best_calm is None or best_bold is None:
            excluded.append(
                {
                    "threat": t["name"],
                    "id": t["id"],
                    "reason": "no_usable_damaging_move_in_top4",
                    "top4": top4,
                    "dropped": dropped,
                }
            )
            continue

        calm = {**calm_hits[best_calm["id"]], "move": best_calm["name"], "move_pct": best_calm.get("pct")}
        bold = {**bold_hits[best_bold["id"]], "move": best_bold["name"], "move_pct": best_bold.get("pct")}

        if best_calm["id"] != best_bold["id"]:
            different_move_threats.append(
                {
                    "threat": t["name"],
                    "calm_move": best_calm["name"],
                    "bold_move": best_bold["name"],
                    "calm_max": calm.get("max_damage"),
                    "bold_max": bold.get("max_damage"),
                }
            )

        winner = nature_winner(
            calm["guaranteed_hko_hits"],
            bold["guaranteed_hko_hits"],
            calm.get("max_damage"),
            bold.get("max_damage"),
        )
        zero_note = None
        if (calm.get("max_damage") or 0) <= 0 and (bold.get("max_damage") or 0) <= 0:
            zero_note = {
                "reason": "chosen_best_move_deals_0_into_sinistcha",
                "calm_move": best_calm["name"],
                "bold_move": best_bold["name"],
            }
            zero_ties.append({"threat": t["name"], "id": t["id"], **zero_note})

        # Record setter-case resolved meta for weather/terrain setters with chosen moves
        if ability in ABILITY_FIELD:
            for nature_label, hit, chosen in (
                ("Calm", calm, best_calm),
                ("Bold", bold, best_bold),
            ):
                setter_cases.append(
                    {
                        "threat": t["name"],
                        "ability": ability,
                        "field": field,
                        "nature_side": nature_label,
                        "move": chosen["name"],
                        "resolved": {
                            "desc_meta": hit.get("desc_meta"),
                            "desc": hit.get("desc"),
                            "damage_range": hit.get("damage_range"),
                            "static_target": chosen.get("target"),
                            "pinned_type": chosen.get("type"),
                            "pinned_bp": chosen.get("basePower"),
                        },
                    }
                )

        rows_a.append(
            {
                "threat_id": t["id"],
                "threat": t["name"],
                "usage_pct": t["usage_pct"],
                "attacker": {
                    "species": t["name"],
                    "joint": {
                        "nature": j0.get("nature"),
                        "evs": clamp_evs(j0.get("evs")),
                        "chaos_weight": j0.get("pct"),
                    },
                    "item": item,
                    "ability": ability,
                },
                "field": field,
                "top4_moves": top4,
                "dropped_moves": dropped,
                "candidate_moves": [
                    {"name": c["name"], "pct": c.get("pct"), "type": c.get("type"), "bp": c.get("basePower")}
                    for c in candidates
                ],
                "chosen_move_calm": best_calm["name"],
                "chosen_move_bold": best_bold["name"],
                "chosen_move_category_calm": best_calm.get("category"),
                "chosen_move_category_bold": best_bold.get("category"),
                "calm": calm,
                "bold": bold,
                "hko_winner": winner,
                "zero_damage_tie": zero_note,
            }
        )

    agg_a = aggregate(rows_a, usage_by_id)
    cat_split = category_split(rows_a)

    h12 = {
        "prompt": "Compare Calm vs Bold on Sinistcha for physical vs special attackers",
        "class": "ASSUME-STATE",
        "cutoff": SHOWDOWN_THREAT_USAGE_CUTOFF,
        "threat_pool_rule": (
            "Every Showdown doubles form with usage_pct/100 ≥ 1-0.5^(1/15) (~4.52%), "
            "minus Sinistcha"
        ),
        "threat_pool_n_before_exclusions": len(threats),
        "attackers_n": len(rows_a),
        "excluded_threats": excluded,
        "zero_damage_ties": zero_ties,
        "move_selection_rule": (
            "Top 4 Showdown doubles moves by usage (status included in the list); "
            "drop status and moves needing unset state (boosts/HP/hit counts/prior-turn); "
            "weather-dependent moves kept; among remaining, highest max-roll into Sinistcha "
            "per nature (Calm and Bold selected separately); ties → higher usage."
        ),
        "field_rule": (
            "Only field condition = weather/terrain from the attacker's own selected top ability. "
            "No Intimidate, screens, or boosts. Arm must state this."
        ),
        "ability_field_map": ABILITY_FIELD,
        "threats_where_natures_choose_different_moves": different_move_threats,
        "expanding_force_calc_probe": ef_probe,
        "weather_ball_calc_probe": wb_probe,
        "multi_move_request_probe": multi_move_probe,
        "setter_resolved_cases": setter_cases,
        "spread_assumption": (
            "Spread moves: calc gameType=Doubles applies 0.75 assuming ≥2 targets hit; "
            "Expanding Force under Psychic Terrain also observed to take 0.75 in Doubles "
            "(see expanding_force_calc_probe)"
        ),
        "baseline": (
            "Attacker-own-field only (ability weather/terrain); no Intimidate/screens/boosts; "
            "plain stages at 0"
        ),
        "sinistcha": {
            "ability": top_ability,
            "item": top_item,
            "common_joint_top3": [
                {
                    "nature": j.get("nature"),
                    "evs": clamp_evs(j.get("evs")),
                    "chaos_weight": j.get("pct"),
                }
                for j in common3
            ],
        },
        "variant_a": {
            "label": "same_spread_nature_swap",
            "source_joint_nature": top_joint.get("nature"),
            "evs": base_evs,
            "item": top_item,
            "ability": top_ability,
            "note": "Top Showdown joint SP; nature swapped Calm↔Bold; same item/ability",
            "per_threat": rows_a,
            "aggregates": agg_a,
            "physical_special_split": cat_split,
        },
        "variant_b": variant_b,
        "variant_b_drop": variant_b_drop,
        "variant_b_per_threat": None,
        "variant_b_aggregates": None,
        "a_b_disagreement": None,
        "variant_b_status": (
            variant_b_drop["reason"]
            if variant_b_drop
            else "constructible; see variant_b_aggregates"
        ),
        "sitrus_berry_note": (
            "Sinistcha holds Sitrus Berry as item context on both natures; "
            "guaranteed-HKO buckets are computed from damage rolls only "
            "(N × min_roll ≥ HP). Sitrus recovery is excluded because its trigger is conditional."
        ),
        "scoring": {
            "must_state_move_selection_rule_best_of_top4_per_nature": "required",
            "must_state_attacker_own_field_assumption": "required",
            "top1_move_rule_or_missing_field": "not SERVED",
            "per_threat_match_stated_variant": "SERVED",
            "claim_tied_to_stated_metric_scored_against_that_metric": True,
            "mixed_or_depends_on_metric_with_numbers": "pass",
            "unqualified_overall_winner_no_metric": "unsupported — does not pass",
            "wrong_winner_for_stated_metric": "false claim",
            "mean_damage_scored_against_capped": True,
            "uncapped_mean_only_if_labeled_and_matches": True,
            "capped_mean_gap_not_meaningful": (
                "≈0.64 pp — arm must not present as a meaningful separation"
            ),
            "adjectives_not_scored": True,
            "partial_threat_list_ok_if_stated_and_counts_match_subset": True,
            "closing_rerun_offer": "expected, not gated",
            "same_move_both_natures_ok_when_key_agrees": True,
            "category_claim_must_match_stored_split": True,
            "category_claim_contradicting_split": "false claim",
            "split_alone_or_aggregate_alone_or_both_ok": True,
            "aggregate_remains_substantive": True,
            "supersedes_old_rule": (
                "Replaces prior 'Calm-leaning with ties noted = pass; favoring Bold on any "
                "stored metric = false' — that line is removed; each direction can be true "
                "on some metric."
            ),
        },
        "guaranteed_hko_rule": (
            "lowest N such that N × min_roll ≥ defender HP (damage rolls only; no berry recovery)"
        ),
        "politoed_note": (
            "Politoed restored to pool; Weather Ball kept; Drizzle → Rain applied so WB is Water 100 BP"
        ),
        "zero_damage_tie_note": (
            "Zero-damage ties arise only when the chosen best-of-top-4 move deals 0 into Sinistcha "
            "(true immunity of that move), not from a prior top-1-move exclusion rule"
        ),
    }

    d["h12_sinistcha_calm_vs_bold"] = h12
    OUT.write_text(json.dumps(d, indent=2) + "\n")
    print("pool", len(threats), "usable", len(rows_a), "excluded", len(excluded))
    for e in excluded:
        print("  EXCL", e.get("threat"), e.get("reason"))
    print("diff_moves", different_move_threats)
    print("zero_ties", [(z["threat"], z.get("calm_move")) for z in zero_ties])
    print("margin", agg_a["margin"])
    print("means", agg_a["mean_pct_damage_max_roll"])
    print("flips", [(f["threat"], f["winner"], f.get("calm_move"), f.get("bold_move")) for f in agg_a["threats_where_nature_changes_hko"]])
    print("overall", agg_a["overall_winner_by_hko_win_counts"], agg_a["usage_weighted_hko_wins"]["overall_winner"])
    for cat, block in (cat_split.get("categories") or {}).items():
        print(
            "split",
            cat,
            "n",
            block["n_threats"],
            "hko",
            block["calm_strictly_better_hko_count"],
            block["bold_strictly_better_hko_count"],
            block["ties_hko_count"],
            "capped",
            block["mean_pct_damage_max_roll"]["capped_at_100"],
            "less",
            block["which_nature_takes_less_mean_capped"],
        )
    print("ef_probe", ef_probe.get("observed") or ef_probe)


if __name__ == "__main__":
    main()
