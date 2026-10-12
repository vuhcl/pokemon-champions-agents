#!/usr/bin/env python3
"""Fast-path mt7_mt8_ar regenerate (eval infra only; does not kill the slow live run).

Resume:
  PART_G_V4_SOLVER_CHECKPOINT_DIR=scripts/eval/part_g_v4/key_artifacts/solver_runs/ckpt_fast \\
  PART_G_V4_CALC_BACKEND=inprocess \\
  PART_G_V4_CALC_IGNORE_DISK=1 \\
  PART_G_V4_SOLVER_WORKERS=8 \\
  python3 -u scripts/eval/part_g_v4/key_artifacts/solver_runs/run_mt7_mt8_ar_fast.py

Re-running the same command resumes from per-stage `{prefix}_cells.jsonl`
(nature cell_id rows). Delete that dir to start clean.

Compare to slow live output when ready:
  python3 scripts/eval/part_g_v4/checks/validate_solver_speedup.py --compare-live
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILDERS = HERE.parents[1] / "builders"
sys.path.insert(0, str(BUILDERS))

os.environ.setdefault("PART_G_V4_CALC_BACKEND", "inprocess")
os.environ.setdefault("PART_G_V4_CALC_IGNORE_DISK", "1")
os.environ.setdefault(
    "PART_G_V4_SOLVER_CHECKPOINT_DIR", str(HERE / "ckpt_fast")
)
os.environ.pop("PART_G_V4_REQUIRE_CALC_ARTIFACT", None)
os.environ.pop("SKIP_SPREAD_SOLVER", None)

from calc_store import health  # noqa: E402
from spread_solver import mt7_mt8_ar_keys  # noqa: E402

def _out_path() -> Path:
    raw = (os.environ.get("PART_G_V4_SOLVER_OUT") or "").strip()
    return Path(raw) if raw else HERE / "mt7_mt8_ar_fast.json"


def main() -> None:
    out = _out_path()
    meta_path = out.with_name(out.stem + "_FINISH.json")
    t0 = time.time()
    h = health()
    print(f"health={h}", flush=True)
    print(
        "backend=",
        os.environ.get("PART_G_V4_CALC_BACKEND"),
        "workers=",
        os.environ.get("PART_G_V4_SOLVER_WORKERS") or "auto",
        "ckpt=",
        os.environ.get("PART_G_V4_SOLVER_CHECKPOINT_DIR"),
        "out=",
        out,
        flush=True,
    )
    print("starting mt7_mt8_ar_keys() [fast]...", flush=True)
    result = mt7_mt8_ar_keys()
    elapsed = time.time() - t0
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    meta = {
        "finished_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "wall_clock_seconds": round(elapsed, 1),
        "wall_clock_hours": round(elapsed / 3600, 3),
        "out": str(out),
        "sha256": __import__("hashlib").sha256(out.read_bytes()).hexdigest(),
        "backend": os.environ.get("PART_G_V4_CALC_BACKEND"),
        "workers": os.environ.get("PART_G_V4_SOLVER_WORKERS") or "auto",
        "checkpoint_dir": os.environ.get("PART_G_V4_SOLVER_CHECKPOINT_DIR"),
        "mt7_t1": {
            "feasible": (result.get("mt7_t1_jolly_cc") or {}).get("feasible"),
            "min_total_sp": (result.get("mt7_t1_jolly_cc") or {}).get("min_total_sp"),
            "solutions_at_minimal_spe_by_class": (result.get("mt7_t1_jolly_cc") or {}).get(
                "solutions_at_minimal_spe_by_class"
            ),
        },
        "mt7_t2": {
            "feasible": (result.get("mt7_t2_adamant_cc") or {}).get("feasible"),
            "min_total_sp": (result.get("mt7_t2_adamant_cc") or {}).get("min_total_sp"),
            "solutions_at_minimal_spe_by_class": (result.get("mt7_t2_adamant_cc") or {}).get(
                "solutions_at_minimal_spe_by_class"
            ),
        },
    }
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps(meta, indent=2), flush=True)
    print(f"wrote {out}", flush=True)


if __name__ == "__main__":
    main()
