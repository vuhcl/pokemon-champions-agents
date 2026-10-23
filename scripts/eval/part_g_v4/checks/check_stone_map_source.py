#!/usr/bin/env python3
"""Fail when showdown_items_ts.pin.json changed but stone_map.v1.json was not re-extracted.

Needs no .cache clone: it compares the source fields the map records with the pin file. Re-extract with
builders/extract_stone_map.py (which does need the cache) when this fails.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
PIN = PKG / "key_artifacts" / "showdown_items_ts.pin.json"
MAP = PKG / "key_artifacts" / "stone_map.v1.json"
FIELDS = ("path", "items_ts_sha256", "showdown_commit")


def main() -> int:
    pin = json.loads(PIN.read_text())
    source = json.loads(MAP.read_text())["source"]
    bad = [f"{f}: pin {pin[f]!r} != stone map {source.get(f)!r}" for f in FIELDS if pin[f] != source.get(f)]
    if bad:
        print("FAIL check_stone_map_source: stone_map.v1.json was extracted from a different items.ts than the pin")
        for b in bad:
            print(" -", b)
        return 1
    print(f"PASS check_stone_map_source: stone map source matches the pin ({pin['showdown_commit'][:7]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
