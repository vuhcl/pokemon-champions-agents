#!/usr/bin/env python3
"""Emit dev.jsonl / held_out.jsonl from hand-authored _rows."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from _rows import build_rows

OUT = Path(__file__).resolve().parent


def main() -> None:
    rows = build_rows()
    by_split: dict[str, list] = defaultdict(list)
    for row in rows:
        by_split[row["split"]].append(row)

    for split, items in by_split.items():
        path = OUT / f"{split}.jsonl"
        with path.open("w", encoding="utf-8") as fh:
            for row in items:
                fh.write(json.dumps(row, ensure_ascii=False) + "\n")
        print(f"wrote {path.name}: {len(items)}")

    # Floor checks (same rules as runner)
    probe_counts: Counter[str] = Counter()
    pair_counts: Counter[str] = Counter()
    pair_dirs: dict[str, set[str]] = defaultdict(set)
    held_probe: Counter[str] = Counter()
    held_pair: Counter[str] = Counter()
    for row in rows:
        if row.get("probe_id"):
            probe_counts[row["probe_id"]] += 1
            if row["split"] == "held_out":
                held_probe[row["probe_id"]] += 1
        if row.get("pair_id"):
            pair_counts[row["pair_id"]] += 1
            pair_dirs[row["pair_id"]].add(row["gold_intent"])
            if row["split"] == "held_out":
                held_pair[row["pair_id"]] += 1

    ok = True
    for pid, n in sorted(probe_counts.items()):
        if n < 3 or held_probe[pid] < 2:
            print(f"FLOOR FAIL probe {pid}: n={n} held={held_probe[pid]}")
            ok = False
    for pid, n in sorted(pair_counts.items()):
        dirs = pair_dirs[pid]
        if n < 3 or held_pair[pid] < 2 or len(dirs) < 2:
            print(
                f"FLOOR FAIL pair {pid}: n={n} held={held_pair[pid]} dirs={sorted(dirs)}"
            )
            ok = False

    residual = [r for r in rows if not r["deterministic_preempt"] and r["split"] == "held_out"]
    print(f"held_out residual: {len(residual)}")
    print(f"payload_free: {sum(1 for r in rows if 'payload_free' in r['tags'])}")
    if not ok:
        raise SystemExit(1)
    print("floors OK")


if __name__ == "__main__":
    main()
