#!/usr/bin/env python3
"""Run multi-turn steering correctness scenarios (no live LLM)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.eval.harness import (  # noqa: E402
    ScenarioResult,
    eval_scenario_id,
    eval_turn_index,
    run_scenario,
)
from scripts.eval.scenarios_steering import (  # noqa: E402
    SCENARIOS,
    TurnAssertError,
)


def _run_one(sc) -> tuple[ScenarioResult | None, str | None]:
    """Return (result, error_message)."""
    try:
        if sc.scenario_id == "12_sqlite_mid_contradiction":
            # Sqlite lifecycle owns its own graph; skip MemorySaver start_graph.
            tok_sc = eval_scenario_id.set(sc.scenario_id)
            tok_turn = eval_turn_index.set(0)
            try:
                result = sc.run(None, {}, {})
            finally:
                eval_scenario_id.reset(tok_sc)
                eval_turn_index.reset(tok_turn)
        else:
            result = run_scenario(
                sc.scenario_id,
                sc.path,
                sc.run,
                calc_degraded=True,
            )
        return result, None
    except (TurnAssertError, AssertionError, Exception) as exc:
        return None, str(exc)


def main() -> int:
    results: list[dict] = []
    failed = 0
    print("Multi-turn steering correctness", flush=True)
    for sc in SCENARIOS:
        print(f"… {sc.scenario_id}", flush=True)
        result, err = _run_one(sc)
        if err is None and result is not None:
            print(f"  PASS  {sc.doc}", flush=True)
            results.append(
                {
                    "scenario_id": sc.scenario_id,
                    "pass": True,
                    "doc": sc.doc,
                    "notes": result.notes,
                }
            )
        else:
            failed += 1
            print(f"  FAIL  {sc.doc}", flush=True)
            print(f"        {err}", flush=True)
            results.append(
                {
                    "scenario_id": sc.scenario_id,
                    "pass": False,
                    "doc": sc.doc,
                    "error": err,
                }
            )

    out = ROOT / ".cache" / "eval" / "last_steering_run.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "passed": sum(1 for r in results if r["pass"]),
        "failed": failed,
        "total": len(results),
        "scenarios": results,
    }
    out.write_text(json.dumps(payload, indent=2) + "\n")
    print(
        f"\n{payload['passed']}/{payload['total']} passed"
        + (f", {failed} failed" if failed else ""),
        flush=True,
    )
    print(f"Wrote {out}", flush=True)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
