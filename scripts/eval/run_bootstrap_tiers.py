#!/usr/bin/env python3
"""Bootstrap tiered-fallback eval — Layer 1 census + Layer 2 named harness.

Measures current shipped discover_bootstrap_directions (including hardcoded
regulation=\"champions-reg-mb\"). Does not modify production code.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import Counter
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.eval.scenarios_bootstrap import (  # noqa: E402
    LEGALITY_SNAP,
    census_one,
    load_became_legal_ids,
    run_all_named,
)


def _repo_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def main() -> int:
    snap = json.loads(LEGALITY_SNAP.read_text(encoding="utf-8"))
    ids = load_became_legal_ids()
    rows = [census_one(sid, snap=snap) for sid in ids]

    counts = Counter(r["tier"] for r in rows)
    pre = counts.get("pre_tier", 0)
    n = 35 - pre
    tier1 = counts.get("tier1", 0)
    tier2 = counts.get("tier2", 0)
    tier3 = counts.get("tier3", 0)
    if tier1 + tier2 + tier3 != n:
        raise RuntimeError(
            f"tier sum {tier1}+{tier2}+{tier3} != N={n} (pre_tier={pre})"
        )

    print("=== Layer 2 named scenarios (VGC_MC harness) ===", flush=True)
    named = run_all_named()
    named_pass = sum(1 for r in named if r.get("passed"))
    named_fail = [r["id"] for r in named if not r.get("passed")]
    for r in named:
        mark = "PASS" if r["passed"] else "FAIL"
        print(
            f"  [{mark}] {r['id']:28} terminal={r['terminal']} "
            f"role={r.get('role_id')} producer={r.get('producer_name')}",
            flush=True,
        )
        if r.get("checks"):
            print(f"         checks={r['checks']}", flush=True)
        if r.get("soft"):
            print(f"         soft={r['soft']}", flush=True)

    summary = {
        "schema_version": 2,
        "layer": "1+2",
        "measured": date.today().isoformat(),
        "repo_head": _repo_head(),
        "note": (
            "Layer 1 census + Layer 2 named harness under VGC_MC. "
            "Shipped bootstrap still hardcodes regulation=champions-reg-mb."
        ),
        "species_total": 35,
        "pre_tier": pre,
        "N_zero_signal": n,
        "tier1": tier1,
        "tier2": tier2,
        "tier3": tier3,
        "rates": {
            "tier1_over_N": f"{tier1}/{n}" if n else "0/0",
            "tier2_over_N": f"{tier2}/{n}" if n else "0/0",
            "tier3_over_N": f"{tier3}/{n}" if n else "0/0",
        },
        "rows": rows,
        "named": named,
        "named_summary": {
            "pass": named_pass,
            "fail": len(named) - named_pass,
            "fail_ids": named_fail,
            "total": len(named),
        },
    }

    out = ROOT / ".cache" / "eval" / "last_bootstrap_tiers_run.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({k: summary[k] for k in summary if k not in ("rows", "named")}, indent=2))
    print(f"\nWrote {out}", flush=True)
    print("\n# 35-row table (id | name | tier | producer_name | role_id)", flush=True)
    for r in rows:
        prod = r["producer_name"] or (r["clarification"] or "")[:60]
        print(
            f"{r['id']}\t{r['name']}\t{r['tier']}\t{prod}\t{r.get('role_id') or '-'}",
            flush=True,
        )
    print(
        f"\nN={n} (35 - {pre} pre_tier) → "
        f"tier1={tier1}/{n} tier2={tier2}/{n} tier3={tier3}/{n}",
        flush=True,
    )
    print(
        f"named={named_pass}/{len(named)} pass "
        f"(fail_ids={named_fail})",
        flush=True,
    )
    return 0 if named_pass == len(named) else 1


if __name__ == "__main__":
    raise SystemExit(main())
