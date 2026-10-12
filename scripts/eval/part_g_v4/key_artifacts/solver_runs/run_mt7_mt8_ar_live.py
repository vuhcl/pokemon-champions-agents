#!/usr/bin/env python3
"""Unattended live mt7_mt8_ar regenerate (includes MT7 t2). Does not touch committed keys."""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILDERS = HERE.parents[1] / "builders"
sys.path.insert(0, str(BUILDERS))

# Ensure live calc allowed
os.environ.pop("PART_G_V4_REQUIRE_CALC_ARTIFACT", None)
os.environ.pop("SKIP_SPREAD_SOLVER", None)

from calc_store import health  # noqa: E402
from spread_solver import mt7_mt8_ar_keys  # noqa: E402

OUT = HERE / "mt7_mt8_ar_live.json"
LOG_META = HERE / "FINISH.json"


def main() -> None:
    t0 = time.time()
    h = health()
    print(f"health={h}", flush=True)
    print("starting mt7_mt8_ar_keys()...", flush=True)
    result = mt7_mt8_ar_keys()
    elapsed = time.time() - t0
    OUT.write_text(json.dumps(result, indent=2) + "\n")
    jolly = (
        (result.get("mt8_t4_way_out") or {}).get("jolly_sneasler") or {}
    ).get("solutions_at_minimal_spe_by_class")
    meta = {
        "finished_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "wall_clock_seconds": round(elapsed, 1),
        "wall_clock_hours": round(elapsed / 3600, 3),
        "out": str(OUT),
        "jolly_solutions_at_minimal_spe_by_class": jolly,
        "match_committed_def_spe": (
            isinstance(jolly, dict)
            and jolly.get("+Def") == 20
            and jolly.get("+Spe") == 2
        ),
        "mt7_t2": {
            "feasible": (result.get("mt7_t2_adamant_cc") or {}).get("feasible"),
            "min_total_sp": (result.get("mt7_t2_adamant_cc") or {}).get("min_total_sp"),
            "solutions_at_minimal_spe_by_class": (result.get("mt7_t2_adamant_cc") or {}).get(
                "solutions_at_minimal_spe_by_class"
            ),
        },
    }
    LOG_META.write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps(meta, indent=2), flush=True)
    print(f"wrote {OUT}", flush=True)


if __name__ == "__main__":
    main()
