#!/usr/bin/env python3
"""Check a dev claim battery against the frozen seed-0 battery.

Usage: check_dev_battery.py DEV_CLAIM_BATTERY.json
Fails on any (type, kind, subject) shared with seed 0, any duplicate inside the dev
battery, or item counts per type that differ from TYPE_PLAN. Also prints whether the
usage_pct field behind the generator's quartile split exists, and the pools the dev items drew on.
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
    frozen = json.loads(FROZEN.read_text())
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

    # The generator's usage-quartile stratification reads sp["usage_pct"]; report whether that
    # field exists in the pinned blob, and the pools the dev items actually came from.
    sp_map = load_ingame()["ingame_doubles"]["species"]
    n_pct = sum(1 for v in sp_map.values() if v.get("usage_pct") is not None)
    speed_sp = {n for i in dev["items"] if i["claim_type"] == "speed"
                for n in (i["claims"][0]["ground_truth"]["s1"], i["claims"][0]["ground_truth"]["s2"])}
    usage = [i for i in dev["items"] if i["claim_type"] == "usage"]
    no_row = sum(1 for i in usage if to_id(i["claims"][0]["ground_truth"]["species"]) not in sp_map)
    print(f"in-game species with usage_pct: {n_pct}/{len(sp_map)} (0 means the quartile split is inactive)")
    print(f"speed items draw on {len(speed_sp)} distinct species; usage items: {len(usage)}, with no in-game row: {no_row}")
    print("rejected by type:", dev.get("overlap_rejected_by_type"))
    print("items by type:", dict(counts), "slots:", dev["n_claims_total"])

    for e in errors:
        print("FAIL:", e)
    print("PASS check_dev_battery" if not errors else f"FAIL check_dev_battery: {len(errors)} problems")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
