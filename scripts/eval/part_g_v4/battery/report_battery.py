#!/usr/bin/env python3
"""Human-readable report for a claim battery: per-type keys and baselines, samples, key lengths, sizing.

Usage: report_battery.py CLAIM_BATTERY.json [--samples N]
Read-only. Item categories use the pinned Showdown items.ts cache if it is present
(key_artifacts/showdown_items_ts.pin.json); the generator itself does not read it.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
ROOT = PKG.parents[2]
sys.path.insert(0, str(PKG / "builders"))

from _lib import load_ingame, load_legality, load_showdown  # noqa: E402

BINARY = {
    "typing": "has_type",
    "ability": "has_ability",
    "ability_form": "has_ability",
    "item": "legal",
    "legality": "legal",
    "speed": "s1_outspeeds",
}


def truth(item: dict) -> bool | None:
    f = BINARY.get(item["claim_type"])
    return item["claims"][0]["ground_truth"][f] if f else None


def item_categories() -> dict[str, str] | None:
    """item name -> category from the pinned items.ts flags, or None if the cache is absent."""
    pin = json.loads((PKG / "key_artifacts" / "showdown_items_ts.pin.json").read_text())
    path = ROOT / pin["path"]
    if not path.is_file():
        return None
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != pin["items_ts_sha256"]:
        return None
    text = raw.decode()
    out = {}
    for m in re.finditer(r"\n\t([a-z0-9]+): \{\n(.*?)\n\t\},", text, re.S):
        body = m.group(2)
        nm = re.search(r'name: "([^"]+)"', body)
        if not nm:
            continue
        for cat, pat in (
            ("mega stone", r"\bmegaStone\b"),
            ("plate", r"\bonPlate\b"),
            ("drive", r"\bonDrive\b"),
            ("memory", r"\bonMemory\b"),
            ("choice", r"\bisChoice\b"),
            ("gem", r"\bisGem\b"),
            ("berry", r"\bisBerry\b"),
        ):
            if re.search(pat, body):
                out[nm.group(1)] = cat
                break
        else:
            out[nm.group(1)] = "other (no flag)"
    return out


def evidence(item: dict, leg: dict, ig: dict, sd: dict) -> str:
    ct = item["claim_type"]
    gt = item["claims"][0]["ground_truth"]
    sp = leg["species"]
    if ct == "typing":
        return f"legality species '{gt['species']}'.types = {gt['types']}"
    if ct == "ability":
        return f"legality species '{gt['species']}'.abilities = {gt['abilities']}"
    if ct == "ability_form":
        return f"{gt['form']} own list {gt['form_abilities']}; pre-Mega {gt['pre_mega']} list {gt['pre_mega_abilities']}"
    if ct == "item":
        it = next(v for v in leg["items"].values() if v["name"] == gt["item"])
        return f"legality items.{it['id']}.is_nonstandard = {it['is_nonstandard']}"
    if ct == "legality":
        s = next(v for v in sp.values() if v["name"] == gt["species"])
        return f"legality species '{s['id']}'.is_nonstandard = {s['is_nonstandard']}"
    if ct == "speed":
        return (
            f"Spe = floor(n*(base+32+20)): {gt['s1']} Jolly {gt['spe1_jolly32']}, "
            f"{gt['s2']} Timid {gt['spe2_timid32']}"
        )
    if ct == "damage":
        return (
            f"legality moves.{gt['move_id']}: {gt['move_category']} bp {gt['move_basePower']} "
            f"{gt['move_type']}; key = calc builder, not stored"
        )
    if ct == "move_static":
        return f"legality moves.{gt['id']} = {gt['category']}/{gt['basePower']}/{gt['type']}; static priority {gt['priority']}"
    if ct == "usage":
        row = ig[to_id(gt["species"])]
        return (
            f"in-game rank {gt['usage_rank']} ({gt['usage_half']}); held {[(x['name'], x['pct']) for x in row['common_items'][:7]]}; "
            f"teammates listed {row['teammates']}"
        )
    row = sd[gt["id"]]
    return (
        f"showdown usage_pct {gt['usage_pct']:.4f} ({gt['usage_half']} half); held {row['common_items']}; "
        f"teammate conditional_pct {[(t['name'], t['conditional_pct']) for t in row['teammates']]}"
    )


def to_id(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("battery", type=Path)
    ap.add_argument("--samples", type=int, default=6)
    args = ap.parse_args()
    b = json.loads(args.battery.read_text())
    leg, ig, sd = load_legality(), load_ingame()["ingame_doubles"]["species"], load_showdown()["showdown_doubles"]["species"]
    by_type: dict[str, list] = collections.defaultdict(list)
    for it in b["items"]:
        by_type[it["claim_type"]].append(it)

    print(f"claim battery seed {b['seed']}: {b['n_items']} items, {b['n_claims_total']} slots")
    print("\n== 1. per type: items, slots, True/False keys, baselines ==")
    print(f"{'type':15}{'items':>6}{'slots':>6}{'True':>6}{'False':>6}  always-yes   always-first-listed")
    tot_t = tot_f = 0
    for t, rows in by_type.items():
        slots = sum(r["n_claims"] for r in rows)
        if t in BINARY:
            tr = sum(1 for r in rows if truth(r))
            fa = len(rows) - tr
            tot_t += tr
            tot_f += fa
            yes = f"{tr / len(rows):.1%}"
            if t == "speed":
                first = [r for r in rows if r["claims"][0]["kind"] == "faster"]
                fl = f"{sum(1 for r in first if truth(r)) / len(first):.1%} ({len(first)} 'faster' items)"
                yes_items = [r for r in rows if r["claims"][0]["kind"] == "outspeed"]
                yes = f"{sum(1 for r in yes_items if truth(r)) / len(yes_items):.1%} ({len(yes_items)} 'outspeed' items)"
            else:
                fl = "n/a (yes/no prompt)"
            print(f"{t:15}{len(rows):6}{slots:6}{tr:6}{fa:6}  {yes:12} {fl}")
        else:
            extra = ""
            if t == "move_static":
                for kind in ("category", "base_power", "move_type"):
                    ks = [r for r in rows if r["claims"][0]["kind"] == kind]
                    f = {"category": "category", "base_power": "basePower", "move_type": "type"}[kind]
                    c = collections.Counter(r["claims"][0]["ground_truth"][f] for r in ks)
                    extra += f" {kind}: n={len(ks)}, modal answer {c.most_common(1)[0][0]!r} = {c.most_common(1)[0][1] / len(ks):.0%};"
            print(f"{t:15}{len(rows):6}{slots:6}{'-':>6}{'-':>6}  n/a (open answer){extra}")
    print(f"binary items total: True {tot_t}, False {tot_f}")

    print("\n== key lengths (tie-inclusive top 5) ==")
    for t in ("usage", "usage_showdown"):
        rows = by_type.get(t, [])
        for f in ("common_items", "teammates"):
            L = collections.Counter(len(r["claims"][0]["ground_truth"][f]) for r in rows)
            print(f"{t:15}{f:14} key length distribution {dict(sorted(L.items()))}")
    print("\n== rejected redraws by type ==", b.get("overlap_rejected_by_type"))

    cats = item_categories()
    print("\n== held-item prompts (type 'item'): legal/illegal and categories ==")
    rows = by_type["item"]
    print(f"illegal share {sum(1 for r in rows if not truth(r))}/{len(rows)}")
    if cats is None:
        print("items.ts cache absent or sha mismatch: categories not computed")
    else:
        c = collections.Counter(
            (cats.get(r["claims"][0]["ground_truth"]["item"], "unknown"), "legal" if truth(r) else "illegal")
            for r in rows
        )
        for k, v in sorted(c.items()):
            print(f"  {k[0]:16}{k[1]:8}{v}")
        names = {r["claims"][0]["ground_truth"]["item"] for r in rows}
        look = ["Choice Band", "Choice Specs", "Choice Scarf", "Assault Vest", "Booster Energy", "Covert Cloak", "Life Orb"]
        print("  named in prompts:", {n: (n in names) for n in look})
        print("  blob-wide categories (all 583 items):", dict(collections.Counter(cats.values())))

    print("\n== 3. sizing ==")
    n = b["n_claims_total"]
    for rate in (0.65, 0.70):
        print(f"answer rate {rate:.0%}: expected scored = {n * rate:.1f}")
    print(f"slots {n}; line as share of slots: 149 -> {149 / n:.1%}, 236 -> {236 / n:.1%}, 313 -> {313 / n:.1%}, 240 floor -> {240 / n:.1%}")
    for rate in (0.65, 0.70):
        e = n * rate
        print(f"  at {rate:.0%}: >=149 {'yes' if e >= 149 else 'NO'}, >=236 {'yes' if e >= 236 else 'NO'}, >=240 floor {'yes' if e >= 240 else 'NO'}, >=313 {'yes' if e >= 313 else 'NO'}")

    print("\n== 2. samples ==")
    for t, rows in by_type.items():
        print(f"\n--- {t} ---")
        picks = []
        if t in BINARY:
            T = [r for r in rows if truth(r)]
            F = [r for r in rows if not truth(r)]
            k = args.samples // 2
            picks = T[:: max(1, len(T) // k)][:k] + F[:: max(1, len(F) // k)][:k]
        else:
            step = max(1, len(rows) // args.samples)
            picks = rows[::step][: args.samples]
        for r in picks:
            gt = r["claims"][0]["ground_truth"]
            keys = [(c["kind"], {k: v for k, v in c["ground_truth"].items()}) for c in r["claims"]]
            ans = truth(r) if t in BINARY else None
            print(f"[{r['id']}] {r['prompt']}")
            if t in BINARY:
                print(f"   key: {ans}")
            elif t == "usage" or t == "usage_showdown":
                print(f"   key: held items {gt['common_items']}; teammates {gt['teammates']}")
            elif t == "damage":
                print(f"   key: none stored (calc builder); move {gt['move']} {gt['move_category']} bp {gt['move_basePower']}")
            else:
                print(f"   key: {r['claims'][0]['kind']} -> " + str({k: gt[k] for k in ('category', 'basePower', 'type') if k in gt}))
            print(f"   evidence: {evidence(r, leg, ig, sd)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
