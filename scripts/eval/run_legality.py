#!/usr/bin/env python3
"""Run scripted scenarios against an independent Showdown legality oracle.

Default suite is current regulation (M-C). Historical M-B: --suite mb.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.eval.harness import VGC_MB, VGC_MC, run_scenario  # noqa: E402
from scripts.eval.oracle import load_oracle_snapshot, pair_legal  # noqa: E402
from scripts.eval.scenarios import SCENARIOS_MB, SCENARIOS_MC  # noqa: E402

SUITE_CFG = {
    "mc": {
        "scenarios": SCENARIOS_MC,
        "format_id": VGC_MC,
        "oracle_mod": "champions",
    },
    "mb": {
        "scenarios": SCENARIOS_MB,
        "format_id": VGC_MB,
        "oracle_mod": "championsregmb",
    },
}


def calc_healthy(timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:4173/health", timeout=timeout
        ) as resp:
            body = json.loads(resp.read().decode())
            return body.get("status") == "ok"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return False


def build_oracle_snapshot(*, mod: str) -> Path:
    env_path = os.environ.get("EVAL_ORACLE_SNAPSHOT")
    if env_path:
        p = Path(env_path)
        if not p.exists():
            raise SystemExit(f"EVAL_ORACLE_SNAPSHOT not found: {p}")
        return p
    out = Path(tempfile.mkdtemp(prefix="eval-oracle-")) / "oracle.json"
    cmd = [
        "npx",
        "tsx",
        "scripts/eval/oracle_snapshot.ts",
        "--out",
        str(out),
        "--mod",
        mod,
    ]
    print(f"$ {' '.join(cmd)}", flush=True)
    subprocess.run(cmd, cwd=ROOT, check=True)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--suite",
        choices=("mc", "mb"),
        default="mc",
        help="mc = current regulation (default); mb = historical M-B regression",
    )
    args = parser.parse_args()
    cfg = SUITE_CFG[args.suite]
    format_id = cfg["format_id"]
    scenarios = cfg["scenarios"]
    oracle_mod = cfg["oracle_mod"]

    snap_path = build_oracle_snapshot(mod=oracle_mod)
    snap = load_oracle_snapshot(snap_path)
    commit = ((snap.get("meta") or {}).get("source") or {}).get("commit", "?")
    snap_mod = ((snap.get("meta") or {}).get("source") or {}).get("mod", "?")
    degraded = not calc_healthy()
    if degraded:
        print(
            "WARN: calc /health failed — stubbing _compute_team_review as available empty",
            flush=True,
        )
    else:
        print("calc healthy", flush=True)

    print(f"suite={args.suite} format_id={format_id} oracle_mod={snap_mod}", flush=True)

    results = []
    for sc in scenarios:
        print(f"… {sc.scenario_id}", flush=True)
        result = run_scenario(
            sc.scenario_id,
            sc.path,
            sc.run,
            calc_degraded=degraded,
            format_id=format_id,
        )
        results.append(result)

    pairs_checked = 0
    false_legal = 0
    false_by_path: dict[str, list[str]] = {}
    stalls: list[str] = []

    print("\n=== scenario results ===")
    for r in results:
        illegal = []
        for species, item in r.pairs:
            pairs_checked += 1
            if not pair_legal(snap, species, item):
                false_legal += 1
                illegal.append(f"{species}/{item or '(no item)'}")
        if illegal:
            false_by_path.setdefault(r.path, []).append(
                f"{r.scenario_id}: {', '.join(illegal)}"
            )
        clean_terminal = r.terminal in {
            "complete",
            "revise_committed",
            "repick_committed",
            "slot_committed",
            "build_abandoned",
            "incomplete_build",
            "unresolved_target_role",
        }
        if not clean_terminal and not r.pairs:
            stalls.append(f"{r.scenario_id} ({r.terminal})")
        elif r.terminal.startswith("stalled") or r.terminal.startswith("discovery:"):
            stalls.append(f"{r.scenario_id} ({r.terminal})")
        print(
            f"{r.scenario_id:32} path={r.path:20} terminal={r.terminal:28} "
            f"pairs={len(r.pairs)} illegal={len(illegal)}"
        )

    rate = (false_legal / pairs_checked) if pairs_checked else 0.0
    summary = {
        "suite": args.suite,
        "format_id": format_id,
        "oracle_mod": snap_mod,
        "scenarios": len(results),
        "pairs_checked": pairs_checked,
        "false_legal": false_legal,
        "false_legal_rate": rate,
        "false_by_path": false_by_path,
        "stalls": stalls,
        "calc_degraded": degraded,
        "oracle_commit": commit,
        "oracle_path": str(snap_path),
    }
    print("\n=== summary ===")
    print(json.dumps(summary, indent=2))
    out = ROOT / ".cache" / "eval" / "last_legality_run.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
