#!/usr/bin/env python3
"""Gate 0: label CAP25 pending_response messages; Vu reviews buckets."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO))

from recommender.nodes_classify import (  # noqa: E402
    CONTINUE_ABANDON_MSG,
    KEEP_BUILD_MSG,
    _MISMATCH_MSG,
)
from recommender.system_claims import NON_CLAIM_MESSAGES  # noqa: E402
from recommender.turn_intent import CLASSIFY_FAIL_USER_MSG  # noqa: E402

SNAP = REPO / "scripts/eval/artifacts/det_graph_capability_baseline_88df2d7"
RUNS = SNAP / "runs"
OUT = Path(__file__).resolve().parent

CAP25 = (
    [f"S{i}" for i in range(1, 10)]
    + ["i1", "i2", "i3", "i4", "i5L", "i6L", "i7", "i8L"]
    + [f"C{i}" for i in range(1, 5)]
    + ["D1", "P1", "P2", "P3"]
)
MODELS = ("qwen2.5_7b", "qwen3.5_latest")

CANNED = set(NON_CLAIM_MESSAGES) | {
    _MISMATCH_MSG,
    CONTINUE_ABANDON_MSG,
    KEEP_BUILD_MSG,
    CLASSIFY_FAIL_USER_MSG,
}

SAMPLING_CAVEAT_NO_MIDFLOW = (
    "All llm_authored rows in this corpus have pending_presentation kind "
    "None (idle) at message time. There is no mid-flow evidence in this "
    "corpus. Mid-flow assurance rests entirely on the passthrough-test "
    "inventory, the per-kind template table, and hostile tests over idle "
    "plus every PendingPresentation.kind."
)

# (request_id, model) -> (bucket, row-specific reason without outcome suffix)
# Buckets: echo_soft_refuse | unactionable_offer | defect_prose | unique_UX
BUCKET_MAP: dict[tuple[str, str], tuple[str, str]] = {
    ("S4", "qwen2.5_7b"): (
        "unactionable_offer",
        "Asks which locked pick to swap for a Kingambit threat; unmatched path "
        "does not execute a swap or bind to candidate_selection.",
    ),
    ("S6", "qwen2.5_7b"): (
        "echo_soft_refuse",
        "Echoes the Farigiraf-vs-Hatterene comparison as a bare question.",
    ),
    ("S8", "qwen2.5_7b"): (
        "echo_soft_refuse",
        "Echoes the 'best criteria for evaluating a team' ask without a "
        "team-review action.",
    ),
    ("i7", "qwen2.5_7b"): (
        "echo_soft_refuse",
        "Echoes the Torkoal+Scovillain pairing question.",
    ),
    ("i8L", "qwen2.5_7b"): (
        "echo_soft_refuse",
        "Echoes the Hatterene support question.",
    ),
    ("C2", "qwen2.5_7b"): (
        "echo_soft_refuse",
        "Echoes Jolly-vs-Adamant outspeed question; no calc on unmatched.",
    ),
    ("C3", "qwen2.5_7b"): (
        "echo_soft_refuse",
        "Echoes max-Attack Kingambit OHKO question; no calc on unmatched.",
    ),
    ("S2", "qwen3.5_latest"): (
        "unactionable_offer",
        "Offers to find a bulky Fire-type for slot 4 and asks roster status; "
        "idle unmatched cannot open candidate discovery for that ask.",
    ),
    ("S4", "qwen3.5_latest"): (
        "unactionable_offer",
        "Claims no roster visibility and asks which slot to swap; idle "
        "unmatched does not open a swap/candidate screen.",
    ),
    ("S7", "qwen3.5_latest"): (
        "defect_prose",
        "Asserts no restriction on duplicate Choice Scarf / Item Clause — "
        "false for Reg M-C (logged defect).",
    ),
    ("S8", "qwen3.5_latest"): (
        "unactionable_offer",
        "Offers to find strong Reg M-C teams/archetypes; idle unmatched "
        "cannot run team search or archetype browse.",
    ),
    ("i6L", "qwen3.5_latest"): (
        "unactionable_offer",
        "Offers to place Garchomp+Scarf in a slot with build details; idle "
        "unmatched does not lock that set.",
    ),
    ("i7", "qwen3.5_latest"): (
        "echo_soft_refuse",
        "Soft pairing help restating Torkoal/Scovillain ask.",
    ),
    ("C1", "qwen3.5_latest"): (
        "unactionable_offer",
        "Offers outspeed analysis if threats are named; idle unmatched "
        "does not invoke @smogon/calc.",
    ),
    ("C4", "qwen3.5_latest"): (
        "unactionable_offer",
        "Offers Modest-vs-Timid Pelipper advice needing team strategy; idle "
        "unmatched has no provisional/build screen.",
    ),
    ("D1", "qwen3.5_latest"): (
        "unactionable_offer",
        "Offers Max Def / Max SpD / balanced spread choices for Sinistcha "
        "with no pending spread or full_build screen to bind the answer to.",
    ),
    ("P1", "qwen3.5_latest"): (
        "defect_prose",
        "Treats illegal Chi-Yu + Choice Specs as a usable OHKO line "
        "(logged defect).",
    ),
    ("P2", "qwen3.5_latest"): (
        "defect_prose",
        "Treats illegal Miraidon as slottable with Scarf (logged defect).",
    ),
    ("P3", "qwen3.5_latest"): (
        "defect_prose",
        "Offers to add illegal Walking Wake / support for it (logged defect).",
    ),
}


def is_canned(msg: str) -> bool:
    if msg in CANNED:
        return True
    if msg.startswith("Unknown build option id") or msg.startswith(
        "Unknown build option ids"
    ):
        return True
    return False


def recorded_outcome(data: dict) -> str:
    oc = data.get("outcome")
    if isinstance(oc, dict):
        return str(oc.get("outcome") or oc)
    return str(oc)


def pending_kind_at_turn(data: dict, turn_index: int) -> str | None:
    """Return pending kind at message time; None means idle."""
    start_pk = (data.get("start") or {}).get("pending_kind")
    turn = (data.get("turns") or [])[turn_index]
    route_pk = turn.get("route_pending_kind")
    before = turn.get("before") or {}
    before_pk = before.get("pending_kind") if isinstance(before, dict) else None
    for pk in (before_pk, route_pk, start_pk):
        if pk in (None, "", "none"):
            continue
        return str(pk)
    return None


def transcript_name(rid: str, model: str) -> str:
    return f"{rid}__{model}__merged_usage_dir__r0.json"


def main() -> int:
    rows: list[dict] = []
    counts: dict[str, dict[str, int]] = {
        m: {"canned": 0, "llm_authored": 0, "empty": 0, "other_intent": 0}
        for m in MODELS
    }
    kind_counts: Counter[str] = Counter()

    for model in MODELS:
        for rid in CAP25:
            path = RUNS / f"{rid}__{model}__merged_usage_dir__r0.json"
            if not path.exists():
                continue
            data = json.loads(path.read_text())
            for ti, turn in enumerate(data.get("turns") or []):
                if turn.get("intent") != "pending_response":
                    counts[model]["other_intent"] += 1
                    continue
                msg = ((turn.get("payload") or {}).get("message") or "").strip()
                if not msg:
                    counts[model]["empty"] += 1
                    continue
                if is_canned(msg):
                    counts[model]["canned"] += 1
                    continue
                counts[model]["llm_authored"] += 1
                key = (rid, model)
                tname = transcript_name(rid, model)
                outcome = recorded_outcome(data)
                pk = pending_kind_at_turn(data, ti)
                kind_counts["None" if pk is None else pk] += 1
                if key not in BUCKET_MAP:
                    bucket, reason = (
                        "unique_UX",
                        f"UNCLASSIFIED — needs Vu decision. transcript={tname}",
                    )
                else:
                    bucket, reason = BUCKET_MAP[key]
                if bucket in {"unactionable_offer", "defect_prose"}:
                    reason = (
                        f"{reason} Recorded outcome={outcome} "
                        f"(transcript `{tname}`)."
                    )
                else:
                    reason = f"{reason} (transcript `{tname}`, outcome={outcome})."
                rows.append(
                    {
                        "request_id": rid,
                        "model": model,
                        "turn_index": ti,
                        "pending_kind": pk,
                        "message": msg,
                        "bucket": bucket,
                        "reason": reason,
                        "recorded_outcome": outcome,
                        "transcript": tname,
                    }
                )

    unique = [r for r in rows if r["bucket"] == "unique_UX"]
    all_idle = kind_counts.get("None", 0) == len(rows) and len(rows) > 0

    # D1 under-A composition note (report-only)
    d1_msg = next(
        (
            r["message"]
            for r in rows
            if r["request_id"] == "D1" and r["model"] == "qwen3.5_latest"
        ),
        None,
    )
    d1_note = {
        "pending_kind": None,
        "user_ask": "Should I run max Def, max Sp. Def, or something in between for Sinistcha?",
        "model_message": d1_msg,
        "under_A_idle": (
            "Unmatched line: UNMATCHED_REPLY_PREFIX ('Didn't catch that.') "
            "+ format_turn idle body (empty roster / no review). "
            "Loses the model's Def/SpD/balanced clarify."
        ),
        "under_A_full_build_confirmation": (
            "Unmatched line: CLASSIFY_FAIL_USER_MSG (name field/value/scope) "
            "+ _format_full_build body + full_build footer (yes / option ids / "
            "compare / edit / defer). Spread-axis options in the body can "
            "absorb a Def/SpD preference ask better than idle refuse; still "
            "not the model's tailored three-way question. UX loss vs model "
            "prose: modest on full_build (footer/body carry actions); larger "
            "on idle. Log as accepted Approach A tradeoff — do not change plan."
        ),
        "verdict": (
            "Acceptable under A for full_build (generic field ask + build UI); "
            "idle is a clear UX loss vs this model clarify — worth logging, "
            "not unique_UX (no pending state to rebuild from)."
        ),
    }

    out = {
        "sampling_caveat": SAMPLING_CAVEAT_NO_MIDFLOW
        if all_idle
        else (
            "CAP25 barely exercises mid-flow kinds; unique_UX_count==0 is "
            "weak mid-flow evidence."
        ),
        "pending_kind_counts": dict(kind_counts),
        "all_llm_authored_rows_idle": all_idle,
        "bucket_schema": [
            "echo_soft_refuse",
            "unactionable_offer",
            "defect_prose",
            "unique_UX",
        ],
        "relabel_note": (
            "Phase2 Step0 addendum: row-specific reasons; pending_kind column; "
            "unactionable_offer/defect_prose cite outcome+transcript filename."
        ),
        "snapshot_head": json.loads((SNAP / "meta.json").read_text())["head"],
        "counts_by_model": counts,
        "llm_authored_rows": rows,
        "unique_UX_count": len(unique),
        "unique_UX_rows": unique,
        "d1_under_A_check": d1_note,
        "s2_s8_outcomes": {
            "S2_qwen2.5_7b": {
                "outcome": recorded_outcome(
                    json.loads(
                        (RUNS / "S2__qwen2.5_7b__merged_usage_dir__r0.json").read_text()
                    )
                ),
                "note": "Not in llm_authored table (turn0 intent was not free-text pending_response).",
                "transcript": "S2__qwen2.5_7b__merged_usage_dir__r0.json",
            },
            "S2_qwen3.5_latest": {
                "outcome": "FAIL-CLOSED",
                "transcript": "S2__qwen3.5_latest__merged_usage_dir__r0.json",
            },
            "S8_qwen2.5_7b": {
                "outcome": "FAIL-CLOSED",
                "transcript": "S8__qwen2.5_7b__merged_usage_dir__r0.json",
            },
            "S8_qwen3.5_latest": {
                "outcome": "FAIL-CLOSED",
                "transcript": "S8__qwen3.5_latest__merged_usage_dir__r0.json",
            },
        },
        "hostile_test_scope": (
            "Idle plus EVERY PendingPresentation.kind (state.py PendingPresentation.kind). "
            "Do not narrow to gap-fill-reachable only. Kinds that do not call _gap_fill "
            "today still parametrize; prove with file:line and assert user-visible "
            "output lacks hostile prose."
        ),
        "stop_for_vu": len(unique) > 0,
    }
    (OUT / "ux_cost_gate0.json").write_text(json.dumps(out, indent=2) + "\n")

    md = [
        "# Gate 0 — UX cost (relabeled, Step0 addendum)",
        "",
        "## Sampling caveat",
        "",
        out["sampling_caveat"],
        "",
        f"**unique_UX_count:** {len(unique)}",
        f"**stop_for_vu:** {len(unique) > 0}",
        f"**pending_kind_counts:** `{dict(kind_counts)}`",
        f"**all_llm_authored_rows_idle:** {all_idle}",
        "",
        "## S2 / S8 recorded outcomes",
        "",
        f"- S2 qwen2.5: `{out['s2_s8_outcomes']['S2_qwen2.5_7b']['outcome']}` "
        f"(`{out['s2_s8_outcomes']['S2_qwen2.5_7b']['transcript']}`) — "
        f"{out['s2_s8_outcomes']['S2_qwen2.5_7b']['note']}",
        f"- S2 qwen3.5: `FAIL-CLOSED` (`S2__qwen3.5_latest__merged_usage_dir__r0.json`)",
        f"- S8 qwen2.5: `FAIL-CLOSED` (`S8__qwen2.5_7b__merged_usage_dir__r0.json`)",
        f"- S8 qwen3.5: `FAIL-CLOSED` (`S8__qwen3.5_latest__merged_usage_dir__r0.json`)",
        "",
        "## D1 under-A check (report-only)",
        "",
        f"- pending_kind: `{d1_note['pending_kind']}` (idle)",
        f"- user: {d1_note['user_ask']}",
        f"- under A idle: {d1_note['under_A_idle']}",
        f"- under A full_build: {d1_note['under_A_full_build_confirmation']}",
        f"- verdict: {d1_note['verdict']}",
        "",
        "## Full llm_authored table",
        "",
        "| request_id | model | pending_kind | bucket | outcome | reason | message |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        msg = r["message"].replace("|", "\\|").replace("\n", " / ")
        if len(msg) > 120:
            msg = msg[:117] + "..."
        md.append(
            f"| {r['request_id']} | {r['model']} | {r['pending_kind']!s} | "
            f"{r['bucket']} | {r['recorded_outcome']} | {r['reason']} | {msg} |"
        )
    md.extend(
        [
            "",
            "## Hostile-test scope",
            "",
            out["hostile_test_scope"],
            "",
        ]
    )
    (OUT / "ux_cost_gate0.md").write_text("\n".join(md) + "\n")
    print(
        json.dumps(
            {
                "unique_UX_count": len(unique),
                "kind_counts": dict(kind_counts),
                "all_idle": all_idle,
                "bucket_counts": {
                    b: sum(1 for r in rows if r["bucket"] == b)
                    for b in (
                        "echo_soft_refuse",
                        "unactionable_offer",
                        "defect_prose",
                        "unique_UX",
                    )
                },
                "d1_verdict": d1_note["verdict"],
            },
            indent=2,
        )
    )
    return 1 if unique else 0


if __name__ == "__main__":
    raise SystemExit(main())
