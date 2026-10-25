#!/usr/bin/env python3
"""Audit-adjusted false bound (ADR-060: no recommender imports). Runs only once the exception log is committed and hashed.

Inputs: the scorer's JSON output (it has a "gate" block only when the log was committed and hashed), the exception log CSV, the canary list, and the
answers and battery the scorer ran on (the claims are re-extracted to match rows to them). Canary-matched rows (audit_canary_check.match) are removed first.
Notes are read case-insensitively after stripping whitespace.
  missed_claim:    note "FALSE:" or "TRUE:" = the audit's verdict on a claim the extractor missed. False += FALSE rows; n += FALSE and TRUE rows.
  wrong_verdict / wrong_extraction: note "NOW FALSE:" or "NOW TRUE:" = the correct verdict of the claim, matched to a scored gated claim by item_id and
                   claim_text (the row text contains the claim's answer span as whole tokens). Scorer TRUE now FALSE adds one false; scorer FALSE now TRUE
                   removes one; n is unchanged.
                   A row that matches only claims that cannot move the gate (usage percentages, ability_plural, chance_nhko, hedges, ...) is listed
                   as "non-gating, not scored"; a row matching no claim at all, or more than one gated claim, is refused.
  other:           listed, never scored.
It fails closed: an unprefixed note, an unmatched or ambiguous wrong_* row, or a scorer-gate count that the re-extraction does not reproduce gives no
verdict, only the list of offending rows. The adjusted bound is the scorer's one-sided 95% Clopper-Pearson upper bound, printed beside the scorer-only numbers.

    python scripts/eval/part_g_v4/audit_adjusted.py --scorer-output OUT.json --exceptions LOG.csv --exception-log-sha256 HEX --canaries LIST.json \
        --answers A.jsonl --battery B.json [--half P|T|ALL --split-file S.json] [--repo DIR]
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


GATED = {"gate", "ko_chance"}  # the scorer's default gate unit
PREFIX = {"missed_claim": ("FALSE:", "TRUE:"), "wrong_verdict": ("NOW FALSE:", "NOW TRUE:"), "wrong_extraction": ("NOW FALSE:", "NOW TRUE:")}


def _note(r: dict) -> str:
    return " ".join((r.get("note") or "").split()).upper()


def adjust(gate: dict, rows: list[dict], canaries: list[dict], claims: dict[str, list[tuple[str, scorer.Verdict | None, bool]]]) -> dict:
    """claims: item_id -> [(answer span text, scorer verdict, gated)] of every extracted claim; gated = scored on the gate unit. Returns a verdict dict, or {"refused": [...]} with the rows."""
    exc = [r for r in rows if r["exception_type"]]
    _, used = chk.match(canaries, exc)
    live = [r for i, r in enumerate(exc) if i not in used]
    refused, other, nongating = [], [r for r in live if r["exception_type"] == "other"], []
    mf = mt = 0
    flips: dict[tuple[str, int], str] = {}  # (item, claim index) -> the audit's verdict
    for r in live:
        t, n = r["exception_type"], _note(r)
        if t == "other":
            continue
        if t not in PREFIX:
            refused.append({"row": r, "why": f"unknown exception_type {t!r}"})
        elif not n.startswith(PREFIX[t]):
            refused.append({"row": r, "why": f"note must start {' or '.join(map(repr, PREFIX[t]))}"})
        elif t == "missed_claim":
            mf, mt = mf + n.startswith("FALSE:"), mt + n.startswith("TRUE:")
        else:
            hit = [(i, g) for i, (span, _, g) in enumerate(claims.get(r["item_id"], [])) if chk.contains_target(r["claim_text"], span)]
            cand = [i for i, g in hit if g and (r["item_id"], i) not in flips]
            if not hit:
                refused.append({"row": r, "why": "no claim matches item_id and claim_text"})
            elif not any(g for _, g in hit):
                nongating.append(r)  # only claims outside the gate unit match: it cannot move the gate
            elif len(cand) != 1:
                refused.append({"row": r, "why": f"{len(cand)} unused scored gated claims match item_id and claim_text (need exactly 1)"})
            else:
                flips[(r["item_id"], cand[0])] = n.removeprefix("NOW ").split(":")[0]  # "FALSE" or "TRUE"
    if refused:
        return {"refused": refused}
    to_false = sum(v == "FALSE" and claims[i][k][1] == scorer.Verdict.TRUE for (i, k), v in flips.items())
    to_true = sum(v == "TRUE" and claims[i][k][1] == scorer.Verdict.FALSE for (i, k), v in flips.items())
    false, scored = gate["false"] + mf + to_false - to_true, gate["scored"] + mf + mt
    ub = scorer.cp_upper(false, scored)
    return {"scorer_only": {k: gate[k] for k in ("false", "scored", "cp_upper_bound", "max_false_tolerated_at_n", "passes_gate")},
            "adjusted": {"false": false, "scored": scored, "cp_upper_bound": ub, "max_false_tolerated_at_n": scorer.max_false_tolerated(scored), "passes_gate": scored > 0 and ub <= scorer.GATE_RATE},
            "missed_noted_false": mf, "missed_noted_true": mt, "wrong_rows_matched": len(flips), "scorer_true_now_false": to_false, "scorer_false_now_true": to_true,
            "canary_rows_excluded": len(used), "other_rows_listed_not_scored": other, "non_gating_rows_not_scored": nongating}


def scored_claims(answers: Path, battery: Path, half: str | None, split_file: Path | None) -> dict[str, list[tuple[str, scorer.Verdict]]]:
    import extractors  # the same extractors the scorer ran; imported late, they are frozen with this script
    items = {i["id"]: i for i in json.loads(battery.read_text())["items"] if i.get("gated", True)}
    if half:
        split = json.loads(split_file.read_text())
        keep = {i for h in (("P", "T") if half == "ALL" else (half,)) for v in split[h].values() for i in v}
        items = {k: v for k, v in items.items() if k in keep}
    out = {}
    for r in map(json.loads, answers.read_text().splitlines()):
        if r["id"] in items:
            out[r["id"]] = [(r["final_text"][c.span[0]:c.span[1]] if c.span else "", c.verdict, c.line in GATED and c.verdict in (scorer.Verdict.TRUE, scorer.Verdict.FALSE))
                            for c in extractors.extract_item(items[r["id"]], r)]
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scorer-output", type=Path, required=True)
    ap.add_argument("--exceptions", type=Path, required=True)
    ap.add_argument("--exception-log-sha256", required=True)
    ap.add_argument("--canaries", type=Path, required=True)
    ap.add_argument("--answers", type=Path, required=True)
    ap.add_argument("--battery", type=Path, required=True)
    ap.add_argument("--half", choices=("P", "T", "ALL"), default=None)
    ap.add_argument("--split-file", type=Path, default=None)
    ap.add_argument("--repo", type=Path, default=None)
    args = ap.parse_args()
    ok, why = scorer.exception_log_verified(args.exceptions, args.exception_log_sha256, args.repo)
    if not ok:
        raise SystemExit(f"refused: the exception log is not committed and hashed ({why})")
    gate = json.loads(args.scorer_output.read_text()).get("gate")
    if not gate:
        raise SystemExit("refused: the scorer output has no gate block (run the scorer with the committed, hashed exception log)")
    claims = scored_claims(args.answers, args.battery, args.half, args.split_file)
    got = [v for cs in claims.values() for _, v, g in cs if g]
    if (got.count(scorer.Verdict.FALSE), len(got)) != (gate["false"], gate["scored"]):
        raise SystemExit(f"refused: re-extraction gives {got.count(scorer.Verdict.FALSE)} false of {len(got)} scored, the scorer output {gate['false']} of {gate['scored']}")
    rows = list(csv.DictReader(args.exceptions.open(newline="")))
    res = adjust(gate, rows, json.loads(args.canaries.read_text())["canaries"], claims)
    print(json.dumps(res, indent=1))
    return 1 if "refused" in res else 0


if __name__ == "__main__":
    raise SystemExit(main())
