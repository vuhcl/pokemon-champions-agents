"""Compare three arm runs: primary (run 1) vs determinism checks (2, 3).

Never averages; never replaces the primary. Diff fields: mechanical class
sequence, ordered (name, args) tool calls, sha256(final_text) per turn.
One-sided error/timeout → status error_mismatch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent


def _text_sha(text: str | None) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _tool_seq(turn: dict[str, Any]) -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    for call in turn.get("tool_calls") or []:
        out.append((str(call.get("name") or ""), call.get("args") or call.get("arguments") or {}))
    return out


def _turn_fingerprint(turn: dict[str, Any] | None) -> dict[str, Any]:
    if turn is None:
        return {"missing": True}
    return {
        "mechanical_class": turn.get("mechanical_class"),
        "final_text_sha256": _text_sha(turn.get("final_text")),
        "tool_calls": _tool_seq(turn),
        "errors": list(turn.get("errors") or []),
        "no_usable_answer": bool(turn.get("no_usable_answer")),
    }


def _load_transcript(out_dir: Path) -> dict[str, dict[str, Any]]:
    path = out_dir / "transcript.json"
    if not path.is_file():
        raise FileNotFoundError(f"missing {path}")
    rows = json.loads(path.read_text(encoding="utf-8"))
    return {r["id"]: r for r in rows if isinstance(r, dict) and "id" in r}


def compare_entry(primary: dict[str, Any] | None, other: dict[str, Any] | None, *, vs_run: int) -> dict[str, Any]:
    """Compare one row's primary transcript entry to another run's entry."""
    rid = (primary or other or {}).get("id")
    result: dict[str, Any] = {
        "id": rid,
        "vs_run": vs_run,
        "status": "equal",
        "diffs": [],
    }
    if primary is None and other is None:
        result["status"] = "missing_both"
        return result
    if primary is None or other is None:
        result["status"] = "error_mismatch"
        result["diffs"].append(
            {
                "kind": "row_presence",
                "primary_present": primary is not None,
                "other_present": other is not None,
            }
        )
        return result

    p_turns = list(primary.get("turns") or [])
    o_turns = list(other.get("turns") or [])
    n = max(len(p_turns), len(o_turns))
    for i in range(n):
        pt = p_turns[i] if i < len(p_turns) else None
        ot = o_turns[i] if i < len(o_turns) else None
        pf, of = _turn_fingerprint(pt), _turn_fingerprint(ot)
        if pf.get("missing") or of.get("missing"):
            result["status"] = "error_mismatch"
            result["diffs"].append(
                {
                    "kind": "turn_presence",
                    "turn": i + 1,
                    "primary": pf,
                    "other": of,
                }
            )
            continue
        p_err, o_err = pf["errors"], of["errors"]
        if bool(p_err) != bool(o_err) or (p_err and o_err and p_err != o_err):
            result["status"] = "error_mismatch"
            result["diffs"].append(
                {
                    "kind": "errors",
                    "turn": i + 1,
                    "primary_errors": p_err,
                    "other_errors": o_err,
                }
            )
        turn_diffs: list[str] = []
        if pf["mechanical_class"] != of["mechanical_class"]:
            turn_diffs.append("class")
        if pf["tool_calls"] != of["tool_calls"]:
            turn_diffs.append("tool_calls")
        if pf["final_text_sha256"] != of["final_text_sha256"]:
            turn_diffs.append("final_text_sha256")
        if turn_diffs:
            if result["status"] == "equal":
                result["status"] = "differ"
            result["diffs"].append(
                {
                    "kind": "turn",
                    "turn": i + 1,
                    "fields": turn_diffs,
                    "primary": {
                        "mechanical_class": pf["mechanical_class"],
                        "final_text_sha256": pf["final_text_sha256"],
                        "tool_calls": pf["tool_calls"],
                    },
                    "other": {
                        "mechanical_class": of["mechanical_class"],
                        "final_text_sha256": of["final_text_sha256"],
                        "tool_calls": of["tool_calls"],
                    },
                }
            )
    return result


def compare_runs(primary_dir: Path, run2_dir: Path, run3_dir: Path) -> dict[str, Any]:
    primary = _load_transcript(primary_dir)
    r2 = _load_transcript(run2_dir)
    r3 = _load_transcript(run3_dir)
    ids = sorted(set(primary) | set(r2) | set(r3))
    vs2 = [compare_entry(primary.get(i), r2.get(i), vs_run=2) for i in ids]
    vs3 = [compare_entry(primary.get(i), r3.get(i), vs_run=3) for i in ids]
    differ = [
        e
        for e in vs2 + vs3
        if e["status"] in {"differ", "error_mismatch", "missing_both"}
    ]
    return {
        "primary_dir": str(primary_dir),
        "run2_dir": str(run2_dir),
        "run3_dir": str(run3_dir),
        "note": (
            "Run 1 is the primary result. Runs 2 and 3 are determinism checks. "
            "Differences are listed beside the primary; never averaged or replacing it."
        ),
        "comparison_fields": [
            "mechanical_class (per turn)",
            "tool_calls (name, args) in order",
            "sha256(final_text) per turn",
        ],
        "vs_run_2": vs2,
        "vs_run_3": vs3,
        "differ": differ,
        "differ_count": len(differ),
        "row_count": len(ids),
    }


def compare_runs_root(runs_root: Path) -> dict[str, Any]:
    return compare_runs(runs_root / "run_1", runs_root / "run_2", runs_root / "run_3")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs-root", type=Path, help="DIR with run_1 / run_2 / run_3")
    parser.add_argument("--primary", type=Path, help="run 1 out dir")
    parser.add_argument("--run2", type=Path, help="run 2 out dir")
    parser.add_argument("--run3", type=Path, help="run 3 out dir")
    parser.add_argument("-o", "--out", type=Path, help="write JSON report here")
    args = parser.parse_args(argv)
    if args.runs_root:
        report = compare_runs_root(args.runs_root)
    elif args.primary and args.run2 and args.run3:
        report = compare_runs(args.primary, args.run2, args.run3)
    else:
        print("need --runs-root or --primary/--run2/--run3", file=sys.stderr)
        return 2
    text = json.dumps(report, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        print(f"wrote {args.out} differ={report['differ_count']}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
