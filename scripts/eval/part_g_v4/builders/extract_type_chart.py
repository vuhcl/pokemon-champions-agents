#!/usr/bin/env python3
"""Extract the Champions type chart (Generations.get(0).types) from the vendored @smogon/calc.

Writes key_artifacts/type_chart.v1.json. The damage-pool selector uses it only to STEER draws (the calc
result is authoritative), and it must not import recommender code (ADR-060). `--check` re-extracts and
fails if the committed file differs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
ROOT = PKG.parents[2]
VENDOR = ROOT / "vendor" / "smogon-calc"
OUT = PKG / "key_artifacts" / "type_chart.v1.json"
JS = (
    "const c=require('./dist/index.js');const g=c.Generations.get(0);const o={};"
    "for(const t of g.types){if(t.name==='???'||t.name==='Stellar')continue;o[t.name]=t.effectiveness;}"
    "console.log(JSON.stringify(o))"
)


def build() -> dict:
    raw = subprocess.run(["node", "-e", JS], cwd=VENDOR, capture_output=True, text=True, check=True).stdout
    chart = json.loads(raw)
    names = sorted(chart)
    return {
        "schema": "part_g_v4_type_chart",
        "source": {
            "path": "vendor/smogon-calc/dist/data/types.js",
            "sha256": hashlib.sha256((VENDOR / "dist" / "data" / "types.js").read_bytes()).hexdigest(),
            "calc_version": json.loads((VENDOR / "package.json").read_text())["version"],
            "generation": "Generations.get(0) (Champions)",
        },
        "types": names,
        "effectiveness": {a: {d: chart[a][d] for d in names} for a in names},
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    text = json.dumps(build(), sort_keys=True, indent=1) + "\n"
    if args.check:
        if OUT.read_text() != text:
            print("FAIL: type_chart.v1.json differs from the vendored calc")
            return 1
        print("PASS: type_chart.v1.json matches the vendored calc")
        return 0
    OUT.write_text(text)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
