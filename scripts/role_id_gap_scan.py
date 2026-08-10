#!/usr/bin/env python3
"""Full role_id gap scan — artifact only. Writes JSON; no classifier changes."""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from recommender.anchor_roles import classify_anchor_role, resolve_anchor_build
from recommender.ids import to_id
from recommender.legality import load_snapshot
from recommender.state import Attr, Slot
from recommender.usage_data import ingame_species_map, showdown_species_map
from recommender.usage_spreads import move_category_counts

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "artifacts" / "role_id_gap_scan_2026-08-09.json"

SUPPORT_MOVES = frozenset(
    {
        "lightscreen",
        "reflect",
        "auroraveil",
        "encore",
        "willowisp",
        "taunt",
        "fakeout",
        "followme",
        "ragepowder",
        "tailwind",
        "trickroom",
        "helpinghand",
        "wideguard",
        "quickguard",
        "allyswitch",
        "imprison",
        "disable",
        "spite",
        "snarl",
        "partingshot",
    }
)
SETUP_MOVES = frozenset(
    {
        "swordsdance",
        "nastyplot",
        "calmmind",
        "bulkup",
        "tidyup",
        "coil",
        "quiverdance",
        "dragondance",
        "shiftgear",
        "shellsmash",
        "workup",
        "growth",
        "irondefense",
        "amnesia",
        "agility",
        "rockpolish",
        "autotomize",
    }
)
PIVOT_MOVES = frozenset(
    {"uturn", "voltswitch", "flipturn", "partingshot", "teleport"}
)
REDIRECT_MOVES = frozenset({"followme", "ragepowder"})
SCREEN_MOVES = frozenset({"lightscreen", "reflect", "auroraveil"})
WEATHER_SPEED = frozenset(
    {"swiftswim", "chlorophyll", "sandrush", "slushrush"}
)
MULTI_HIT = frozenset(
    {
        "populationbomb",
        "bulletseed",
        "iciclespear",
        "rockblast",
        "armthrust",
        "watershuriken",
        "scaleshot",
        "tripleaxel",
        "dualwingbeat",
    }
)


def item_class(item: str | None) -> str:
    iid = to_id(item or "")
    if not iid:
        return "none"
    if iid == "choicescarf":
        return "choice_scarf"
    if iid in {"choiceband", "choicespecs"}:
        return "choice_attacking"
    if iid == "lifeorb":
        return "life_orb"
    if iid in {"sitrusberry", "leftovers", "rockyhelmet"}:
        return "bulky_item"
    if iid == "focussash":
        return "focus_sash"
    if iid.endswith(("ite", "itex", "itey")) or "ite" in iid:
        return "mega_stone"
    if iid == "lightclay":
        return "light_clay"
    if iid == "damprock":
        return "damp_rock"
    if iid == "heatrock":
        return "heat_rock"
    if iid == "smoothrock":
        return "smooth_rock"
    if iid == "icyrock":
        return "icy_rock"
    return "other"


def support_set(moves: list[str]) -> frozenset[str]:
    return frozenset(to_id(m) for m in moves if to_id(m) in SUPPORT_MOVES)


def setup_set(moves: list[str]) -> frozenset[str]:
    return frozenset(to_id(m) for m in moves if to_id(m) in SETUP_MOVES)


def damage_bias(moves: list[str]) -> str:
    p, s = move_category_counts(moves)
    if p == 0 and s == 0:
        return "status_only"
    if p > 0 and s > 0:
        return "mixed"
    if p > 0:
        return "physical"
    return "special"


