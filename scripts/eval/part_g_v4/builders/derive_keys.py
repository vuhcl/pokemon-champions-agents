#!/usr/bin/env python3
"""Derive Part G v4 draft keys from pinned JSON only (ADR-060)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _lib import (  # noqa: E402
    SPEED_MINUS,
    SPEED_PLUS,
    base_stats,
    champions_hp,
    champions_spe,
    is_legal_species,
    load_ingame,
    load_legality,
    load_showdown,
    to_id,
)

OUT = Path(__file__).resolve().parents[1] / "key_artifacts"
OUT.mkdir(exist_ok=True)


def h11_water_hurricane(snap: dict) -> dict:
    learnsets = snap.get("learnsets") or {}
    names = []
    mega_false_pos_note = []
    for sid, sp in snap["species"].items():
        if not is_legal_species(sp):
            continue
        if "Water" not in (sp.get("types") or []):
            continue
        moves = learnsets.get(sid) or {}
        # learnsets may be {move: method} or list
        if isinstance(moves, dict):
            has = "hurricane" in {to_id(k) for k in moves}
        else:
            has = "hurricane" in {to_id(m) for m in moves}
        if has:
            names.append(sp["name"])
        # Mega Water with empty learnset: note if name suggests mega
        if "mega" in sid and not has:
            mega_false_pos_note.append(sp["name"])
    names_sorted = sorted(names, key=lambda n: to_id(n))
    return {
        "key_set": names_sorted,
        "count": len(names_sorted),
        "mega_waters_empty_learnset_examples": sorted(mega_false_pos_note)[:20],
        "note": (
            "Own learnset only; no base_species walk. "
            "Naming Mega Gyarados (empty Mega learnset) = deliberate false positive. "
            "Alternate/regional formes in scope if they pass the filter alone."
        ),
    }


def primarina_joints(sd: dict) -> dict:
    sp = sd["showdown_doubles"]["species"].get("primarina") or {}
    spreads = sp.get("top_spreads") or []
    modest = [r for r in spreads if (r.get("nature") or "") == "Modest"]
    timid = [r for r in spreads if (r.get("nature") or "") == "Timid"]

    def top(rows):
        if not rows:
            return None
        return max(rows, key=lambda r: float(r.get("pct") or 0))

    tm, td = top(modest), top(timid)
    out = {"modest_top": tm, "timid_top": td}
    if tm and td:
        base = None
        # Spe compare using SP from evs.spe
        snap = load_legality()
        base_spe = base_stats(snap, "Primarina")["spe"]
        out["modest_spe"] = champions_spe(base_spe, int((tm.get("evs") or {}).get("spe") or 0), "Modest")
        out["timid_spe"] = champions_spe(base_spe, int((td.get("evs") or {}).get("spe") or 0), "Timid")
    return out


def common_joint(sd: dict, species: str, n: int = 3) -> list:
    """COMMON_JOINT = top n retained Showdown joint spreads by chaos weight (default 3)."""
    sid = to_id(species)
    spreads = (sd["showdown_doubles"]["species"].get(sid) or {}).get("top_spreads") or []
    return spreads[:n]


def common_item(sd: dict, species: str) -> list:
    sid = to_id(species)
    return (sd["showdown_doubles"]["species"].get(sid) or {}).get("common_items") or []


def common_speed_cells(snap: dict, sd: dict, species: str) -> dict:
    """COMMON_SPEED = top 3 distinct grouped final-Speed values; scarf lines separate."""
    from speed_grid import common_speed_distinct, scarf_lines

    base = base_stats(snap, species)["spe"]
    distinct = common_speed_distinct(sd, species)
    items = common_item(sd, species)
    has_scarf = any(to_id(i.get("name") if isinstance(i, dict) else str(i)) == "choicescarf" for i in items)
    return {
        "species": species,
        "base_spe": base,
        "has_scarf_in_common_items": has_scarf,
        "common_speed_distinct": distinct,
        "scarf_lines_only": scarf_lines(base, has_scarf),
        "items": items[:8],
    }


def hu1_bulk(snap: dict) -> list:
    out = []
    for sid, sp in snap["species"].items():
        if not is_legal_species(sp):
            continue
        if "mega" in sid:
            continue
        if "Fire" not in (sp.get("types") or []):
            continue
        bs = sp["base_stats"]
        score = bs["hp"] * 2 + bs["def"] + bs["spd"]
        if score >= 350:
            out.append((sp["name"], score))
    return sorted(out, key=lambda x: (-x[1], to_id(x[0])))


def speed_pair(snap: dict, a: str, a_sp: int, a_nat: str, b: str, b_sp: int, b_nat: str) -> dict:
    return {
        a: champions_spe(base_stats(snap, a)["spe"], a_sp, a_nat),
        b: champions_spe(base_stats(snap, b)["spe"], b_sp, b_nat),
        "a_outspeeds": champions_spe(base_stats(snap, a)["spe"], a_sp, a_nat)
        > champions_spe(base_stats(snap, b)["spe"], b_sp, b_nat),
    }


def is3_is4(snap: dict) -> dict:
    def grid(species: str) -> dict:
        base = base_stats(snap, species)["spe"]
        return {
            "base": base,
            "neutral_0": champions_spe(base, 0, "Serious"),
            "neutral_32": champions_spe(base, 32, "Serious"),
            "plus_32": champions_spe(base, 32, "Timid" if species != "Slowbro" else "Timid"),
            "plus_32_scarf": champions_spe(base, 32, "Timid", scarf=True),
            "plus_32_scarf_tw": champions_spe(base, 32, "Timid", scarf=True) * 2,
            "max_stack": champions_spe(base, 32, "Timid", scarf=True) * 2,
        }

    slow = grid("Slowbro")
    # Slowbro beneficial Spe natures: Timid etc — Spe+ 
    drag = grid("Dragapult")
    pin = grid("Pincurchin")
    # Mega Alakazam
    mega_a = grid("Alakazam-Mega")
    return {
        "Slowbro": slow,
        "Dragapult": drag,
        "Pincurchin": pin,
        "Alakazam-Mega": mega_a,
        "notes": {
            "slowbro_vs_max_dragapult": {
                "drag_plus_32": drag["plus_32"],
                "slow_max_stack": slow["max_stack"],
                "reachable_only_extreme": slow["max_stack"] > drag["plus_32"],
            },
            "pincurchin_vs_mega_alakazam": {
                "pin_max_stack": pin["max_stack"],
                "mega_plus_32": mega_a["plus_32"],
                "unreachable_vs_max": pin["max_stack"] < mega_a["plus_32"],
            },
        },
    }


def mega_blaziken_spe(snap: dict) -> dict:
    base = base_stats(snap, "Blaziken-Mega")["spe"]
    jolly32 = champions_spe(base, 32, "Jolly")
    return {
        "base_spe": base,
        "jolly_32": jolly32,
        "jolly_32_plus1": int(jolly32 * 1.5),  # +1 Spe stage
        "note": "Speed Boost applies after turn ends; Scarf incompatible with stone",
    }


def hn2d_opp(snap: dict) -> dict:
    """Garchomp Jolly Spe-32 sits between Blaziken-Mega pre/post Speed Boost."""
    base = base_stats(snap, "Garchomp")["spe"]
    spe = champions_spe(base, 32, "Jolly")
    return {
        "species": "Garchomp",
        "nature": "Jolly",
        "spe_sp": 32,
        "spe": spe,
        "note": "before Speed Boost: Blaziken does not outspeed; after +1: does",
    }


def dm3_pair() -> dict:
    return {
        "attacker": "Tyranitar",
        "move": "Rock Slide",
        "targets": ["Incineroar", "Rillaboom"],
        "note": "doubles spread modifier must appear in calc into both targets",
    }


def dm4_pair() -> dict:
    return {
        "attacker": "Garchomp",
        "move": "Earthquake",
        "target": "Incineroar",
        "note": (
            "OHKO unreachable at Adamant Atk-SP 32 vs bulky Incineroar; "
            "2HKO reachable (calc probe: guaranteed 2HKO under max Atk investment)"
        ),
    }


def mt7_special() -> dict:
    return {"species": "Gholdengo", "move": "Make It Rain"}


def ix2_pain_split_magic_guard() -> dict:
    """Derive from Showdown source (not ability-description prose alone)."""
    return {
        "key": (
            "Showdown source: `.cache/pokemon-showdown/data/moves.ts` `painsplit.onHit` "
            "uses `sethp` (HP equalization, not the damage pipeline); "
            "`.cache/pokemon-showdown/data/abilities.ts` `magicguard.onDamage` only "
            "returns false when `effect.effectType !== 'Move'` — Pain Split never "
            "enters that hook via sethp, so Magic Guard does not block it. "
            ".cache HEAD `942cda7`; legality meta Showdown commit `9fb3a5b`; "
            "painsplit + magicguard text identical at both. "
            "Note: pinned `data/abilities/all.v1.json` description also lists Pain Split "
            "as direct damage; key is grounded in the TS sources above."
        ),
        "sources": [
            ".cache/pokemon-showdown/data/moves.ts#painsplit",
            ".cache/pokemon-showdown/data/abilities.ts#magicguard",
        ],
        "cache_head": "942cda71d14bf0618bd57991708a2e2734b6daba",
        "legality_meta_showdown_commit": "9fb3a5b99f1a0bea17f495c5cc1bfe04fdd19c3e",
        "painsplit_magicguard_identical_at_both_commits": True,
        "verified": True,
    }


def water_fire_intersection(snap: dict) -> list:
    out = []
    for sp in snap["species"].values():
        if not is_legal_species(sp):
            continue
        types = sp.get("types") or []
        if "Water" in types and "Fire" in types:
            out.append(sp["name"])
    return sorted(out, key=to_id)


def past_items(snap: dict) -> list:
    return sorted(
        v["name"] for v in snap["items"].values() if v.get("is_nonstandard") == "Past"
    )


def annihilape_gholdengo(snap: dict) -> dict:
    return {
        "ann_jolly32": champions_spe(base_stats(snap, "Annihilape")["spe"], 32, "Jolly"),
        "ghol_timid32": champions_spe(base_stats(snap, "Gholdengo")["spe"], 32, "Timid"),
        "ann_outspeeds_max": champions_spe(base_stats(snap, "Annihilape")["spe"], 32, "Jolly")
        > champions_spe(base_stats(snap, "Gholdengo")["spe"], 32, "Timid"),
    }


def sneasler_top(sd: dict) -> dict:
    rows = common_joint(sd, "Sneasler")
    return {"top": rows[0] if rows else None, "rows": rows}


def arch_joints(sd: dict) -> dict:
    return {"rows": common_joint(sd, "Archaludon"), "items": common_item(sd, "Archaludon")}


def slowbro_scarf_share(sd: dict) -> dict:
    items = common_item(sd, "Slowbro")
    # also check ingame
    return {"showdown_items": items}


def learnset_has(snap: dict, species: str, move: str) -> bool:
    sid = to_id(species)
    moves = (snap.get("learnsets") or {}).get(sid) or {}
    mid = to_id(move)
    if isinstance(moves, dict):
        return mid in {to_id(k) for k in moves}
    return mid in {to_id(m) for m in moves}


def flutter_specs(snap: dict) -> dict:
    fm = snap["species"].get("fluttermane") or {}
    specs = snap["items"].get("choicespecs") or {}
    return {
        "fluttermane_is_nonstandard": fm.get("is_nonstandard"),
        "choicespecs_is_nonstandard": specs.get("is_nonstandard"),
    }


def main() -> None:
    snap = load_legality()
    ing = load_ingame()
    sd = load_showdown()

    artifacts = {
        "h11": h11_water_hurricane(snap),
        "h15_primarina": primarina_joints(sd),
        "hu1": hu1_bulk(snap),
        "hn2": annihilape_gholdengo(snap),
        "hn2d_mega_blaziken": mega_blaziken_spe(snap),
        "hn2d_opp": hn2d_opp(snap),
        "dm3": dm3_pair(),
        "dm4": dm4_pair(),
        "mt7_special": mt7_special(),
        "ix2_pain_split_magic_guard": ix2_pain_split_magic_guard(),
        "hc1_water_fire": water_fire_intersection(snap),
        "past_items_count": len(past_items(snap)),
        "is3_is4": is3_is4(snap),
        "pelipper_speed": common_speed_cells(snap, sd, "Pelipper"),
        "annihilape_speed": common_speed_cells(snap, sd, "Annihilape"),
        "gholdengo_speed": common_speed_cells(snap, sd, "Gholdengo"),
        "sneasler": sneasler_top(sd),
        "archaludon": arch_joints(sd),
        "slowbro_items": slowbro_scarf_share(sd),
        "arch_snarl": learnset_has(snap, "Archaludon", "Snarl"),
        "arch_soak": learnset_has(snap, "Archaludon", "Soak"),
        "flutter_specs": flutter_specs(snap),
        "ingame_top10_usage": sorted(
            [
                (sp.get("usage_rank"), name, sid)
                for sid, sp in (ing["ingame_doubles"]["species"] or {}).items()
                for name in [sp.get("name") or sid]
                if sp.get("usage_rank") is not None
            ]
        )[:10],
    }
    # fix top10 properly
    ranked = []
    for sid, sp in (ing["ingame_doubles"]["species"] or {}).items():
        r = sp.get("usage_rank")
        if r is not None:
            ranked.append((int(r), sp.get("name") or sid, sid))
    ranked.sort()
    artifacts["ingame_top10_usage"] = ranked[:10]

    path = OUT / "derived_keys.json"
    path.write_text(json.dumps(artifacts, indent=2) + "\n")
    print(f"wrote {path}")
    print("H11:", artifacts["h11"]["key_set"])
    print("HU1:", artifacts["hu1"])
    print("H15:", artifacts["h15_primarina"])
    print("IS notes:", artifacts["is3_is4"]["notes"])
    print("HN2:", artifacts["hn2"])
    print("HN2d:", artifacts["hn2d_mega_blaziken"], "opp", artifacts["hn2d_opp"])
    print("DM3/DM4/MT7:", artifacts["dm3"], artifacts["dm4"], artifacts["mt7_special"])
    print("HC1 Water∧Fire:", artifacts["hc1_water_fire"])
    print("IX2 verified:", artifacts["ix2_pain_split_magic_guard"]["verified"])
    print("Sneasler top:", artifacts["sneasler"]["top"])
    print("Snarl/Soak:", artifacts["arch_snarl"], artifacts["arch_soak"])
    print("Flutter/Specs:", artifacts["flutter_specs"])


if __name__ == "__main__":
    main()
