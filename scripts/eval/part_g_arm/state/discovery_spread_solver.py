"""Part 1 discovery for the arm spread solver (read-only; report only).

Measures in-process calc latency, persist=False isolation, mirror-speed gate
from COMMON_JOINT, monotonicity on AR3 + MT7/MT8, enumerator availability,
and the 66-SP joint filter for Archaludon.
"""

from __future__ import annotations

import json
import os
import statistics
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

# Builders live as a flat package under part_g_v4/builders (imports are bare).
_BUILDERS = Path(__file__).resolve().parents[2] / "part_g_v4" / "builders"
if str(_BUILDERS) not in sys.path:
    sys.path.insert(0, str(_BUILDERS))

os.environ.setdefault("PART_G_V4_CALC_BACKEND", "inprocess")

from _lib import champions_spe, common_joint, load_legality, load_showdown, to_id  # noqa: E402
from calc_store import CALC_DIR, calculate, reset_call_log  # noqa: E402
from spread_solver import (  # noqa: E402
    MIRROR_CORE_CELLS,
    MIRROR_DROPPED_MAX,
    MIRROR_MIN_SPE,
    _ok,
    _sneasler,
    _zard_y,
)

OUT_DEFAULT = Path.home() / "part-g-arm-state-out-spread-discovery"
STAT_KEYS = ("hp", "atk", "def", "spa", "spd", "spe")
MANIFEST = (
    Path(__file__).resolve().parents[2]
    / "part_g_v4"
    / "key_artifacts"
    / "ar3_probes"
    / "MANIFEST.json"
)


def _req() -> dict[str, Any]:
    return {
        "attacker": {
            "species": "Sneasler",
            "level": 50,
            "nature": "Jolly",
            "ability": "Unburden",
            "item": "White Herb",
            "evs": {"hp": 2, "atk": 32, "def": 0, "spa": 0, "spd": 0, "spe": 32},
        },
        "defender": {
            "species": "Archaludon",
            "level": 50,
            "nature": "Bold",
            "ability": "Stamina",
            "item": "Leftovers",
            "evs": {"hp": 0, "atk": 0, "def": 12, "spa": 0, "spd": 0, "spe": 5},
        },
        "move": "Close Combat",
        "field": {"gameType": "Doubles"},
    }


def measure_latency(n: int = 30) -> dict[str, Any]:
    """Cold = first in-process call (ignore disk); warm = memory cache hits."""
    os.environ["PART_G_V4_CALC_IGNORE_DISK"] = "1"
    reset_call_log()
    # Clear module cache
    import calc_store as cs

    cs._CACHE.clear()
    req = _req()
    t0 = time.perf_counter()
    calculate(req, "probe", persist=False)
    cold_ms = (time.perf_counter() - t0) * 1000
    warm: list[float] = []
    for _ in range(n):
        t0 = time.perf_counter()
        calculate(req, "probe", persist=False)
        warm.append((time.perf_counter() - t0) * 1000)
    # Different request → still cold-ish for worker but new body
    req2 = dict(req)
    req2 = {
        **req,
        "defender": {**req["defender"], "evs": {"hp": 1, "atk": 0, "def": 12, "spa": 0, "spd": 0, "spe": 5}},
    }
    distinct: list[float] = []
    for i in range(20):
        r = {
            **req,
            "defender": {
                **req["defender"],
                "evs": {"hp": i % 10, "atk": 0, "def": 12, "spa": 0, "spd": 0, "spe": 5},
            },
        }
        t0 = time.perf_counter()
        calculate(r, "probe", persist=False)
        distinct.append((time.perf_counter() - t0) * 1000)
    del os.environ["PART_G_V4_CALC_IGNORE_DISK"]
    return {
        "backend": os.environ.get("PART_G_V4_CALC_BACKEND"),
        "cold_first_ms": round(cold_ms, 3),
        "warm_same_req_ms": {
            "n": n,
            "mean": round(statistics.fmean(warm), 3),
            "median": round(statistics.median(warm), 3),
            "p90": round(sorted(warm)[int(0.9 * (n - 1))], 3),
        },
        "warm_distinct_req_ms": {
            "n": len(distinct),
            "mean": round(statistics.fmean(distinct), 3),
            "median": round(statistics.median(distinct), 3),
            "p90": round(sorted(distinct)[int(0.9 * (len(distinct) - 1))], 3),
            "note": "new request bodies; in-process worker reused, no disk",
        },
    }


