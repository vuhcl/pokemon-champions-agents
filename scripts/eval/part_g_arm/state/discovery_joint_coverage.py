"""Discovery: how concentrated Showdown joint-spread usage is (read-only).

Reuses Part 0 accessors in scripts/eval/part_g_v4/builders/_lib.py
(load_showdown, common_joint, load_legality). Does not choose a cutoff.
"""

from __future__ import annotations

import json
import statistics
import subprocess
import sys
from pathlib import Path
from typing import Any

from scripts.eval.part_g_v4.builders._lib import (
    SHOWDOWN,
    common_joint,
    is_legal_species,
    load_legality,
    load_showdown,
    to_id,
)

CUTOFFS = (1, 3, 5, 10, 15, 20)
CURVE_RANKS = tuple(range(1, 21))
STAT_KEYS = ("hp", "atk", "def", "spa", "spd", "spe")
PIN_BLOB = "63bcefe4512a202d75b62e79f2ccc5436527b46e"
OUT_DEFAULT = Path.home() / "part-g-arm-state-out-joint-coverage"

# Dev species from state/fixtures.py DEV_SPECIES, plus MT7/MT8 focals.
FOCAL = (
    "Archaludon",
    "Venusaur",
    "Venusaur-Mega",
    "Blastoise",
    "Beedrill",
    "Bulbasaur",
    "Sneasler",
    "Charizard",
    "Charizard-Mega-X",
    "Charizard-Mega-Y",
)


def _weight(row: dict[str, Any]) -> float:
    return float(row.get("chaos_weight", row.get("pct") or 0.0))


def _evs(row: dict[str, Any]) -> dict[str, int]:
    raw = row.get("evs") or {}
    return {k: int(raw.get(k) or 0) for k in STAT_KEYS}


def _sp_sum(evs: dict[str, int]) -> int:
    return sum(evs[k] for k in STAT_KEYS)


def _spreads_for(sd: dict[str, Any], sid: str) -> list[dict[str, Any]]:
    """All retained joints in file order (already chaos-weight desc; ties = file order).

    common_joint(sd, name, n) is the same list sliced to n — we pull the full
    retained list once so cutoffs > 3 stay on the same path.
    """
    return list((sd["showdown_doubles"]["species"].get(sid) or {}).get("top_spreads") or [])


def _cum_shares(weights: list[float], cutoffs: tuple[int, ...]) -> dict[int, float | None]:
    total = sum(weights)
    if total <= 0:
        return {k: None for k in cutoffs}
    out: dict[int, float | None] = {}
    running = 0.0
    for i, w in enumerate(weights, start=1):
        running += w
        if i in cutoffs:
            out[i] = running / total
    last = running / total
    for k in cutoffs:
        if k not in out:
            # Requested cutoff past the listed length → full listed mass.
            out[k] = last if weights else None
    return out


def _pctile(sorted_vals: list[float], p: float) -> float:
    if not sorted_vals:
        return float("nan")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    idx = (len(sorted_vals) - 1) * p
    lo = int(idx)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = idx - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def _agg(values: list[float], weights: list[float] | None = None) -> dict[str, float | None]:
    if not values:
        return {"mean": None, "median": None, "p10": None, "p90": None, "n": 0}
    s = sorted(values)
    mean: float
    if weights is None:
        mean = statistics.fmean(values)
    else:
        tw = sum(weights)
        mean = sum(v * w for v, w in zip(values, weights, strict=True)) / tw if tw else float("nan")
    return {
        "mean": mean,
        "median": statistics.median(s),
        "p10": _pctile(s, 0.10),
        "p90": _pctile(s, 0.90),
        "n": len(values),
    }


def _fmt_pct(x: float | None) -> str:
    if x is None:
        return "—"
    return f"{100.0 * x:6.2f}%"


def _band(rank: int) -> str:
    if rank <= 30:
        return "top30"
    if rank <= 100:
        return "31-100"
    return "rest"


