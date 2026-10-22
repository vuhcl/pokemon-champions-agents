#!/usr/bin/env python3
"""Deterministic Part G v4 claim + false-legal battery generator (seed=0).

Eval-only. Reads pinned JSON under data/; no recommender imports.
"""
from __future__ import annotations

import hashlib
import argparse
import json
import random
import re
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
    global SEED
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out-dir", type=Path, default=None)
    args = ap.parse_args()
    SEED = args.seed
    if SEED != 0 and args.out_dir is None:
        ap.error("--seed != 0 requires --out-dir (the default dir holds the frozen seed-0 battery)")
    rng = random.Random(SEED)
    claim = build_claim_battery(rng)
    # Separate RNG stream continuation is fine; false-legal uses same seed restart for stability
    rng_fl = random.Random(SEED + 1)
    false_legal = build_false_legal(rng_fl)

    out_dir = args.out_dir or PKG / "battery"
    out_dir.mkdir(parents=True, exist_ok=True)
    claim_path = out_dir / "claim_battery_v4.json"
    fl_path = out_dir / "false_legal_battery_v4.json"

    claim_text = canonical_dumps(claim)
    fl_text = canonical_dumps(false_legal)
    claim_hash = sha256_text(claim_text)
    fl_hash = sha256_text(fl_text)

    claim_path.write_text(claim_text)
    fl_path.write_text(fl_text)

    # Gate arithmetic is on *scored* claims (post-run), not designed slots.
    slots = claim["n_claims_total"]
    answer_rate = 0.70  # explicit pre-run assumption
    expected_scored = slots * answer_rate  # ≈267

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
        for _ in range(120):
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

    staircase = {str(k): min_n(k) for k in range(0, 4)}
    design_floor = 240  # 1-failure threshold (236) + margin
    expected_scored_int = int(round(expected_scored))  # 267
    # Item scored iff ≥1 of its designed slots is answered.
    # Independence within an item: each designed slot answered iid with p=answer_rate.
    # → P(item scored | n_i) = 1 − (1−p)^{n_i}; E = Σ_i that probability.
    # (300×0.70=210 is a lower bound: ignores multi-slot items.)
    expected_scored_items_exact = sum(
        1.0 - (1.0 - answer_rate) ** int(it["n_claims"]) for it in claim["items"]
    )
    expected_scored_items = int(round(expected_scored_items_exact))  # ~227
    item_tol = max_k(expected_scored_items)
    # Row-level secondary (request set; separate pool from battery items).
    # n_i = claim-type tokens on the row (split on +); same within-row iid slot model.
    request_md = (
        Path(__file__).resolve().parent.parent / "part3_request_set_v4.md"
    ).read_text(encoding="utf-8")
    row_ns: list[int] = []
    for line in request_md.splitlines():
        if not re.match(r"^\|\s*[A-Z]{1,3}\d+[a-z]?\s*\|", line):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6:
            continue
        ct = cells[5].strip().strip("`")
        if not ct or ct in ("—", "-", "–"):
            row_ns.append(1)
        else:
            row_ns.append(max(1, len([x for x in re.split(r"[+/]", ct) if x.strip()])))
    n_rows = len(row_ns)
    expected_scored_rows_exact = sum(
        1.0 - (1.0 - answer_rate) ** n for n in row_ns
    )
    expected_scored_rows = int(round(expected_scored_rows_exact))
    row_tol = max_k(expected_scored_rows)

    manifest = {
        "seed": SEED,
        "claim_battery_path": "battery/claim_battery_v4.json",
        "false_legal_battery_path": "battery/false_legal_battery_v4.json",
        "claim_battery_sha256": claim_hash,
        "false_legal_battery_sha256": fl_hash,
        "canonical_serialization": "json.dumps(sort_keys=True, separators=(',', ':')) + newline",
        "n_claim_items": claim["n_items"],
        "claim_slot_counts_by_type": claim["claim_counts_by_type"],
        "claim_slots_total": slots,
        "realized_definition": {
            "claim_slots": slots,
            "answer_rate_assumption": answer_rate,
            "expected_scored_claims": expected_scored,
            "expected_scored_claims_rounded": expected_scored_int,
            "formula": "expected_scored_claims = claim_slots × answer_rate",
            "note": (
                "Gate denominator = scored (model-authored) claims after a run, not claim slots. "
                f"{slots} slots × {answer_rate} ≈ {expected_scored_int} expected scored."
            ),
        },
        "gate": {
            "rule": (
                "one-sided 95% Clopper-Pearson UCB on false-claim rate ≤ 2%, "
                "on scored (model-authored) claims — not designed slots"
            ),
            "exact_min_scored_n_for_k_false": staircase,
            "prior_design_table": {"0": 149, "1": 237, "2": 314},
            "delta_vs_prior_design_table": {
                "0": 0,
                "1": staircase["1"] - 237,
                "2": staircase["2"] - 314,
                "note": "Exact binary-search CP is 1 below the prior table for k=1 and k=2",
            },
            "design_floor": design_floor,
            "design_floor_meaning": "1-failure threshold (236) + margin; stop/extend if scored < 240",
            "expected_scored_claims_at_70pct": expected_scored_int,
            "max_false_claims_passing_at_expected_scored": max_k(expected_scored_int),
            "answer_rate_tolerance_drops": {
                "below_rate_for_2_false": staircase["2"] / slots,
                "below_rate_for_1_false": staircase["1"] / slots,
                "below_rate_for_0_false_gate_fails": staircase["0"] / slots,
                "note": (
                    "If answer rate falls below these fractions of slots, "
                    "max false claims that still pass drops (2→1, 1→0, then even 0 fails)."
                ),
            },
            "answer_rate_note": (
                "70% is a pre-run assumption for sizing. The gate verdict uses actual "
                "scored counts from the first run. Answer rate below ~62% (236/381) "
                "loses the 1-failure tolerance (0-only or extend)."
            ),
            "cluster_secondaries": {
                "does_not_replace_headline_gate": True,
                "headline_unchanged": (
                    "claim-level one-sided 95% Clopper-Pearson UCB ≤ 2% on scored claims"
                ),
                "item_level": {
                    "unit": "scored_battery_item",
                    "independence_assumption": (
                        "within an item, each designed claim slot is answered iid with "
                        f"p={answer_rate}; an item is scored if at least one slot is answered. "
                        "Items are treated as independent of each other for this secondary."
                    ),
                    "method": (
                        "E[scored items] = Σ_i [1 − (1−p)^{n_i}] over the 300 generated items "
                        f"(seed 0); p={answer_rate}. 300×0.70=210 is a lower bound "
                        "(mean n_claims≈1.27)."
                    ),
                    "expected_scored_items_exact": round(expected_scored_items_exact, 4),
                    "expected_scored_items_at_70pct": expected_scored_items,
                    "gap_to_1_failure_threshold_236": staircase["1"]
                    - expected_scored_items,
                    "exact_min_scored_items_for_k_false": {
                        str(k): staircase[str(k)] for k in ("0", "1", "2")
                    },
                    "max_false_items_passing_at_expected_scored_items": item_tol,
                    "plain": (
                        f"At expected scored items ({expected_scored_items}), item-level "
                        f"tolerance is {item_tol} false items "
                        f"({staircase['1'] - expected_scored_items} below the 236 line for k=1)."
                    ),
                },
                "row_level": {
                    "unit": "scored_request_set_row",
                    "relationship_to_battery_items": (
                        "The 300 claim-battery items are a separate eval pool from the "
                        "134 request-set rows — not one item per row, not repeated "
                        "phrasings of rows. Multi-turn request-set cases are one row each. "
                        "Request-set companions (AR3, IS2, build traps, H12/DM*) are "
                        "documented beside the battery, not in the battery item pool. "
                        "Battery items share no fixture_id with request-set rows; some "
                        "claim types reuse species/keys conceptually. Within a request-set "
                        "row, turns/claims share fixtures, keys, and assumptions."
                    ),
                    "independence_assumption": (
                        "within a row, each claim-type token (split on +) is answered iid "
                        f"with p={answer_rate}; a row is scored if at least one slot is "
                        "answered. Rows are treated as independent of each other for this "
                        "secondary."
                    ),
                    "method": (
                        "E[scored rows] = Σ_j [1 − (1−p)^{n_j}] over the 134 request-set "
                        "rows' claim-type token counts; "
                        f"p={answer_rate}. One-opportunity lower bound = 134×0.70≈94."
                    ),
                    "n_request_set_rows": n_rows,
                    "expected_scored_rows_exact": round(expected_scored_rows_exact, 4),
                    "expected_scored_rows_at_70pct": expected_scored_rows,
                    "one_opportunity_lower_bound": round(n_rows * answer_rate, 1),
                    "exact_min_scored_rows_for_k_false": {
                        str(k): staircase[str(k)] for k in ("0", "1", "2")
                    },
                    "max_false_rows_passing_at_expected_scored_rows": row_tol,
                    "can_demonstrate_2pct_bound_at_row_level": row_tol >= 0
                    and expected_scored_rows >= staircase["0"],
                    "plain": (
                        f"At expected scored rows (~{expected_scored_rows}), even 0 false "
                        f"rows cannot pass the CP≤2% bound (need ≥{staircase['0']} scored "
                        "for k=0). The request set cannot demonstrate the 2% bound at "
                        "row level under the 70% answer-rate assumption."
                    ),
                },
            },
            # Backward-compatible alias of item-level secondary
            "cluster_aware": {
                "unit": "scored_battery_item",
                "method": (
                    "E[scored items]=Σ[1−(1−p)^{n_i}] with within-item iid slot answers "
                    f"at p={answer_rate}; expected≈{expected_scored_items} "
                    "(210 was the 300×0.70 lower bound)"
                ),
                "expected_scored_items_at_70pct": expected_scored_items,
                "expected_scored_items_exact": round(expected_scored_items_exact, 4),
                "gap_to_236": staircase["1"] - expected_scored_items,
                "exact_min_scored_items_for_k_false": {
                    str(k): staircase[str(k)] for k in ("0", "1", "2")
                },
                "max_false_items_passing_at_expected_scored_items": item_tol,
                "stricter_than_headline": True,
                "plain": (
                    f"At expected scored items ({expected_scored_items}), item-level "
                    f"tolerance is {item_tol} false items; "
                    f"headline at expected scored claims ({expected_scored_int}) allows 1 false claim."
                ),
                "does_not_replace_headline_gate": True,
                "limitation": (
                    "headline assumes independent scored claims; "
                    "clustering by item/shared keys makes it optimistic"
                ),
            },
        },
        "held_out": SEED == 0,
        "frozen": SEED == 0,
        "tuning_forbidden": SEED == 0,
    }
    (out_dir / "battery_manifest.json").write_text(canonical_dumps(manifest))
    print(
        json.dumps(
            {
                "claim_sha256": claim_hash,
                "claim_slots": slots,
                "expected_scored": expected_scored_int,
                "by_type": claim["claim_counts_by_type"],
                "gate": manifest["gate"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
