#!/usr/bin/env python3
"""Re-run independent calc checks with Champions-legal dummy defenders."""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path("/Users/nowaki027/pokemon-champions-agents")
sys.path.insert(0, str(REPO))
OUT = Path("/tmp/det_graph_capability")
MERGED = REPO / "scripts/eval/artifacts/_scratch_mc_showdown_fill/merged_usage_dir"
SHIPPED = REPO / "data/usage"


def run(usage_dir: Path) -> dict:
    from recommender.calc_client import CalcClient
    from recommender.usage_data import species_usage
    from recommender.by_usage import query_by_usage
    from recommender.legality import is_species_legal, load_snapshot
    from recommender.ids import to_id
    import recommender.usage_data as usage_data

    prev = usage_data.USAGE_DIR
    usage_data.USAGE_DIR = usage_dir
    for fn_name in ("load_usage", "species_usage", "showdown_species_map"):
        fn = getattr(usage_data, fn_name, None)
        if fn and hasattr(fn, "cache_clear"):
            fn.cache_clear()

    client = CalcClient()
    snap = load_snapshot()
    out: dict = {
        "usage_dir": str(usage_dir),
        "sp_rules": {
            "budget": 66,
            "cap_per_stat": 32,
            "source": "recommender/recommend.py SP_BUDGET/_SP_CAP; recommender/usage_spreads.py sum==66",
        },
    }

    try:
        usage_rows = query_by_usage(None, 40)
        threats = [
            getattr(r, "ladder_species", None) or getattr(r, "species", None)
            for r in usage_rows
        ]
        threats = [t for t in threats if t and is_species_legal(snap, t)]
        # Prefer usage_rank when present (merged Showdown fill can return dex-order junk).
        ranked = []
        for t in threats:
            su = species_usage(t, regulation="champions-reg-mc") or {}
            ranked.append((su.get("usage_rank") or 10**9, -(su.get("usage_pct") or 0), t))
        ranked.sort()
        if ranked and ranked[0][0] < 10**9:
            threats = [t for _, __, t in ranked[:20]]
        else:
            threats = threats[:20]
        out["threat_rank_source"] = "species_usage.usage_rank" if ranked and ranked[0][0] < 10**9 else "query_by_usage_order"
    except Exception as e:
        threats = []
        out["threats_error"] = str(e)
    out["threats"] = threats

    dummy = {
        "species": "Garchomp",
        "nature": "Impish",
        "evs": {"hp": 32, "atk": 0, "def": 32, "spa": 0, "spd": 2, "spe": 0},
        "ability": "Rough Skin",
        "item": "Rocky Helmet",
        "moves": ["Protect"],
    }

    def spe_of(species, nature, spe_sp, **kit):
        rem = 66 - spe_sp
        hp = min(32, rem)
        rem -= hp
        atk = spa = 0
        if nature in ("Adamant", "Jolly", "Brave", "Lonely"):
            atk = min(32, rem)
            rem -= atk
        else:
            spa = min(32, rem)
            rem -= spa
        spd = min(32, rem)
        rem -= spd
        defense = rem
        evs = {
            "hp": hp,
            "atk": atk,
            "def": defense,
            "spa": spa,
            "spd": spd,
            "spe": spe_sp,
        }
        r = client.calculate(
            {
                "species": species,
                "nature": nature,
                "evs": evs,
                "ability": kit.get("ability") or "Illuminate",
                "item": kit.get("item") or "Focus Sash",
                "moves": kit.get("moves") or ["Protect"],
            },
            dummy,
            "Protect",
        )
        return ((r.get("raw") or {}).get("stats") or {}).get("attacker", {}).get("spe")

    # C1
    try:
        timid = spe_of(
            "Pelipper", "Timid", 32, ability="Drizzle", item="Damp Rock", moves=["Hurricane"]
        )
        modest = spe_of(
            "Pelipper", "Modest", 32, ability="Drizzle", item="Damp Rock", moves=["Hurricane"]
        )
        flips = []
        for t in threats:
            try:
                cands = []
                for nat in ("Timid", "Jolly", "Modest", "Adamant"):
                    try:
                        cands.append(spe_of(t, nat, 32))
                    except Exception:
                        pass
                cands = [x for x in cands if x is not None]
                if not cands or timid is None or modest is None:
                    continue
                # Flip relative to each candidate speed band: use max Spe proxy for threat
                threat_spe = max(cands)
                if (timid > threat_spe) != (modest > threat_spe):
                    flips.append(
                        {
                            "threat": t,
                            "threat_spe_max_proxy": threat_spe,
                            "timid_pelipper": timid,
                            "modest_pelipper": modest,
                        }
                    )
            except Exception as e:
                flips.append({"threat": t, "error": str(e)[:120]})
        out["C1"] = {
            "pelipper_timid_spe32": timid,
            "pelipper_modest_spe32": modest,
            "flips_vs_threat_max_spe_proxy": flips,
            "n_threats": len(threats),
            "note": "Threat Spe = max over Timid/Jolly/Modest/Adamant at Spe SP=32 (usage set not always available).",
        }
    except Exception as e:
        out["C1"] = {"error": str(e)}

    # C2
    try:
        jolly = spe_of(
            "Garchomp", "Jolly", 32, ability="Rough Skin", item="Life Orb", moves=["Earthquake"]
        )
        adamant = spe_of(
            "Garchomp",
            "Adamant",
            32,
            ability="Rough Skin",
            item="Life Orb",
            moves=["Earthquake"],
        )
        flips = []
        for t in threats:
            try:
                cands = []
                for nat in ("Timid", "Jolly"):
                    try:
                        cands.append(spe_of(t, nat, 32))
                    except Exception:
                        pass
                cands = [x for x in cands if x is not None]
                if not cands:
                    continue
                threat_spe = max(cands)
                if (jolly > threat_spe) != (adamant > threat_spe):
                    flips.append(
                        {
                            "threat": t,
                            "threat_spe_max_proxy": threat_spe,
                            "jolly": jolly,
                            "adamant": adamant,
                        }
                    )
            except Exception:
                continue
        out["C2"] = {
            "garchomp_jolly_spe32": jolly,
            "garchomp_adamant_spe32": adamant,
            "flips": flips,
        }
    except Exception as e:
        out["C2"] = {"error": str(e)}

    # C3
    def kb_vs(target, atk_sp):
        rem = 66 - atk_sp
        hp = min(32, rem)
        rem -= hp
        spe = min(32, rem)
        rem -= spe
        spd = rem
        moves = ["Kowtow Cleave", "Sucker Punch", "Iron Head"]
        results = {}
        for mv in moves:
            try:
                r = client.calculate(
                    {
                        "species": "Kingambit",
                        "nature": "Adamant",
                        "evs": {
                            "hp": hp,
                            "atk": atk_sp,
                            "def": 0,
                            "spa": 0,
                            "spd": spd,
                            "spe": spe,
                        },
                        "ability": "Defiant",
                        "item": "Black Glasses",
                        "moves": moves + ["Protect"],
                    },
                    {
                        "species": target,
                        "nature": "Bold",
                        "evs": {"hp": 32, "atk": 0, "def": 20, "spa": 0, "spd": 14, "spe": 0},
                        "ability": "Illuminate",
                        "item": "Sitrus Berry",
                        "moves": ["Protect"],
                    },
                    mv,
                )
                results[mv] = {
                    "damageRange": r.get("damageRange"),
                    "koChance": r.get("koChance"),
                    "atk_stat": ((r.get("raw") or {}).get("stats") or {})
                    .get("attacker", {})
                    .get("atk"),
                }
            except Exception as e:
                results[mv] = {"error": str(e)[:160]}
        return {
            "spread": {"hp": hp, "atk": atk_sp, "def": 0, "spa": 0, "spd": spd, "spe": spe},
            "vs": results,
        }

    targets = [t for t in threats if t != "Kingambit"][:8]
    out["C3"] = {
        "targets": targets,
        "atk32": {t: kb_vs(t, 32) for t in targets},
        "atk16": {t: kb_vs(t, 16) for t in targets},
        "assumed_remainder": "hp first (cap 32), then spe, then spd; Adamant; Black Glasses",
    }

    # D1
    def sin_spread(defn, spdef):
        rem = 66 - defn - spdef
        hp = min(32, rem)
        rem -= hp
        spa = min(32, rem)
        rem -= spa
        spe = rem
        return {"hp": hp, "atk": 0, "def": defn, "spa": spa, "spd": spdef, "spe": spe}

    spreads = {
        "max_def_32": sin_spread(32, 0),
        "max_spd_32": sin_spread(0, 32),
        "split_16_16": sin_spread(16, 16),
    }
    out["D1_spreads"] = spreads
    out["D1_assumed"] = (
        "Remainder after Def/SpD: HP (cap 32), then Spa, then Spe; nature Bold; "
        "ability Hospitality; item Sitrus Berry. Attacker: Adamant Life Orb Spe32 Atk32."
    )

    def usage_moves(species: str) -> list[str]:
        su = species_usage(species, regulation="champions-reg-mc") or {}
        moves = []
        for key in ("common_moves", "moves", "Moves", "top_moves"):
            rows = su.get(key) or []
            for mrow in rows:
                if isinstance(mrow, dict):
                    m = mrow.get("move") or mrow.get("name") or mrow.get("id")
                else:
                    m = mrow
                if not m:
                    continue
                mid = to_id(str(m))
                if mid in ("protect", "substitute", "rest", "encore", "disable"):
                    continue
                moves.append(str(m))
            if moves:
                break
        for fs in su.get("featured_sets") or []:
            if isinstance(fs, dict):
                for m in fs.get("moves") or []:
                    if m and to_id(str(m)) not in ("protect", "substitute", "rest"):
                        moves.append(str(m))
        seen = set()
        out_m = []
        for m in moves:
            k = to_id(m)
            if k in seen:
                continue
            seen.add(k)
            out_m.append(m)
        return out_m[:4]

    d1 = {}
    for t in threats[:12]:
        moves = usage_moves(t)
        entry = {"moves_used": moves}
        for sname, spr in spreads.items():
            entry[sname] = {}
            for mv in moves:
                try:
                    r = client.calculate(
                        {
                            "species": t,
                            "nature": "Adamant",
                            "evs": {
                                "hp": 2,
                                "atk": 32,
                                "def": 0,
                                "spa": 0,
                                "spd": 0,
                                "spe": 32,
                            },
                            "ability": "Illuminate",
                            "item": "Life Orb",
                            "moves": [mv],
                        },
                        {
                            "species": "Sinistcha",
                            "nature": "Bold",
                            "evs": spr,
                            "ability": "Hospitality",
                            "item": "Sitrus Berry",
                            "moves": [
                                "Matcha Gotcha",
                                "Rage Powder",
                                "Strength Sap",
                                "Protect",
                            ],
                        },
                        mv,
                    )
                    # also try modest spa attacker for special moves — keep Adamant; if 0 dmg try Modest Spa
                    dr = r.get("damageRange")
                    if dr == [0, 0] or dr == (0, 0):
                        r2 = client.calculate(
                            {
                                "species": t,
                                "nature": "Modest",
                                "evs": {
                                    "hp": 2,
                                    "atk": 0,
                                    "def": 0,
                                    "spa": 32,
                                    "spd": 0,
                                    "spe": 32,
                                },
                                "ability": "Illuminate",
                                "item": "Life Orb",
                                "moves": [mv],
                            },
                            {
                                "species": "Sinistcha",
                                "nature": "Bold",
                                "evs": spr,
                                "ability": "Hospitality",
                                "item": "Sitrus Berry",
                                "moves": [
                                    "Matcha Gotcha",
                                    "Rage Powder",
                                    "Strength Sap",
                                    "Protect",
                                ],
                            },
                            mv,
                        )
                        entry[sname][mv] = {
                            "attacker_nature": "Modest",
                            "damageRange": r2.get("damageRange"),
                            "koChance": r2.get("koChance"),
                        }
                    else:
                        entry[sname][mv] = {
                            "attacker_nature": "Adamant",
                            "damageRange": dr,
                            "koChance": r.get("koChance"),
                        }
                except Exception as e:
                    entry[sname][mv] = {"error": str(e)[:160]}
        # class flips: survive vs KO between spreads for same move
        flips = []
        for mv in moves:
            classes = {}
            for sname in spreads:
                cell = entry.get(sname, {}).get(mv) or {}
                ko = str(cell.get("koChance") or "")
                if "error" in cell:
                    classes[sname] = "error"
                elif "OHKO" in ko or ko.strip() == "guaranteed OHKO":
                    classes[sname] = "OHKO"
                elif "2HKO" in ko:
                    classes[sname] = "2HKO"
                elif cell.get("damageRange") in ([0, 0], (0, 0), None):
                    classes[sname] = "nodamage"
                else:
                    classes[sname] = "chip"
            if len(set(classes.values())) > 1:
                flips.append({"move": mv, "classes": classes})
        entry["class_flips"] = flips
        d1[t] = entry
    out["D1"] = d1

    usage_data.USAGE_DIR = prev
    return out


if __name__ == "__main__":
    for label, path in (("merged", MERGED), ("shipped", SHIPPED)):
        print("running", label, flush=True)
        data = run(path)
        outp = OUT / f"independent_checks_{label}.json"
        outp.write_text(json.dumps(data, indent=2, default=str))
        print(
            "wrote",
            outp,
            "C1",
            data.get("C1"),
            "C2 flips",
            len((data.get("C2") or {}).get("flips") or []),
            flush=True,
        )