def check_persist_false() -> dict[str, Any]:
    before = {p.name for p in CALC_DIR.glob("*.json")} if CALC_DIR.is_dir() else set()
    reset_call_log()
    os.environ["PART_G_V4_CALC_IGNORE_DISK"] = "1"
    import calc_store as cs

    cs._CACHE.clear()
    # Unique defender so probe id is new
    req = _req()
    req["defender"] = {
        **req["defender"],
        "evs": {"hp": 7, "atk": 0, "def": 11, "spa": 0, "spd": 3, "spe": 5},
    }
    rec = calculate(req, "probe", persist=False)
    after = {p.name for p in CALC_DIR.glob("*.json")} if CALC_DIR.is_dir() else set()
    new_files = sorted(after - before)
    del os.environ["PART_G_V4_CALC_IGNORE_DISK"]
    from calc_store import CALL_LOG

    return {
        "persist_arg": False,
        "new_files_in_calc_dir": new_files,
        "wrote_nothing": new_files == [],
        "call_log_tail": CALL_LOG[-1] if CALL_LOG else None,
        "response_ok": "error" not in (rec.get("response") or {}),
        "frozen_note": (
            "CALC_DIR is key_artifacts/calc/; persist=False sets path_note=(not_persisted) "
            "and skips the write. Disk may still SERVE existing artifacts unless "
            "PART_G_V4_CALC_IGNORE_DISK=1."
        ),
    }


def mirror_gate_report() -> dict[str, Any]:
    sd = load_showdown()
    snap = load_legality()
    base = snap["species"][to_id("Archaludon")]["base_stats"]["spe"]
    cells = []
    for r in common_joint(sd, "Archaludon"):  # top 3 — Part 0
        nat = r.get("nature") or "Serious"
        spe_sp = int((r.get("evs") or {}).get("spe") or 0)
        cells.append(
            {
                "nature": nat,
                "spe_sp": spe_sp,
                "spe_stat": champions_spe(base, spe_sp, nat),
                "chaos_weight": r.get("pct"),
            }
        )
    # Also list ALL retained joints' Spe for the helper proposal
    all_joints = (sd["showdown_doubles"]["species"].get("archaludon") or {}).get("top_spreads") or []
    all_cells = []
    for r in all_joints:
        nat = r.get("nature") or "Serious"
        spe_sp = int((r.get("evs") or {}).get("spe") or 0)
        all_cells.append(champions_spe(base, spe_sp, nat))
    joint_sorted = sorted({c["spe_stat"] for c in cells})
    dropped = max(joint_sorted) if joint_sorted else None
    core = [s for s in joint_sorted if s != dropped]
    gate = (max(core) + 1) if core else None
    return {
        "part0_rule": (
            "COMMON_JOINT = top 3 retained Showdown joints by chaos weight; "
            "for outspeed comparisons drop the max-speed cell; gate = max(core)+1. "
            "COMMON_SPEED is not the mirror gate."
        ),
        "hardcoded_in_spread_solver": {
            "MIRROR_MIN_SPE": MIRROR_MIN_SPE,
            "MIRROR_CORE_CELLS": MIRROR_CORE_CELLS,
            "MIRROR_DROPPED_MAX": MIRROR_DROPPED_MAX,
        },
        "recomputed_from_common_joint": {
            "top3_cells": cells,
            "joint_spe_sorted": joint_sorted,
            "core": core,
            "dropped": dropped,
            "gate": gate,
            "matches_hardcode": gate == MIRROR_MIN_SPE and core == MIRROR_CORE_CELLS,
        },
        "proposal": (
            "Tool takes an explicit speed target (integer Spe stat). Optional helper "
            "lists Spe stats from the species' joint entries (66-SP filtered) so the "
            "model can state 'outspeed joint Spe {cells} → gate {gate}' without "
            "reading a key answer. Do not bake MIRROR_MIN_SPE into the tool."
        ),
        "all_listed_joint_spe_stats": sorted(set(all_cells)),
    }


