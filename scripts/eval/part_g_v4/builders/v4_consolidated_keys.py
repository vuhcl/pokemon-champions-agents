#!/usr/bin/env python3
"""H5/H15/H18(+b)/H19 helpers + remaining key patches (eval-only, ADR-060)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib import (
    ROOT,
    champions_spe,
    common_joint,
    load_legality,
    load_showdown,
    to_id,
)
from calc_store import calculate, health

OUT = Path(__file__).resolve().parents[1] / "key_artifacts" / "derived_keys.json"
FIX = Path(__file__).resolve().parents[1] / "fixtures"

WEATHER_ABILITIES = frozenset(
    {
        "Drought",
        "Drizzle",
        "Sand Stream",
        "Snow Warning",
        "Orichalcum Pulse",
        "Hadron Engine",
        "Desolate Land",
        "Primordial Sea",
        "Delta Stream",
    }
)


def clamp(evs):
    return {k: min(32, int((evs or {}).get(k) or 0)) for k in ("hp", "atk", "def", "spa", "spd", "spe")}


def h5_hatterene(sd, snap):
    hat = sd["showdown_doubles"]["species"]["hatterene"]
    j = hat["top_spreads"][0]
    item = hat["common_items"][0]["name"]
    ab = hat["common_abilities"][0]["name"]
    evs = clamp(j["evs"])
    rec = calculate(
        {
            "attacker": {
                "species": "Incineroar",
                "level": 50,
                "nature": "Adamant",
                "ability": "Intimidate",
                "item": "Life Orb",
                "evs": {"hp": 0, "atk": 32, "def": 0, "spa": 0, "spd": 4, "spe": 0},
            },
            "defender": {
                "species": "Hatterene",
                "level": 50,
                "nature": j["nature"],
                "ability": ab,
                "item": item,
                "evs": evs,
            },
            "move": "Flare Blitz",
            "field": {"gameType": "Singles"},  # single-target; no spread
        },
        "h5_inc_fb_hatterene_topjoint",
        persist=True,
    )
    # also Bold 0/0 control for false-claim note
    bold = calculate(
        {
            "attacker": {
                "species": "Incineroar",
                "level": 50,
                "nature": "Adamant",
                "ability": "Intimidate",
                "item": "Life Orb",
                "evs": {"hp": 0, "atk": 32, "def": 0, "spa": 0, "spd": 4, "spe": 0},
            },
            "defender": {
                "species": "Hatterene",
                "level": 50,
                "nature": "Bold",
                "ability": ab,
                "item": item,
                "evs": {"hp": 0, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
            },
            "move": "Flare Blitz",
            "field": {"gameType": "Singles"},
        },
        "h5_inc_fb_hatterene_bold00_control",
        persist=True,
    )
    return {
        "class": "ASSUME-STATE",
        "attacker": {
            "species": "Incineroar",
            "nature": "Adamant",
            "atk_sp": 32,
            "ability": "Intimidate",
            "item": "Life Orb",
        },
        "defender": {
            "species": "Hatterene",
            "top_joint": {"nature": j["nature"], "evs": evs, "chaos_weight": j["pct"]},
            "top_item": item,
            "ability": ab,
            "note": "Fire-resist berry would change result; top item recorded",
        },
        "assumptions": "single-target; no field modifiers",
        "key": rec.get("key"),
        "bold_0_0_control": bold.get("key"),
        "bold_0_0_not_served": True,
        "scoring": "range/%/OHKO chance; flat yes/no wrong; offer rerun",
    }


def h15_primarina(sd, snap):
    from _lib import showdown_threats_ge_cutoff

    pr = sd["showdown_doubles"]["species"]["primarina"]
    base = snap["species"]["primarina"]["base_stats"]["spe"]
    modest = next(j for j in pr["top_spreads"] if j.get("nature") == "Modest")
    spe_sp = clamp(modest["evs"])["spe"]
    modest_spe = champions_spe(base, spe_sp, "Modest")
    timid_spe = champions_spe(base, spe_sp, "Timid")

    def foe_spe(t):
        sp = sd["showdown_doubles"]["species"][t["id"]]
        j = (sp.get("top_spreads") or [None])[0]
        if not j:
            return None
        bs = (snap["species"].get(t["id"]) or {}).get("base_stats") or {}
        bspe = bs.get("spe")
        if bspe is None:
            return None
        evs = clamp(j.get("evs"))
        return {
            "id": t["id"],
            "name": t["name"],
            "nature": j.get("nature"),
            "spe_sp": evs["spe"],
            "spe": champions_spe(bspe, evs["spe"], j.get("nature") or "Hardy"),
            "usage_pct": t["usage_pct"],
        }

    foes = []
    for t in showdown_threats_ge_cutoff(sd):
        if t["id"] == "primarina":
            continue
        f = foe_spe(t)
        if f:
            foes.append(f)
    foes.sort(key=lambda x: (-x["spe"], x["name"]))

    def lists(my_spe):
        outspeeds = [f["name"] for f in foes if my_spe > f["spe"]]
        ties = [f["name"] for f in foes if my_spe == f["spe"]]
        outsped_by = [f["name"] for f in foes if my_spe < f["spe"]]
        return {
            "outspeeds": outspeeds,
            "ties": ties,
            "outsped_by": outsped_by,
            "counts": {
                "outspeeds": len(outspeeds),
                "ties": len(ties),
                "outsped_by": len(outsped_by),
            },
        }

    return {
        "modest_top": {
            "nature": "Modest",
            "evs": clamp(modest["evs"]),
            "chaos_weight": modest.get("chaos_weight", modest.get("pct")),
        },
        "modest_top_joint": {
            "nature": "Modest",
            "evs": clamp(modest["evs"]),
            "chaos_weight": modest.get("chaos_weight", modest.get("pct")),
            "chaos_weight_label": "weight (not a percentage; presenting as % = false claim)",
        },
        "timid_retained": False,
        "stated_spe_sp": spe_sp,
        "speed_stats": {
            "Modest": modest_spe,
            "Timid_same_SP_hypothetical": timid_spe,
            "base_spe": base,
        },
        "verdict_rule": (
            "'Modest' default SERVED when basis stated (only retained joint; Timid not retained) "
            "and speed tradeoff mentioned; conditional Timid OK with named benchmark matching key; "
            "'Timid is better' with no benchmark = false; fabricated Timid joint/usage = false"
        ),
        "benchmarks": {
            "modest_spe": modest_spe,
            "timid_hypothetical_spe": timid_spe,
            "foe_rule": (
                "Each ≥4.52% Showdown threat at its top retained joint Spe "
                "(Champions Spe formula); Primarina excluded"
            ),
            "modest_vs_threats": lists(modest_spe),
            "timid_hypothetical_vs_threats": lists(timid_spe),
            "foes": foes,
            "note": (
                "Named benchmark for conditional Timid must match a foe Spe row here; "
                "chaos_weight is weight not percent"
            ),
        },
    }


def h18_hyper_offense(sd, snap):
    """Legal species whose top retained joint has 32 Atk or SpA; ability not weather."""
    passes = []
    for sid, sp in sd["showdown_doubles"]["species"].items():
        legal = snap["species"].get(sid)
        if not legal or legal.get("is_nonstandard") is not None:
            continue
        joints = sp.get("top_spreads") or []
        if not joints:
            continue
        j = joints[0]
        evs = clamp(j.get("evs"))
        if evs["atk"] < 32 and evs["spa"] < 32:
            continue
        abs_ = sp.get("common_abilities") or []
        ab = abs_[0]["name"] if abs_ else next(iter((legal.get("abilities") or {}).values()), None)
        if ab in WEATHER_ABILITIES:
            continue
        passes.append(
            {
                "id": sid,
                "name": sp.get("name"),
                "nature": j.get("nature"),
                "evs": evs,
                "ability": ab,
                "boosted": "Atk" if evs["atk"] >= 32 else "SpA",
            }
        )
    return {
        "class": "ASSUME-STATE",
        "rule": (
            "every drafted/locked slot has 32 SP in Atk or SpA; "
            "candidate-only species judged by retained top Showdown joint"
        ),
        "limitation": "measures investment, not behavior",
        "pass_count": len(passes),
        "pass_list": passes,
        "weather_abilities_excluded": sorted(WEATHER_ABILITIES),
        "scoring": {
            "state_definition_equivalent_to_sp_rule_and_invite_alternate": "required",
            "state_and_proceed": "required (progress + definition together)",
            "bare_what_do_you_mean_no_progress": "fail",
            "definition_not_matching_sp_rule": "not SERVED",
            "missing_definition_statement": "not SERVED",
        },
    }


def write_fixtures():
    FIX.mkdir(parents=True, exist_ok=True)
    (FIX / "h18b_hyper_offense.json").write_text(
        json.dumps(
            {
                "note": "H18b: hyper-offense constraint recorded; legal offensive slots seeded",
                "constraints": ["hyper_offense_32_atk_or_spa", "no_weather_ability"],
                "slots": [
                    {
                        "slot": 1,
                        "species": "Garchomp",
                        "ability": "Rough Skin",
                        "item": "Choice Scarf",
                        "nature": "Jolly",
                        "evs": {"hp": 0, "atk": 32, "def": 0, "spa": 0, "spd": 2, "spe": 32},
                        "locked": True,
                    },
                    {
                        "slot": 2,
                        "species": "Dragapult",
                        "ability": "Clear Body",
                        "item": "Choice Specs",
                        "note": "Choice Specs may be Past-illegal — use Life Orb if so",
                        "nature": "Timid",
                        "evs": {"hp": 0, "atk": 0, "def": 0, "spa": 32, "spd": 2, "spe": 32},
                        "locked": True,
                    },
                ],
                "t2_ask_species": "Sinistcha",
                "t2_note": (
                    "Sinistcha top joint fails HO SP rule (Relaxed 0 Atk / 2 SpA). "
                    "Incineroar top joint PASSES (Adamant Atk-32) — do not use as the fail case."
                ),
            },
            indent=2,
        )
        + "\n"
    )
    # Fix Dragapult item to legal
    snap = load_legality()
    specs_illegal = (snap["items"].get("choicespecs") or {}).get("is_nonstandard") == "Past"
    data = json.loads((FIX / "h18b_hyper_offense.json").read_text())
    if specs_illegal:
        data["slots"][1]["item"] = "Life Orb"
        data["slots"][1].pop("note", None)
    (FIX / "h18b_hyper_offense.json").write_text(json.dumps(data, indent=2) + "\n")

    (FIX / "h25_team.json").write_text(
        json.dumps(
            {
                "note": "H25 seeded 3-member team; weakest-swap vs Kingambit",
                "slots": [
                    {"slot": 1, "species": "Pelipper", "ability": "Drizzle", "item": "Damp Rock", "locked": True},
                    {"slot": 2, "species": "Barraskewda", "ability": "Swift Swim", "item": "Life Orb", "locked": True},
                    {"slot": 3, "species": "Toxapex", "ability": "Regenerator", "item": "Black Sludge", "locked": True},
                ],
            },
            indent=2,
        )
        + "\n"
    )
    # Black Sludge may be Past — check
    if (snap["items"].get("blacksludge") or {}).get("is_nonstandard") == "Past":
        data = json.loads((FIX / "h25_team.json").read_text())
        data["slots"][2]["item"] = "Leftovers"
        (FIX / "h25_team.json").write_text(json.dumps(data, indent=2) + "\n")

    (FIX / "h26_torkoal_locked.json").write_text(
        json.dumps(
            {
                "note": "H26: Torkoal locked; Hatterene not locked",
                "slots": [
                    {
                        "slot": 1,
                        "species": "Torkoal",
                        "ability": "Drought",
                        "item": "Charcoal",
                        "locked": True,
                    }
                ],
                "hatterene_locked": False,
            },
            indent=2,
        )
        + "\n"
    )

    (FIX / "ms5_rain_conflict.json").write_text(
        json.dumps(
            {
                "note": "MS5: Charizard-Mega-Y + Solar Beam (conflict) + control slot",
                "archetype_before": None,
                "slots": [
                    {
                        "slot": 1,
                        "species": "Charizard-Mega-Y",
                        "item": "Charizardite Y",
                        "ability": "Drought",
                        "moves": ["Heat Wave", "Solar Beam", "Protect", "Scorching Sands"],
                        "locked": True,
                    },
                    {
                        "slot": 2,
                        "species": "Pelipper",
                        "ability": "Drizzle",
                        "item": "Damp Rock",
                        "moves": ["Hurricane", "U-turn", "Protect", "Tailwind"],
                        "locked": True,
                        "control_no_conflict": True,
                    },
                ],
            },
            indent=2,
        )
        + "\n"
    )

    (FIX / "mu2_mu3_team.json").write_text(
        json.dumps(
            {
                "note": "MU2/MU3: locked team + item making clause checks non-trivial; slot 2 open",
                "slots": [
                    {
                        "slot": 1,
                        "species": "Garchomp",
                        "item": "Choice Scarf",
                        "ability": "Rough Skin",
                        "locked": True,
                    },
                    {"slot": 2, "open": True},
                    {
                        "slot": 3,
                        "species": "Incineroar",
                        "item": "Sitrus Berry",
                        "ability": "Intimidate",
                        "locked": True,
                    },
                ],
            },
            indent=2,
        )
        + "\n"
    )

    (FIX / "mu4_pelipper.json").write_text(
        json.dumps(
            {
                "note": "MU4: Pelipper unlocked; interacting locked slot",
                "slots": [
                    {
                        "slot": 1,
                        "species": "Torkoal",
                        "ability": "Drought",
                        "item": "Heat Rock",
                        "locked": True,
                    },
                    {
                        "slot": 2,
                        "species": "Pelipper",
                        "ability": "Drizzle",
                        "item": "Damp Rock",
                        "locked": False,
                    },
                ],
            },
            indent=2,
        )
        + "\n"
    )

    (FIX / "sc3_two_slots.json").write_text(
        json.dumps(
            {
                "note": "SC3: species locked in slots 2 and 4",
                "slots": [
                    {"slot": 2, "species": "Archaludon", "ability": "Stamina", "item": "Leftovers", "locked": True},
                    {"slot": 4, "species": "Gholdengo", "ability": "Good as Gold", "item": "Life Orb", "locked": True},
                ],
            },
            indent=2,
        )
        + "\n"
    )


def main():
    assert health().get("status") == "ok"
    snap = load_legality()
    sd = load_showdown()
    d = json.loads(OUT.read_text())
    write_fixtures()
    d["h5"] = h5_hatterene(sd, snap)
    d["h15_primarina"] = h15_primarina(sd, snap)
    d["h18_hyper_offense"] = h18_hyper_offense(sd, snap)
    # H19: Trick Room setters from learnsets
    tr = []
    for sid, sp in snap["species"].items():
        if sp.get("is_nonstandard") is not None:
            continue
        ls = snap.get("learnsets", {}).get(sid) or snap.get("learnsets", {}).get(sp.get("base_species_id") or "")
        if not ls:
            continue
        moves = ls if not isinstance(ls, dict) else list(ls.keys())
        ids = {to_id(m) for m in moves}
        if "trickroom" in ids:
            tr.append(sp.get("name") or sid)
    d["h19_trick_room_setters"] = {
        "source": "pinned learnset contains Trick Room (own learnset; megas via base_species walk if empty)",
        "compendium_role_source": "not used in this key — learnset-only",
        "count": len(tr),
        "species": sorted(tr),
    }
    # MV3 accuracy
    acc = json.loads(
        (ROOT / "data/moves/gen9_accuracy.v1.json").read_text()
    )
    rs = (acc.get("moves") or acc).get("rockslide") or {}
    d["mv3_rock_slide"] = {
        "target": "allAdjacentFoes",
        "accuracy": rs.get("accuracy"),
        "accuracy_source": "data/moves/gen9_accuracy.v1.json",
        "required_claim": "targets all adjacent foes (both opponents in doubles)",
        "required_caveat": f"accuracy {rs.get('accuracy')}% so either/both can avoid",
        "false_claims": ["always hits both", "can't miss"],
        "targeting_without_accuracy": "not SERVED",
        "optional_separate_accuracy_rolls": "scored if made",
        "spread_0_75_dropped": "unverified — not required",
    }
    # MU1 legality asserts
    def _legal_sp(name):
        sp = snap["species"].get(to_id(name)) or {}
        return sp.get("is_nonstandard") is None

    def _legal_item(name):
        it = snap["items"].get(to_id(name)) or {}
        return it.get("is_nonstandard") is None

    d["mu1_item_clause"] = {
        "required_claim": "Item Clause blocks both Garchomp and Jolteon holding Choice Scarf",
        "garchomp_legal": _legal_sp("Garchomp"),
        "jolteon_legal": _legal_sp("Jolteon"),
        "choice_scarf_legal": _legal_item("Choice Scarf"),
    }
    d["h18b"] = {
        "class": "SERVED",
        "fixture": "fixtures/h18b_hyper_offense.json",
        "t2_fail_species": "Sinistcha",
        "incineroar_top_joint_passes_ho": True,
        "note": "Incineroar Adamant Atk-32 passes HO SP rule; Sinistcha is the fail case from the pin",
        "definition_at_t1": "established at t1 — do not re-ask at t2",
        "scoring": {
            "state_set_differs_from_usual": "required",
            "state_set_satisfies_32_sp_rule": "required",
            "offer_usual_set_instead": "required (offer is not a mutation)",
            "ho_constraint_stays_recorded": True,
            "draft_changes_only_as_t2_asks": True,
        },
    }
    d["limitations_v4"] = [
        "Spread-move 0.75 condition untested in Champions; DM3/DM4 follow calc multi-target assumption",
        "Learnsets/moves not oracle-cross-checked",
        "H18 SP rule measures investment, not behavior",
        (
            "H12 scores each threat's best move by max-roll damage into Sinistcha; "
            "accuracy and conditional effects are ignored. The Expanding Force case "
            "depends on the untested multi-target (0.75) assumption."
        ),
    ]
    d["tool_surface_v4"] = [
        (
            "Hosted /calculate takes a single move per request; a moves list per request "
            "would cut the arm's per-threat calc count (H12)."
        ),
    ]
    OUT.write_text(json.dumps(d, indent=2) + "\n")
    print("H5", d["h5"]["key"])
    print("H15 spe", d["h15_primarina"]["speed_stats"])
    print("H18 pass", d["h18_hyper_offense"]["pass_count"])
    print("H19 TR", d["h19_trick_room_setters"]["count"])
    print("MV3", d["mv3_rock_slide"])
    print("MU1", d["mu1_item_clause"])
    print("H18b", d["h18b"])


if __name__ == "__main__":
    main()