def classify_kit(
    species: str,
    ability: str | None,
    item: str | None,
    moves: list[str],
    *,
    corpus: str,
    variant: str,
    usage_rank: int | None,
) -> dict[str, Any]:
    slot = Slot(
        species=Attr(value=species, locked=True),
        ability=Attr(value=ability, locked=True) if ability else Attr(),
        item=Attr(value=item, locked=True) if item else Attr(),
        moveset=Attr(value=list(moves), locked=True) if moves else Attr(),
    )
    build = resolve_anchor_build(slot)
    decision = classify_anchor_role(build)
    evidence = decision.evidence[0].detail if decision.evidence else None
    fallback = any(e.detail == "infer_role fallback" for e in decision.evidence)
    compendium = bool(evidence and "compendium" in evidence)
    if fallback:
        cascade = "infer_role"
    elif compendium:
        cascade = "exact"
    elif any(m.role_id and m.present for m in decision.mechanisms) and (
        decision.role_id
        in {m.role_id for m in decision.mechanisms if m.present and m.role_id}
        or any(e.detail != "infer_role fallback" for e in decision.evidence)
    ):
        # mechanism path: evidence detail is mechanic name, not infer_role/compendium
        if evidence and "compendium" not in evidence and evidence != "infer_role fallback":
            # could still be declared — we never pass user_role
            mech_roles = {
                m.role_id for m in decision.mechanisms if m.present and m.role_id
            }
            cascade = "mechanism" if decision.role_id in mech_roles else "other"
        else:
            cascade = "other"
    elif decision.role_id == "unresolved":
        cascade = "unresolved"
    else:
        mech_roles = {m.role_id for m in decision.mechanisms if m.present and m.role_id}
        cascade = "mechanism" if decision.role_id in mech_roles else "other"

    # Refine cascade from evidence source field
    if decision.evidence:
        src = decision.evidence[0].source
        detail = decision.evidence[0].detail
        if detail == "infer_role fallback":
            cascade = "infer_role"
        elif "compendium" in detail:
            cascade = "exact"
        elif src in {"usage_derived", "user_confirmed", "legality_only", "synthesized", "provisional"} and detail != "infer_role fallback":
            if decision.role_id in {
                m.role_id for m in decision.mechanisms if m.present and m.role_id
            }:
                cascade = "mechanism"
            elif "compendium" in detail:
                cascade = "exact"
            else:
                # mechanism evidence uses mechanic name as detail
                cascade = "mechanism" if any(
                    m.mechanic == detail for m in decision.mechanisms
                ) else cascade

    mechs = [
        {
            "mechanic": m.mechanic,
            "kind": m.kind,
            "relation": m.relation,
            "role_id": m.role_id,
            "importance": m.importance,
            "present": m.present,
        }
        for m in decision.mechanisms
    ]
    supp = support_set(moves)
    setups = setup_set(moves)
    support_offense = (
        decision.primary_function == "offense"
        and fallback
        and len(supp) >= 2
    )
    return {
        "corpus": corpus,
        "variant": variant,
        "usage_rank": usage_rank,
        "species": species,
        "ability": ability,
        "item": item,
        "moves": moves,
        "cascade": cascade,
        "role_id": decision.role_id,
        "secondary_role_ids": list(decision.secondary_role_ids),
        "primary_function": decision.primary_function,
        "mechanisms": mechs,
        "mechanism_role_ids": sorted(
            {m["role_id"] for m in mechs if m["role_id"] and m["present"]}
        ),
        "mechanism_kinds": sorted({m["kind"] for m in mechs if m["present"]}),
        "infer_role_fallback": fallback,
        "support_moves_present_but_offense_label": support_offense,
        "support_moves": sorted(supp),
        "setup_moves": sorted(setups),
        "pivot_moves": sorted(to_id(m) for m in moves if to_id(m) in PIVOT_MOVES),
        "item_class": item_class(item),
        "damage_bias": damage_bias(moves),
        "has_redirect": bool(supp & REDIRECT_MOVES),
        "has_screens": bool(supp & SCREEN_MOVES),
        "ability_id": to_id(ability or ""),
        "has_technician": to_id(ability or "") == "technician",
        "has_weather_speed": to_id(ability or "") in WEATHER_SPEED,
        "has_multi_hit": bool({to_id(m) for m in moves} & MULTI_HIT),
        "has_fakeout": "fakeout" in {to_id(m) for m in moves},
        "has_intimidate": to_id(ability or "") == "intimidate",
        "has_prankster": to_id(ability or "") == "prankster",
    }