def main(argv: list[str]) -> int:
    out_dir = Path(argv[1]) if len(argv) > 1 else OUT_DEFAULT
    out_dir.mkdir(parents=True, exist_ok=True)

    blob = subprocess.check_output(["git", "hash-object", str(SHOWDOWN)], text=True).strip()
    if blob != PIN_BLOB:
        print(
            f"WARNING: showdown file blob {blob} != pin {PIN_BLOB} "
            "(reporting measured blob; pin from check_pins / request-set).",
            file=sys.stderr,
        )

    sd = load_showdown()
    # Sanity: common_joint path matches full list prefix.
    probe = "Archaludon"
    assert common_joint(sd, probe, 3) == _spreads_for(sd, to_id(probe))[:3]

    leg = load_legality()
    legal_ids = {
        sid
        for sid, sp in (leg.get("species") or {}).items()
        if isinstance(sp, dict) and is_legal_species(sp)
    }

    rows: list[dict[str, Any]] = []
    anomalies: list[dict[str, Any]] = []
    species_map = sd["showdown_doubles"]["species"]

    for sid, sp in species_map.items():
        if sid not in legal_ids:
            continue
        spreads = _spreads_for(sd, sid)
        # Rank by usage; file order for ties among equal weights is preserved below.
        weights = [_weight(r) for r in spreads]
        # Detect file-order vs weight-desc mismatch (should not happen).
        ordered = sorted(range(len(weights)), key=lambda i: (-weights[i], i))
        if ordered != list(range(len(weights))):
            anomalies.append(
                {
                    "kind": "weight_order_mismatch",
                    "species": sp.get("name") or sid,
                    "file_order_ok": False,
                }
            )
            spreads = [spreads[i] for i in ordered]
            weights = [_weight(r) for r in spreads]

        listed_sum = sum(weights)
        shares = _cum_shares(weights, CUTOFFS)
        curve = _cum_shares(weights, CURVE_RANKS)

        seen_keys: set[tuple[Any, ...]] = set()
        for r in spreads:
            evs = _evs(r)
            total = _sp_sum(evs)
            key = (r.get("nature"), tuple(evs[k] for k in STAT_KEYS))
            if key in seen_keys:
                anomalies.append(
                    {
                        "kind": "duplicate_joint",
                        "species": sp.get("name") or sid,
                        "nature": r.get("nature"),
                        "evs": evs,
                    }
                )
            seen_keys.add(key)
            if total != 66:
                anomalies.append(
                    {
                        "kind": "sp_sum_ne_66",
                        "species": sp.get("name") or sid,
                        "nature": r.get("nature"),
                        "evs": evs,
                        "sp_sum": total,
                    }
                )
            over = {k: v for k, v in evs.items() if v > 32}
            if over:
                anomalies.append(
                    {
                        "kind": "stat_over_32",
                        "species": sp.get("name") or sid,
                        "nature": r.get("nature"),
                        "over": over,
                        "evs": evs,
                    }
                )

        # Same SP vector, different natures among listed.
        by_sp: dict[tuple[int, ...], set[str]] = {}
        for r in spreads:
            evs = _evs(r)
            by_sp.setdefault(tuple(evs[k] for k in STAT_KEYS), set()).add(str(r.get("nature") or ""))
        same_sp_diff_nat = {
            "/".join(str(x) for x in sp_vec): sorted(nats)
            for sp_vec, nats in by_sp.items()
            if len(nats) > 1
        }

        rows.append(
            {
                "id": sid,
                "name": sp.get("name") or sid,
                "usage_pct": float(sp.get("usage_pct") or 0.0),
                "n_listed": len(spreads),
                "listed_weight_sum": listed_sum,
                "shares_of_listed": {str(k): shares[k] for k in CUTOFFS},
                "curve_of_listed": {str(k): curve[k] for k in CURVE_RANKS},
                "top10": [
                    {
                        "rank": i + 1,
                        "nature": r.get("nature"),
                        "evs": _evs(r),
                        "chaos_weight": _weight(r),
                        "sp_sum": _sp_sum(_evs(r)),
                    }
                    for i, r in enumerate(spreads[:10])
                ],
                "natures_in_top5": sorted(
                    {str(r.get("nature") or "") for r in spreads[:5]}
                ),
                "natures_in_top10": sorted(
                    {str(r.get("nature") or "") for r in spreads[:10]}
                ),
                "same_sp_diff_nature": same_sp_diff_nat,
            }
        )

    rows.sort(key=lambda r: (-r["usage_pct"], r["id"]))
    for i, r in enumerate(rows, start=1):
        r["usage_rank"] = i
        r["band"] = _band(i)

    n_lt5 = sum(1 for r in rows if r["n_listed"] < 5)
    n_lt10 = sum(1 for r in rows if r["n_listed"] < 10)

    # Aggregates
    def table_for(subset: list[dict[str, Any]], label: str) -> dict[str, Any]:
        block: dict[str, Any] = {"label": label, "n_species": len(subset), "cutoffs": {}}
        usages = [r["usage_pct"] for r in subset]
        for k in CUTOFFS:
            vals = [r["shares_of_listed"][str(k)] for r in subset]
            vals_f = [v for v in vals if v is not None]
            block["cutoffs"][str(k)] = {
                "unweighted": _agg(vals_f),
                "usage_weighted": _agg(
                    vals_f,
                    [u for v, u in zip(vals, usages, strict=True) if v is not None],
                ),
            }
        return block

    aggregates = [
        table_for(rows, "all_legal_with_joints"),
        table_for([r for r in rows if r["band"] == "top30"], "usage_rank_top30"),
        table_for([r for r in rows if r["band"] == "31-100"], "usage_rank_31_100"),
        table_for([r for r in rows if r["band"] == "rest"], "usage_rank_rest"),
    ]

    # Top-30: distinct natures in top 5
    top30 = [r for r in rows if r["usage_rank"] <= 30]
    nature_counts_top5 = [len(r["natures_in_top5"]) for r in top30]
    nature_hist = {n: nature_counts_top5.count(n) for n in sorted(set(nature_counts_top5))}

    focals: list[dict[str, Any]] = []
    for name in FOCAL:
        sid = to_id(name)
        hit = next((r for r in rows if r["id"] == sid), None)
        if hit is None:
            focals.append(
                {
                    "requested": name,
                    "id": sid,
                    "present": False,
                    "reason": (
                        "not in legal∩showdown joint set"
                        if sid not in species_map
                        else "illegal or no row"
                    ),
                }
            )
            continue
        focals.append({"requested": name, "present": True, **hit})

    same_sp_species = sum(1 for r in rows if r["same_sp_diff_nature"])

    report = {
        "source": {
            "file": "data/usage/champions-reg-mc.showdown_doubles.v1.json",
            "pin_blob_expected": PIN_BLOB,
            "pin_blob_measured": blob,
            "content_sha256_note": "see FROZEN_MANIFEST / check_pins",
            "meta": sd.get("meta"),
            "unit": (
                "Champions SP (fields named 'evs' in the blob; request-set / ADR-082: "
                "Showdown joint values are SP, not mainline EVs; no conversion step)"
            ),
            "natures_in_joint": True,
            "accessor": (
                "scripts/eval/part_g_v4/builders/_lib.py::common_joint "
                "(top_spreads[:n]; this script uses the same top_spreads list)"
            ),
            "retain_limit": 8,
            "ranking": (
                "chaos_weight descending as stored; ties broken by file order "
                "(extractor already sorts by -weight)"
            ),
        },
        "denominator": {
            "total_usage_share": (
                "NOT computable from the pin. top_spreads[].pct is raw Smogon chaos "
                "Spreads weight (pct_kind=chaos_weight), not divided by Raw, and the "
                "blob keeps only the top 8 joints (_SPREAD_LIMIT=8). Unlisted joints "
                "and Raw are absent, so share of all joint usage / of species Raw "
                "cannot be formed."
            ),
            "listed_joint_share": (
                "sum(top-k chaos_weight) / sum(all retained top_spreads chaos_weight). "
                "This is what the tables report."
            ),
            "species_usage_pct": (
                "species-level usage_pct is present and used only to weight aggregates "
                "and to band by usage rank; it is not the joint denominator."
            ),
        },
        "counts": {
            "legal_species_with_joints": len(rows),
            "n_listed_lt_5": n_lt5,
            "n_listed_lt_10": n_lt10,
            "n_listed_hist": {
                str(n): sum(1 for r in rows if r["n_listed"] == n)
                for n in sorted({r["n_listed"] for r in rows})
            },
            "species_with_same_sp_diff_nature_in_listed": same_sp_species,
        },
        "aggregates": aggregates,
        "top30_distinct_natures_in_top5": {
            "histogram_n_species_by_distinct_nature_count": nature_hist,
            "mean_distinct_natures": (
                statistics.fmean(nature_counts_top5) if nature_counts_top5 else None
            ),
            "note": (
                "If top-5 joints mostly change SP at one nature, distinct natures≈1; "
                "if they mostly change nature, distinct natures approaches 5."
            ),
        },
        "focals": focals,
        "anomalies": anomalies,
        "per_species": rows,
    }

    (out_dir / "joint_coverage.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )

    lines: list[str] = []
    def p(s: str = "") -> None:
        lines.append(s)
        print(s)

    p("=== Joint-spread coverage discovery (listed denominator only) ===")
    p(f"file: {report['source']['file']}")
    p(f"pin blob: {blob} (expected {PIN_BLOB})")
    p(f"unit: {report['source']['unit']}")
    p(f"natures in each joint entry: yes")
    p(f"retain limit: 8 (every legal species in pin has n_listed={report['counts']['n_listed_hist']})")
    p(f"legal species with joints: {len(rows)}")
    p(f"n_listed < 5: {n_lt5}; n_listed < 10: {n_lt10}")
    p()
    p("Denominator: (b) share of LISTED joint chaos_weight only.")
    p("(a) share of TOTAL joint / Raw: not computable from the pin (see JSON).")
    p()
    p("Aggregate table — mean / median / p10 / p90 of (listed-share at cutoff)")
    header = f"{'band':22} {'cut':>4} {'n':>4}  {'mean':>8} {'med':>8} {'p10':>8} {'p90':>8}  | w_mean"
    p(header)
    for block in aggregates:
        for k in CUTOFFS:
            uw = block["cutoffs"][str(k)]["unweighted"]
            ww = block["cutoffs"][str(k)]["usage_weighted"]
            p(
                f"{block['label']:22} {k:>4} {uw['n']:>4}  "
                f"{_fmt_pct(uw['mean'])} {_fmt_pct(uw['median'])} "
                f"{_fmt_pct(uw['p10'])} {_fmt_pct(uw['p90'])}  | {_fmt_pct(ww['mean'])}"
            )
        p()

    p("Top-30 species: distinct natures in top-5 joints")
    p(f"  histogram (distinct_natures -> n_species): {nature_hist}")
    p(f"  mean distinct natures in top 5: {report['top30_distinct_natures_in_top5']['mean_distinct_natures']}")
    p()

    p("=== Focal curves (share of listed at rank 1..20; top-10 natures) ===")
    for f in focals:
        if not f.get("present"):
            p(f"{f['requested']}: ABSENT ({f.get('reason')})")
            continue
        p(
            f"{f['name']} usage_pct={f['usage_pct']:.4f} rank={f['usage_rank']} "
            f"n_listed={f['n_listed']} natures@5={f['natures_in_top5']} "
            f"natures@10={f['natures_in_top10']}"
        )
        curve = f["curve_of_listed"]
        bits = " ".join(f"r{r}={_fmt_pct(curve[str(r)]).strip()}" for r in CURVE_RANKS)
        p(f"  curve: {bits}")
        for ent in f["top10"]:
            p(
                f"  #{ent['rank']} {ent['nature']:8} SP={ent['evs']} "
                f"sum={ent['sp_sum']} w={ent['chaos_weight']:.3f}"
            )
        p()

    p(f"Anomalies: {len(anomalies)} (see JSON)")
    by_kind: dict[str, int] = {}
    for a in anomalies:
        by_kind[a["kind"]] = by_kind.get(a["kind"], 0) + 1
    p(f"  by kind: {by_kind}")
    p(f"Species with same-SP / different-nature among listed: {same_sp_species}")
    p()
    p(f"Wrote {out_dir / 'joint_coverage.json'}")
    (out_dir / "joint_coverage.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
