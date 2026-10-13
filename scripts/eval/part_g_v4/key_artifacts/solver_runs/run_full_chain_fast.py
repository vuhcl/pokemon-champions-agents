#!/usr/bin/env python3
"""Unspliced full builder chain with fast in-process calc → temp derived_keys.

Does not modify the committed derived_keys.json permanently: restores from git
after copying the result to PART_G_V4_CHAIN_OUT (default under solver_runs/).
"""
from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

# run_full_chain_fast.py → solver_runs → key_artifacts → part_g_v4 → eval → scripts → repo
REPO = Path(__file__).resolve().parents[5]
BUILDERS_DIR = REPO / "scripts/eval/part_g_v4/builders"
KEYS = REPO / "scripts/eval/part_g_v4/key_artifacts/derived_keys.json"
HERE = Path(__file__).resolve().parent
OUT = Path(
    os.environ.get("PART_G_V4_CHAIN_OUT")
    or str(HERE / "full_chain_fast_derived_keys.json")
)
LOG = HERE / "full_chain_fast.log"

BUILDERS = [
    "derive_outputs.py",
    "dm_intimidate_derive.py",
    "h12_derive.py",
    "ar3_derive.py",
    "ar3_followup.py",
    "ar3_hp_fix.py",
    "v4_rows_ah_derive.py",
    "v4_consolidated_keys.py",
]


def main() -> int:
    t0 = time.time()
    env = os.environ.copy()
    env["PART_G_V4_CALC_BACKEND"] = env.get("PART_G_V4_CALC_BACKEND") or "inprocess"
    env["PART_G_V4_CALC_IGNORE_DISK"] = env.get("PART_G_V4_CALC_IGNORE_DISK") or "1"
    env.pop("PART_G_V4_REQUIRE_CALC_ARTIFACT", None)
    env.pop("SKIP_SPREAD_SOLVER", None)
    env.setdefault(
        "PART_G_V4_SOLVER_CHECKPOINT_DIR", str(HERE / "ckpt_full_chain")
    )
    env.setdefault("PART_G_V4_SOLVER_WORKERS", "4")
    env["PYTHONUNBUFFERED"] = "1"

    # Ensure we start from committed keys shape only where builders patch in place;
    # derive_outputs overwrites the whole file.
    subprocess.check_call(
        ["git", "checkout", "HEAD", "--", str(KEYS.relative_to(REPO))],
        cwd=str(REPO),
    )

    def _restore_keys() -> None:
        subprocess.check_call(
            ["git", "checkout", "HEAD", "--", str(KEYS.relative_to(REPO))],
            cwd=str(REPO),
        )

    LOG.write_text("")
    failed = False
    try:
        with LOG.open("a") as log:
            log.write(
                f"backend={env['PART_G_V4_CALC_BACKEND']} ignore_disk="
                f"{env['PART_G_V4_CALC_IGNORE_DISK']} workers="
                f"{env.get('PART_G_V4_SOLVER_WORKERS')}\n"
            )
            for name in BUILDERS:
                print(f"=== {name} ===", flush=True)
                log.write(f"=== {name} ===\n")
                log.flush()
                rc = subprocess.call(
                    [sys.executable, str(BUILDERS_DIR / name)],
                    cwd=str(REPO),
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
                if rc != 0:
                    print(f"FAIL {name} rc={rc}", flush=True)
                    failed = True
                    break
                print(f"OK {name}", flush=True)
                log.write(f"OK {name}\n")

        if failed:
            print(f"restored committed {KEYS.name} after builder failure", flush=True)
            return 1

        OUT.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(KEYS, OUT)
        sha = hashlib.sha256(OUT.read_bytes()).hexdigest()
        elapsed = time.time() - t0
        meta = {
            "out": str(OUT),
            "sha256": sha,
            "wall_clock_seconds": round(elapsed, 1),
            "wall_clock_hours": round(elapsed / 3600, 3),
            "backend": env["PART_G_V4_CALC_BACKEND"],
            "ignore_disk": env["PART_G_V4_CALC_IGNORE_DISK"],
            "workers": env.get("PART_G_V4_SOLVER_WORKERS"),
        }
        (HERE / "full_chain_fast_FINISH.json").write_text(
            __import__("json").dumps(meta, indent=2) + "\n"
        )
        print(meta, flush=True)
        print(f"restored committed {KEYS.name}; result at {OUT}", flush=True)
        return 0
    finally:
        # Always restore committed derived_keys (leave calc probe dirt for git clean).
        _restore_keys()


if __name__ == "__main__":
    raise SystemExit(main())
