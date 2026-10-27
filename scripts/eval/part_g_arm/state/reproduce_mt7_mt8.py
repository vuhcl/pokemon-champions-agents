"""Part 3: reproduce MT7/MT8 keys with the arm solve_spread (write-free).

Membership = calc-feasible under the same survive/outspeed conditions as the key.
Does not call search_conditions (which persists examples). Does not edit frozen files.

Shares solve_spread's feasibility predicate (_parse_constraints / _feasible / _survives)
for membership only — not the frontier search, L1 fill, or nature-set ranking.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("PART_G_V4_CALC_BACKEND", "inprocess")

from scripts.eval.part_g_arm.state.spread_solve import (  # noqa: E402
    STAT_KEYS,
    _feasible,
    _parse_constraints,
    solve_spread,
)

OUT_DEFAULT = Path.home() / "part-g-arm-state-out-spread-reproduce"
KEYS = (
    Path(__file__).resolve().parents[2]
    / "part_g_v4"
    / "key_artifacts"
    / "derived_keys.json"
)

DOUBLES = {"gameType": "Doubles"}
SUN = {"gameType": "Doubles", "weather": "Sun"}


def _sneasler(nature: str) -> dict[str, Any]:
    return {
        "species": "Sneasler",
        "nature": nature,
        "ability": "Unburden",
        "item": "White Herb",
        "sp": {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32},
    }


def _zard(nature: str) -> dict[str, Any]:
    return {
        "species": "Charizard-Mega-Y",
        "nature": nature,
        "ability": "Drought",
        "item": "",
        "sp": {"hp": 0, "atk": 0, "def": 0, "spa": 32, "spd": 0, "spe": 0},
    }


CASES: dict[str, dict[str, Any]] = {
    "mt7_t1": {
        "key": "mt7_t1_jolly_cc",
        "expect_feasible": True,
        "constraints": [
            {
                "type": "survive",
                "attacker": _sneasler("Jolly"),
                "move": "Close Combat",
                "field": DOUBLES,
            },
            {"type": "outspeed", "target_spe": 110},
        ],
    },
    "mt7_t2": {
        "key": "mt7_t2_adamant_cc",
        "expect_feasible": True,
        "constraints": [
            {
                "type": "survive",
                "attacker": _sneasler("Adamant"),
                "move": "Close Combat",
                "field": DOUBLES,
            },
            {"type": "outspeed", "target_spe": 110},
        ],
    },
    "mt7_t3": {
        "key": "mt7_t3_adamant_cc_flamethrower",
        "expect_feasible": True,
        "constraints": [
            {
                "type": "survive",
                "attacker": _sneasler("Adamant"),
                "move": "Close Combat",
                "field": DOUBLES,
            },
            {
                "type": "survive",
                "attacker": _zard("Modest"),
                "move": "Flamethrower",
                "field": SUN,
            },
            {"type": "outspeed", "target_spe": 110},
        ],
    },
    "mt8_t3_modest": {
        "key": "mt8_t3_adamant_cc_weatherball",
        "expect_feasible": False,
        "constraints": [
            {
                "type": "survive",
                "attacker": _sneasler("Adamant"),
                "move": "Close Combat",
                "field": DOUBLES,
            },
            {
                "type": "survive",
                "attacker": _zard("Modest"),
                "move": "Weather Ball",
                "field": SUN,
            },
            {"type": "outspeed", "target_spe": 110},
        ],
    },
    "mt8_t3_timid": {
        "key": "mt8_t3_timid_weatherball_extra",
        "expect_feasible": True,
        "constraints": [
            {
                "type": "survive",
                "attacker": _sneasler("Adamant"),
                "move": "Close Combat",
                "field": DOUBLES,
            },
            {
                "type": "survive",
                "attacker": _zard("Timid"),
                "move": "Weather Ball",
                "field": SUN,
            },
            {"type": "outspeed", "target_spe": 110},
        ],
    },
    "mt8_relax_jolly_sneasler": {
        "key": "mt8_t4_make_sneasler_jolly",
        "expect_feasible": True,
        "constraints": [
            {
                "type": "survive",
                "attacker": _sneasler("Jolly"),
                "move": "Close Combat",
                "field": DOUBLES,
            },
            {
                "type": "survive",
                "attacker": _zard("Modest"),
                "move": "Weather Ball",
                "field": SUN,
            },
            {"type": "outspeed", "target_spe": 110},
        ],
    },
    "mt8_relax_drop_gate": {
        "key": "mt8_t4_drop_speed_gate",
        "expect_feasible": False,
        "constraints": [
            {
                "type": "survive",
                "attacker": _sneasler("Adamant"),
                "move": "Close Combat",
                "field": DOUBLES,
            },
            {
                "type": "survive",
                "attacker": _zard("Modest"),
                "move": "Weather Ball",
                "field": SUN,
            },
            # no outspeed — key says drop Spe gate still 0 solutions under SP cap
        ],
    },
}


def _membership_ok(constraints: list[dict[str, Any]], nature: str, sp: dict[str, int]) -> bool:
    preds, _, err = _parse_constraints("Archaludon", "Stamina", "Leftovers", constraints)
    if err:
        return False
    return _feasible(preds, nature, sp)


def run_case(name: str, spec: dict[str, Any]) -> dict[str, Any]:
    constraints = spec["constraints"]
    out = solve_spread(
        "Archaludon",
        constraints,
        ability="Stamina",
        item="Leftovers",
        time_budget_s=120,
    )
    expect_f = spec["expect_feasible"]
    status = out.get("status")
    if expect_f:
        ok_status = status in {"optimal", "feasible"}
        spread = out.get("spread")
        member = False
        verified = False
        if spread and ok_status:
            nature = spread["nature"]
            sp = {k: int(spread[k]) for k in STAT_KEYS}
            member = _membership_ok(constraints, nature, sp)
            verified = all(r.get("ok") for r in (out.get("constraint_results") or []))
        return {
            "case": name,
            "key": spec["key"],
            "expect_feasible": expect_f,
            "status": status,
            "spread": spread,
            "rank": out.get("rank"),
            "distance": out.get("distance"),
            "claim_wording": out.get("claim_wording"),
            "membership": member,
            "calc_verified": verified,
            "pass": ok_status and member and verified,
            "message": out.get("message") or out.get("error"),
        }
    # expect infeasible
    ok = status == "infeasible"
    return {
        "case": name,
        "key": spec["key"],
        "expect_feasible": expect_f,
        "status": status,
        "spread": out.get("spread"),
        "membership": None,
        "calc_verified": None,
        "pass": ok,
        "message": out.get("message") or out.get("error"),
        "natures_covered": out.get("natures_covered"),
    }


def main(argv: list[str]) -> int:
    out_dir = Path(argv[1]) if len(argv) > 1 else OUT_DEFAULT
    out_dir.mkdir(parents=True, exist_ok=True)
    key_doc = json.loads(KEYS.read_text())
    ar = key_doc["mt7_mt8_ar"]
    rows = []
    for name, spec in CASES.items():
        print(f"running {name}...", flush=True)
        row = run_case(name, spec)
        key_leaf = ar.get(spec["key"]) or {}
        row["key_feasible"] = key_leaf.get("feasible")
        row["key_example"] = key_leaf.get("example")
        rows.append(row)
        print(
            f"  status={row['status']} pass={row['pass']} spread={row.get('spread')}",
            flush=True,
        )
    stop_held = all(r["pass"] for r in rows)
    report = {
        "stop_rule_held": stop_held,
        "stop_rule": (
            "If membership/calc-verify/infeasible match fails by end of 2026-10-28, "
            "STOP: fall back to lookup-only arm for MT7/MT8 as dev findings; "
            "solver ships as a later configuration."
        ),
        "rows": rows,
    }
    (out_dir / "mt7_mt8_reproduce.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        f"stop_rule_held={stop_held}",
        *[f"{r['case']}: pass={r['pass']} status={r['status']}" for r in rows],
    ]
    (out_dir / "mt7_mt8_reproduce.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("SUMMARY", *lines, sep="\n  ")
    return 0 if stop_held else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
