#!/usr/bin/env python3
"""Run all Part G v4 eval package checks."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CHECKS = [
    "check_request_set.py",
    "check_eval_independence.py",
    "check_pins.py",
    "check_calc_artifacts.py",
    "check_item_stratum.py",
    "check_stone_map_source.py",
    "check_stone_map_vs_calc.py",
    "check_move_conditionals_source.py",
    "../builders/extract_calc_rules.py --check",  # node + vendored calc only; no calc service, no .cache
    "check_battery_hash.py",
    "check_ar3_probes.py",
    "check_keys_no_error_fields.py",
]


def main() -> int:
    rc = 0
    for name in CHECKS:
        print(f"== {name} ==")
        script, *args = name.split()
        proc = subprocess.run([sys.executable, str((HERE / script).resolve()), *args], cwd=str(HERE.parent))
        if proc.returncode != 0:
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