def _ohko_from_artifact(path: Path) -> bool | None:
    d = json.loads(path.read_text())
    resp = d.get("response") or {}
    if "error" in resp:
        return None
    raw = resp.get("raw") or {}
    dmg = raw.get("damage") or []
    if not dmg:
        return False
    hp = (raw.get("stats") or {}).get("defender", {}).get("hp")
    if hp is None:
        return None
    return min(dmg) >= hp


def ar3_monotonicity() -> dict[str, Any]:
    """Atk-SP ladders: if Atk=k OHKOs, Atk=k+1 must OHKO (fixed nature/move/joint)."""
    man = json.loads(MANIFEST.read_text())
    groups: dict[tuple[str, str, int], dict[int, bool | None]] = defaultdict(dict)
    skipped = 0
    for entry in man["files"]:
        aid = entry["artifact_id"]
        path = CALC_DIR / f"{aid}.json"
        if not path.is_file():
            skipped += 1
            continue
        if aid.startswith("ar3_probe_"):
            rest = aid[len("ar3_probe_") :]
        elif aid.startswith("ar3fu_ohko_"):
            rest = aid[len("ar3fu_ohko_") :]
        else:
            skipped += 1
            continue
        segs = rest.split("_")
        jseg = segs[-2]
        if not jseg.startswith("j") or not jseg[1:].isdigit():
            skipped += 1
            continue
        try:
            atk = int(segs[-1])
        except ValueError:
            skipped += 1
            continue
        joint_i = int(jseg[1:])
        atk_nat = segs[-3]
        move = "_".join(segs[:-3])
        groups[(move, atk_nat, joint_i)][atk] = _ohko_from_artifact(path)

    flips = []
    adjacent_ok = 0
    for key, ladder in groups.items():
        atks = sorted(ladder)
        for i, a in enumerate(atks):
            for b in atks[i + 1 :]:
                # Adding Atk SP must never turn OHKO into non-OHKO.
                if ladder[a] is True and ladder[b] is False:
                    flips.append(
                        {
                            "move": key[0],
                            "nature": key[1],
                            "joint": key[2],
                            "atk_lo": a,
                            "atk_hi": b,
                        }
                    )
                if ladder[a] is True and ladder[b] is True:
                    adjacent_ok += 1
    return {
        "manifest_files": len(man["files"]),
        "ladders_grouped": len(groups),
        "skipped_entries": skipped,
        "ohko_then_ohko_ordered_pairs": adjacent_ok,
        "flips_ohko_lo_not_hi": flips,
        "passed": flips == [],
        "note": (
            "OHKO = min(damage) >= defender HP from persisted calc artifacts. "
            "Ladders are incomplete (binary-search probes); check every stored "
            "atk_lo < atk_hi pair."
        ),
    }


