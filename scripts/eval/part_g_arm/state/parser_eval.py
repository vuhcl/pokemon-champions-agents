"""FU74: parser-only eval (no arm run). Vu runs on local qwen3.5.

  uv run python -m scripts.eval.part_g_arm.state.parser_eval \\
    --parser-eval --model qwen3.5:latest

Compares parser v1 and v2 on: (a) dev labels + fu74 new rows, (b) the 32
disagreement turns (original + fu74 played text), (c) all CSV turns vs key class.
All printed numbers are labeled DEV.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
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


def _parse_one(llm: Any, text: str, *, parser_v2: bool) -> dict[str, Any]:
    from scripts.eval.part_g_arm.state.fixtures import empty_team
    from scripts.eval.part_g_arm.state.guard_parser import parse_user_turn
    from scripts.eval.part_g_arm.state.tools import set_parser_v2

    set_parser_v2(parser_v2)
    try:
        return parse_user_turn(llm, text, empty_team())
    finally:
        set_parser_v2(False)


def _primary_class(rec: dict[str, Any]) -> str:
    subs = rec.get("sub_requests") or []
    if not subs:
        return "ASK"
    return str(subs[0].get("class") or "ASK").upper()


def _score(
    rows: list[dict[str, Any]],
    *,
    llm: Any,
    parser_v2: bool,
    label_key: str = "class",
) -> dict[str, Any]:
    confusion: dict[str, Counter[str]] = defaultdict(Counter)
    disagree: list[dict[str, Any]] = []
    n_ok = 0
    for row in rows:
        text = row["text"]
        want = str(row[label_key]).upper()
        rec = _parse_one(llm, text, parser_v2=parser_v2)
        got = _primary_class(rec)
        confusion[want][got] += 1
        ok = got == want
        if ok:
            n_ok += 1
        else:
            disagree.append(
                {
                    "id": row.get("id"),
                    "text": text,
                    "key": want,
                    "got": got,
                    "uncertain": rec.get("uncertain"),
                }
            )
    n = len(rows)
    return {
        "n": n,
        "agree": n_ok,
        "agreement": (n_ok / n) if n else 0.0,
        "confusion": {k: dict(v) for k, v in sorted(confusion.items())},
        "disagree": disagree,
        "parser_v2": parser_v2,
        "label": "DEV",
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
            {"id": f"{rid}__t{turn}", "text": original, "class": key}
        )
        played = _played_text(rid, turn, original)
        disagree_fu74.append(
            {
                "id": f"{rid}__t{turn}",
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
    args = p.parse_args(argv)

    sets = build_sets()
    wanted = [s.strip() for s in args.sets.split(",") if s.strip()]
    llm = _make_llm(args.model)
    report: dict[str, Any] = {
        "label": "DEV",
        "model": args.model,
        "note": (
            "Parser-only eval. No arm run. Agreement numbers are DEV "
            "(118 turns audited; no held-out set)."
        ),
        "results": {},
    }
    for name in wanted:
        rows = sets[name]
        print(f"== {name} n={len(rows)} (DEV) ==", file=sys.stderr)
        for v2 in (False, True):
            tag = "v2" if v2 else "v1"
            print(f"  scoring parser {tag}…", file=sys.stderr)
            scored = _score(rows, llm=llm, parser_v2=v2)
            report["results"][f"{name}__parser_{tag}"] = scored
            print(
                f"  {tag}: agree={scored['agree']}/{scored['n']} "
                f"({scored['agreement']:.3f}) DEV  disagree={len(scored['disagree'])}",
                file=sys.stderr,
            )
        if name == "disagree_32_fu74":
            differ = [r["id"] for r in rows if r.get("text_differs")]
            report["disagree_32_text_differs"] = differ
            print(f"  text differs under fu74: {differ}", file=sys.stderr)

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
