#!/usr/bin/env python3
"""Canary detection after the audit (ADR-060: no recommender imports). Runs only once the exception log is committed and hashed.

A canary counts as detected when an exception row on its item_id has a claim_text that overlaps the canary's target (the answer span, the displayed
claim, or the altered displayed claim; overlap = one normalised string contains the other), and as type-matched when that row's exception_type is the
canary's type. Each canary matches at most one row (a type-matched row is preferred); matched rows are removed from the real exception counts and every
other exception row is real. Prints counts, rates and the one-sided 95% Clopper-Pearson lower bounds; it never prints the canary list.

    python scripts/eval/part_g_v4/audit_canary_check.py --canaries LIST.json --exceptions LOG.csv --exception-log-sha256 HEX [--repo DIR]
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scorer  # noqa: E402

ALPHA = 0.05


def cp_lower(k: int, n: int, alpha: float = ALPHA) -> float:
    """One-sided (1-alpha) Clopper-Pearson lower bound: the p where P(X >= k) = alpha (0 when k = 0)."""
    if k <= 0 or n <= 0:
        return 0.0
    lo, hi = 0.0, k / n
    for _ in range(100):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if 1 - scorer._binom_cdf(k - 1, n, mid) < alpha else (lo, mid)
    return lo


def _norm(t: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", str(t).lower()).split())


def _overlaps(claim_text: str, texts: list[str]) -> bool:
    a = _norm(claim_text)
    return bool(a) and any(b and (a in b or b in a) for b in map(_norm, texts))


def match(canaries: list[dict], rows: list[dict]) -> tuple[list[tuple[int, int, bool]], set[int]]:
    """-> ([(canary index, row index, type_matched)], matched row indexes). Exception rows only: a row needs an exception_type."""
    used: set[int] = set()
    out = []
    for ci, c in enumerate(canaries):
        texts = [c["target_claim_text"], c["displayed_claim"].split(" | ", 1)[-1]] + [c.get(k, "").split(" | ", 1)[-1] for k in ("altered_claim", "partner_claim") if c.get(k)]
        cand = [ri for ri, r in enumerate(rows) if ri not in used and r["item_id"] == c["item_id"] and r["exception_type"] and _overlaps(r["claim_text"], texts)]
        if cand:
            cand.sort(key=lambda ri: rows[ri]["exception_type"] != c["canary_type"])
            used.add(cand[0])
            out.append((ci, cand[0], rows[cand[0]]["exception_type"] == c["canary_type"]))
    return out, used


def check(canaries: list[dict], rows: list[dict]) -> dict:
    exc = [r for r in rows if r["exception_type"]]
    matched, used = match(canaries, exc)
    n, det, typ = len(canaries), len(matched), sum(1 for *_, t in matched if t)
    by_type = {}
    for ctype in sorted({c["canary_type"] for c in canaries}):
        idx = {ci for ci, c in enumerate(canaries) if c["canary_type"] == ctype}
        by_type[ctype] = {"canaries": len(idx), "detected": sum(1 for ci, _, _ in matched if ci in idx), "type_matched": sum(1 for ci, _, t in matched if ci in idx and t)}
    return {"canaries": n, "detected": det, "type_matched": typ, "detected_rate": det / n if n else None, "type_matched_rate": typ / n if n else None,
            "detected_lower_bound_95": cp_lower(det, n), "type_matched_lower_bound_95": cp_lower(typ, n), "by_type": by_type,
            "real_exceptions_after_removal": len(exc) - len(used), "real_exceptions_by_type": dict(sorted(Counter(r["exception_type"] for i, r in enumerate(exc) if i not in used).items())),
            "canary_rows_removed": len(used)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--canaries", type=Path, required=True)
    ap.add_argument("--exceptions", type=Path, required=True)
    ap.add_argument("--exception-log-sha256", required=True)
    ap.add_argument("--repo", type=Path, default=None)
    args = ap.parse_args()
    ok, why = scorer.exception_log_verified(args.exceptions, args.exception_log_sha256, args.repo)
    if not ok:
        raise SystemExit(f"refused: the exception log is not committed and hashed ({why})")
    canaries = json.loads(args.canaries.read_text())["canaries"]
    rows = list(csv.DictReader(args.exceptions.open(newline="")))
    print(json.dumps(check(canaries, rows), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