def mt_monotonicity() -> dict[str, Any]:
    """Survive constraints: feasible S, S+1 on HP/Def/SpD/Spe (sum≤66) stays feasible."""
    doubles = {"gameType": "Doubles"}
    sun = {"gameType": "Doubles", "weather": "Sun"}
    cases = {
        "mt7_t1": [(_sneasler("Jolly"), "Close Combat", doubles)],
        "mt7_t2": [(_sneasler("Adamant"), "Close Combat", doubles)],
        "mt7_t3": [
            (_sneasler("Adamant"), "Close Combat", doubles),
            (_zard_y("Modest"), "Flamethrower", sun),
        ],
        "mt8_t3_modest": [
            (_sneasler("Adamant"), "Close Combat", doubles),
            (_zard_y("Modest"), "Weather Ball", sun),
        ],
        "mt8_t3_timid": [
            (_sneasler("Adamant"), "Close Combat", doubles),
            (_zard_y("Timid"), "Weather Ball", sun),
        ],
    }
    # Seed spreads from derived keys examples + a few nearby
    seeds = [
        ("Bold", {"hp": 0, "atk": 0, "def": 12, "spa": 0, "spd": 0, "spe": 5}),
        ("Bold", {"hp": 6, "atk": 0, "def": 22, "spa": 0, "spd": 0, "spe": 5}),
        ("Bold", {"hp": 31, "atk": 0, "def": 1, "spa": 0, "spd": 22, "spe": 5}),
        ("Bold", {"hp": 31, "atk": 0, "def": 1, "spa": 0, "spd": 23, "spe": 5}),
        ("Bold", {"hp": 32, "atk": 0, "def": 0, "spa": 0, "spd": 29, "spe": 5}),
        ("Impish", {"hp": 20, "atk": 0, "def": 20, "spa": 0, "spd": 10, "spe": 5}),
        ("Calm", {"hp": 32, "atk": 0, "def": 0, "spa": 0, "spd": 29, "spe": 5}),
    ]
    flips = []
    checked = 0
    seeds_ok: dict[str, int] = {}
    # Use disk cache (probes already pinned); we only care about mono, not writes.
    for case, conds in cases.items():
        n_ok = 0
        for nature, spread in seeds:
            if not _ok(nature, spread, conds):
                continue
            n_ok += 1
            for stat in ("hp", "def", "spd", "spe"):
                if spread[stat] >= 32:
                    continue
                if sum(spread.values()) >= 66:
                    continue
                bumped = dict(spread)
                bumped[stat] = spread[stat] + 1
                checked += 1
                if not _ok(nature, bumped, conds):
                    flips.append(
                        {
                            "case": case,
                            "nature": nature,
                            "spread": spread,
                            "added": stat,
                            "bumped": bumped,
                        }
                    )
        seeds_ok[case] = n_ok
    return {
        "pairs_checked": checked,
        "seeds_feasible_per_case": seeds_ok,
        "flips": flips,
        "passed": flips == [],
        "definition": (
            "Adding 1 SP to HP/Def/SpD/Spe with others fixed and sum≤66 must not "
            "turn a feasible survive-set infeasible."
        ),
    }


