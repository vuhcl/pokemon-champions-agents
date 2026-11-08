"""FU74: parser-only eval (no arm run). Vu runs on local qwen3.5.

  uv run python -m scripts.eval.part_g_arm.state.parser_eval \\
    --parser-eval --model qwen3.5:latest

Compares parser v1 and v2. Reports per-turn state passed to the parser.
State-dependent turns that cannot be reconstructed offline are excluded from
the headline and listed separately. All numbers are labeled DEV.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from copy import deepcopy
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REV3 = HERE / "expected_tools_fu16" / "expected_tools_rev3_2026-11-02.csv"
DEV_A6 = HERE / "dev_guard_parser_labels.json"
DEV_FU74 = HERE / "dev_guard_parser_labels_fu74.json"

# Register entry 37 / report_58 — 32 turns (row, turn).
DISAGREE_32: list[tuple[str, int]] = [
    ("GS1", 2),
    ("H18b", 1),
    ("H18b", 2),
    ("HC1", 1),
    ("HC2", 1),
    ("IC1", 2),
    ("MM1", 1),
    ("MR1", 1),
    ("MR2", 1),
    ("MR3", 1),
    ("MR4", 1),
    ("MR6", 1),
    ("MR8", 1),
    ("MS1", 1),
    ("MS2", 1),
    ("MS7", 1),
    ("MS8", 1),
    ("MT1", 1),
    ("MT1", 2),
    ("MT2", 1),
    ("MT3", 3),
    ("MT5", 2),
    ("MT6", 1),
    ("MT6", 2),
    ("MU3", 1),
    ("MU4", 1),
    ("MU5", 1),
    ("OL2b", 1),
    ("OL5", 1),
    ("OL7a", 1),
    ("OL8", 1),
    ("TB1", 1),
]

# Mid-trajectory turns whose real arm state is not reconstructible offline
# (no seed / fixture for post-prior-turn team). Headline excludes these.
STATE_DEPENDENT_NOT_MEASURED: frozenset[tuple[str, int]] = frozenset(
    {
        ("MT2", 3),  # needs Pelipper locked from t1; start loader is empty_team
        ("MT6", 3),  # needs constraints from t1/t2; start loader is empty_team
    }
)

# Invented examples embedded in prompt_guard_parser_v2.md (in-sample DEV rows).
IN_PROMPT_EXAMPLE_IDS: frozenset[str] = frozenset(
    {
        "fu74-dev-constraint-electric",
        "fu74-dev-place-azumarill",
        "fu74-dev-dual-constraint",
        "fu74-dev-slot-no-antecedent",
        "fu74-dev-options-electric",
    }
)


def _key_class(row: dict[str, str]) -> str:
    return (row.get("guard_class_override") or row.get("proposed_guard_class") or "").strip().upper()


def load_csv_turns() -> dict[tuple[str, int], dict[str, str]]:
    out: dict[tuple[str, int], dict[str, str]] = {}
    with REV3.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            key = (row["row_id"], int(row["turn"]))
            out[key] = row
    return out


def load_dev_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in (DEV_A6, DEV_FU74):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for r in doc.get("rows") or []:
            rows.append({**r, "_source_file": path.name})
    return rows


def _make_llm(model: str, *, temperature: float = 0.0) -> Any:
    from langchain_ollama import ChatOllama

    return ChatOllama(
        model=model,
        temperature=temperature,
        reasoning=False,
        num_ctx=8192,
        num_predict=512,
    )


def _resolve_parser_state(
    row_id: str, turn: int
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, dict[str, Any]]:
    """Return (state, pending_asked, meta) using the same start builders as the runner.

    Mid-trajectory turns in STATE_DEPENDENT_NOT_MEASURED return state=None.
    """
    from scripts.eval.part_g_arm.state.guard_allowed import prepare_start_state_for_guard
    from scripts.eval.part_g_arm.state.request_set_rows import resolve_start_state

    meta_base: dict[str, Any] = {
        "row_id": row_id,
        "turn": turn,
        "state_dependent_not_measured": False,
    }
    if (row_id, turn) in STATE_DEPENDENT_NOT_MEASURED:
        meta_base["state_dependent_not_measured"] = True
        meta_base["reason"] = (
            "mid-trajectory; start loader does not reconstruct prior-turn team/constraints"
        )
        return None, None, meta_base

    state, meta = resolve_start_state({"id": row_id, "state": "", "prompt": ""})
    meta_base.update(
        {
            "source": meta.get("source"),
            "loaded": meta.get("loaded"),
            "error": meta.get("error"),
        }
    )
    if state is None:
        meta_base["state_dependent_not_measured"] = True
        meta_base["reason"] = meta.get("error") or "start state failed to load"
        return None, None, meta_base

    prepare_start_state_for_guard(state)
    pending_asked = state.get("_guard_pending_asked")
    if not isinstance(pending_asked, dict):
        pending_asked = None
    return state, pending_asked, meta_base


def _dev_start_state(start: str) -> tuple[dict[str, Any], dict[str, Any] | None]:
    from scripts.eval.part_g_arm.state.fixtures import empty_team, one_locked_slot
    from scripts.eval.part_g_arm.state.seeds import BUILDERS

    pending_asked = None
    if start == "empty":
        return empty_team(), None
    if start == "one_locked":
        return one_locked_slot("Venusaur", 1), None
    if start == "cs_pending":
        return BUILDERS["cs_pending"](), {
            "action": "select_option",
            "missing_argument": "option",
            "slot_context": 2,
        }
    return empty_team(), None


def _parse_one(
    llm: Any,
    text: str,
    *,
    parser_v2: bool,
    state: dict[str, Any],
    pending_asked: dict[str, Any] | None,
) -> dict[str, Any]:
    from scripts.eval.part_g_arm.state.guard_parser import parse_user_turn
    from scripts.eval.part_g_arm.state.tools import set_parser_v2

    set_parser_v2(parser_v2)
    try:
        return parse_user_turn(llm, text, state, pending_asked=pending_asked)
    finally:
        set_parser_v2(False)


def _primary_class(rec: dict[str, Any]) -> str:
    subs = rec.get("sub_requests") or []
    if not subs:
        return "ASK"
    return str(subs[0].get("class") or "ASK").upper()


def _state_report(
    state: dict[str, Any] | None,
    pending_asked: dict[str, Any] | None,
    meta: dict[str, Any],
) -> dict[str, Any]:
    from scripts.eval.part_g_arm.state.guard_parser import compact_state_summary

    if state is None:
        return {
            "state_dependent_not_measured": True,
            "reason": meta.get("reason"),
            "source": meta.get("source"),
        }
    summary = compact_state_summary(state, pending_asked=pending_asked)
    return {
        "state_dependent_not_measured": False,
        "source": meta.get("source"),
        "pending_kind": summary.get("pending_kind"),
        "asked_action": summary.get("asked_action"),
        "constraint_count_active": summary.get("constraint_count_active"),
        "constraint_count_total": summary.get("constraint_count_total"),
        "slots": summary.get("slots"),
        "pending_fingerprint_matches": summary.get("pending_fingerprint_matches"),
    }


def _score_pair(
    rows: list[dict[str, Any]],
    *,
    llm: Any,
) -> dict[str, Any]:
    """Score v1 and v2 on the same rows; skip state-dependent; report gains/regressions."""
    measured: list[dict[str, Any]] = []
    state_dependent: list[dict[str, Any]] = []
    per_turn: list[dict[str, Any]] = []

    for row in rows:
        rid = row.get("row_id") or row.get("id")
        turn = int(row.get("turn") or 1)
        text = row["text"]
        want = str(row["class"]).upper()

        if row.get("dev"):
            state, pending_asked = _dev_start_state(str(row.get("start") or "empty"))
            meta = {"source": f"dev:{row.get('start') or 'empty'}", "row_id": rid, "turn": turn}
            state_rep = _state_report(state, pending_asked, meta)
        else:
            row_id = str(row.get("row_id") or str(rid).split("__")[0])
            state, pending_asked, meta = _resolve_parser_state(row_id, turn)
            state_rep = _state_report(state, pending_asked, meta)

        if state_rep.get("state_dependent_not_measured"):
            state_dependent.append(
                {
                    "id": row.get("id"),
                    "row_id": row.get("row_id"),
                    "turn": turn,
                    "text": text,
                    "key": want,
                    "state": state_rep,
                }
            )
            continue

        assert state is not None
        v1 = _parse_one(llm, text, parser_v2=False, state=state, pending_asked=pending_asked)
        # Fresh copy so v2 cannot see mutations (parser is read-only, but be safe).
        state2 = deepcopy(state)
        v2 = _parse_one(llm, text, parser_v2=True, state=state2, pending_asked=pending_asked)
        g1 = _primary_class(v1)
        g2 = _primary_class(v2)
        entry = {
            "id": row.get("id"),
            "row_id": row.get("row_id"),
            "turn": turn,
            "text": text,
            "key": want,
            "v1": g1,
            "v2": g2,
            "v1_ok": g1 == want,
            "v2_ok": g2 == want,
            "uncertain_v1": v1.get("uncertain"),
            "uncertain_v2": v2.get("uncertain"),
            "state": state_rep,
            "in_prompt_example": row.get("id") in IN_PROMPT_EXAMPLE_IDS,
        }
        if g1 == want and g2 != want:
            entry["delta"] = "regression"
        elif g1 != want and g2 == want:
            entry["delta"] = "gain"
        elif g1 != g2:
            entry["delta"] = "swap"
        else:
            entry["delta"] = "same"
        measured.append(entry)
        per_turn.append(entry)

    def _pack(tag: str, pred_key: str) -> dict[str, Any]:
        confusion: dict[str, Counter[str]] = defaultdict(Counter)
        n_ok = 0
        disagree = []
        for e in measured:
            want = e["key"]
            got = e[pred_key]
            confusion[want][got] += 1
            if got == want:
                n_ok += 1
            else:
                disagree.append(
                    {
                        "id": e["id"],
                        "text": e["text"],
                        "key": want,
                        "got": got,
                        "state": e["state"],
                    }
                )
        n = len(measured)
        return {
            "n": n,
            "agree": n_ok,
            "agreement": (n_ok / n) if n else 0.0,
            "confusion": {k: dict(v) for k, v in sorted(confusion.items())},
            "disagree": disagree,
            "parser": tag,
            "label": "DEV",
        }

    gains = [e for e in measured if e["delta"] == "gain"]
    regressions = [e for e in measured if e["delta"] == "regression"]
    return {
        "label": "DEV",
        "v1": _pack("v1", "v1"),
        "v2": _pack("v2", "v2"),
        "gains_v1_to_v2": [
            {"id": e["id"], "key": e["key"], "v1": e["v1"], "v2": e["v2"], "text": e["text"]}
            for e in gains
        ],
        "regressions_v1_to_v2": [
            {"id": e["id"], "key": e["key"], "v1": e["v1"], "v2": e["v2"], "text": e["text"]}
            for e in regressions
        ],
        "per_turn": per_turn,
        "state_dependent_not_measured": state_dependent,
        "n_measured": len(measured),
        "n_state_dependent": len(state_dependent),
    }


def _played_text(row_id: str, turn: int, original: str) -> str:
    from scripts.eval.part_g_arm.state.revised_keys import apply_turn_text_override

    return apply_turn_text_override(row_id, turn - 1, original, key_set="fu74")


def build_sets() -> dict[str, list[dict[str, Any]]]:
    csv_turns = load_csv_turns()
    dev = [
        {
            "id": r["id"],
            "text": r["text"],
            "class": r["class"],
            "start": r.get("start") or "empty",
            "dev": True,
        }
        for r in load_dev_rows()
    ]
    disagree_orig: list[dict[str, Any]] = []
    disagree_fu74: list[dict[str, Any]] = []
    for rid, turn in DISAGREE_32:
        row = csv_turns.get((rid, turn))
        if not row:
            continue
        original = row["user_turn_text"]
        key = _key_class(row)
        disagree_orig.append(
            {
                "id": f"{rid}__t{turn}",
                "row_id": rid,
                "turn": turn,
                "text": original,
                "class": key,
            }
        )
        played = _played_text(rid, turn, original)
        disagree_fu74.append(
            {
                "id": f"{rid}__t{turn}",
                "row_id": rid,
                "turn": turn,
                "text": played,
                "class": key,
                "text_differs": played != original,
            }
        )
    all_turns: list[dict[str, Any]] = []
    for (rid, turn), row in sorted(csv_turns.items()):
        all_turns.append(
            {
                "id": f"{rid}__t{turn}",
                "row_id": rid,
                "turn": turn,
                "text": row["user_turn_text"],
                "class": _key_class(row),
            }
        )
    return {
        "dev": dev,
        "disagree_32_original": disagree_orig,
        "disagree_32_fu74": disagree_fu74,
        "all_csv": all_turns,
    }


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--parser-eval",
        action="store_true",
        required=True,
        help="required flag (makes the intent explicit; no arm run)",
    )
    p.add_argument("--model", default="qwen3.5:latest")
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="optional JSON report path (outside repo preferred)",
    )
    p.add_argument(
        "--sets",
        default="dev,disagree_32_original,disagree_32_fu74,all_csv",
        help="comma list of sets to score",
    )
    p.add_argument(
        "--keys",
        choices=("committed", "fu74"),
        default="committed",
        help="start-state key set (fu74 loads keys_fu72 seeds when applicable)",
    )
    args = p.parse_args(argv)

    from scripts.eval.part_g_arm.state.revised_keys import set_key_set

    set_key_set(args.keys)

    sets = build_sets()
    wanted = [s.strip() for s in args.sets.split(",") if s.strip()]
    llm = _make_llm(args.model)
    report: dict[str, Any] = {
        "label": "DEV",
        "model": args.model,
        "keys": args.keys,
        "note": (
            "Parser-only eval. No arm run. Agreement numbers are DEV. "
            "Headline excludes state_dependent_not_measured turns; those are listed separately. "
            "Per-turn state is the compact summary passed to the parser (same builders as the runner)."
        ),
        "state_dependent_policy": sorted(f"{a} t{b}" for a, b in STATE_DEPENDENT_NOT_MEASURED),
        "results": {},
    }

    for name in wanted:
        rows = sets[name]
        print(f"== {name} n={len(rows)} (DEV) ==", file=sys.stderr)
        scored = _score_pair(rows, llm=llm)
        report["results"][name] = scored
        print(
            f"  measured={scored['n_measured']} state_dependent={scored['n_state_dependent']}",
            file=sys.stderr,
        )
        for tag in ("v1", "v2"):
            s = scored[tag]
            print(
                f"  {tag}: agree={s['agree']}/{s['n']} ({s['agreement']:.3f}) DEV  "
                f"disagree={len(s['disagree'])}",
                file=sys.stderr,
            )
        print(
            f"  gains={len(scored['gains_v1_to_v2'])} "
            f"regressions={len(scored['regressions_v1_to_v2'])}",
            file=sys.stderr,
        )
        for e in scored["gains_v1_to_v2"]:
            print(
                f"    GAIN {e['id']}: key={e['key']} v1={e['v1']}→v2={e['v2']}",
                file=sys.stderr,
            )
        for e in scored["regressions_v1_to_v2"]:
            print(
                f"    REGRESS {e['id']}: key={e['key']} v1={e['v1']}→v2={e['v2']}",
                file=sys.stderr,
            )
        if name == "disagree_32_fu74":
            differ = [r["id"] for r in rows if r.get("text_differs")]
            report["disagree_32_text_differs"] = differ
            print(f"  text differs under fu74: {differ}", file=sys.stderr)
        if name == "dev":
            # Agreement with and without the five in-prompt example rows.
            measured = scored["per_turn"]
            with_ex = measured
            without = [e for e in measured if not e.get("in_prompt_example")]
            for label, subset in (
                ("with_in_prompt_examples", with_ex),
                ("without_in_prompt_examples", without),
            ):
                n = len(subset)
                a1 = sum(1 for e in subset if e["v1_ok"])
                a2 = sum(1 for e in subset if e["v2_ok"])
                report.setdefault("dev_splits", {})[label] = {
                    "n": n,
                    "v1_agree": a1,
                    "v1_agreement": (a1 / n) if n else 0.0,
                    "v2_agree": a2,
                    "v2_agreement": (a2 / n) if n else 0.0,
                    "label": "DEV",
                }
                print(
                    f"  {label}: v1={a1}/{n} v2={a2}/{n} DEV",
                    file=sys.stderr,
                )

    # Headline table of state-dependent turns across sets.
    sd_table = []
    for name, block in report["results"].items():
        for e in block.get("state_dependent_not_measured") or []:
            sd_table.append(
                {
                    "set": name,
                    **{k: e.get(k) for k in ("id", "row_id", "turn", "key", "text")},
                }
            )
    report["state_dependent_table"] = sd_table
    if sd_table:
        print("== state_dependent_not_measured (excluded from headline) ==", file=sys.stderr)
        for e in sd_table:
            print(
                f"  {e.get('set')} {e.get('id') or e.get('row_id')} "
                f"t{e.get('turn')} key={e.get('key')}",
                file=sys.stderr,
            )

    text = json.dumps(report, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
