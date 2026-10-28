"""Exact two-sided 95% Clopper-Pearson intervals on pass counts.

Inputs (optional; any combination):
  --scorer PATH   class_scorer.score_transcript JSON
  --audit-csv PATH  hand_audit_export.csv (row_id,turn,rubric_point_id,verdict,overall,note)

Reports intervals per B1 bucket, per key class, and overall, at row and turn
(or rubric-point) level. Never pools classes into a gate (ADR-078); the
"overall" line is descriptive only.

    uv run python -m scripts.eval.part_g_arm.state.clopper_pearson --scorer scorer.json
    uv run python -m scripts.eval.part_g_arm.state.clopper_pearson --audit-csv hand_audit_export.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
DISCOVERY = HERE / "b1_discovery.json"
ALPHA = 0.05  # two-sided 95% → α/2 each tail


def _binom_cdf(k: int, n: int, p: float) -> float:
    """P(X <= k) for X ~ Binomial(n, p)."""
    if n < 0 or k < 0:
        raise ValueError("n and k must be non-negative")
    if k >= n:
        return 1.0
    if p <= 0.0:
        return 1.0
    if p >= 1.0:
        return 0.0 if k < n else 1.0
    lp, lq = math.log(p), math.log1p(-p)
    return sum(
        math.exp(
            math.lgamma(n + 1)
            - math.lgamma(i + 1)
            - math.lgamma(n - i + 1)
            + i * lp
            + (n - i) * lq
        )
        for i in range(k + 1)
    )


def clopper_pearson_two_sided(
    passes: int, n: int, *, alpha: float = ALPHA
) -> tuple[float, float]:
    """Exact two-sided Clopper-Pearson (1-alpha) interval for a binomial proportion.

    passes = number of successes (k); n = trials.
    """
    if n < 0 or passes < 0 or passes > n:
        raise ValueError(f"need 0 <= passes <= n; got passes={passes}, n={n}")
    if n == 0:
        return (float("nan"), float("nan"))
    half = alpha / 2.0

    if passes == 0:
        lo = 0.0
    else:
        # largest p with P(X >= k) = half  ⇔  P(X <= k-1) = 1-half
        target = 1.0 - half
        lo_b, hi_b = 0.0, passes / n
        for _ in range(100):
            mid = (lo_b + hi_b) / 2.0
            if _binom_cdf(passes - 1, n, mid) > target:
                lo_b = mid
            else:
                hi_b = mid
        lo = hi_b

    if passes == n:
        hi = 1.0
    else:
        # smallest p with P(X <= k) = half
        target = half
        lo_b, hi_b = passes / n, 1.0
        for _ in range(100):
            mid = (lo_b + hi_b) / 2.0
            if _binom_cdf(passes, n, mid) > target:
                lo_b = mid
            else:
                hi_b = mid
        hi = hi_b

    return (lo, hi)


def _interval_row(label: str, passes: int, n: int) -> dict[str, Any]:
    lo, hi = clopper_pearson_two_sided(passes, n)
    rate = (passes / n) if n else float("nan")
    return {
        "label": label,
        "passes": passes,
        "n": n,
        "rate": rate,
        "ci95_lo": lo,
        "ci95_hi": hi,
    }


def _discovery_buckets() -> dict[str, str]:
    doc = json.loads(DISCOVERY.read_text(encoding="utf-8"))
    return {row["row"]: row["bucket"] for row in doc.get("covered") or []}


def from_scorer(doc: dict[str, Any]) -> list[dict[str, Any]]:
    """Build CI rows from class_scorer.score_transcript output."""
    buckets = _discovery_buckets()
    # turn-level: match counts
    by_bucket_turn: dict[str, list[int]] = {}
    by_class_turn: dict[str, list[int]] = {}
    overall_turn = [0, 0]
    # row-level: row passes iff every scored turn matches
    by_bucket_row: dict[str, list[int]] = {}
    by_class_row: dict[str, list[int]] = {}  # by first-turn / primary class
    overall_row = [0, 0]

    for entry in doc.get("per_row") or []:
        if entry.get("excluded") in {"stale_pin", "not_covered", "unknown_row"}:
            continue
        # hand audit / not scorable: still have turns for observation; skip rate buckets
        if entry.get("excluded") in {"hand audit", "not scorable"}:
            continue
        turns = entry.get("turns") or []
        if not turns:
            continue
        rid = entry["row"]
        bucket = buckets.get(rid, "mechanical")
        row_ok = all(t.get("match") for t in turns)
        by_bucket_row.setdefault(bucket, [0, 0])
        by_bucket_row[bucket][1] += 1
        by_bucket_row[bucket][0] += int(row_ok)
        overall_row[1] += 1
        overall_row[0] += int(row_ok)
        # primary class = first turn's expected class
        primary = turns[0].get("key_class_expected") or "?"
        by_class_row.setdefault(primary, [0, 0])
        by_class_row[primary][1] += 1
        by_class_row[primary][0] += int(row_ok)

        for t in turns:
            ok = int(bool(t.get("match")))
            by_bucket_turn.setdefault(bucket, [0, 0])
            by_bucket_turn[bucket][1] += 1
            by_bucket_turn[bucket][0] += ok
            klass = t.get("key_class_expected") or "?"
            by_class_turn.setdefault(klass, [0, 0])
            by_class_turn[klass][1] += 1
            by_class_turn[klass][0] += ok
            overall_turn[1] += 1
            overall_turn[0] += ok

    out: list[dict[str, Any]] = []
    for level, bucket_store, class_store, overall in (
        ("turn", by_bucket_turn, by_class_turn, overall_turn),
        ("row", by_bucket_row, by_class_row, overall_row),
    ):
        for label, (p, n) in sorted(bucket_store.items()):
            out.append({**_interval_row(f"bucket:{label}", p, n), "level": level, "group": "bucket"})
        for label, (p, n) in sorted(class_store.items()):
            out.append({**_interval_row(f"class:{label}", p, n), "level": level, "group": "class"})
        out.append(
            {
                **_interval_row("overall", overall[0], overall[1]),
                "level": level,
                "group": "overall",
                "note": "descriptive only; ADR-078 never pools classes for a gate",
            }
        )
    return out


def from_audit_csv(path: Path) -> list[dict[str, Any]]:
    """CI on audit CSV: pass among non-empty pass/fail verdicts (skips not_applicable / blank)."""
    buckets = _discovery_buckets()
    # point-level
    by_bucket_pt: dict[str, list[int]] = {}
    overall_pt = [0, 0]
    # section-level (row_id + turn): overall column pass/fail
    sections: dict[tuple[str, str], str] = {}
    with path.open(encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rid = (row.get("row_id") or "").strip()
            turn = (row.get("turn") or "").strip()
            verdict = (row.get("verdict") or "").strip().lower()
            overall = (row.get("overall") or "").strip().lower()
            if rid and turn and overall in {"pass", "fail"}:
                sections[(rid, turn)] = overall
            if verdict not in {"pass", "fail"}:
                continue
            bucket = buckets.get(rid, "hand audit")
            by_bucket_pt.setdefault(bucket, [0, 0])
            by_bucket_pt[bucket][1] += 1
            by_bucket_pt[bucket][0] += int(verdict == "pass")
            overall_pt[1] += 1
            overall_pt[0] += int(verdict == "pass")

    by_bucket_sec: dict[str, list[int]] = {}
    overall_sec = [0, 0]
    for (rid, _turn), ov in sections.items():
        bucket = buckets.get(rid, "hand audit")
        by_bucket_sec.setdefault(bucket, [0, 0])
        by_bucket_sec[bucket][1] += 1
        by_bucket_sec[bucket][0] += int(ov == "pass")
        overall_sec[1] += 1
        overall_sec[0] += int(ov == "pass")

    out: list[dict[str, Any]] = []
    for level, store, overall in (
        ("rubric_point", by_bucket_pt, overall_pt),
        ("section", by_bucket_sec, overall_sec),
    ):
        for label, (p, n) in sorted(store.items()):
            out.append({**_interval_row(f"bucket:{label}", p, n), "level": level, "group": "bucket"})
        out.append(
            {
                **_interval_row("overall", overall[0], overall[1]),
                "level": level,
                "group": "overall",
                "note": "descriptive only; ADR-078 never pools for a gate",
            }
        )
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scorer", type=Path, help="class_scorer JSON output")
    ap.add_argument("--audit-csv", type=Path, help="hand_audit_export.csv")
    ap.add_argument("--json", action="store_true", help="print JSON instead of a table")
    args = ap.parse_args(argv)
    if not args.scorer and not args.audit_csv:
        ap.error("provide --scorer and/or --audit-csv")

    rows: list[dict[str, Any]] = []
    if args.scorer:
        rows.extend(from_scorer(json.loads(args.scorer.read_text(encoding="utf-8"))))
    if args.audit_csv:
        rows.extend(from_audit_csv(args.audit_csv))

    if args.json:
        print(json.dumps(rows, indent=2))
        return 0

    print(f"{'level':<14} {'group':<10} {'label':<28} {'pass/n':>10} {'rate':>8} {'95% CI':>22}")
    for r in rows:
        ci = f"[{r['ci95_lo']:.4f}, {r['ci95_hi']:.4f}]" if r["n"] else "[nan, nan]"
        rate = f"{r['rate']:.4f}" if r["n"] else "nan"
        print(
            f"{r['level']:<14} {r['group']:<10} {r['label']:<28} "
            f"{r['passes']}/{r['n']:>4} {rate:>8} {ci:>22}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
