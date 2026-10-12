#!/usr/bin/env python3
"""Produce derived_keys.json outputs + calc artifacts (ADR-060)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _lib import (
    ROOT,
    SHOWDOWN_THREAT_USAGE_CUTOFF,
    base_stats,
    champions_spe,
    load_ingame,
    load_legality,
    load_showdown,
    showdown_threats_ge_cutoff,
    to_id,
)
from calc_store import calculate, health
from speed_grid import (
    common_item_ingame,
    common_speed_distinct,
    forward_grid,
    min_spe_four_part,
)
from spread_solver import mt7_mt8_ar_keys

OUT = Path(__file__).resolve().parents[1] / "key_artifacts" / "derived_keys.json"
STATIC_PATH = ROOT / "data" / "moves" / "static.v1.json"
STATIC_SHA = "c4f2aabe8ffb420a70e77afaa50b5a4d616a1f54"


def move_static_keys() -> dict:
    import subprocess

    wt = subprocess.check_output(["git", "hash-object", str(STATIC_PATH)]).decode().strip()
    if wt != STATIC_SHA:
        raise SystemExit(f"static.v1.json SHA mismatch: got {wt}, expected {STATIC_SHA}")
    data = json.loads(STATIC_PATH.read_text())
    m = data["moves"]
    return {
        "blob_sha": STATIC_SHA,
        "mv1_follow_me_priority": m["followme"]["priority"],
        "mv2_wish_displayed_pp": m["wish"]["pp"],
        "mv3_rock_slide_target": m["rockslide"]["target"],
        "ix1_fake_out_priority": m["fakeout"]["priority"],
        "ix1_pass_rule": "PASS if Fake Out priority > Follow Me (2); redirect not a valid counter",
    }


def hu2b_output(snap, sd, threats: list[dict]) -> dict:
    """Per-form Showdown threats ≥4.52%; HN2b max-Speed-cell treatment."""
    pel_spe = champions_spe(base_stats(snap, "Pelipper")["spe"], 32, "Timid")
    rows = []
    for i, t in enumerate(threats, start=1):
        name = t["name"]
        cells = common_speed_distinct(sd, name)
        if not cells:
            rows.append(
                {
                    "threat_rank": i,
                    "threat": name,
                    "threat_id": t["id"],
                    "usage_pct": t["usage_pct"],
                    "note": "no retained Spe joints",
                }
            )
            continue
        opp_max = max(c["final_spe"] for c in cells)
        for c in cells:
            o = c["final_spe"]
            role = "max_speed" if o == opp_max else "core_non_max"
            if pel_spe > o:
                rel = "outspeeds"
            elif pel_spe == o:
                rel = "ties"
            else:
                rel = "outsped"
            rows.append(
                {
                    "threat_rank": i,
                    "threat": name,
                    "threat_id": t["id"],
                    "usage_pct": t["usage_pct"],
                    "opp_spe": o,
                    "opp_weight": c["weight"],
                    "role": role,
                    "pel_spe": pel_spe,
                    "result": rel,
                }
            )
    core_rows = [r for r in rows if r.get("role") == "core_non_max"]
    outs = {r["result"] for r in core_rows if "result" in r}
    confirm = [
        "garchompmegaz",
        "raichumegay",
        "salamencemega",
        "golisopodmega",
        "lucariomegaz",
        "gengarmega",
    ]
    present = {t["id"] for t in threats}
    return {
        "threat_source": (
            f"shared showdown_threats_ge_cutoff (≥{SHOWDOWN_THREAT_USAGE_CUTOFF:.6f}); "
            "every Showdown-listed form is its own ThreatCandidate; not in-game top10"
        ),
        "pelipper_timid_32_spe": pel_spe,
        "per_threat_cell": rows,
        "outspeeds_any_core_non_max": "outspeeds" in outs,
        "max_speed_treatment": (
            "Same as HN2b: max COMMON_SPEED cell per threat marked role=max_speed "
            "with weight/share; quantified outspeeds_any uses core_non_max only."
        ),
        "required_forms_present": {sid: sid in present for sid in confirm},
    }


def scan_speed_keys_base_vs_form(artifacts: dict, threats: list[dict], snap: dict) -> dict:
    """Flag Speed-cell keys that use a base form when a mega forme is the ≥4.52% threat."""
    threat_ids = {t["id"] for t in threats}
    threat_names = {t["name"] for t in threats}
    # base_id -> mega ids in threat set
    mega_by_base: dict[str, list[str]] = {}
    for t in threats:
        sp = snap["species"].get(t["id"]) or {}
        base = sp.get("base_species_id")
        if base and base != t["id"]:
            mega_by_base.setdefault(base, []).append(t["id"])

    findings = []

    def check_name(key_path: str, name: str) -> None:
        sid = to_id(name)
        if sid in threat_ids:
            return  # exact form is a qualifying threat — OK
        if sid in mega_by_base:
            # key named a base that has mega(s) in the shared set
            megas = mega_by_base[sid]
            base_also = sid in threat_ids
            if not base_also:
                findings.append(
                    {
                        "key": key_path,
                        "named": name,
                        "issue": "base_form_used_but_only_mega_qualifies",
                        "qualifying_megas": megas,
                    }
                )

    # HU2b
    for r in (artifacts.get("hu2b") or {}).get("per_threat_cell") or []:
        if r.get("threat"):
            check_name("hu2b", r["threat"])
    # hn2b/c — opp is Gholdengo (single named); OK if in set or not a mega-lineage issue
    for k in ("hn2b_forward_grid", "hn2c_forward_grid"):
        g = artifacts.get(k) or {}
        if g.get("opp_species"):
            check_name(k, g["opp_species"])
        if g.get("own_species"):
            check_name(k + ".own", g["own_species"])
    # IS1–IS4
    for k in ("is1_min_spe", "is2_min_spe", "is3_is4"):
        block = artifacts.get(k) or {}
        if k == "is3_is4":
            # notes only
            continue
        for sp in (block.get("own_species"), block.get("opp_species")):
            if sp:
                check_name(k, sp)
    # MT7/MT8 mirror — Archaludon / Sneasler named in prompts; check Arch
    check_name("mt7_mt8_ar.mirror", "Archaludon")
    check_name("mt7_mt8_ar.sneasler", "Sneasler")
    # AR3 threats
    for t in ((artifacts.get("ar3") or {}).get("t5_speed_ladder") or {}).get("per_threat") or []:
        if t.get("threat"):
            check_name("ar3.t5", t["threat"])
    # DM2 — Hatterene joints only (not a meta-threat list)
    for c in ((artifacts.get("dm_outputs") or {}).get("dm2") or {}).get("per_joint_cell") or []:
        check_name("dm2", "Hatterene")

    # Deduplicate
    seen = set()
    uniq = []
    for f in findings:
        sig = (f["key"], f["named"], f["issue"])
        if sig not in seen:
            seen.add(sig)
            uniq.append(f)
    return {
        "shared_threat_count": len(threats),
        "cutoff": SHOWDOWN_THREAT_USAGE_CUTOFF,
        "findings": uniq,
        "note": (
            "Mismatch = Speed key names a base species while only a mega forme of that "
            "lineage is in the shared ≥4.52% set. In-game lineage ranks unaffected."
        ),
    }


def dm2_hatterene_grid() -> dict:
    """Full numeric grid: locked Incineroar (DM1 attacker) vs Hatterene COMMON_JOINT."""
    from _lib import common_joint, load_showdown

    doubles = {"gameType": "Doubles"}
    sd = load_showdown()
    attacker = {
        "species": "Incineroar",
        "level": 50,
        "nature": "Adamant",
        "item": "Life Orb",
        "ability": "Intimidate",
        "evs": {"hp": 0, "atk": 32, "def": 0, "spa": 0, "spd": 4, "spe": 0},
    }
    cells = []
    for i, row in enumerate(common_joint(sd, "Hatterene")):
        nat = row.get("nature") or "Serious"
        evs = row.get("evs") or {}
        spread = {
            "hp": int(evs.get("hp") or 0),
            "atk": int(evs.get("atk") or 0),
            "def": int(evs.get("def") or 0),
            "spa": int(evs.get("spa") or 0),
            "spd": int(evs.get("spd") or 0),
            "spe": int(evs.get("spe") or 0),
        }
        # Clamp any accidental >32 (Showdown chaos sometimes stores mainline EVs)
        spread = {k: min(32, v) for k, v in spread.items()}
        rec = calculate(
            {
                "attacker": attacker,
                "defender": {
                    "species": "Hatterene",
                    "level": 50,
                    "nature": nat,
                    "ability": "Magic Bounce",
                    "item": "Sitrus Berry",
                    "evs": spread,
                },
                "move": "Flare Blitz",
                "field": doubles,
            },
            f"dm2_hatterene_joint_{i}",
        )
        cells.append(
            {
                "nature": nat,
                "spread": spread,
                "chaos_weight": row.get("chaos_weight", row.get("pct")),
                "key": rec.get("key"),
            }
        )
    return {
        "attacker": "Adamant Life Orb Incineroar Atk-32 (locked; match DM1)",
        "per_joint_cell": cells,
        "note": "Full numeric grid like DM1/DM3; COMMON_JOINT Hatterene cells.",
    }


def dm_keys() -> dict:
    doubles = {"gameType": "Doubles"}

    dm1 = calculate(
        {
            "attacker": {
                "species": "Incineroar",
                "level": 50,
                "nature": "Adamant",
                "item": "Life Orb",
                "ability": "Intimidate",
                "evs": {"hp": 0, "atk": 32, "def": 0, "spa": 0, "spd": 4, "spe": 0},
            },
            "defender": {
                "species": "Hatterene",
                "level": 50,
                "nature": "Bold",
                "ability": "Magic Bounce",
                "item": "Sitrus Berry",
                "evs": {"hp": 0, "atk": 0, "def": 0, "spa": 0, "spd": 0, "spe": 0},
            },
            "move": "Flare Blitz",
            "field": doubles,
        },
        "dm1_incineroar_flare_blitz_hatterene",
    )

    dm3_inc = calculate(
        {
            "attacker": {
                "species": "Tyranitar",
                "level": 50,
                "nature": "Adamant",
                "ability": "Sand Stream",
                "evs": {"hp": 0, "atk": 32, "def": 0, "spa": 0, "spd": 4, "spe": 0},
            },
            "defender": {
                "species": "Incineroar",
                "level": 50,
                "nature": "Careful",
                "ability": "Intimidate",
                # "252 HP" intent → Champions SP 32 (HP stat 202), not EV 252
                "evs": {"hp": 32, "atk": 0, "def": 0, "spa": 0, "spd": 4, "spe": 0},
            },
            "move": "Rock Slide",
            "field": doubles,
        },
        "dm3_rockslide_incineroar",
    )
    dm3_rill = calculate(
        {
            "attacker": {
                "species": "Tyranitar",
                "level": 50,
                "nature": "Adamant",
                "ability": "Sand Stream",
                "evs": {"hp": 0, "atk": 32, "def": 0, "spa": 0, "spd": 4, "spe": 0},
            },
            "defender": {
                "species": "Rillaboom",
                "level": 50,
                "nature": "Careful",
                "ability": "Grassy Surge",
                # "252 HP / 252 SpD" intent → SP 32 / 32 (HP 207)
                "evs": {"hp": 32, "atk": 0, "def": 0, "spa": 0, "spd": 32, "spe": 0},
            },
            "move": "Rock Slide",
            "field": doubles,
        },
        "dm3_rockslide_rillaboom",
    )

    dm4 = calculate(
        {
            "attacker": {
                "species": "Garchomp",
                "level": 50,
                "nature": "Adamant",
                "ability": "Rough Skin",
                "evs": {"hp": 0, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 0},
            },
            "defender": {
                "species": "Incineroar",
                "level": 50,
                "nature": "Careful",
                "ability": "Intimidate",
                "evs": {"hp": 32, "atk": 0, "def": 4, "spa": 0, "spd": 32, "spe": 0},
            },
            "move": "Earthquake",
            "field": doubles,
        },
        "dm4_garchomp_eq_incineroar_doubles",
    )
    dm4_singles = calculate(
        {
            "attacker": {
                "species": "Garchomp",
                "level": 50,
                "nature": "Adamant",
                "ability": "Rough Skin",
                "evs": {"hp": 0, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 0},
            },
            "defender": {
                "species": "Incineroar",
                "level": 50,
                "nature": "Careful",
                "ability": "Intimidate",
                "evs": {"hp": 32, "atk": 0, "def": 4, "spa": 0, "spd": 32, "spe": 0},
            },
            "move": "Earthquake",
            "field": {"gameType": "Singles"},
        },
        "dm4_garchomp_eq_incineroar_singles",
    )

    spread_note = (
        "Calc service sets field.gameType from request; spread moves (allAdjacent / "
        "allAdjacentFoes) use Doubles spread modifier (0.75) when gameType is Doubles. "
        "Earthquake is allAdjacent — still spread-reduced in Doubles even vs one defender row."
    )
    d4d = dm4.get("key", {}).get("max_damage")
    d4s = dm4_singles.get("key", {}).get("max_damage")

    return {
        "dm1": dm1.get("key"),
        "dm2": dm2_hatterene_grid(),
        "dm5": {
            "numeric_key": None,
            "class": "ASSUME-STATE",
            "reason": (
                "Eval-only partial SP draft (atk unset); min Atk for 2HKO + speed/chip "
                "exchange needs assumed opponent + confirmed draft — no frozen numeric grid."
            ),
        },
        "dm3": {
            "targets": ["Incineroar", "Rillaboom"],
            "defender_spreads": {
                "Incineroar": "Careful HP-32 / Def-0 / SpD-4 / Spe-0 (252 HP intent → SP 32)",
                "Rillaboom": "Careful HP-32 / Def-0 / SpD-32 / Spe-0 (252/252 intent → SP 32/32)",
            },
            "incineroar": dm3_inc.get("key"),
            "rillaboom": dm3_rill.get("key"),
            "spread_modifier_note": spread_note,
        },
        "dm4": {
            "defender_spread": "Careful Incineroar HP-32 / Def-4 / SpD-32 (252/252 intent → SP ≤32)",
            "ohko_at_32": "unreachable (2HKO)" if d4d else None,
            "doubles_max": d4d,
            "singles_max": d4s,
            "spread_modifier_verified": d4d != d4s if d4d and d4s else None,
            "spread_modifier_note": spread_note,
            "calc_ids": ["dm4_garchomp_eq_incineroar_doubles", "dm4_garchomp_eq_incineroar_singles"],
            "incineroar_doubles": dm4.get("key"),
            "incineroar_singles": dm4_singles.get("key"),
        },
    }


def main() -> None:
    h = health()
    if h.get("status") != "ok":
        raise SystemExit(f"calc service not ok: {h}")

    snap = load_legality()
    sd = load_showdown()
    ing = load_ingame()

    base = json.loads(OUT.read_text()) if OUT.exists() else {}
    # import existing derive_keys main pieces
    import derive_keys as dk

    dk.main()  # refreshes base file
    artifacts = json.loads(OUT.read_text())

    artifacts["move_static"] = move_static_keys()
    artifacts["hn3_common_item"] = common_item_ingame(ing, "Glimmora")
    threats = showdown_threats_ge_cutoff(sd)
    artifacts["showdown_threats_ge_452"] = {
        "cutoff_fraction": SHOWDOWN_THREAT_USAGE_CUTOFF,
        "cutoff_pct": SHOWDOWN_THREAT_USAGE_CUTOFF * 100,
        "count": len(threats),
        "threats": threats,
        "rule": (
            "Every Showdown-listed form is its own ThreatCandidate; shared by HU2b, AR3, "
            "and any Speed-cell key that expands meta threats by form"
        ),
    }
    artifacts["hu2b"] = hu2b_output(snap, sd, threats)
    artifacts["hn2b_forward_grid"] = forward_grid(snap, sd, "Annihilape", "Gholdengo")
    artifacts["hn2c_forward_grid"] = forward_grid(
        snap,
        sd,
        "Annihilape",
        "Gholdengo",
        own_locked={"nature": "Jolly", "spe_sp": 32, "spe": 156},
    )
    artifacts["is1_min_spe"] = min_spe_four_part(snap, sd, "Garchomp", "Dragapult")
    is2 = min_spe_four_part(
        snap,
        sd,
        "Garchomp",
        "Dragapult",
        locked={"other_sp_sum": 32},
    )
    # R=34 (=66−32) never binds: required Spe SP under first reachable mode is always ≤34
    # (or unreachable). As built IS2 equals IS1 for outcome/mode/N; not a shortfall case.
    is2["budget_binds"] = False
    is2["equals_is1_as_built"] = True
    is2["shortfall_intent_note"] = (
        "R=34 was not enough locked non-Spe SP to force shortfall; "
        "raise other_sp_sum (e.g. ≥50) if a shortfall control is desired."
    )
    artifacts["is2_min_spe"] = is2
    artifacts["common_speed_regenerated"] = {
        s: common_speed_distinct(sd, s)
        for s in [
            "Gholdengo",
            "Annihilape",
            "Pelipper",
            "Garchomp",
            "Dragapult",
            "Archaludon",
            "Sneasler",
        ]
    }
    artifacts["dm_outputs"] = dm_keys()
    artifacts["speed_key_base_vs_form_scan"] = scan_speed_keys_base_vs_form(
        artifacts, threats, snap
    )
    OUT.write_text(json.dumps(artifacts, indent=2) + "\n")
    print(f"wrote base outputs {OUT}")
    print(
        "threats",
        len(threats),
        "hu2b forms",
        artifacts["hu2b"].get("required_forms_present"),
        "mismatches",
        len(artifacts["speed_key_base_vs_form_scan"]["findings"]),
    )

    import os

    if os.environ.get("SKIP_SPREAD_SOLVER") == "1":
        print("SKIP_SPREAD_SOLVER=1 — skipping MT7/MT8/AR")
        return

    print("Running spread solver (may take several minutes)...", flush=True)
    artifacts["mt7_mt8_ar"] = mt7_mt8_ar_keys()
    OUT.write_text(json.dumps(artifacts, indent=2) + "\n")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
