#!/usr/bin/env python3
"""Check a dev claim battery against the frozen seed-0 battery.

Usage: check_dev_battery.py DEV_CLAIM_BATTERY.json [SEED0_CLAIM_BATTERY.json]
Fails on any (type, kind, subject) shared with seed 0, any duplicate inside the dev
battery, an empty usage ground truth, or item counts per type that differ from TYPE_PLAN.
Also prints how many usage items and speed species fall in the top and bottom usage_rank quartile.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from generate_claim_battery import TYPE_PLAN, item_keys, load_ingame, to_id  # noqa: E402

FROZEN = HERE / "claim_battery_v4.json"


def main(argv: list[str]) -> int:
    dev = json.loads(Path(argv[1]).read_text())
    frozen = json.loads((Path(argv[2]) if len(argv) > 2 else FROZEN).read_text())
    if dev["seed"] == frozen["seed"]:
        print("FAIL: dev battery has the frozen seed")
        return 1

    errors = []
    frozen_keys = set().union(*(item_keys(i) for i in frozen["items"]))
    seen: dict[tuple, str] = {}
    for it in dev["items"]:
        shared = item_keys(it) & frozen_keys
        if shared:
            errors.append(f"{it['id']} overlaps seed 0: {sorted(shared)}")
        for k in item_keys(it):
            if k in seen:
                errors.append(f"{it['id']} duplicates {seen[k]}: {k}")
            seen[k] = it["id"]

    counts = Counter(i["claim_type"] for i in dev["items"])
    for t, n, _ in TYPE_PLAN:
        if counts[t] != n:
            errors.append(f"{t}: {counts[t]} items, TYPE_PLAN says {n}")

    # Quartiles as the generator defines them: n//4 in-game species by usage_rank (1 = most used).
    sp_map = load_ingame()["ingame_doubles"]["species"]
    rows = sorted(((s, v["usage_rank"]) for s, v in sp_map.items() if v.get("usage_rank") is not None),
                  key=lambda x: (x[1], x[0]))
    q = len(rows) // 4
    top, bot = {s for s, _ in rows[:q]}, {s for s, _ in rows[-q:]}
    where = Counter()
    for it in dev["items"]:
        g = it["claims"][0]["ground_truth"] if it["claims"] else {}
        names = [g["species"]] if it["claim_type"] == "usage" else [g["s1"], g["s2"]] if it["claim_type"] == "speed" else []
        for n in names:
            where[(it["claim_type"], "top" if to_id(n) in top else "bottom" if to_id(n) in bot else "other")] += 1
        if it["claim_type"] == "usage" and not (g["common_items"] or g["teammates"]):
            errors.append(f"{it['id']}: empty usage ground truth")
    print(f"ranked in-game species={len(rows)} quartile size={q}")
    print("usage items / speed species slots by quartile:", dict(sorted(where.items())))
    print("rejected by type:", dev.get("overlap_rejected_by_type"))
    print("items by type:", dict(counts), "slots:", dev["n_claims_total"])

    for e in errors:
        print("FAIL:", e)
    print("PASS check_dev_battery" if not errors else f"FAIL check_dev_battery: {len(errors)} problems")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
