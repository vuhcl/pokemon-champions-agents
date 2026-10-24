#!/usr/bin/env python3
"""Audit-adjusted false bound (ADR-060: no recommender imports). Runs only once the exception log is committed and hashed.

Inputs: the scorer's JSON output (it has a "gate" block only when the log was committed and hashed), the exception log CSV and the canary list.
A missed_claim row whose note begins "FALSE" is a claim the extractor missed that the audit judged false; "TRUE" one it judged true. Rows matched to a
canary (audit_canary_check.match) are removed first. Then:
    adjusted false = scorer false + missed_claim rows noted FALSE
    adjusted n     = scorer scored claims + missed_claim rows noted FALSE or TRUE
The adjusted bound is the same one-sided 95% Clopper-Pearson upper bound as the scorer's; it is printed beside the scorer-only numbers. missed_claim rows with
neither prefix are counted and flagged, not scored.

    python scripts/eval/part_g_v4/audit_adjusted.py --scorer-output OUT.json --exceptions LOG.csv --exception-log-sha256 HEX --canaries LIST.json [--repo DIR]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import audit_canary_check as chk  # noqa: E402
import scorer  # noqa: E402


def adjust(gate: dict, rows: list[dict], canaries: list[dict]) -> dict:
    exc = [r for r in rows if r["exception_type"]]
    _, used = chk.match(canaries, exc)
    missed = [r for i, r in enumerate(exc) if i not in used and r["exception_type"] == "missed_claim"]
    note = lambda r: (r.get("note") or "").lstrip()  # noqa: E731
    mf = sum(note(r).startswith("FALSE") for r in missed)
    mt = sum(note(r).startswith("TRUE") for r in missed)
    false, scored = gate["false"] + mf, gate["scored"] + mf + mt
    return {"scorer_only": {"false": gate["false"], "scored": gate["scored"], "cp_upper_bound": gate["cp_upper_bound"], "max_false_tolerated_at_n": gate["max_false_tolerated_at_n"],
                            "passes_gate": gate["passes_gate"]},
            "adjusted": {"false": false, "scored": scored, "cp_upper_bound": scorer.cp_upper(false, scored), "max_false_tolerated_at_n": scorer.max_false_tolerated(scored),
                         "passes_gate": scored > 0 and scorer.cp_upper(false, scored) <= scorer.GATE_RATE},
            "missed_claim_rows_after_canary_removal": len(missed), "missed_noted_false": mf, "missed_noted_true": mt, "missed_unprefixed_not_scored": len(missed) - mf - mt,
            "canary_rows_excluded": len(used)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scorer-output", type=Path, required=True)
    ap.add_argument("--exceptions", type=Path, required=True)
    ap.add_argument("--exception-log-sha256", required=True)
    ap.add_argument("--canaries", type=Path, required=True)
    ap.add_argument("--repo", type=Path, default=None)
    args = ap.parse_args()
    ok, why = scorer.exception_log_verified(args.exceptions, args.exception_log_sha256, args.repo)
    if not ok:
        raise SystemExit(f"refused: the exception log is not committed and hashed ({why})")
    gate = json.loads(args.scorer_output.read_text()).get("gate")
    if not gate:
        raise SystemExit("refused: the scorer output has no gate block (run the scorer with the committed, hashed exception log)")
    rows = list(csv.DictReader(args.exceptions.open(newline="")))
    print(json.dumps(adjust(gate, rows, json.loads(args.canaries.read_text())["canaries"]), indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
