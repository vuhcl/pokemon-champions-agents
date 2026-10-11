#!/usr/bin/env python3
"""Deterministic Part G v4 claim + false-legal battery generator (seed=0).

Eval-only. Reads pinned JSON under data/; no recommender imports.
"""
from __future__ import annotations

import hashlib
import json
import random
import sys
from pathlib import Path
from typing import Any

PKG = Path(__file__).resolve().parents[1]
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PKG / "builders"))

from _lib import (  # noqa: E402
    champions_spe,
    is_legal_species,
    load_ingame,
    load_legality,
    load_showdown,
    to_id,
)

SEED = 0
CLAIM_ITEMS = 300
FALSE_LEGAL_ITEMS = 240
LEGAL_CONTROL_ITEMS = 80

# Design table (items, claims_per_item) — integer claims per item
TYPE_PLAN: list[tuple[str, int, float]] = [
    ("typing", 38, 1.0),
    ("ability", 38, 1.0),
    ("item", 38, 1.1),
    ("legality", 30, 1.0),
    ("speed", 44, 1.2),
    ("damage", 44, 1.5),
    ("usage", 38, 2.0),
    ("move_static", 30, 1.3),
]


def canonical_dumps(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def claims_for_item(rate: float, rng: random.Random) -> int:
    """Integer claim count with fractional part as Bernoulli (deterministic)."""
    base = int(rate)
    frac = rate - base
    return base + (1 if rng.random() < frac else 0)


def legal_species(snap: dict) -> list[tuple[str, dict]]:
    out = []
    for sid, sp in (snap.get("species") or {}).items():
        if is_legal_species(sp):
            out.append((sid, sp))
    out.sort(key=lambda x: x[0])
    return out


def illegal_species(snap: dict) -> list[tuple[str, dict]]:
    out = []
    for sid, sp in (snap.get("species") or {}).items():
        if not is_legal_species(sp):
            out.append((sid, sp))
    out.sort(key=lambda x: x[0])
    return out


def legal_items(snap: dict) -> list[tuple[str, dict]]:
    out = []
    for iid, it in (snap.get("items") or {}).items():
        if it.get("is_nonstandard") is None:
            out.append((iid, it))
    out.sort(key=lambda x: x[0])
    return out


def illegal_items(snap: dict) -> list[tuple[str, dict]]:
    out = []
    for iid, it in (snap.get("items") or {}).items():
        if it.get("is_nonstandard") is not None:
            out.append((iid, it))
    out.sort(key=lambda x: x[0])
    return out


def load_moves_static() -> dict:
    return json.loads((ROOT / "data/moves/static.v1.json").read_text())


def quartile_split(species_rows: list[tuple[str, float]], rng: random.Random) -> tuple[list, list]:
    rows = sorted(species_rows, key=lambda x: (-x[1], x[0]))
    n = len(rows)
    if n < 4:
        return rows, rows
    top = rows[: max(1, n // 4)]
    bot = rows[-(max(1, n // 4)) :]
    rng.shuffle(top)
    rng.shuffle(bot)
    return top, bot


def build_claim_battery(rng: random.Random) -> dict[str, Any]:
    snap = load_legality()
    ingame = load_ingame()
    sd = load_showdown()
    static = load_moves_static()
    moves = sorted((static.get("moves") or {}).items(), key=lambda x: x[0])

    leg_sp = legal_species(snap)
    illeg_sp = illegal_species(snap)
    leg_it = legal_items(snap)
    illeg_it = illegal_items(snap)

    usage_rows: list[tuple[str, float]] = []
    for sid, sp in (ingame.get("ingame_doubles") or {}).get("species", {}).items():
        pct = sp.get("usage_pct")
        if pct is None:
            continue
        usage_rows.append((sid, float(pct)))
    top_q, bot_q = quartile_split(usage_rows, rng)

    items: list[dict[str, Any]] = []
    claim_counts: dict[str, int] = {t: 0 for t, _, _ in TYPE_PLAN}

    templates = {
        "typing": [
            ("What type is {S}?", "types"),
            ("Is {S} a {T} type?", "has_type"),
            ("What are {S}'s types?", "types"),
        ],
        "ability": [
            ("Does {S} have {A}?", "has_ability"),
            ("What abilities can {S} have?", "abilities"),
            ("Is {A} legal on {S}?", "ability_legal"),
        ],
        "item": [
            ("Is {I} legal on {S}?", "item_on_species"),
            ("Is {I} legal in Champions VGC?", "item_legal"),
        ],
        "legality": [
            ("Is {S} legal?", "species_legal"),
            ("Can I use {S} in Champions VGC?", "species_legal"),
        ],
        "speed": [
            ("Does {S1} outspeed {S2} at max Spe?", "outspeed"),
            ("Who is faster: {S1} or {S2}?", "faster"),
        ],
        "damage": [
            ("What damage does {S1}'s {M} do into {S2}?", "damage_range"),
            ("Does {S1}'s {M} OHKO {S2}?", "ohko"),
        ],
        "usage": [
            ("What are common items on {S} (in-game)?", "common_items"),
            ("Who are top teammates for {S} (in-game)?", "teammates"),
        ],
        "move_static": [
            ("What category is {M}?", "category"),
            ("What is the base power of {M}?", "base_power"),
            ("What type is {M}?", "move_type"),
        ],
    }

    damaging_moves = [
        (mid, m)
        for mid, m in moves
        if (m.get("category") or "") in ("Physical", "Special") and int(m.get("basePower") or 0) > 0
    ]

    for ctype, n_items, rate in TYPE_PLAN:
        for i in range(n_items):
            n_claims = claims_for_item(rate, rng)
            tmpl_prompt, claim_kind = rng.choice(templates[ctype])
            entry: dict[str, Any] = {
                "id": f"{ctype}_{i:03d}",
                "claim_type": ctype,
                "template": tmpl_prompt,
                "claims": [],
            }

            if ctype == "typing":
                sid, sp = rng.choice(leg_sp)
                types = list(sp.get("types") or [])
                name = sp.get("name") or sid
                t = rng.choice(types) if types else "Normal"
                prompt = tmpl_prompt.format(S=name, T=t)
                gt = {"species": name, "types": types, "has_type": t in types}
                for c in range(n_claims):
                    entry["claims"].append(
                        {"index": c, "kind": claim_kind, "ground_truth": gt}
                    )
            elif ctype == "ability":
                sid, sp = rng.choice(leg_sp)
                name = sp.get("name") or sid
                abs_map = sp.get("abilities") or {}
                abil = [str(v) for v in abs_map.values() if v]
                a = rng.choice(abil) if abil else "Unknown"
                prompt = tmpl_prompt.format(S=name, A=a)
                gt = {"species": name, "abilities": abil, "has_ability": a in abil}
                for c in range(n_claims):
                    entry["claims"].append(
                        {"index": c, "kind": claim_kind, "ground_truth": gt}
                    )
            elif ctype == "item":
                use_illegal = i % 5 == 0 and illeg_it
                iid, it = rng.choice(illeg_it if use_illegal else leg_it)
                iname = it.get("name") or iid
                sid, sp = rng.choice(leg_sp)
                sname = sp.get("name") or sid
                prompt = tmpl_prompt.format(I=iname, S=sname)
                legal = it.get("is_nonstandard") is None
                gt = {"item": iname, "legal": legal, "species": sname}
                for c in range(n_claims):
                    entry["claims"].append(
                        {"index": c, "kind": claim_kind, "ground_truth": gt}
                    )
            elif ctype == "legality":
                use_illegal = i % 4 == 0 and illeg_sp
                sid, sp = rng.choice(illeg_sp if use_illegal else leg_sp)
                name = sp.get("name") or sid
                prompt = tmpl_prompt.format(S=name)
                gt = {"species": name, "legal": is_legal_species(sp)}
                for c in range(n_claims):
                    entry["claims"].append(
                        {"index": c, "kind": claim_kind, "ground_truth": gt}
                    )
            elif ctype == "speed":
                pool = top_q if i % 2 == 0 else bot_q
                if len(pool) < 2:
                    pool = [(s, 0.0) for s, _ in leg_sp[:20]]
                (s1, _), (s2, _) = rng.sample(pool, 2) if len(pool) >= 2 else (pool[0], pool[0])
                sp1 = snap["species"].get(to_id(s1)) or {}
                sp2 = snap["species"].get(to_id(s2)) or {}
                n1, n2 = sp1.get("name") or s1, sp2.get("name") or s2
                b1 = int((sp1.get("base_stats") or {}).get("spe") or 0)
                b2 = int((sp2.get("base_stats") or {}).get("spe") or 0)
                spe1 = champions_spe(b1, 32, "Jolly")
                spe2 = champions_spe(b2, 32, "Timid")
                prompt = tmpl_prompt.format(S1=n1, S2=n2)
                gt = {
                    "s1": n1,
                    "s2": n2,
                    "spe1_jolly32": spe1,
                    "spe2_timid32": spe2,
                    "s1_outspeeds": spe1 > spe2,
                    "condition": "max Spe; no Scarf/TW",
                }
                for c in range(n_claims):
                    entry["claims"].append(
                        {"index": c, "kind": claim_kind, "ground_truth": gt}
                    )
            elif ctype == "damage":
                # Prompt+GT placeholder: keys come from stored calc ids when available;
                # battery items are fidelity probes, not live calc at generation.
                sid1, sp1 = rng.choice(leg_sp)
                sid2, sp2 = rng.choice(leg_sp)
                mid, mv = rng.choice(damaging_moves) if damaging_moves else ("tackle", {})
                mname = mv.get("name") or mid
                n1, n2 = sp1.get("name") or sid1, sp2.get("name") or sid2
                prompt = tmpl_prompt.format(S1=n1, S2=n2, M=mname)
                gt = {
                    "attacker": n1,
                    "defender": n2,
                    "move": mname,
                    "note": "score via calc HTTP under explicit abilities; not asserted here",
                    "requires_calc": True,
                }
                for c in range(n_claims):
                    entry["claims"].append(
                        {"index": c, "kind": claim_kind, "ground_truth": gt}
                    )
            elif ctype == "usage":
                pool = top_q if i % 3 != 2 else bot_q
                sid = rng.choice(pool)[0] if pool else rng.choice(leg_sp)[0]
                sp = (ingame.get("ingame_doubles") or {}).get("species", {}).get(to_id(sid)) or {}
                name = sp.get("name") or sid
                prompt = tmpl_prompt.format(S=name)
                def _name(x):
                    if isinstance(x, str):
                        return x
                    if isinstance(x, dict):
                        return x.get("name") or x.get("species")
                    return None

                items_u = [n for n in (_name(x) for x in (sp.get("common_items") or [])[:5]) if n]
                mates = [n for n in (_name(x) for x in (sp.get("teammates") or [])[:5]) if n]
                gt = {
                    "species": name,
                    "source": "in-game",
                    "common_items": items_u,
                    "teammates": mates,
                }
                for c in range(n_claims):
                    kind = "common_items" if c % 2 == 0 else "teammates"
                    entry["claims"].append(
                        {"index": c, "kind": kind, "ground_truth": gt}
                    )
            else:  # move_static
                mid, mv = rng.choice(moves)
                mname = mv.get("name") or mid
                prompt = tmpl_prompt.format(M=mname)
                gt = {
                    "move": mname,
                    "id": mid,
                    "category": mv.get("category"),
                    "basePower": mv.get("basePower"),
                    "type": mv.get("type"),
                    "priority": mv.get("priority"),
                    "target": mv.get("target"),
                }
                for c in range(n_claims):
                    entry["claims"].append(
                        {"index": c, "kind": claim_kind, "ground_truth": gt}
                    )

            entry["prompt"] = prompt
            entry["n_claims"] = len(entry["claims"])
            claim_counts[ctype] += entry["n_claims"]
            items.append(entry)

    assert len(items) == CLAIM_ITEMS
    return {
        "schema": "part_g_v4_claim_battery",
        "seed": SEED,
        "n_items": len(items),
        "items": items,
        "claim_counts_by_type": claim_counts,
        "n_claims_total": sum(claim_counts.values()),
        "ground_truth_framing": "fidelity to pinned snapshot",
        "showdown_usage_pin": "63bcefe4512a202d75b62e79f2ccc5436527b46e",
    }


def build_false_legal(rng: random.Random) -> dict[str, Any]:
    snap = load_legality()
    illeg_sp = illegal_species(snap)
    illeg_it = illegal_items(snap)
    leg_sp = legal_species(snap)
    leg_it = legal_items(snap)
    items: list[dict[str, Any]] = []

    templates_ill = [
        "Can I use {S} in Champions VGC?",
        "Is {S} legal?",
        "Is {I} legal?",
        "Give me a set for {S} holding {I}.",
    ]
    for i in range(FALSE_LEGAL_ITEMS):
        mode = i % 3  # species-only / item-only / both
        if mode == 0:
            sid, sp = rng.choice(illeg_sp)
            sname = sp.get("name") or sid
            prompt = templates_ill[i % 2].format(S=sname, I="")
            gt = {"illegal_species": sname, "kind": "species_only"}
        elif mode == 1:
            iid, it = rng.choice(illeg_it)
            iname = it.get("name") or iid
            prompt = "Is {I} legal?".format(I=iname)
            gt = {"illegal_item": iname, "kind": "item_only"}
        else:
            sid, sp = rng.choice(illeg_sp)
            iid, it = rng.choice(illeg_it)
            sname, iname = sp.get("name") or sid, it.get("name") or iid
            prompt = templates_ill[3].format(S=sname, I=iname)
            gt = {"illegal_species": sname, "illegal_item": iname, "kind": "both"}
        items.append(
            {
                "id": f"false_legal_{i:03d}",
                "prompt": prompt,
                "ground_truth": gt,
                "score": "treats_illegal_as_usable → fail",
            }
        )

    controls = []
    for i in range(LEGAL_CONTROL_ITEMS):
        sid, sp = rng.choice(leg_sp)
        iid, it = rng.choice(leg_it)
        sname, iname = sp.get("name") or sid, it.get("name") or iid
        controls.append(
            {
                "id": f"legal_control_{i:03d}",
                "prompt": f"Is {sname} legal holding {iname}?",
                "ground_truth": {"species": sname, "item": iname, "legal": True},
                "score": "legal_treated_illegal → false-illegal (reported; not ≤2% gate)",
            }
        )

    return {
        "schema": "part_g_v4_false_legal_battery",
        "seed": SEED,
        "n_items": len(items),
        "n_legal_controls": len(controls),
        "items": items,
        "legal_controls": controls,
    }


def main() -> int:
    rng = random.Random(SEED)
    claim = build_claim_battery(rng)
    # Separate RNG stream continuation is fine; false-legal uses same seed restart for stability
    rng_fl = random.Random(SEED + 1)
    false_legal = build_false_legal(rng_fl)

    out_dir = PKG / "battery"
    claim_path = out_dir / "claim_battery_v4.json"
    fl_path = out_dir / "false_legal_battery_v4.json"

    claim_text = canonical_dumps(claim)
    fl_text = canonical_dumps(false_legal)
    claim_hash = sha256_text(claim_text)
    fl_hash = sha256_text(fl_text)

    claim_path.write_text(claim_text)
    fl_path.write_text(fl_text)

    # Gate arithmetic on designed claim slots (n_claims_total)
    n = claim["n_claims_total"]

    def binom_cdf_le(k: int, n_: int, p: float) -> float:
        from math import comb

        s = 0.0
        for i in range(k + 1):
            s += comb(n_, i) * (p**i) * ((1 - p) ** (n_ - i))
        return s

    def cp_upper(k: int, n_: int, alpha: float = 0.05) -> float:
        if n_ == 0:
            return 1.0
        if k >= n_:
            return 1.0
        if k < 0:
            return 0.0
        lo, hi = 0.0, 1.0
        for _ in range(100):
            mid = (lo + hi) / 2
            if binom_cdf_le(k, n_, mid) > alpha:
                lo = mid
            else:
                hi = mid
        return hi

    def max_k(n_: int, bound: float = 0.02) -> int:
        best = -1
        for k in range(0, n_ + 1):
            if cp_upper(k, n_) <= bound + 1e-15:
                best = k
            else:
                break
        return best

    def min_n(k: int, bound: float = 0.02) -> int:
        n_ = max(k + 1, 1)
        while cp_upper(k, n_) > bound + 1e-15:
            n_ += 1
        return n_

    max_k_at_n = max_k(n)
    min_n_one_fail = min_n(1)
    design_floor = 240

    manifest = {
        "seed": SEED,
        "claim_battery_path": "battery/claim_battery_v4.json",
        "false_legal_battery_path": "battery/false_legal_battery_v4.json",
        "claim_battery_sha256": claim_hash,
        "false_legal_battery_sha256": fl_hash,
        "canonical_serialization": "json.dumps(sort_keys=True, separators=(',', ':')) + newline",
        "n_claim_items": claim["n_items"],
        "realized_claim_counts_by_type": claim["claim_counts_by_type"],
        "realized_claims_total": n,
        "gate": {
            "rule": "one-sided 95% Clopper-Pearson upper bound on false-claim rate ≤ 2%",
            "realized_n": n,
            "max_false_claims_passing_at_realized_n": max_k_at_n,
            "smallest_n_where_exactly_one_false_claim_passes": min_n_one_fail,
            "design_floor": design_floor,
            "design_floor_matches": design_floor >= min_n_one_fail,
            "pass_table_reference": {"0": 149, "1": 237, "2": 314},
            "computed_min_n": {"0": min_n(0), "1": min_n_one_fail, "2": min_n(2)},
            "note": "Reference table uses 237/314; exact CP binary search yields 236/313 at bound≤0.02. Design floor 240 covers one false claim under either figure.",
        },
        "held_out": True,
        "frozen": True,
        "tuning_forbidden": True,
    }
    (out_dir / "battery_manifest.json").write_text(canonical_dumps(manifest))
    print(json.dumps({"claim_sha256": claim_hash, "realized_claims": n, "by_type": claim["claim_counts_by_type"], "gate": manifest["gate"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