def top_moves(row: dict, n: int = 4) -> list[str]:
    return [m["name"] for m in (row.get("common_moves") or [])[:n] if m.get("name")]


def top_item(row: dict) -> str | None:
    items = row.get("common_items") or []
    return items[0]["name"] if items else None


def abilities_ge5(row: dict) -> list[dict]:
    return [a for a in (row.get("common_abilities") or []) if a.get("pct", 0) >= 5]


def dual_move_clusters(row: dict) -> list[list[str]]:
    """Alternate top-4 when move index 3 and 4 both >= ~40% usage."""
    moves = row.get("common_moves") or []
    if len(moves) < 5:
        return []
    m3, m4 = moves[3], moves[4]
    if (m3.get("pct") or 0) < 40 or (m4.get("pct") or 0) < 40:
        return []
    # cluster A: indices 0,1,2,3 ; cluster B: 0,1,2,4
    names = [m.get("name") for m in moves]
    if not all(names[:5]):
        return []
    a = [names[0], names[1], names[2], names[3]]
    b = [names[0], names[1], names[2], names[4]]
    if a == b:
        return []
    return [a, b]


def signature(row: dict[str, Any]) -> str:
    """Mechanical signature for clustering — not species."""
    parts = [
        f"ability:{row['ability_id'] or 'none'}",
        f"setup:{','.join(row['setup_moves']) or 'none'}",
        f"support:{','.join(row['support_moves']) or 'none'}",
        f"item:{row['item_class']}",
        f"bias:{row['damage_bias']}",
        f"cascade:{row['cascade']}",
        f"role:{row['role_id']}",
    ]
    # compress high-value gates
    if row["has_technician"]:
        parts.append("gate:technician")
    if row["has_multi_hit"]:
        parts.append("gate:multihit")
    if row["has_weather_speed"]:
        parts.append("gate:weather_speed")
    if row["has_fakeout"]:
        parts.append("gate:fakeout")
    if row["has_intimidate"]:
        parts.append("gate:intimidate")
    if row["has_prankster"]:
        parts.append("gate:prankster")
    if row["has_screens"]:
        parts.append("gate:screens")
    if row["has_redirect"]:
        parts.append("gate:redirect")
    if row["pivot_moves"]:
        parts.append(f"pivot:{','.join(row['pivot_moves'])}")
    return "|".join(parts)


def pattern_key(row: dict[str, Any]) -> str:
    """Broader pattern key for gap table (shared mechanical family)."""
    if row["infer_role_fallback"] and row["has_technician"] and row["has_multi_hit"]:
        return "technician_multihit_offense"
    if row["infer_role_fallback"] and "tidyup" in row["setup_moves"]:
        return "tidyup_setup_unrecognized"
    if row["infer_role_fallback"] and row["setup_moves"] and not (
        set(row["setup_moves"]) & {"swordsdance", "nastyplot", "calmmind", "bulkup"}
    ):
        return f"unrecognized_setup:{','.join(row['setup_moves'])}"
    if row["support_moves_present_but_offense_label"] and row["has_screens"]:
        return "screens_support_as_offense_fallback"
    if row["support_moves_present_but_offense_label"] and row["has_prankster"]:
        return "prankster_support_as_offense_fallback"
    if row["infer_role_fallback"] and row["has_fakeout"] and row["has_intimidate"]:
        return "fakeout_intimidate_support"
    if row["infer_role_fallback"] and row["has_fakeout"]:
        return "fakeout_support"
    if row["infer_role_fallback"] and row["has_weather_speed"]:
        return "weather_speed_ability_ignored"
    if row["infer_role_fallback"] and row["item_class"] == "bulky_item" and not row["pivot_moves"]:
        return "bulky_item_false_pivot"
    if row["infer_role_fallback"] and row["item_class"] == "bulky_item" and row["pivot_moves"]:
        return "bulky_item_true_pivot"
    if row["infer_role_fallback"] and row["item_class"] in {"life_orb", "choice_attacking", "choice_scarf"}:
        return f"item_driven_offense:{row['item_class']}:{row['damage_bias']}"
    if row["infer_role_fallback"] and row["item_class"] == "mega_stone":
        return f"mega_offense_fallback:{row['damage_bias']}"
    if row["infer_role_fallback"] and row["item_class"] == "focus_sash":
        return f"sash_offense_fallback:{row['damage_bias']}"
    if row["infer_role_fallback"] and row["has_redirect"]:
        return "redirect_move_without_compendium_exact"
    if row["support_moves_present_but_offense_label"]:
        return f"support_kit_offense_fallback:supp={','.join(row['support_moves'])}"
    if row["infer_role_fallback"]:
        return f"generic_infer_fallback:{row['damage_bias']}:{row['item_class']}"
    if row["cascade"] == "exact":
        return f"compendium_ok:{row['role_id']}"
    if row["cascade"] == "mechanism":
        return f"mechanism_ok:{row['role_id']}"
    return f"other:{row['role_id']}"


