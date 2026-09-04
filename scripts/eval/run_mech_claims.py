#!/usr/bin/env python3
"""Mechanical-claim fidelity checks (Task B). Requires healthy calc service."""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from recommender.build_compare import parse_ko_turns  # noqa: E402
from recommender.calc_client import calculate_batch  # noqa: E402
from recommender.ids import to_id  # noqa: E402
from recommender.matchup import clear_matchup_memo, classify_matchup  # noqa: E402
from recommender.state import all_locked  # noqa: E402
from recommender.usage_spreads import effective_spe  # noqa: E402
from scripts.eval.calc_log import EvalSpies  # noqa: E402
from scripts.eval.harness import run_scenario  # noqa: E402
from scripts.eval.scenarios import SCENARIOS  # noqa: E402
from scripts.eval.scenarios_mech import (  # noqa: E402
    COMPARE_SCENARIOS,
    _run_compare,
    run_charge_recharge_structural,
)

_DMG_LINE = re.compile(
    r"^\s+(\S+): (.+) dmg=(\[[^\]]+\]|\S+) ko=(.*?)(?: \((guaranteed )?(\d+)HKO\))?$"
)


def calc_healthy(timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(
            "http://127.0.0.1:4173/health", timeout=timeout
        ) as resp:
            return json.loads(resp.read().decode()).get("status") == "ok"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return False


def _builds_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for slot in state.get("team_draft") or []:
        if not all_locked(slot):
            continue
        out.append(
            {
                "species": str(slot.species.value),
                "ability": str(slot.ability.value or ""),
                "item": str(slot.item.value or ""),
                "nature": str(slot.nature.value or "Serious"),
                "evs": dict(slot.spread.value or {}),
                "moves": list(slot.moveset.value or []),
            }
        )
    return out


def check_spe(builds: list[dict[str, Any]], *, limit: int = 15) -> dict[str, Any]:
    """Compare effective_spe(scarf=False) to calc raw.stats.attacker.spe."""
    seen: set[str] = set()
    sample: list[dict[str, Any]] = []
    for b in builds:
        key = f"{b['species']}|{b['nature']}|{b['evs'].get('spe')}|{b['item']}"
        if key in seen:
            continue
        seen.add(key)
        sample.append(b)
        if len(sample) >= limit:
            break

    agree = 0
    mismatches: list[dict[str, Any]] = []
    for b in sample:
        espe = effective_spe(
            b["species"],
            dict(b["evs"]),
            str(b["nature"]),
            scarf=False,
        )
        move = next(
            (m for m in b.get("moves") or [] if to_id(m) != "protect"),
            (b.get("moves") or ["Tackle"])[0] if b.get("moves") else "Tackle",
        )
        req = {
            "attacker": {
                "species": b["species"],
                "ability": b.get("ability") or None,
                "item": b.get("item") or None,
                "nature": b["nature"],
                "evs": dict(b["evs"]),
                "moves": list(b.get("moves") or [move]),
            },
            "defender": {
                "species": "Incineroar",
                "moves": ["Knock Off"],
            },
            "move": move,
        }
        # Drop None fields
        req["attacker"] = {k: v for k, v in req["attacker"].items() if v is not None}
        result = calculate_batch([req])[0]  # type: ignore[list-item]
        if not isinstance(result, dict) or result.get("error"):
            mismatches.append(
                {
                    "build": b,
                    "effective_spe": espe,
                    "calc_spe": None,
                    "error": result.get("error") if isinstance(result, dict) else "bad",
                }
            )
            continue
        cspe = ((result.get("raw") or {}).get("stats") or {}).get("attacker", {}).get(
            "spe"
        )
        if cspe == espe:
            agree += 1
        else:
            mismatches.append(
                {
                    "species": b["species"],
                    "nature": b["nature"],
                    "spe_ev": b["evs"].get("spe"),
                    "item": b["item"],
                    "effective_spe": espe,
                    "calc_spe": cspe,
                }
            )
    n = len(sample)
    return {
        "n": n,
        "agree": agree,
        "rate": (agree / n) if n else 0.0,
        "mismatches": mismatches,
    }


def check_damage_ko(
    compare_texts: list[tuple[str, str, int]],
    calc_log: list[Any],
) -> dict[str, Any]:
    """compare_texts: (scenario_id, analysis, turn_index)."""
    corr_ok = corr_n = 0
    fresh_ok = fresh_n = 0
    mismatches: list[dict[str, Any]] = []

    for scenario_id, analysis, turn_index in compare_texts:
        # Batches for this compare turn (one per threat).
        batches = [
            e
            for e in calc_log
            if e.scenario_id == scenario_id and e.turn_index == turn_index
        ]
        dmg_lines = [
            ln for ln in analysis.splitlines() if " dmg=" in ln and " ko=" in ln
        ]
        # Flatten logged responses in order.
        flat: list[tuple[Any, Any]] = []
        for e in batches:
            for req, resp in zip(e.requests, e.responses, strict=False):
                flat.append((req, resp))

        for i, line in enumerate(dmg_lines):
            m = _DMG_LINE.match(line)
            if not m:
                mismatches.append({"line": line, "error": "parse_fail"})
                continue
            oid, move, dmg_s, ko, _g, _turns = m.groups()
            # damageRange printed as list repr
            try:
                dmg = json.loads(dmg_s.replace("'", '"')) if dmg_s.startswith("[") else dmg_s
            except json.JSONDecodeError:
                dmg = dmg_s

            if i >= len(flat):
                mismatches.append({"line": line, "error": "no_logged_batch_row"})
                continue
            req, logged = flat[i]
            corr_n += 1
            if not isinstance(logged, dict) or logged.get("error"):
                mismatches.append({"line": line, "error": "logged_error", "logged": logged})
                continue
            tier_turns, tier_g = parse_ko_turns(str(logged.get("koChance") or ""), logged)
            tier = ""
            if tier_turns is not None:
                tier = f" ({'guaranteed ' if tier_g else ''}{tier_turns}HKO)"
            expected = f"  {oid}: {move} dmg={logged.get('damageRange')} ko={logged.get('koChance') or ''}{tier}"
            # Compare field equality rather than exact line (whitespace).
            a_ok = (
                logged.get("damageRange") == dmg
                or str(logged.get("damageRange")) == dmg_s
            ) and str(logged.get("koChance") or "") == ko
            if a_ok:
                corr_ok += 1
            else:
                mismatches.append(
                    {
                        "check": "a_correlation",
                        "line": line,
                        "expected_like": expected,
                        "logged_dmg": logged.get("damageRange"),
                        "logged_ko": logged.get("koChance"),
                    }
                )

            # (b) fresh re-issue
            fresh_n += 1
            fresh = calculate_batch([req])[0]
            if not isinstance(fresh, dict) or fresh.get("error"):
                mismatches.append({"check": "b_fresh", "line": line, "error": fresh})
                continue
            ft, fg = parse_ko_turns(str(fresh.get("koChance") or ""), fresh)
            fresh_tier = ""
            if ft is not None:
                fresh_tier = f" ({'guaranteed ' if fg else ''}{ft}HKO)"
            fresh_line = (
                f"  {oid}: {move} dmg={fresh.get('damageRange')} "
                f"ko={fresh.get('koChance') or ''}{fresh_tier}"
            )
            # Match displayed line content to fresh
            if (
                fresh.get("damageRange") == dmg
                or str(fresh.get("damageRange")) == dmg_s
            ) and str(fresh.get("koChance") or "") == ko:
                # Also require tier label agreement when present
                if ("HKO)" in line) == bool(fresh_tier):
                    if "HKO)" not in line or line.rstrip().endswith(fresh_tier.rstrip()):
                        fresh_ok += 1
                        continue
            mismatches.append(
                {
                    "check": "b_fresh",
                    "line": line,
                    "fresh_line": fresh_line,
                }
            )

    return {
        "correlation": {
            "n": corr_n,
            "agree": corr_ok,
            "rate": (corr_ok / corr_n) if corr_n else 0.0,
        },
        "fresh": {
            "n": fresh_n,
            "agree": fresh_ok,
            "rate": (fresh_ok / fresh_n) if fresh_n else 0.0,
        },
        "mismatches": mismatches[:20],
    }


def check_matchup_memo(captures: list[Any]) -> dict[str, Any]:
    by_key: dict[Any, Any] = {}
    for c in captures:
        by_key.setdefault(c.cache_key, c)

    agree = 0
    mismatches: list[dict[str, Any]] = []
    for key, c in by_key.items():
        clear_matchup_memo()
        again = classify_matchup(c.build_a, c.build_b, c.field)
        if again.outcome == c.result.outcome and again.severity == c.result.severity:
            agree += 1
        else:
            mismatches.append(
                {
                    "cache_key": str(key)[:120],
                    "first": {"outcome": c.result.outcome, "severity": c.result.severity},
                    "rerun": {"outcome": again.outcome, "severity": again.severity},
                }
            )
    n = len(by_key)
    return {
        "n": n,
        "agree": agree,
        "rate": (agree / n) if n else 0.0,
        "mismatches": mismatches,
    }


def main() -> int:
    if not calc_healthy():
        print("FATAL: calc /health failed — aborting mech-claim measurement", flush=True)
        return 2

    spies = EvalSpies()
    spies.install()
    all_builds: list[dict[str, Any]] = []
    compare_texts: list[tuple[str, str, int]] = []

    try:
        print("=== Task A scenarios (with calc/matchup spies) ===", flush=True)
        for sc in SCENARIOS:
            print(f"… {sc.scenario_id}", flush=True)
            clear_matchup_memo()
            result = run_scenario(sc.scenario_id, sc.path, sc.run, calc_degraded=False)
            all_builds.extend(_builds_from_state(result.state))

        print("=== compare extras ===", flush=True)
        from scripts.eval.harness import eval_turn_index

        for sid, oids in COMPARE_SCENARIOS:
            print(f"… {sid}", flush=True)
            clear_matchup_memo()
            before = eval_turn_index.get()
            result = run_scenario(sid, "compare", _run_compare(sid, oids))
            # turn() increments; compare is one turn
            turn_idx = eval_turn_index.get()  # already reset after run_scenario
            # Recover turn index from last calc log entry for this scenario
            turns = [e.turn_index for e in spies.calc_log if e.scenario_id == sid]
            turn_idx = turns[-1] if turns else 1
            if result.compare_analysis:
                compare_texts.append((sid, result.compare_analysis, turn_idx))
                print(result.compare_analysis[:200].replace("\n", " | "), flush=True)

        print("=== check 4 charge/recharge ===", flush=True)
        check4 = run_charge_recharge_structural()
    finally:
        spies.uninstall()

    # Prefer scarf-bearing builds in Spe sample when present
    scarf = [b for b in all_builds if to_id(b.get("item") or "") == "choicescarf"]
    others = [b for b in all_builds if to_id(b.get("item") or "") != "choicescarf"]
    spe_pool = scarf + others

    check1 = check_spe(spe_pool, limit=15)
    check2 = check_damage_ko(compare_texts, spies.calc_log)
    check3 = check_matchup_memo(spies.matchups)

    summary = {
        "check1_spe": check1,
        "check2_damage_ko": check2,
        "check3_matchup_memo": check3,
        "check4_turn_economy": check4,
        "builds_seen": len(all_builds),
        "calc_log_entries": len(spies.calc_log),
        "matchup_captures": len(spies.matchups),
    }
    print("\n=== summary ===")
    # Compact print (truncate mismatch lists)
    printable = json.loads(json.dumps(summary, default=str))
    print(json.dumps(printable, indent=2)[:8000])
    out = ROOT / ".cache" / "eval" / "last_mech_claims_run.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(printable, indent=2) + "\n")
    print(f"wrote {out}")
    if check2["fresh"]["n"] == 0:
        print("FATAL: Check 2 sample size 0 — compare extras failed", flush=True)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