def estimate_and_enumerator() -> dict[str, Any]:
    """Measure one-nature grid cost; check whether search_conditions can stay write-free."""
    from speed_grid import ALL_NATURES
    from spread_solver import _min_spe_sp, _search_one_nature

    snap = load_legality()
    base_spe = snap["species"][to_id("Archaludon")]["base_stats"]["spe"]
    doubles = {"gameType": "Doubles"}
    sun = {"gameType": "Doubles", "weather": "Sun"}
    cases = {
        "mt7_t1": [(_sneasler("Jolly"), "Close Combat", doubles)],
        "mt7_t2": [(_sneasler("Adamant"), "Close Combat", doubles)],
        "mt7_t3": [
            (_sneasler("Adamant"), "Close Combat", doubles),
            (_zard_y("Modest"), "Flamethrower", sun),
        ],
        "mt8_t3": [
            (_sneasler("Adamant"), "Close Combat", doubles),
            (_zard_y("Modest"), "Weather Ball", sun),
        ],
    }
    # Gate natures that can hit Spe ≥ 110
    gate_natures = []
    for n in ALL_NATURES:
        ms = _min_spe_sp(base_spe, n)
        if ms is not None:
            gate_natures.append((n, ms))

    # Structural upper bound (per nature, 1 condition → 1 calc per SpD probe)
    rem_at_spe5 = 66 - 5
    cells = sum(1 for hp in range(33) for df in range(33) if hp + df <= rem_at_spe5)
    spd_probes = 6  # ~log2(33) + boundary verify
    upper_per_nat_1cond = cells * spd_probes

    # Measured: one nature (Bold) on mt7_t1 with disk allowed (cache hits) then ignore-disk
    before = {p.name for p in CALC_DIR.glob("*.json")}
    os.environ["PART_G_V4_CALC_BACKEND"] = "inprocess"
    reset_call_log()
    import calc_store as cs

    cs._CACHE.clear()
    from calc_store import CALL_LOG

    nature = "Bold"
    spe = _min_spe_sp(base_spe, nature) or 0
    t0 = time.perf_counter()
    row_disk = _search_one_nature(nature, cases["mt7_t1"], spe, base_spe, use_staircase=False)
    elapsed_disk = time.perf_counter() - t0
    calls_disk = len(CALL_LOG)
    sources_disk = Counter(c.get("source") for c in CALL_LOG)

    # Cold-ish: ignore disk, memory cleared, single nature
    os.environ["PART_G_V4_CALC_IGNORE_DISK"] = "1"
    reset_call_log()
    cs._CACHE.clear()
    t0 = time.perf_counter()
    row_cold = _search_one_nature(nature, cases["mt7_t1"], spe, base_spe, use_staircase=False)
    elapsed_cold = time.perf_counter() - t0
    calls_cold = len(CALL_LOG)
    warm_ms = None
    if calls_cold:
        # second pass identical → memory hits
        reset_call_log()
        t0 = time.perf_counter()
        _search_one_nature(nature, cases["mt7_t1"], spe, base_spe, use_staircase=False)
        elapsed_warm = time.perf_counter() - t0
        warm_ms = round(elapsed_warm * 1000 / max(1, len(CALL_LOG)), 3) if CALL_LOG else None
        calls_warm_pass = len(CALL_LOG)
    else:
        elapsed_warm = None
        calls_warm_pass = 0

    after_one = {p.name for p in CALC_DIR.glob("*.json")}
    one_nature_writes = sorted(after_one - before)

    # Full search_conditions always persist=True on the example — prove it.
    reset_call_log()
    # Allow disk reads for speed; we only check NEW files from example persist
    if "PART_G_V4_CALC_IGNORE_DISK" in os.environ:
        del os.environ["PART_G_V4_CALC_IGNORE_DISK"]
    before2 = {p.name for p in CALC_DIR.glob("*.json")}
    # Use a unique prefix so any write is detectable even if content matches
    prefix = "discovery_mt7_t1_persist_probe"
    # Narrow: monkeypatch ALL_NATURES to just Bold by temporarily patching jobs —
    # call search_conditions would scan all natures (slow). Instead document from source
    # and simulate the example-persist path:
    from spread_solver import _defender

    ex = row_disk.get("example")
    if ex:
        calculate(
            {
                "attacker": cases["mt7_t1"][0][0],
                "defender": _defender(ex["nature"], ex["spread"]),
                "move": cases["mt7_t1"][0][1],
                "field": cases["mt7_t1"][0][2],
            },
            f"{prefix}_ex_0",
            persist=True,
        )
    after2 = {p.name for p in CALC_DIR.glob("*.json")}
    example_writes = sorted(after2 - before2)
    # Clean up discovery write so we don't leave frozen dirt for the commit
    for name in example_writes:
        (CALC_DIR / name).unlink(missing_ok=True)

    # Estimate full solves from measured Bold mt7_t1 × gate natures × condition factor
    n_gate = len(gate_natures)
    per_case_est = {}
    for name, conds in cases.items():
        factor = len(conds)  # each SpD probe runs all conditions
        # Prefer measured cold call count scaled by natures and conditions vs mt7_t1
        est_calls = int(calls_cold * (n_gate / 1) * (factor / 1))
        per_case_est[name] = {
            "n_conditions": factor,
            "est_calc_calls_full_natures": est_calls,
            "est_wall_s_at_cold_rate": round(
                (elapsed_cold / max(1, calls_cold)) * est_calls, 1
            )
            if calls_cold
            else None,
            "est_wall_s_at_disk_rate": round(
                elapsed_disk * n_gate * factor, 1
            )
            if calls_disk
            else None,
        }

    return {
        "n_all_natures": len(ALL_NATURES),
        "n_gate_natures": n_gate,
        "structural_upper_bound_per_nature_1cond": {
            "hp_def_cells_at_spe5": cells,
            "spd_probes_assumed": spd_probes,
            "calcs": upper_per_nat_1cond,
            "full_solve_upper": upper_per_nat_1cond * n_gate,
        },
        "measured_one_nature_mt7_t1_Bold": {
            "disk_cache": {
                "elapsed_s": round(elapsed_disk, 3),
                "calc_calls": calls_disk,
                "sources": dict(sources_disk),
                "n_ok": row_disk.get("n_ok"),
                "min_total": row_disk.get("min_total"),
            },
            "ignore_disk_cold": {
                "elapsed_s": round(elapsed_cold, 3),
                "calc_calls": calls_cold,
                "n_ok": row_cold.get("n_ok"),
                "ms_per_call": round(elapsed_cold * 1000 / max(1, calls_cold), 3),
            },
            "memory_warm_second_pass": {
                "elapsed_s": round(elapsed_warm, 3) if elapsed_warm is not None else None,
                "calc_calls": calls_warm_pass,
                "ms_per_call_approx": warm_ms,
            },
            "one_nature_new_calc_files": one_nature_writes,
        },
        "per_case_estimates": per_case_est,
        "search_conditions_persist": {
            "probe_path": "_survives uses persist=False",
            "example_path": (
                "search_conditions ALWAYS calculate(..., persist=True) for "
                "{prefix}_ex_{i} when an example exists (spread_solver.py ~387–398)"
            ),
            "simulated_example_write": example_writes,
            "cleaned_up": True,
            "can_run_full_set_write_free": False,
            "full_feasible_set_available": False,
            "needed": (
                "1) search_conditions does not return the full feasible set — only "
                "feasible/min_total/example + class COUNTS. "
                "2) Even for feasibility, the example always persists into "
                "key_artifacts/calc/. For tests: either add an enumerate/persist=False "
                "mode in builders (outside state/ → STOP this part's dependency) or "
                "reimplement a write-free grid enumerator under state/ for membership "
                "checks only. Checkpoint dir also writes if PART_G_V4_SOLVER_CHECKPOINT_DIR set."
            ),
        },
    }