def main() -> None:
    rows: list[dict[str, Any]] = []
    ing = ingame_species_map()
    ranked = sorted(ing.values(), key=lambda r: r.get("usage_rank") or 999)

    # Pass 1: baseline
    for row in ranked:
        name = row["name"]
        rank = row.get("usage_rank")
        abs0 = (abilities_ge5(row) or (row.get("common_abilities") or [{}]))[0]
        ability = abs0.get("name") if abs0 else None
        if not ability and row.get("common_abilities"):
            ability = row["common_abilities"][0].get("name")
        rows.append(
            classify_kit(
                name,
                ability,
                top_item(row),
                top_moves(row, 4),
                corpus="ingame_baseline",
                variant="ability0_item0_moves0-3",
                usage_rank=rank,
            )
        )

    # Pass 3a: ability variants (>=5%), moves/item fixed from baseline
    for row in ranked:
        name = row["name"]
        rank = row.get("usage_rank")
        item = top_item(row)
        moves = top_moves(row, 4)
        abs_list = abilities_ge5(row)
        if len(abs_list) < 2:
            continue
        for a in abs_list:
            rows.append(
                classify_kit(
                    name,
                    a["name"],
                    item,
                    moves,
                    corpus="ingame_ability_variant",
                    variant=f"ability={a['name']}_pct={a.get('pct')}",
                    usage_rank=rank,
                )
            )

    # Pass 3b: dual-set move clusters
    for row in ranked:
        name = row["name"]
        rank = row.get("usage_rank")
        ability = None
        abs_list = abilities_ge5(row) or row.get("common_abilities") or []
        if abs_list:
            ability = abs_list[0].get("name")
        item = top_item(row)
        for i, cluster in enumerate(dual_move_clusters(row)):
            rows.append(
                classify_kit(
                    name,
                    ability,
                    item,
                    cluster,
                    corpus="ingame_dual_moveset",
                    variant=f"cluster_{i}:{cluster[3]}",
                    usage_rank=rank,
                )
            )

    # Pass 2: showdown featured sets
    sd = showdown_species_map()
    for sid, row in sorted(sd.items()):
        name = row.get("name") or sid
        for i, fs in enumerate(row.get("featured_sets") or []):
            rows.append(
                classify_kit(
                    name,
                    fs.get("ability"),
                    fs.get("item"),
                    list(fs.get("moves") or [])[:4],
                    corpus="showdown_featured",
                    variant=f"featured_{i}",
                    usage_rank=None,
                )
            )

    # Underdiff flag: same species+moves+item, different abilities, same role_id
    by_kit: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        if r["corpus"] not in {"ingame_baseline", "ingame_ability_variant"}:
            continue
        key = (r["species"], tuple(r["moves"]), r["item"])
        by_kit[key].append(r)
    underdiff_species: set[str] = set()
    for key, group in by_kit.items():
        abilities = {g["ability"] for g in group}
        roles = {g["role_id"] for g in group}
        if len(abilities) >= 2 and len(roles) == 1:
            underdiff_species.add(key[0])
            for g in group:
                g["ability_ignored_underdiff"] = True
    for r in rows:
        r.setdefault("ability_ignored_underdiff", False)

    # Pattern clusters
    flagged = [
        r
        for r in rows
        if r["infer_role_fallback"]
        or r["ability_ignored_underdiff"]
        or r["support_moves_present_but_offense_label"]
    ]
    clusters: dict[str, list[dict]] = defaultdict(list)
    for r in flagged:
        clusters[pattern_key(r)].append(r)

    # Threshold: ≥2 species OR ≥1 top-20 with clear gate
    patterns_out = []
    for pkey, members in sorted(clusters.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        species = sorted({m["species"] for m in members})
        top20 = [
            m
            for m in members
            if m.get("usage_rank") is not None and m["usage_rank"] <= 20
        ]
        clear_gate = any(
            m["has_technician"]
            or m["has_weather_speed"]
            or m["has_fakeout"]
            or m["has_screens"]
            or m["has_redirect"]
            or m["has_prankster"]
            or m["setup_moves"]
            or m["item_class"] in {"bulky_item", "life_orb", "choice_attacking", "choice_scarf", "mega_stone", "light_clay"}
            for m in members
        )
        keep = len(species) >= 2 or (bool(top20) and clear_gate)
        if not keep:
            continue
        # sample damage biases
        biases = sorted({m["damage_bias"] for m in members})
        patterns_out.append(
            {
                "pattern_key": pkey,
                "species_count": len(species),
                "build_count": len(members),
                "species": species,
                "top20_species": sorted(
                    {
                        m["species"]
                        for m in members
                        if m.get("usage_rank") is not None and m["usage_rank"] <= 20
                    }
                ),
                "damage_biases": biases,
                "example_builds": [
                    {
                        "species": m["species"],
                        "ability": m["ability"],
                        "item": m["item"],
                        "moves": m["moves"],
                        "role_id": m["role_id"],
                        "cascade": m["cascade"],
                        "corpus": m["corpus"],
                        "usage_rank": m["usage_rank"],
                        "damage_bias": m["damage_bias"],
                        "flags": {
                            "infer_role_fallback": m["infer_role_fallback"],
                            "ability_ignored_underdiff": m["ability_ignored_underdiff"],
                            "support_moves_present_but_offense_label": m[
                                "support_moves_present_but_offense_label"
                            ],
                        },
                    }
                    for m in members[:5]
                ],
            }
        )

    summary = {
        "corpus_counts": {
            c: sum(1 for r in rows if r["corpus"] == c)
            for c in sorted({r["corpus"] for r in rows})
        },
        "cascade_counts": {
            c: sum(1 for r in rows if r["cascade"] == c)
            for c in sorted({r["cascade"] for r in rows})
        },
        "flag_counts": {
            "infer_role_fallback": sum(1 for r in rows if r["infer_role_fallback"]),
            "ability_ignored_underdiff": sum(
                1 for r in rows if r["ability_ignored_underdiff"]
            ),
            "support_moves_present_but_offense_label": sum(
                1 for r in rows if r["support_moves_present_but_offense_label"]
            ),
        },
        "underdiff_species": sorted(underdiff_species),
        "dual_moveset_species": sorted(
            {r["species"] for r in rows if r["corpus"] == "ingame_dual_moveset"}
        ),
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "summary": summary,
        "patterns": patterns_out,
        "builds": rows,
    }
    OUT.write_text(json.dumps(payload, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    print("patterns_kept", len(patterns_out))
    print("wrote", OUT)


if __name__ == "__main__":
    main()
