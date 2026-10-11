#!/usr/bin/env python3
"""DM3/DM4 Intimidate on/off + DM6/DM7 keys (eval-only, ADR-060)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib import common_item_showdown, common_joint, load_legality, load_showdown, to_id
from calc_store import calculate, health

OUT = Path(__file__).resolve().parents[1] / "key_artifacts" / "derived_keys.json"

# Standalone pinned list (Showdown abilities.ts onTryBoost vs Intimidate) — not recommender.
INTIMIDATE_ATK_IMMUNE = frozenset(
    {
        "Inner Focus",
        "Own Tempo",
        "Oblivious",
        "Scrappy",
        "Guard Dog",  # blocks drop (then +1); treated as immune-to-drop for DM3/DM4 assert
    }
)
DEFIANT_COMPETITIVE = frozenset({"Defiant", "Competitive"})

# Minimal type chart for recorded effectiveness (attacking type → defender types).
TYPE_CHART = {
    "Fighting": {"Normal": 2, "Rock": 2, "Steel": 2, "Ice": 2, "Dark": 2, "Flying": 0.5, "Poison": 0.5, "Bug": 0.5, "Psychic": 0.5, "Fairy": 0.5, "Ghost": 0},
    "Ghost": {"Ghost": 2, "Psychic": 2, "Dark": 0.5, "Normal": 0},
    "Ice": {"Grass": 2, "Ground": 2, "Flying": 2, "Dragon": 2, "Fire": 0.5, "Water": 0.5, "Ice": 0.5, "Steel": 0.5},
    "Steel": {"Ice": 2, "Rock": 2, "Fairy": 2, "Fire": 0.5, "Water": 0.5, "Electric": 0.5, "Steel": 0.5},
    "Dark": {"Ghost": 2, "Psychic": 2, "Fighting": 0.5, "Dark": 0.5, "Fairy": 0.5},
}


def type_effectiveness(move_type: str, def_types: list[str]) -> float:
    chart = TYPE_CHART.get(move_type) or {}
    mult = 1.0
    for t in def_types:
        mult *= chart.get(t, 1.0)
    return mult


def top_joint(sd, species: str) -> dict:
    j = common_joint(sd, species, n=1)[0]
    evs = {k: min(32, int((j.get("evs") or {}).get(k) or 0)) for k in ("hp", "atk", "def", "spa", "spd", "spe")}
    return {"nature": j.get("nature"), "evs": evs, "chaos_weight": j.get("pct")}


def top_item(sd, species: str) -> str:
    items = common_item_showdown(sd, species)
    return (items[0].get("name") if items else "") or ""


def top_ability_showdown(sd, species: str) -> tuple[str, float]:
    abs_ = (sd["showdown_doubles"]["species"].get(to_id(species)) or {}).get("common_abilities") or []
    if not abs_:
        raise RuntimeError(f"no common_abilities for {species}")
    return abs_[0]["name"], float(abs_[0].get("pct") or 0)


def assert_attacker_ok_for_dual_case(ability: str) -> None:
    if ability in INTIMIDATE_ATK_IMMUNE:
        raise RuntimeError(f"attacker {ability} is Intimidate-immune — not a dual-case row")
    if ability in DEFIANT_COMPETITIVE:
        raise RuntimeError(f"attacker {ability} is Defiant/Competitive — use dedicated row")


def mon(species, nature, ability, item, evs, boosts=None):
    m = {
        "species": species,
        "level": 50,
        "nature": nature,
        "ability": ability,
        "evs": evs,
    }
    if item:
        m["item"] = item
    if boosts:
        m["boosts"] = boosts
    return m


def run_case(aid, attacker, defender, move, field, persist=True):
    rec = calculate(
        {"attacker": attacker, "defender": defender, "move": move, "field": field},
        aid,
        persist=persist,
    )
    key = rec.get("key") or {}
    raw = (rec.get("response") or {}).get("raw") or {}
    dmg = raw.get("damage") or []
    min_d = min(dmg) if dmg else None
    return {
        "calc_id": aid,
        "attacker_boosts": attacker.get("boosts") or {"atk": 0},
        "attacker_ability": attacker["ability"],
        "defender_ability": defender["ability"],
        "defender_spread": {
            "nature": defender["nature"],
            "evs": defender["evs"],
            "item": defender["item"],
        },
        "damage_range": key.get("damage_range"),
        "min_damage": min_d,
        "max_damage": key.get("max_damage"),
        "ko_chance": key.get("ko_chance"),
        "desc": key.get("desc") or raw.get("desc"),
        "ability_assert": rec.get("ability_assert"),
        "defender_hp": (raw.get("stats") or {}).get("defender", {}).get("hp"),
    }


def min_atk_sp_for_ohko(attacker_base, defender, move, field, aid_prefix, atk_boosts=None):
    """Lowest Atk SP in 0..32 with min_roll >= defender HP; None if unreachable at 32.

    Other SP left as in attacker_base (DM4 Garchomp baseline = all 0 except Atk).
    """
    def_hp = None
    for atk_sp in range(0, 33):
        evs = {k: int((attacker_base.get("evs") or {}).get(k) or 0) for k in ("hp", "atk", "def", "spa", "spd", "spe")}
        evs["atk"] = atk_sp
        case = run_case(
            f"{aid_prefix}_atk{atk_sp}",
            mon(
                attacker_base["species"],
                attacker_base["nature"],
                attacker_base["ability"],
                attacker_base.get("item") or "",
                evs,
                atk_boosts,
            ),
            defender,
            move,
            field,
            persist=False,
        )
        def_hp = case.get("defender_hp") or def_hp
        min_d = case.get("min_damage")
        if min_d is not None and def_hp and min_d >= def_hp:
            return {
                "min_atk_sp": atk_sp,
                "definition": "guaranteed OHKO = min_roll >= defender HP",
                "search": "Atk SP 0-32; other SP fixed from attacker baseline",
                "at_min": {
                    "damage_range": case["damage_range"],
                    "ko_chance": case["ko_chance"],
                    "min_damage": min_d,
                    "defender_hp": def_hp,
                },
            }
    return {
        "min_atk_sp": None,
        "definition": "guaranteed OHKO = min_roll >= defender HP",
        "search": "Atk SP 0-32; other SP fixed from attacker baseline",
        "unreachable_at_32": True,
        "defender_hp": def_hp,
    }


def main() -> None:
    assert health().get("status") == "ok"
    snap = load_legality()
    sd = load_showdown()
    d = json.loads(OUT.read_text())

    inc_joint = top_joint(sd, "Incineroar")
    inc_item = top_item(sd, "Incineroar")
    ril_joint = top_joint(sd, "Rillaboom")
    ril_item = top_item(sd, "Rillaboom")
    assert inc_item == "Sitrus Berry", inc_item
    assert inc_joint["nature"] == "Adamant", inc_joint

    spread_assumption = (
        "Spread moves (Rock Slide allAdjacentFoes / Earthquake allAdjacent): calc applies "
        "0.75 spread modifier when gameType=Doubles, assuming ≥2 targets are hit. "
        "The single-target figure is the same matchup without that 0.75 (labeled single-target "
        "in doubles, not a Singles-format row)."
    )

    field_d = {"gameType": "Doubles"}
    # Single-target: Singles gameType removes 0.75; labeled as single-target doubles in key.
    field_st = {"gameType": "Singles"}

    ttar = {
        "species": "Tyranitar",
        "nature": "Adamant",
        "ability": "Sand Stream",
        "item": "",
        "evs": {"hp": 0, "atk": 32, "def": 0, "spa": 0, "spd": 4, "spe": 0},
    }
    assert_attacker_ok_for_dual_case(ttar["ability"])

    garchomp = {
        "species": "Garchomp",
        "nature": "Adamant",
        "ability": "Rough Skin",
        "item": "",
        "evs": {"hp": 0, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 0},
    }
    assert_attacker_ok_for_dual_case(garchomp["ability"])

    def_inc = mon(
        "Incineroar",
        inc_joint["nature"],
        "Intimidate",
        inc_item,
        inc_joint["evs"],
    )
    def_ril = mon(
        "Rillaboom",
        ril_joint["nature"],
        "Grassy Surge",
        ril_item,
        ril_joint["evs"],
    )

    # --- DM3 ---
    dm3 = {
        "targets": ["Incineroar", "Rillaboom"],
        "move": "Rock Slide",
        "attacker": {**ttar, "item": ttar["item"] or None},
        "spread_assumption": spread_assumption,
        "intimidate_immune_list_source": "standalone Showdown abilities.ts onTryBoost vs Intimidate",
        "intimidate_atk_immune": sorted(INTIMIDATE_ATK_IMMUNE),
        "scoring": {
            "both_cases_labeled": "SERVED",
            "intimidate_on_only_with_assumption_and_offer": "SERVED (ASSUME-STATE)",
            "intimidate_off_only_or_unstated": "false claim",
            "figures_match_neither": "false claim",
        },
        "incineroar_defender": {
            "top_joint": inc_joint,
            "top_item": inc_item,
            "ability": "Intimidate",
            "cases": {
                "intimidate_on": run_case(
                    "dm3_rs_inc_intim_on",
                    mon(ttar["species"], ttar["nature"], ttar["ability"], "", ttar["evs"], {"atk": -1}),
                    def_inc,
                    "Rock Slide",
                    field_d,
                ),
                "intimidate_off": run_case(
                    "dm3_rs_inc_intim_off",
                    mon(ttar["species"], ttar["nature"], ttar["ability"], "", ttar["evs"]),
                    def_inc,
                    "Rock Slide",
                    field_d,
                ),
            },
        },
        "rillaboom_defender": {
            "top_joint": ril_joint,
            "top_item": ril_item,
            "ability": "Grassy Surge",
            "note": "Same top-joint rule as Incineroar (highest-usage Showdown joint); not a bulk Careful spread",
            "cases": {
                "intimidate_on": run_case(
                    "dm3_rs_ril_intim_on",
                    mon(ttar["species"], ttar["nature"], ttar["ability"], "", ttar["evs"], {"atk": -1}),
                    def_ril,
                    "Rock Slide",
                    field_d,
                ),
                "intimidate_off": run_case(
                    "dm3_rs_ril_intim_off",
                    mon(ttar["species"], ttar["nature"], ttar["ability"], "", ttar["evs"]),
                    def_ril,
                    "Rock Slide",
                    field_d,
                ),
            },
        },
    }

    # --- DM4 ---
    def dm4_case(aid, boosts, field):
        out = run_case(
            aid,
            mon(garchomp["species"], garchomp["nature"], garchomp["ability"], "", garchomp["evs"], boosts),
            def_inc,
            "Earthquake",
            field,
        )
        mins = min_atk_sp_for_ohko(
            garchomp, def_inc, "Earthquake", field, aid + "_min", atk_boosts=boosts
        )
        out["min_atk_sp"] = mins["min_atk_sp"]
        out["min_atk_sp_detail"] = mins
        return out

    dm4 = {
        "target": "Incineroar",
        "move": "Earthquake",
        "attacker": garchomp,
        "spread_assumption": spread_assumption,
        "ohko_definition": "guaranteed OHKO = min_roll >= defender HP; min_atk_sp searched 0-32",
        "incineroar_defender": {
            "top_joint": inc_joint,
            "top_item": inc_item,
            "ability": "Intimidate",
            "cases": {
                "intimidate_on": {
                    "spread_0_75": dm4_case("dm4_eq_inc_intim_on_spread", {"atk": -1}, field_d),
                    "single_target_doubles": dm4_case(
                        "dm4_eq_inc_intim_on_singletarget", {"atk": -1}, field_st
                    ),
                },
                "intimidate_off": {
                    "spread_0_75": dm4_case("dm4_eq_inc_intim_off_spread", None, field_d),
                    "single_target_doubles": dm4_case(
                        "dm4_eq_inc_intim_off_singletarget", None, field_st
                    ),
                },
            },
        },
        "scoring": {
            **dm3["scoring"],
            "min_atk_sp": "arm answer must match stored min_atk_sp for the case it states; null = unreachable at 32",
        },
    }

    # --- DM1: both sides from pin top joint/item (ASSUME-STATE; prompt states neither) ---
    dm_out = d.get("dm_outputs") or {}
    hat_joint = top_joint(sd, "Hatterene")
    hat_item = top_item(sd, "Hatterene")
    hat_ab, _ = top_ability_showdown(sd, "Hatterene")
    assert hat_ab == "Magic Bounce", hat_ab
    dm1_rec = run_case(
        "dm1_incineroar_flare_blitz_hatterene",
        mon(
            "Incineroar",
            inc_joint["nature"],
            "Intimidate",
            inc_item,
            inc_joint["evs"],
        ),
        mon(
            "Hatterene",
            hat_joint["nature"],
            "Magic Bounce",
            hat_item,
            hat_joint["evs"],
        ),
        "Flare Blitz",
        field_d,
    )
    dm1 = {
        "id": "DM1",
        "class": "ASSUME-STATE",
        "prompt": "Does my Incineroar's Flare Blitz KO Hatterene?",
        "attacker": {
            "species": "Incineroar",
            "nature": inc_joint["nature"],
            "evs": inc_joint["evs"],
            "item": inc_item,
            "ability": "Intimidate",
            "source": {
                "nature_sp": "showdown_doubles Incineroar top retained joint (COMMON_JOINT[0])",
                "item": "showdown_doubles Incineroar top item",
                "ability": "explicit Intimidate (top Showdown ability)",
                "joint_chaos_weight": inc_joint["chaos_weight"],
            },
        },
        "defender": {
            "species": "Hatterene",
            "nature": hat_joint["nature"],
            "evs": hat_joint["evs"],
            "item": hat_item,
            "ability": "Magic Bounce",
            "source": {
                "nature_sp": "showdown_doubles Hatterene top retained joint (same as H5)",
                "item": "showdown_doubles Hatterene top item (same as H5)",
                "ability": "explicit Magic Bounce (same as H5)",
                "joint_chaos_weight": hat_joint["chaos_weight"],
            },
        },
        "move": "Flare Blitz",
        "field": field_d,
        "key": {
            "damage_range": dm1_rec.get("damage_range"),
            "ko_chance": dm1_rec.get("ko_chance"),
            "desc": dm1_rec.get("desc"),
            "max_damage": dm1_rec.get("max_damage"),
            "min_damage": dm1_rec.get("min_damage"),
        },
        "calc": dm1_rec,
        "pair_with_h5": (
            "H5/DM1 reported separately (not pooled). H5 states Adamant Life Orb on the "
            "attacker; DM1 assumes pinned top item (not Life Orb unless it is the pin). "
            "Same Hatterene top joint/item/Magic Bounce defender."
        ),
        "scoring": {
            "stated_attacker_and_defender_match_key_and_numbers_match_calc": "SERVED",
            "stated_conditions_differ_from_key": "not SERVED",
            "bold_0_0_or_life_orb_unless_pinned": "not SERVED",
            "numbers_with_no_stated_conditions_or_flat_yes_no": "false claim",
            "rerun_offer": "expected, not gated",
        },
    }
    dm_out["dm1"] = dm1
    # DM2 fixture attacker unchanged (Adamant Life Orb Atk-32 Intimidate) — confirm below
    dm2 = dm_out.get("dm2") or {}
    dm2_attacker_note = (
        "DM2 fixture/locked attacker remains Adamant Life Orb Atk-32 ability Intimidate "
        "(not the DM1 pin top-item attacker). Grid in dm_outputs.dm2."
    )
    if dm2:
        dm2["locked_attacker_confirmed"] = {
            "nature": "Adamant",
            "item": "Life Orb",
            "ability": "Intimidate",
            "evs": {"hp": 0, "atk": 32, "def": 0, "spa": 0, "spd": 4, "spe": 0},
            "note": dm2_attacker_note,
        }
        dm_out["dm2"] = dm2

    # --- DM6 Gallade-Mega Inner Focus ---
    gallade_ability = "Inner Focus"
    assert gallade_ability in INTIMIDATE_ATK_IMMUNE
    g_joint = top_joint(sd, "Gallade-Mega")
    g_item = top_item(sd, "Gallade-Mega")
    assert g_item == "Galladite", g_item
    # Close Combat: legal via base Gallade learnset walk
    learn = (snap.get("learnsets") or {}).get("gallade") or []
    learn_ids = {to_id(m) for m in (learn if not isinstance(learn, dict) else learn.keys())}
    assert "closecombat" in learn_ids
    move_g = "Close Combat"
    move_ent = (snap.get("moves") or {}).get("closecombat") or {}
    inc_types = snap["species"]["incineroar"]["types"]
    te_g = type_effectiveness(move_ent.get("type") or "Fighting", inc_types)

    dm6 = {
        "id": "DM6",
        "attacker": {
            "species": "Gallade-Mega",
            "ability": gallade_ability,
            "item": g_item,
            "nature": g_joint["nature"],
            "evs": g_joint["evs"],
            "source": {
                "nature_sp": "showdown_doubles Gallade-Mega top retained joint (COMMON_JOINT[0])",
                "item": "showdown_doubles Gallade-Mega top item (Galladite / mega stone)",
                "ability": "mega form sole ability Inner Focus (also top Showdown ability 100%)",
                "joint_chaos_weight": g_joint["chaos_weight"],
            },
        },
        "move": move_g,
        "move_type": move_ent.get("type") or "Fighting",
        "type_effectiveness_vs_incineroar": te_g,
        "type_effectiveness_note": f"{move_ent.get('type')} vs {inc_types} = {te_g}x",
        "defender": {"top_joint": inc_joint, "top_item": inc_item, "ability": "Intimidate"},
        "single_case": "attacker_atk_stage_0",
        "single_case_note": "attacker Atk stage 0 (no Intimidate drop); Inner Focus immune",
        "false_claims": [
            "applying -1 Atk stage",
            "presenting intimidate_off as a meaningful second case",
            "stated attacker nature/SP/item differing from key",
            "numbers with no stated attacker conditions",
        ],
        "case": run_case(
            "dm6_gallade_cc_inc_atk0",
            mon("Gallade-Mega", g_joint["nature"], gallade_ability, g_item, g_joint["evs"]),
            def_inc,
            move_g,
            field_d,
        ),
        "spread_assumption": "not a spread move — no 0.75 / multi-target text",
        "class": "ASSUME-STATE",
        "scoring": {
            "arm_states_attacker_nature_sp_item_matching_key": "SERVED (ASSUME-STATE)",
            "stated_attacker_differs_from_key": "not SERVED",
            "numbers_without_stated_attacker_conditions": "false claim",
            "applying_minus1_or_second_case": "false claim",
        },
    }

    # --- DM7 Annihilape Defiant ---
    top_ab, top_pct = top_ability_showdown(sd, "Annihilape")
    assert top_ab == "Defiant", (top_ab, top_pct)
    a_joint = top_joint(sd, "Annihilape")
    a_item = top_item(sd, "Annihilape")
    # Pick physical move Incineroar does not resist — Close Combat (Fighting) is 2x
    move_a = "Close Combat"
    te_a = type_effectiveness("Fighting", inc_types)
    assert te_a >= 1.0, te_a
    # Kingambit note
    kb_moves = [
        m["name"]
        for m in (sd["showdown_doubles"]["species"]["kingambit"].get("common_moves") or [])[:4]
    ]
    kb_note = []
    for mn in kb_moves:
        mid = to_id(mn)
        mt = (snap.get("moves") or {}).get(mid, {}).get("type")
        if mt:
            kb_note.append({"move": mn, "type": mt, "effectiveness": type_effectiveness(mt, inc_types)})

    dm7 = {
        "id": "DM7",
        "attacker": {
            "species": "Annihilape",
            "ability_assumed": top_ab,
            "ability_usage_pct": top_pct,
            "nature": a_joint["nature"],
            "item": a_item,
            "evs": a_joint["evs"],
            "source": {
                "nature_sp": "showdown_doubles Annihilape top retained joint (COMMON_JOINT[0])",
                "item": "showdown_doubles Annihilape top item",
                "ability": "top Showdown ability Defiant (assumed; must be stated)",
                "joint_chaos_weight": a_joint["chaos_weight"],
            },
        },
        "move": move_a,
        "move_type": "Fighting",
        "type_effectiveness_vs_incineroar": te_a,
        "defender": {"top_joint": inc_joint, "top_item": inc_item, "ability": "Intimidate"},
        "cases": {
            "intimidate_on": run_case(
                "dm7_ape_cc_inc_defiant_on",
                mon(
                    "Annihilape",
                    a_joint["nature"],
                    "Defiant",
                    a_item,
                    a_joint["evs"],
                    {"atk": 1},  # Intimidate then Defiant → net +1
                ),
                def_inc,
                move_a,
                field_d,
            ),
            "intimidate_off": run_case(
                "dm7_ape_cc_inc_defiant_off",
                mon(
                    "Annihilape",
                    a_joint["nature"],
                    "Defiant",
                    a_item,
                    a_joint["evs"],
                ),
                def_inc,
                move_a,
                field_d,
            ),
        },
        "net_boost_note": "intimidate_on = Intimidate then Defiant → attacker Atk +1; off = 0",
        "stated_ability_must_be_top": top_ab,
        "kingambit_rejected": {
            "reason": (
                "top-4 damaging moves Kowtow Cleave / Sucker Punch / Iron Head are all "
                "0.5× vs Incineroar Fire/Dark; Protect is Status (not a damaging option)"
            ),
            "top4": kb_note,
        },
        "spread_assumption": "not a spread move — no 0.75 / multi-target text",
        "class": "ASSUME-STATE",
        "scoring": {
            **dm3["scoring"],
            "arm_states_attacker_nature_sp_item_matching_key": "required (with Defiant)",
            "stated_attacker_differs_from_key": "not SERVED",
            "numbers_without_stated_attacker_conditions": "false claim",
            "stated_ability_not_defiant": "not SERVED",
        },
    }

    dm_out["dm3"] = dm3
    dm_out["dm4"] = dm4
    dm_out["dm6"] = dm6
    dm_out["dm7"] = dm7
    dm_out["shared_incineroar_top_joint"] = {
        "joint": inc_joint,
        "item": inc_item,
        "ability": "Intimidate",
        "source": "showdown_doubles.incineroar top_spreads[0] + common_items[0] (pin 63bcefe…)",
    }
    d["dm_outputs"] = dm_out
    # keep thin dm3/dm4 pointers for gen_request_set
    d["dm3"] = {"attacker": "Tyranitar", "move": "Rock Slide", "targets": ["Incineroar", "Rillaboom"]}
    d["dm4"] = {"attacker": "Garchomp", "move": "Earthquake", "target": "Incineroar"}

    OUT.write_text(json.dumps(d, indent=2) + "\n")
    print("Incineroar joint", inc_joint, "item", inc_item)
    print("Rillaboom joint", ril_joint, "item", ril_item)
    for label, case in dm3["incineroar_defender"]["cases"].items():
        print("DM3 Inc", label, case["damage_range"], case["ko_chance"])
    for label, case in dm3["rillaboom_defender"]["cases"].items():
        print("DM3 Ril", label, case["damage_range"], case["ko_chance"])
    for label, bundle in dm4["incineroar_defender"]["cases"].items():
        print(
            "DM4",
            label,
            "spread",
            bundle["spread_0_75"]["damage_range"],
            bundle["spread_0_75"]["ko_chance"],
            "single",
            bundle["single_target_doubles"]["damage_range"],
            bundle["single_target_doubles"]["ko_chance"],
        )
    print(
        "DM6",
        g_joint,
        g_item,
        dm6["case"]["damage_range"],
        dm6["case"]["ko_chance"],
        "te",
        te_g,
    )
    print(
        "DM7",
        a_joint,
        a_item,
        "on",
        dm7["cases"]["intimidate_on"]["damage_range"],
        dm7["cases"]["intimidate_on"]["ko_chance"],
        "off",
        dm7["cases"]["intimidate_off"]["damage_range"],
        dm7["cases"]["intimidate_off"]["ko_chance"],
    )
    for label, bundle in dm4["incineroar_defender"]["cases"].items():
        for sub, case in bundle.items():
            print("DM4 min_atk_sp", label, sub, case.get("min_atk_sp"))
    print("Kingambit", kb_note)
    print(
        "DM1",
        dm1["attacker"]["nature"],
        dm1["attacker"]["evs"],
        dm1["attacker"]["item"],
        "vs",
        dm1["defender"]["nature"],
        dm1["defender"]["evs"],
        dm1["defender"]["item"],
        dm1["key"],
    )
    print("DM2 fixture", (dm_out.get("dm2") or {}).get("locked_attacker_confirmed"))


if __name__ == "__main__":
    main()
