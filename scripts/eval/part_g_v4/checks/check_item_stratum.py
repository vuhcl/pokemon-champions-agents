#!/usr/bin/env python3
"""Assert every entry of battery/item_stratum.json against the pinned legality blob.

Doubles as a data-freshness check on the blob: if a refresh changes an item's status the check
fails and lists the entries. It never edits the file.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
ROOT = PKG.parents[2]
STRATUM = PKG / "battery" / "item_stratum.json"
LEGALITY = ROOT / "data" / "legality" / "champions.v1.json"


def disagreements(doc: dict, legality: dict) -> list[str]:
    by_name = {v["name"]: v for v in legality["items"].values()}
    seen, bad = set(), []
    for e in doc["entries"]:
        name, want = e["item"], e["expected"]
        if name in seen:
            bad.append(f"{name}: listed twice")
        seen.add(name)
        row = by_name.get(name)
        if row is None:
            bad.append(f"{name}: not in the legality blob")
            continue
        status = "legal" if row["is_nonstandard"] is None else "illegal"
        if status != want:
            bad.append(f"{name}: expected {want}, blob says {status} (is_nonstandard={row['is_nonstandard']})")
    return bad


def main() -> int:
    doc = json.loads(STRATUM.read_text())
    bad = disagreements(doc, json.loads(LEGALITY.read_text()))
    if bad:
        print("FAIL check_item_stratum:")
        for b in bad:
            print(" -", b)
        return 1
    n = collections_count(doc)
    print(f"PASS check_item_stratum: {len(doc['entries'])} entries ({n}) agree with the legality blob")
    return 0


def collections_count(doc: dict) -> str:
    legal = sum(1 for e in doc["entries"] if e["expected"] == "legal")
    return f"{legal} legal, {len(doc['entries']) - legal} illegal"


if __name__ == "__main__":
    sys.exit(main())
