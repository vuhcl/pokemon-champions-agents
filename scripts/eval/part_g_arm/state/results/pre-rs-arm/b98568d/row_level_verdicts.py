#!/usr/bin/env python3
"""Row-level PRE-RS-ARM verdicts from hand_audit_export_1.csv + class_scorer.json.

NOT in FROZEN_MANIFEST_ARM_STATE. Written after the registered runs.

Row verdict = pass iff every section with overall pass/fail has overall pass;
sections with overall not_applicable are excluded; a row with no pass/fail
section has no verdict.

Mechanical rows use class_scorer per_row (all turns match + state_expectation_met).
Dual rows contribute separately to dual hand-part and dual class-part buckets.
SC2 and TB2: counted not passed when included in the combined 103.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
WT = Path("/Users/nowaki027/part-g-arm-state-run-b98568d")
sys.path.insert(0, str(WT))
from scripts.eval.part_g_arm.state.clopper_pearson import clopper_pearson_two_sided  # noqa: E402
DISCOVERY = WT / "scripts/eval/part_g_arm/state/b1_discovery.json"
COVERED = WT / "scripts/eval/part_g_arm/state/covered_list.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def row_verdict_from_section_overalls(overalls: list[str]) -> str | None:
    pf = [o for o in overalls if o in ("pass", "fail")]
    if not pf:
        return None
    return "pass" if all(o == "pass" for o in pf) else "fail"


def main() -> int:
    audit_csv = HERE / "run_1_hand_audit" / "hand_audit_export_1.csv"
    scorer_path = HERE / "run_1" / "class_scorer.json"
    out_path = HERE / "row_level_verdicts.json"

    buckets = {
        r["row"]: r["bucket"]
        for r in json.loads(DISCOVERY.read_text())["covered"]
    }
    covered = list(json.loads(COVERED.read_text())["covered"])

    rows = list(csv.DictReader(audit_csv.open()))
    sec: dict[tuple[str, int], str] = {}
    for r in rows:
        sec[(r["row_id"], int(r["turn"]))] = (r.get("overall") or "").strip()

    by_row: dict[str, list[str]] = defaultdict(list)
    for (rid, _turn), ov in sec.items():
        by_row[rid].append(ov)

    hand_verdict = {
        rid: row_verdict_from_section_overalls(ovs) for rid, ovs in by_row.items()
    }

    scorer = json.loads(scorer_path.read_text())
    class_pass: dict[str, bool | None] = {}
    for e in scorer.get("per_row") or []:
        rid = e["row"]
        turns = e.get("turns") or []
        if e.get("excluded") in {"stale_pin", "not_covered", "unknown_row", "hand audit"}:
            # Dual rows are not excluded as hand audit in this scorer output.
            if buckets.get(rid) != "mechanical + hand audit":
                continue
        if not turns:
            class_pass[rid] = False  # no scored turns → not passed
            continue
        class_pass[rid] = all(
            bool(t.get("match") and t.get("state_expectation_met")) for t in turns
        )

    hand_only_ids = [r for r in covered if buckets.get(r) == "hand audit"]
    mech_only_ids = [r for r in covered if buckets.get(r) == "scorable-mechanical"]
    dual_ids = [r for r in covered if buckets.get(r) == "mechanical + hand audit"]

    def count_pass(ids: list[str], verdicts: dict[str, Any]) -> tuple[int, int, list[str]]:
        """Return (passes, n_with_verdict_or_false, missing_list)."""
        passes = 0
        n = 0
        missing = []
        for rid in ids:
            v = verdicts.get(rid)
            if v is None and rid not in verdicts:
                missing.append(rid)
                # treat absent audited/scored row as not passed when counting combined
                n += 1
                continue
            if v is None:
                missing.append(rid)
                n += 1
                continue
            n += 1
            if v is True or v == "pass":
                passes += 1
        return passes, n, missing

    # Hand-only: only rows present in the audit CSV (58)
    hand_audited = [r for r in hand_only_ids if r in hand_verdict]
    hand_pass = sum(1 for r in hand_audited if hand_verdict[r] == "pass")
    hand_fail = sum(1 for r in hand_audited if hand_verdict[r] == "fail")

    mech_pass = sum(1 for r in mech_only_ids if class_pass.get(r) is True)
    mech_n = len(mech_only_ids)

    dual_hand_ids = [r for r in dual_ids if r in hand_verdict]
    dual_hand_pass = sum(1 for r in dual_hand_ids if hand_verdict[r] == "pass")
    # Dual class part: only rows with ≥1 scored turn (TB2 load_fail → empty turns, excluded from denom).
    dual_class_ids = [
        rid
        for rid in dual_ids
        if any(
            e["row"] == rid and (e.get("turns") or [])
            for e in (scorer.get("per_row") or [])
        )
    ]
    for rid in dual_ids:
        if rid not in class_pass:
            class_pass[rid] = False
    dual_class_pass = sum(1 for r in dual_class_ids if class_pass.get(r) is True)

    # Combined 103: row passes if
    # - hand audit only: hand pass
    # - mechanical only: class pass
    # - dual: BOTH hand pass (if audited) AND class pass; if no hand audit section, hand part absent → fail hand side
    combined_pass = []
    combined_fail = []
    for rid in covered:
        b = buckets.get(rid)
        if b == "hand audit":
            v = hand_verdict.get(rid)
            ok = v == "pass"
        elif b == "scorable-mechanical":
            ok = class_pass.get(rid) is True
        elif b == "mechanical + hand audit":
            hv = hand_verdict.get(rid)
            cv = class_pass.get(rid) is True
            ok = (hv == "pass") and cv
        else:
            ok = False
        (combined_pass if ok else combined_fail).append(rid)

    # Without SC2 and TB2
    without = [r for r in covered if r not in {"SC2", "TB2"}]
    pass_without = [r for r in combined_pass if r not in {"SC2", "TB2"}]
    fail_without = [r for r in without if r not in pass_without]

    def ci(passes: int, n: int) -> dict[str, Any]:
        lo, hi = clopper_pearson_two_sided(passes, n)
        return {
            "passes": passes,
            "n": n,
            "rate": (passes / n) if n else None,
            "ci95_lo": lo,
            "ci95_hi": hi,
        }

    out = {
        "audit_csv": str(audit_csv),
        "audit_csv_sha256": _sha(audit_csv),
        "class_scorer_sha256": _sha(scorer_path),
        "script": str(Path(__file__).resolve()),
        "rule": (
            "row pass iff every section overall in {pass,fail} is pass; "
            "not_applicable excluded; no pass/fail section → no verdict. "
            "Mechanical: all scorer turns match+state_expectation_met. "
            "Dual: hand pass AND class pass. SC2/TB2 counted not passed in combined 103."
        ),
        "hand_only": {
            **ci(hand_pass, len(hand_audited)),
            "fail": hand_fail,
            "audited_rows": len(hand_audited),
            "covered_hand_audit_bucket": len(hand_only_ids),
            "not_in_export": sorted(set(hand_only_ids) - set(hand_audited)),
        },
        "mechanical_only": ci(mech_pass, mech_n),
        "dual_hand_part": {
            **ci(dual_hand_pass, len(dual_hand_ids)),
            "rows": dual_hand_ids,
            "verdicts": {r: hand_verdict.get(r) for r in dual_hand_ids},
            "note": "TB2 not in export (load_fail)",
        },
        "dual_class_part": {
            **ci(dual_class_pass, len(dual_class_ids)),
            "rows": dual_class_ids,
            "verdicts": {r: class_pass.get(r) for r in dual_class_ids},
            "excluded_no_scored_turns": sorted(set(dual_ids) - set(dual_class_ids)),
        },
        "combined_103": {
            **ci(len(combined_pass), len(covered)),
            "pass_ids": combined_pass,
            "sc2_tb2_passed": {
                "SC2": "SC2" in combined_pass,
                "TB2": "TB2" in combined_pass,
            },
        },
        "combined_without_sc2_tb2": ci(len(pass_without), len(without)),
        "per_row": {
            rid: {
                "bucket": buckets.get(rid),
                "hand_verdict": hand_verdict.get(rid),
                "class_pass": class_pass.get(rid),
                "combined_pass": rid in combined_pass,
            }
            for rid in covered
        },
    }
    blob = json.dumps(out, indent=2, sort_keys=True) + "\n"
    out_path.write_text(blob)
    out["output_sha256"] = hashlib.sha256(blob.encode()).hexdigest()
    out_path.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n")

    print(
        f"hand-only {hand_pass}/{len(hand_audited)} "
        f"(fail {hand_fail}); mechanical {mech_pass}/{mech_n}; "
        f"dual hand {dual_hand_pass}/{len(dual_hand_ids)}; "
        f"dual class {dual_class_pass}/{len(dual_class_ids)}; "
        f"combined {len(combined_pass)}/{len(covered)}; "
        f"without SC2/TB2 {len(pass_without)}/{len(without)}"
    )
    print("wrote", out_path)
    print("script_sha256", _sha(Path(__file__)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
