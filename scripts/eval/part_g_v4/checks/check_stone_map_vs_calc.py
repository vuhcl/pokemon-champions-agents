#!/usr/bin/env python3
"""Cross-check stone_map.v1.json against the vendored @smogon/calc MEGA_STONES table (needs node).

The calc table is a second source, not an oracle: pairs whose Mega forme is not legal in Champions are only
reported. The check fails when the two disagree on a legal pair (a pair present in one source and missing
from the other, or listed under different stones).
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
ROOT = PKG.parents[2]
MAP = PKG / "key_artifacts" / "stone_map.v1.json"
JS = "console.log(JSON.stringify(require('./dist/index.js').MEGA_STONES))"


def to_id(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def calc_pairs() -> set[tuple[str, str, str]]:
    raw = subprocess.run(["node", "-e", JS], cwd=ROOT / "vendor" / "smogon-calc", capture_output=True, text=True, check=True).stdout
    return {(stone, to_id(h), to_id(m)) for stone, pairs in json.loads(raw).items() for h, m in pairs.items()}


def main() -> int:
    legality = json.loads((ROOT / "data/legality/champions.v1.json").read_text())["species"]

    def legal(mega: str) -> bool:
        return mega in legality and legality[mega]["is_nonstandard"] is None

    ours = {(p["stone"], p["holder"], p["mega"]) for p in json.loads(MAP.read_text())["pairs"]}
    theirs = calc_pairs()
    legal_ours, legal_theirs = {t for t in ours if legal(t[2])}, {t for t in theirs if legal(t[2])}
    only_ours, only_theirs = sorted(legal_ours - legal_theirs), sorted(legal_theirs - legal_ours)
    other = len((ours ^ theirs) - (legal_ours ^ legal_theirs))
    if only_ours or only_theirs:
        print("FAIL check_stone_map_vs_calc: the stone map and the vendored calc disagree on legal pairs")
        for t in only_ours:
            print(" - only in stone map:", t)
        for t in only_theirs:
            print(" - only in calc table:", t)
        return 1
    print(f"PASS check_stone_map_vs_calc: {len(legal_ours)} legal pairs agree; {other} differences on non-legal pairs (reported only)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