def joint_66_filter() -> dict[str, Any]:
    from _lib import is_legal_species

    sd = load_showdown()
    snap = load_legality()
    species = sd["showdown_doubles"]["species"]
    hist = Counter()
    per = {}
    rows_kept = 0
    rows_dropped = 0
    for sid, sp in species.items():
        rows = sp.get("top_spreads") or []
        keep = []
        drop = 0
        for r in rows:
            evs = r.get("evs") or {}
            s = sum(int(evs.get(k) or 0) for k in STAT_KEYS)
            if s == 66:
                keep.append(r)
                rows_kept += 1
            else:
                drop += 1
                rows_dropped += 1
        hist[len(keep)] += 1
        per[sid] = {"name": sp.get("name"), "kept": len(keep), "dropped": drop}
    arch = per.get("archaludon") or {}
    arch_rows = []
    for i, r in enumerate(
        (species.get("archaludon") or {}).get("top_spreads") or []
    ):
        evs = r.get("evs") or {}
        s = sum(int(evs.get(k) or 0) for k in STAT_KEYS)
        if s == 66:
            arch_rows.append(
                {
                    "filtered_rank": len(arch_rows) + 1,
                    "file_rank": i + 1,
                    "nature": r.get("nature"),
                    "evs": {k: int(evs.get(k) or 0) for k in STAT_KEYS},
                    "chaos_weight": r.get("pct"),
                }
            )
    legal_ids = {
        sid for sid, sp in snap["species"].items() if is_legal_species(sp)
    }
    no_ref = sorted(legal_ids - set(species))
    return {
        "joint_species_n": len(species),
        "rows_kept": rows_kept,
        "rows_dropped": rows_dropped,
        "kept_count_hist": dict(sorted(hist.items())),
        "species_with_lt_8_kept": sum(1 for v in per.values() if v["kept"] < 8),
        "species_with_lt_5_kept": sum(1 for v in per.values() if v["kept"] < 5),
        "species_with_0_kept": sum(1 for v in per.values() if v["kept"] == 0),
        "legal_species_n": len(legal_ids),
        "legal_without_joint_n": len(no_ref),
        "legal_without_joint_sample": no_ref[:20],
        "archaludon": {
            "kept": arch.get("kept"),
            "dropped": arch.get("dropped"),
            "entries": arch_rows,
            "natures": sorted({e["nature"] for e in arch_rows}),
        },
    }


