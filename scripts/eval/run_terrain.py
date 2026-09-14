#!/usr/bin/env python3
"""Terrain mechanism eval — discovery strategic roles + seeded Grassy field."""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.eval.scenarios_terrain import run_all_terrain  # noqa: E402


def calc_healthy(timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:4173/health", timeout=timeout
        ) as resp:
            return json.loads(resp.read().decode()).get("status") == "ok"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return False


def _repo_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def main() -> int:
    if not calc_healthy():
        print("ERROR: calc /health failed — terrain eval requires calc", flush=True)
        return 2

    results = run_all_terrain()
    passed = sum(1 for r in results if r.get("passed"))
    summary = {
        "schema_version": 1,
        "measured": date.today().isoformat(),
        "repo_head": _repo_head(),
        "calc_healthy": True,
        "pass": passed,
        "total": len(results),
        "results": results,
    }
    out = ROOT / ".cache" / "eval" / "last_terrain_run.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"\nWrote {out}", flush=True)
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
