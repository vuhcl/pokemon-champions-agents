"""B4 — per-class request-set scorer (ADR-078: never pooled).

Reads the request set and derived_keys.json read-only, plus state/errata.json.
Scores mechanical class + state expectation only. Does not invent claim rules.
Hand-audit / not-scorable rows are excluded.
stale_pin_rows may be empty (2026-10-28: MT2/H6 cleared — not content-stale at current pins).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from scripts.eval.part_g_arm.state.errata_read import expected_turns, load_errata, stale_pin_rows
from scripts.eval.part_g_arm.state.request_set_rows import load_covered_ids, load_request_rows

HERE = Path(__file__).resolve().parent
DISCOVERY = HERE / "b1_discovery.json"

# Request-set class atom → allowed mechanical_class values (state-only).
_CLASS_TO_MECH: dict[str, set[str]] = {
    # recorded = reject_option / reject_all (MS7, OL8); dismissed alone is not MUTATION-OK.
    "MUTATION-OK": {"wrote", "bound", "recorded"},
    "MUTATION-REFUSED": {"refused", "no change", "lookup only"},
    "NO-MUTATION": {"lookup only", "no change"},
    "FAIL-CLOSED": {"refused", "no change", "lookup only"},
    "ASK": {"no change", "lookup only", "dismissed"},
    "SERVED": {"lookup only", "no change"},
    "ASSUME-STATE": {"lookup only", "no change"},
    "PARTIAL": {"lookup only", "no change"},
    "PARTIAL+ASSUME-STATE": {"lookup only", "no change"},
    "ASK|ASSUME-STATE": {"no change", "lookup only"},
}


def _discovery_bucket(row_id: str) -> str:
    doc = json.loads(DISCOVERY.read_text(encoding="utf-8"))
    for row in doc["covered"]:
        if row["row"] == row_id:
            return row["bucket"]
    return "not scorable"


def _state_unchanged(turn: dict[str, Any]) -> bool:
    before = turn.get("state_before") or {}
    after = turn.get("state_after") or {}
    return before.get("slots") == after.get("slots") and before.get("steering") == after.get("steering")


def score_turn(
    *,
    observed_mech: str,
    expected_key_class: str,
    turn: dict[str, Any],
) -> dict[str, Any]:
    allowed = _CLASS_TO_MECH.get(expected_key_class, set())
    match = observed_mech in allowed if allowed else False
    # State expectation: mutation classes may change; others must not write draft.
    if expected_key_class in {"MUTATION-OK"}:
        state_ok = observed_mech in {"wrote", "bound", "recorded"}
    elif expected_key_class in {"MUTATION-REFUSED", "NO-MUTATION", "FAIL-CLOSED", "ASK",
                                 "SERVED", "ASSUME-STATE", "PARTIAL", "PARTIAL+ASSUME-STATE",
                                 "ASK|ASSUME-STATE"}:
        state_ok = _state_unchanged(turn) or observed_mech in {
            "refused", "lookup only", "no change", "dismissed"
        }
        if expected_key_class != "MUTATION-OK" and (turn.get("state_before") or {}).get("slots") != (
            turn.get("state_after") or {}
        ).get("slots"):
            state_ok = False
    else:
        state_ok = False
    return {
        "mechanical_class_observed": observed_mech,
        "key_class_expected": expected_key_class,
        "match": match,
        "state_expectation_met": state_ok,
    }


def score_transcript(
    transcript: list[dict[str, Any]],
    *,
    rows_by_id: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Score a list of {id, turns:[{mechanical_class, state_before, state_after, ...}]}."""
    rows_by_id = rows_by_id or {r["id"]: r for r in load_request_rows()}
    covered = load_covered_ids()
    stale = stale_pin_rows()
    per_row: list[dict[str, Any]] = []
    by_class: dict[str, dict[str, int]] = {}

    for entry in transcript:
        rid = entry["id"]
        row = rows_by_id.get(rid)
        if row is None:
            per_row.append({"row": rid, "excluded": "unknown_row"})
            continue
        if rid in stale:
            per_row.append({"row": rid, "excluded": "stale_pin", "stale": True})
            continue
        bucket = _discovery_bucket(rid)
        if bucket in {"hand audit", "not scorable"} and rid in covered:
            # Still emit mechanical observation vs key class for audit, but mark excluded from rates.
            excluded = bucket
        elif rid not in covered:
            per_row.append({"row": rid, "excluded": "not_covered"})
            continue
        else:
            excluded = None

        turns_expected = expected_turns(rid, row["class"])
        turns_obs = entry.get("turns") or []
        turn_scores = []
        for i, turn in enumerate(turns_obs):
            exp = turns_expected[i] if i < len(turns_expected) else turns_expected[-1]
            observed = turn.get("mechanical_class") or "no change"
            sc = score_turn(observed_mech=observed, expected_key_class=exp, turn=turn)
            turn_scores.append(sc)
            if excluded is None:
                bucket_c = by_class.setdefault(exp, {"n": 0, "match": 0, "state_ok": 0})
                bucket_c["n"] += 1
                bucket_c["match"] += int(sc["match"])
                bucket_c["state_ok"] += int(sc["state_expectation_met"])

        per_row.append(
            {
                "row": rid,
                "excluded": excluded,
                "turns": turn_scores,
            }
        )

    return {
        "per_row": per_row,
        "per_class": by_class,
        "errata": load_errata().get("source"),
        "note": "ADR-078: rates are per class, never pooled",
    }


def score_dev_transcript(path: Path) -> dict[str, Any]:
    """Score a harness-style dev transcript (list of {id, turns, pass})."""
    data = json.loads(path.read_text(encoding="utf-8"))
    # Dev rows are not request-set rows; map via synthetic expected classes from mechanical only.
    # For B4 acceptance: run scorer on synthetic transcripts + report observed classes on dev.
    synthetic = []
    for row in data:
        synthetic.append({"id": row["id"], "turns": row["turns"]})
    # Use a fake rows_by_id so unknown_row isn't hit — treat each as excluded hand audit
    # unless we inject class from errata. Dev report path:
    return {
        "dev_observed": [
            {
                "row": r["id"],
                "classes": [t.get("mechanical_class") for t in r.get("turns") or []],
                "pass": r.get("pass"),
            }
            for r in data
        ],
        "note": "dev rows are not request-set keys; observed mechanical classes only",
    }
