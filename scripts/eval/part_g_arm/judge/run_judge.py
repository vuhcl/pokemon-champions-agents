#!/usr/bin/env python3
"""Run the judge over a JSONL of {id, prompt, final_text}; write one record per item. Refuses to start unless `ollama ps` shows nothing loaded,
checks the pinned digest, unloads the model at the end, and does no retries or repairs.

    python scripts/eval/part_g_arm/judge/run_judge.py --items tuning_items.jsonl --out runs/judge_tuning_vN.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import extract as ex  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--items", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    loaded = ex.loaded_models()
    if loaded:
        raise SystemExit(f"refused: `ollama ps` shows {loaded} loaded; the judge runs only when nothing is loaded")
    if ex.local_digest() != ex.PINNED_DIGEST:
        raise SystemExit(f"refused: {ex.MODEL} digest {ex.local_digest()} != pinned {ex.PINNED_DIGEST}")
    items = [json.loads(line) for line in args.items.read_text().splitlines() if line.strip()]
    meta = {"model": ex.MODEL, "digest": ex.PINNED_DIGEST, "prompt_sha256": ex.prompt_sha256(), "sampler": ex.SAMPLER, "think": False, "schema": ex.SCHEMA}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w") as fh:
        fh.write(json.dumps({"meta": meta}, sort_keys=True) + "\n")
        for k, it in enumerate(items):
            t0 = time.monotonic()
            last = k == len(items) - 1
            res = ex.extract(it["prompt"], it["final_text"], keep_alive=0 if last else "5m")  # the last call unloads the model
            fh.write(json.dumps({"id": it["id"], **res, "wall_s": round(time.monotonic() - t0, 2)}, sort_keys=True) + "\n")
            print(f"{it['id']}: parsed={res['parsed']} claims={len(res['claims'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
