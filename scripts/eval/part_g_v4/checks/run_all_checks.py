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
    "check_battery_hash.py",
]


def main() -> int:
    rc = 0
    for name in CHECKS:
        print(f"== {name} ==")
        proc = subprocess.run([sys.executable, str(HERE / name)], cwd=str(HERE.parent))
        if proc.returncode != 0:
            rc = 1
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
