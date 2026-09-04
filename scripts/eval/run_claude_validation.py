"""Task C — targeted Claude API validation (parser-only, live Anthropic).

Fail closed if ANTHROPIC_API_KEY / BOOTSTRAP_ANTHROPIC_MODEL / langchain-anthropic
are missing — never silently mock.

Usage:
  export ANTHROPIC_API_KEY=...
  export BOOTSTRAP_ANTHROPIC_MODEL=claude-sonnet-4-20250514   # or current id
  uv run --extra anthropic python scripts/eval/run_claude_validation.py
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.eval.scenarios_claude import ClaudeScenario, build_scenarios


def _fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)


def _require_live_anthropic() -> tuple[Any, str]:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        _fail(
            "ANTHROPIC_API_KEY is unset. Task C requires a live Anthropic key "
            "(fail closed; no mock fallback)."
        )
    model = os.environ.get("BOOTSTRAP_ANTHROPIC_MODEL")
    if not model:
        _fail(
            "BOOTSTRAP_ANTHROPIC_MODEL is unset. Set it to the Anthropic model id "
            "to validate (same env as production anthropic provider)."
        )
    try:
        from recommender.turn_intent import build_anthropic_turn_intent_parser
    except ImportError as exc:
        _fail(f"langchain-anthropic unavailable: {exc}. Try: uv sync --extra anthropic")
    try:
        parser = build_anthropic_turn_intent_parser(model)
    except Exception as exc:
        _fail(f"failed to build Anthropic turn-intent parser: {exc}")
    return parser, model


def _norm(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_norm(v) for v in value]
    if isinstance(value, list):
        return [_norm(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _norm(v) for k, v in value.items()}
    if isinstance(value, str):
        return value.strip()
    return value


def _payload_dict(result: dict[str, Any]) -> dict[str, Any]:
    payload = result.get("turn_payload")
    if payload is None:
        return {}
    if hasattr(payload, "items"):
        return dict(payload)  # type: ignore[arg-type]
    return {}


def _option_ids_equal(a: Any, b: Any) -> bool:
    na = _norm(a)
    nb = _norm(b)
    if not isinstance(na, list) or not isinstance(nb, list):
        return na == nb
    # Order-insensitive for multi-axis compose; order-sensitive length check first.
    if len(na) != len(nb):
        return False
    return sorted(map(str, na)) == sorted(map(str, nb))


def _payload_agrees(sc: ClaudeScenario, got: dict[str, Any]) -> tuple[bool, list[str]]:
    mismatches: list[str] = []
    for key in sc.payload_keys:
        if key not in sc.expected_payload:
            continue
        exp = sc.expected_payload[key]
        if key not in got:
            mismatches.append(f"missing payload.{key}")
            continue
        actual = got[key]
        if key == "option_ids":
            if not _option_ids_equal(exp, actual):
                mismatches.append(f"option_ids expected={exp!r} got={actual!r}")
        elif _norm(exp) != _norm(actual):
            mismatches.append(f"{key} expected={exp!r} got={actual!r}")
    return (not mismatches), mismatches


def _run_one(parser: Any, sc: ClaudeScenario) -> dict[str, Any]:
    from recommender.turn_intent import parse_turn_intent

    result = parse_turn_intent(
        parser,
        user_text=sc.user_text,
        pending_kind=sc.pending_kind,
        pending_context=sc.pending_context,
        roster_summary=sc.roster_summary,
        last_system_claim=sc.last_system_claim,
        had_pending=sc.pending_kind not in ("", "none"),
    )
    got_intent = result.get("turn_intent")
    got_payload = _payload_dict(result)
    intent_ok = got_intent == sc.expected_intent
    payload_ok, payload_mismatches = _payload_agrees(sc, got_payload)
    # Intent is the hard gate; payload keys are additional when declared.
    agrees = intent_ok and payload_ok
    return {
        "scenario_id": sc.scenario_id,
        "component": sc.component,
        "known_deferred": sc.known_deferred,
        "expected_intent": sc.expected_intent,
        "got_intent": got_intent,
        "expected_payload": _norm(sc.expected_payload),
        "got_payload": _norm(got_payload),
        "agrees": agrees,
        "intent_ok": intent_ok,
        "payload_mismatches": payload_mismatches,
        "doc": sc.doc,
    }


def _summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_comp: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_comp[row["component"]].append(row)

    rates: dict[str, dict[str, Any]] = {}
    for comp, items in by_comp.items():
        scored = [r for r in items if not r["known_deferred"]]
        deferred = [r for r in items if r["known_deferred"]]
        n = len(scored)
        ok = sum(1 for r in scored if r["agrees"])
        rates[comp] = {
            "n": n,
            "agree": ok,
            "rate": (ok / n) if n else None,
            "deferred_n": len(deferred),
            "deferred_agree": sum(1 for r in deferred if r["agrees"]),
        }

    divergences = [
        {
            "scenario_id": r["scenario_id"],
            "component": r["component"],
            "triage": (
                "known_deferred_multi_axis_bare_number"
                if r["known_deferred"]
                else "divergence_bug_candidate"
            ),
            "expected_intent": r["expected_intent"],
            "got_intent": r["got_intent"],
            "expected_payload": r["expected_payload"],
            "got_payload": r["got_payload"],
            "payload_mismatches": r["payload_mismatches"],
        }
        for r in rows
        if not r["agrees"]
    ]
    return {"by_component": rates, "divergences": divergences, "total": len(rows)}


def main() -> None:
    parser, model = _require_live_anthropic()
    scenarios = build_scenarios()
    print(f"model={model} scenarios={len(scenarios)}", flush=True)

    rows: list[dict[str, Any]] = []
    for sc in scenarios:
        print(f"  run {sc.scenario_id}…", flush=True)
        row = _run_one(parser, sc)
        mark = "OK" if row["agrees"] else ("DEFERRED" if sc.known_deferred else "DIFF")
        print(
            f"    {mark} intent={row['got_intent']!r} "
            f"(expected {row['expected_intent']!r})",
            flush=True,
        )
        rows.append(row)

    summary = _summarize(rows)
    out = {
        "measured": date.today().isoformat(),
        "model": model,
        "scenarios": rows,
        "summary": summary,
    }
    print(json.dumps({"summary": summary}, indent=2))
    out_path = os.environ.get("EVAL_CLAUDE_JSON")
    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2)
            fh.write("\n")
        print(f"wrote {out_path}")

    # Machine-readable block for pasting into eval_results.md
    print("\n--- EVAL_RESULTS_SNIPPET ---")
    for comp, stats in summary["by_component"].items():
        rate = stats["rate"]
        rate_s = "n/a" if rate is None else f"{stats['agree']} / {stats['n']} ({rate:.1%})"
        print(f"- {comp}: {rate_s} (deferred excluded: {stats['deferred_n']})")
    if summary["divergences"]:
        print("Divergences:")
        for d in summary["divergences"]:
            print(
                f"  - {d['scenario_id']} [{d['triage']}]: "
                f"expected={d['expected_intent']!r} got={d['got_intent']!r}"
            )
    else:
        print("Divergences: none")


if __name__ == "__main__":
    main()
