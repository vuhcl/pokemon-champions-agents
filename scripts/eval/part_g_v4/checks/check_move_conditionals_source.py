#!/usr/bin/env python3
"""Fail when showdown_moves_ts.pin.json changed but move_conditionals.v1.json was not re-derived.

Needs no .cache clone: it compares the source fields the file records with the pin file. Re-derive with
builders/extract_move_conditionals.py (which does need the cache) when this fails. It cannot catch a hand edit
of the move lists; check_pins covers byte changes, extract_move_conditionals.py --check covers the derivation.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
PIN = PKG / "key_artifacts" / "showdown_moves_ts.pin.json"
DOC = PKG / "key_artifacts" / "move_conditionals.v1.json"
FIELDS = ("path", "moves_ts_sha256", "mod_path", "mod_moves_ts_sha256", "showdown_commit")


def main() -> int:
    pin = json.loads(PIN.read_text())
    source = json.loads(DOC.read_text())["source"]
    bad = [f"{f}: pin {pin[f]!r} != move_conditionals {source.get(f)!r}" for f in FIELDS if pin[f] != source.get(f)]
    if bad:
        print("FAIL check_move_conditionals_source: move_conditionals.v1.json was derived from different Showdown files than the pin")
        for b in bad:
            print(" -", b)
        return 1
    print(f"PASS check_move_conditionals_source: move conditionals source matches the pin ({pin['showdown_commit'][:7]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
