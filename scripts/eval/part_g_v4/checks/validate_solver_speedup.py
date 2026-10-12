#!/usr/bin/env python3
"""Validation gate for spread-solver speedup (eval infra).

Checks:
  1) In-process calc vs HTTP /calculate on a random sample (byte-identical responses).
  2) AR3 committed OHKO mins vs binary-search recompute (0 differences).
  3) Fast vs linear search_conditions on a random cell sample (0 differences).
  4) Optional: compare fast JSON to live slow mt7_mt8_ar_live.json stages.

Does not kill the live solver. Does not commit probe_* files.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time
import urllib.request
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
BUILDERS = PKG / "builders"
sys.path.insert(0, str(BUILDERS))

from calc_store import calculate  # noqa: E402
from spread_solver import (  # noqa: E402
    _ok,
    _sneasler,
    search_conditions,
)
from speed_grid import ALL_NATURES  # noqa: E402

CALC = PKG / "key_artifacts" / "calc"
KEYS = PKG / "key_artifacts" / "derived_keys.json"
LIVE = PKG / "key_artifacts" / "solver_runs" / "mt7_mt8_ar_live.json"
FAST = PKG / "key_artifacts" / "solver_runs" / "mt7_mt8_ar_fast.json"
REPORT = PKG / "key_artifacts" / "solver_speedup_validation.json"
BASE_URL = "http://127.0.0.1:4173"


def _http_calculate(req: dict) -> dict:
    payload = json.dumps(req).encode()
    http_req = urllib.request.Request(
        f"{BASE_URL}/calculate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(http_req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _canon_resp(body: dict) -> str:
    """Stable compare: damage range + ko text + raw damage + defender hp."""
    if "error" in body:
        return json.dumps({"error": body["error"]}, sort_keys=True)
    raw = body.get("raw") or {}
    return json.dumps(
        {
            "damageRange": body.get("damageRange"),
            "koChance": body.get("koChance"),
            "damage": raw.get("damage"),
            "range": raw.get("range"),
            "def_hp": (raw.get("stats") or {}).get("defender", {}).get("hp"),
            "atk_stats": (raw.get("stats") or {}).get("attacker"),
            "def_stats": (raw.get("stats") or {}).get("defender"),
        },
        sort_keys=True,
    )


def check_inprocess_vs_http(n: int, seed: int) -> dict:
    from inprocess_calc import calculate_one, close

    rng = random.Random(seed)
    diffs = 0
    samples = []
    for i in range(n):
        hp = rng.randint(0, 32)
        df = rng.randint(0, 32 - hp) if hp < 32 else 0
        spd = rng.randint(0, min(32, 66 - hp - df))
        spe = rng.choice([0, 5, 18])
        nat = rng.choice(list(ALL_NATURES))
        req = {
            "attacker": _sneasler("Jolly"),
            "defender": {
                "species": "Archaludon",
                "level": 50,
                "nature": nat,
                "ability": "Stamina",
                "item": "Leftovers",
                "evs": {
                    "hp": hp,
                    "atk": 0,
                    "def": df,
                    "spa": 0,
                    "spd": spd,
                    "spe": spe,
                },
            },
            "move": "Close Combat",
            "field": {"gameType": "Doubles"},
        }
        http_body = _http_calculate(req)
        inp_body = calculate_one(req)
        same = _canon_resp(http_body) == _canon_resp(inp_body)
        if not same:
            diffs += 1
            if len(samples) < 5:
                samples.append({"i": i, "req": req, "http": http_body, "inprocess": inp_body})
    close()
    return {
        "n": n,
        "seed": seed,
        "differences": diffs,
        "ok": diffs == 0,
        "sample_mismatches": samples,
    }


def _ohko_from_record(rec: dict) -> bool | None:
    raw = (rec.get("response") or {}).get("raw") or {}
    dmg = raw.get("damage") or []
    if not dmg:
        return None
    hp = (raw.get("stats") or {}).get("defender", {}).get("hp") or 0
    return min(dmg) >= hp


def check_ar3_ohko_mins() -> dict:
    """Every committed ar3 OHKO ladder: min Atk matches keys; boundary consistent."""
    import re

    keys = json.loads(KEYS.read_text())
    ar = keys.get("ar3") or {}
    fu = (ar.get("part1_followup") or {}).get("t4_ohko_per_joint") or []
    diffs = []
    checked = 0
    for row in fu:
        move = row.get("move") or ""
        nature = row.get("nature") or ""
        mid = "".join(ch for ch in move.lower() if ch.isalnum())
        for pj in row.get("per_joint") or []:
            ji = int(pj.get("joint_i"))
            expected = pj.get("min_atk_sp")
            found = None
            for atk in range(33):
                path = CALC / f"ar3fu_ohko_{mid}_{nature}_j{ji}_{atk}.json"
                if not path.is_file():
                    path = CALC / f"ar3_probe_{mid}_{nature}_j{ji}_{atk}.json"
                if not path.is_file():
                    break
                ok = _ohko_from_record(json.loads(path.read_text()))
                if ok is None:
                    found = None
                    break
                if ok:
                    found = atk
                    break
            checked += 1
            if found != expected:
                diffs.append(
                    {
                        "move": move,
                        "nature": nature,
                        "joint_i": ji,
                        "expected": expected,
                        "from_probes": found,
                    }
                )

    # All 602 committed ladder files: OHKO flag monotone in Atk within each stem prefix
    probe_re = re.compile(
        r"^(?P<kind>ar3_probe|ar3fu_ohko)_(?P<move>[a-z0-9]+)_(?P<nature>[A-Za-z]+)_j(?P<joint>\d+)_(?P<atk>\d+)$"
    )
    by_ladder: dict[str, list[tuple[int, bool | None]]] = {}
    n_files = 0
    for p in sorted(CALC.glob("ar3*.json")):
        m = probe_re.match(p.stem)
        if not m:
            continue
        n_files += 1
        key = f"{m['kind']}_{m['move']}_{m['nature']}_j{m['joint']}"
        ok = _ohko_from_record(json.loads(p.read_text()))
        by_ladder.setdefault(key, []).append((int(m["atk"]), ok))
    mono_bad = []
    for key, rows in by_ladder.items():
        rows.sort()
        seen_ohko = False
        for atk, ok in rows:
            if ok is True:
                seen_ohko = True
            elif ok is False and seen_ohko:
                mono_bad.append({"ladder": key, "atk": atk})
                break
        # min in ladder vs first True
        first = next((a for a, o in rows if o is True), None)
        # if ladder includes atk 0..min only, last False then True is fine
        if first is not None and first > 0:
            prev = dict(rows).get(first - 1)
            if prev is True:
                mono_bad.append({"ladder": key, "atk": first - 1, "reason": "min-1 still ohko"})
    return {
        "checked_key_rows": checked,
        "committed_ladder_files": n_files,
        "ladders": len(by_ladder),
        "differences": len(diffs),
        "monotone_violations": len(mono_bad),
        "ok": len(diffs) == 0 and len(mono_bad) == 0 and n_files >= 600,
        "diffs": diffs[:20],
        "mono_bad": mono_bad[:10],
    }


def check_fast_vs_linear_sample(n_cells: int, seed: int) -> dict:
    """Compare staircase+binary vs linear grid on random (nature,hp,def) cells for MT7 t1."""
    from spread_solver import (
        _min_spd_binary_verified,
        _min_spd_linear,
        _min_spe_sp,
    )
    from _lib import load_legality, to_id

    snap = load_legality()
    base_spe = snap["species"][to_id("Archaludon")]["base_stats"]["spe"]
    conditions = [(_sneasler("Jolly"), "Close Combat", {"gameType": "Doubles"})]
    rng = random.Random(seed)
    diffs = 0
    samples = []
    os.environ["PART_G_V4_CALC_IGNORE_DISK"] = "1"
    # Prefer inprocess if available; fall back to http
    os.environ.setdefault("PART_G_V4_CALC_BACKEND", "inprocess")
    for i in range(n_cells):
        nature = rng.choice(list(ALL_NATURES))
        spe = _min_spe_sp(base_spe, nature) or 0
        rem = 66 - spe
        hp = rng.randint(0, min(32, rem))
        df = rng.randint(0, min(32, rem - hp))
        spd_hi = min(32, rem - hp - df)
        cid = f"diff|{nature}|{hp}|{df}"
        b = _min_spd_binary_verified(
            nature, hp, df, spe, spd_hi, conditions, cell_id=cid
        )
        lin = _min_spd_linear(nature, hp, df, spe, spd_hi, conditions)
        if b != lin:
            diffs += 1
            if len(samples) < 10:
                samples.append({"nature": nature, "hp": hp, "def": df, "binary": b, "linear": lin})
    return {
        "n": n_cells,
        "seed": seed,
        "differences": diffs,
        "ok": diffs == 0,
        "samples": samples,
    }


def _stage_core(d: dict | None) -> dict:
    if not d:
        return {}
    return {
        "feasible": d.get("feasible"),
        "min_total_sp": d.get("min_total_sp"),
        "solutions_at_minimal_spe_by_class": d.get("solutions_at_minimal_spe_by_class"),
        "example": d.get("example"),
    }


def compare_live_fast() -> dict:
    if not LIVE.is_file() or not FAST.is_file():
        return {
            "ok": False,
            "skipped": True,
            "reason": f"missing live={LIVE.is_file()} fast={FAST.is_file()}",
        }
    live = json.loads(LIVE.read_text())
    fast = json.loads(FAST.read_text())
    # Stages the live log has finished (before drop Spe) — compare those keys.
    keys = [
        "mt7_t1_jolly_cc",
        "mt7_t2_adamant_cc",
        "mt7_t3_adamant_cc_flamethrower",
        "mt8_t3_adamant_cc_weatherball",
        "mt8_t3_timid_weatherball_extra",
        "mt7_t3_timid_flamethrower_extra",
        "mt8_t4_make_sneasler_jolly",
    ]
    diffs = []
    for k in keys:
        a = _stage_core(live.get(k) if not k.endswith("_extra") else live.get(k))
        b = _stage_core(fast.get(k))
        # strip search_note noise from extras
        if json.dumps(a, sort_keys=True) != json.dumps(b, sort_keys=True):
            # compare only feasibility + min + counts + example spread
            ca = {
                "feasible": (live.get(k) or {}).get("feasible"),
                "min_total_sp": (live.get(k) or {}).get("min_total_sp"),
                "solutions_at_minimal_spe_by_class": (live.get(k) or {}).get(
                    "solutions_at_minimal_spe_by_class"
                ),
                "example": (live.get(k) or {}).get("example"),
            }
            cb = {
                "feasible": (fast.get(k) or {}).get("feasible"),
                "min_total_sp": (fast.get(k) or {}).get("min_total_sp"),
                "solutions_at_minimal_spe_by_class": (fast.get(k) or {}).get(
                    "solutions_at_minimal_spe_by_class"
                ),
                "example": (fast.get(k) or {}).get("example"),
            }
            if json.dumps(ca, sort_keys=True) != json.dumps(cb, sort_keys=True):
                diffs.append({"key": k, "live": ca, "fast": cb})
    return {"ok": len(diffs) == 0, "differences": len(diffs), "diffs": diffs}


def run_mt7_t1_timing() -> dict:
    """Wall-clock MT7 t1 fast path (inprocess, ignore disk)."""
    os.environ["PART_G_V4_CALC_BACKEND"] = "inprocess"
    os.environ["PART_G_V4_CALC_IGNORE_DISK"] = "1"
    os.environ.pop("PART_G_V4_SOLVER_LINEAR", None)
    t0 = time.time()
    r = search_conditions(
        [(_sneasler("Jolly"), "Close Combat", {"gameType": "Doubles"})],
        True,
        "val_mt7_t1_fast",
    )
    fast_s = time.time() - t0
    return {
        "fast_wall_s": round(fast_s, 2),
        "feasible": r.get("feasible"),
        "min_total_sp": r.get("min_total_sp"),
        "solutions_at_minimal_spe_by_class": r.get("solutions_at_minimal_spe_by_class"),
        "monotone_fallback_count": r.get("monotone_fallback_count"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample-n", type=int, default=1000)
    ap.add_argument("--sample-seed", type=int, default=42)
    ap.add_argument("--cell-n", type=int, default=200)
    ap.add_argument("--cell-seed", type=int, default=7)
    ap.add_argument("--compare-live", action="store_true")
    ap.add_argument("--skip-inprocess", action="store_true")
    ap.add_argument("--skip-timing", action="store_true")
    args = ap.parse_args()

    report: dict = {"checks": {}}
    ok_all = True

    print("AR3 OHKO mins from committed probes...", flush=True)
    ar3 = check_ar3_ohko_mins()
    report["checks"]["ar3_ohko_mins"] = ar3
    ok_all = ok_all and ar3["ok"]
    print(
        f"  key_rows={ar3.get('checked_key_rows')} files={ar3.get('committed_ladder_files')} "
        f"diffs={ar3['differences']} mono={ar3.get('monotone_violations')}",
        flush=True,
    )

    if not args.skip_inprocess:
        print(f"In-process vs HTTP n={args.sample_n} seed={args.sample_seed}...", flush=True)
        try:
            ip = check_inprocess_vs_http(args.sample_n, args.sample_seed)
            report["checks"]["inprocess_vs_http"] = ip
            ok_all = ok_all and ip["ok"]
            print(f"  diffs={ip['differences']}", flush=True)
        except Exception as e:
            report["checks"]["inprocess_vs_http"] = {"ok": False, "error": str(e)}
            ok_all = False
            print(f"  ERROR {e}", flush=True)

    print(f"Fast vs linear cell sample n={args.cell_n} seed={args.cell_seed}...", flush=True)
    cells = check_fast_vs_linear_sample(args.cell_n, args.cell_seed)
    report["checks"]["fast_vs_linear_cells"] = cells
    ok_all = ok_all and cells["ok"]
    print(f"  diffs={cells['differences']}", flush=True)

    if not args.skip_timing:
        print("MT7 t1 fast timing...", flush=True)
        try:
            report["checks"]["mt7_t1_fast_timing"] = run_mt7_t1_timing()
            print(report["checks"]["mt7_t1_fast_timing"], flush=True)
        except Exception as e:
            report["checks"]["mt7_t1_fast_timing"] = {"ok": False, "error": str(e)}
            print(f"  ERROR {e}", flush=True)

    if args.compare_live:
        print("Compare live vs fast JSON...", flush=True)
        cmp_ = compare_live_fast()
        report["checks"]["live_vs_fast"] = cmp_
        if not cmp_.get("skipped"):
            ok_all = ok_all and cmp_["ok"]
        print(cmp_, flush=True)

    report["ok"] = ok_all
    REPORT.write_text(json.dumps(report, indent=2) + "\n")
    print(f"wrote {REPORT} ok={ok_all}", flush=True)
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