def main(argv: list[str]) -> int:
    out_dir = Path(argv[1]) if len(argv) > 1 else OUT_DEFAULT
    out_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {}
    print("1. latency...", flush=True)
    report["latency"] = measure_latency()
    print(json.dumps(report["latency"], indent=2), flush=True)
    print("2. persist=False...", flush=True)
    report["persist_false"] = check_persist_false()
    print(json.dumps(report["persist_false"], indent=2), flush=True)
    print("3. mirror gate...", flush=True)
    report["mirror_gate"] = mirror_gate_report()
    print(json.dumps(report["mirror_gate"], indent=2), flush=True)
    print("4a. AR3 monotonicity...", flush=True)
    report["ar3_monotonicity"] = ar3_monotonicity()
    print(json.dumps(report["ar3_monotonicity"], indent=2), flush=True)
    print("4b. MT7/MT8 monotonicity...", flush=True)
    report["mt_monotonicity"] = mt_monotonicity()
    print(json.dumps(report["mt_monotonicity"], indent=2), flush=True)
    print("5. calc estimate + enumerator write probe...", flush=True)
    report["enumerator"] = estimate_and_enumerator()
    print(json.dumps(report["enumerator"], indent=2), flush=True)
    print("6. 66-SP filter...", flush=True)
    report["joint_66_filter"] = joint_66_filter()
    print(json.dumps(report["joint_66_filter"], indent=2), flush=True)

    mono_pass = (
        report["ar3_monotonicity"]["passed"] and report["mt_monotonicity"]["passed"]
    )
    report["monotonicity_passed"] = mono_pass
    report["part1_clears_build"] = mono_pass and report["persist_false"]["wrote_nothing"]
    report["stop_build_reason"] = None if report["part1_clears_build"] else (
        "monotonicity flip" if not mono_pass else "persist wrote files"
    )

    (out_dir / "spread_solver_discovery.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    summary = [
        f"monotonicity_passed={mono_pass}",
        f"part1_clears_build={report['part1_clears_build']}",
        f"cold_ms={report['latency']['cold_first_ms']}",
        f"warm_median_ms={report['latency']['warm_same_req_ms']['median']}",
        f"bold_mt7_t1_cold_calcs={report['enumerator']['measured_one_nature_mt7_t1_Bold']['ignore_disk_cold']['calc_calls']}",
        f"bold_mt7_t1_cold_s={report['enumerator']['measured_one_nature_mt7_t1_Bold']['ignore_disk_cold']['elapsed_s']}",
        f"arch_kept={report['joint_66_filter']['archaludon']['kept']}",
    ]
    (out_dir / "spread_solver_discovery.txt").write_text(
        "\n".join(summary) + "\n", encoding="utf-8"
    )
    print("SUMMARY", *summary, sep="\n  ")
    print(f"Wrote {out_dir}", flush=True)
    return 0 if mono_pass else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
