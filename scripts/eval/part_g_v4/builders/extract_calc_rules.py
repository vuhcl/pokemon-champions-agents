#!/usr/bin/env python3
"""Run scan_calc_rules.mjs against the vendored @smogon/calc and write key_artifacts/calc_move_rules.v1.json.

The file records where the calc's damage calculation departs from the plain type chart or from the legality
blob (move rules, Scrappy, type-changing abilities and forms, calc dex gaps, defender abilities with no
effect on the rolls). The damage-pool selector reads it so its effectiveness classes follow the calc.
`--check` re-scans and fails if the committed file differs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PKG = HERE.parent
ROOT = PKG.parents[2]
OUT = PKG / "key_artifacts" / "calc_move_rules.v1.json"
SCAN = HERE / "scan_calc_rules.mjs"


def build() -> dict:
    raw = subprocess.run(["node", str(SCAN)], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    doc = json.loads(raw)
    doc["scanner_sha256"] = hashlib.sha256(SCAN.read_bytes()).hexdigest()
    doc["inputs"] = {
        "vendor_types_js_sha256": hashlib.sha256((ROOT / "vendor/smogon-calc/dist/data/types.js").read_bytes()).hexdigest(),
        "vendor_champions_js_sha256": hashlib.sha256((ROOT / "vendor/smogon-calc/dist/mechanics/champions.js").read_bytes()).hexdigest(),
    }
    return doc


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    text = json.dumps(build(), sort_keys=True, indent=1, ensure_ascii=False) + "\n"
    if args.check:
        if OUT.read_text() != text:
            print("FAIL: calc_move_rules.v1.json differs from a fresh scan of the vendored calc")
            return 1
        print("PASS: calc_move_rules.v1.json matches a fresh scan of the vendored calc")
        return 0
    OUT.write_text(text)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
