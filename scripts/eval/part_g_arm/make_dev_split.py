#!/usr/bin/env python3
"""Type-stratified random split of the seed-1 dev battery into half P (parser building) and half T (timing sample).

Within each claim type the item ids are shuffled with a fixed seed; P takes ceil(n/2), T the rest. The output file
dev_split.json is committed and never edited: parsers are built and tuned on P only, and T is touched only for the
50-answer timing and then excluded from tuning. Run once; rerunning must reproduce the committed file.
"""
import hashlib, json, random, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SEED = 20261024
BATTERY = HERE / "dev_seed1" / "claim_battery_v4.json"


def build() -> dict:
    raw = BATTERY.read_bytes()
    by_type: dict[str, list[str]] = {}
    for it in json.loads(raw)["items"]:
        by_type.setdefault(it["claim_type"], []).append(it["id"])
    rng = random.Random(SEED)
    P, T = {}, {}
    for ty in sorted(by_type):
        ids = sorted(by_type[ty])
        rng.shuffle(ids)
        k = (len(ids) + 1) // 2
        P[ty], T[ty] = sorted(ids[:k]), sorted(ids[k:])
    return {"seed": SEED, "method": "per claim type: sort ids, shuffle with random.Random(seed), P = first ceil(n/2), T = rest",
            "battery": "dev_seed1/claim_battery_v4.json", "battery_sha256": hashlib.sha256(raw).hexdigest(),
            "counts": {"P": sum(map(len, P.values())), "T": sum(map(len, T.values()))}, "P": P, "T": T}


if __name__ == "__main__":
    out = HERE / "dev_split.json"
    doc = build()
    text = json.dumps(doc, indent=1, sort_keys=True) + "\n"
    if out.exists():
        sys.exit("dev_split.json exists and is frozen" if out.read_text() == text else "dev_split.json differs from a fresh build; do not overwrite")
    out.write_text(text)
    print(out, hashlib.sha256(text.encode()).hexdigest(), doc["counts"])
