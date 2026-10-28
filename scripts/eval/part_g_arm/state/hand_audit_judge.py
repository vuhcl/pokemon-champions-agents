"""Part 5 — second-rater for hand-audit rows (gemma). Never mechanical scoring."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PROMPT_PATH = HERE / "judge_prompt.md"
JUDGE_MODEL = "gemma4:12b"
JUDGE_TEMPERATURE = 0.0

_JSON_RE = re.compile(r"\{.*\}", re.S)


def prompt_sha256() -> str:
    return hashlib.sha256(PROMPT_PATH.read_bytes()).hexdigest()


def _extract_json(text: str) -> dict[str, Any]:
    text = (text or "").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = _JSON_RE.search(text)
        if not m:
            return {"points": [], "overall": "fail", "parse_error": True, "raw": text[:500]}
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            return {"points": [], "overall": "fail", "parse_error": True, "raw": text[:500]}


def build_user_payload(
    *,
    rubric: str,
    user_turns: list[str] | str,
    final_text: str,
    tool_results: list[Any] | None = None,
) -> str:
    turns = user_turns if isinstance(user_turns, list) else [user_turns]
    return json.dumps(
        {
            "rubric": rubric,
            "user_turns": turns,
            "final_text": final_text,
            "tool_results": tool_results or [],
        },
        indent=2,
    )


def judge_one(llm: Any, *, rubric: str, user_turns: Any, final_text: str, tool_results: Any = None) -> dict[str, Any]:
    from langchain_core.messages import HumanMessage, SystemMessage

    messages = [
        SystemMessage(PROMPT_PATH.read_text(encoding="utf-8")),
        HumanMessage(
            build_user_payload(
                rubric=rubric,
                user_turns=user_turns,
                final_text=final_text,
                tool_results=tool_results,
            )
        ),
    ]
    ai = llm.invoke(messages)
    content = ai.content if isinstance(ai.content, str) else str(ai.content)
    parsed = _extract_json(content)
    parsed["raw_response"] = content
    return parsed


def run_calibration(out_dir: Path) -> dict[str, Any]:
    from langchain_ollama import ChatOllama

    items = json.loads((HERE / "judge_calibration.json").read_text(encoding="utf-8"))["items"]
    llm = ChatOllama(model=JUDGE_MODEL, temperature=JUDGE_TEMPERATURE, reasoning=False)
    rows = []
    agree = false_pass = false_fail = 0
    for item in items:
        got = judge_one(
            llm,
            rubric=item["rubric"],
            user_turns=item["user"],
            final_text=item["final_text"],
            tool_results=item.get("tool_results"),
        )
        overall = (got.get("overall") or "fail").lower()
        if overall not in {"pass", "fail"}:
            overall = "fail"
        exp = item["expected_overall"]
        match = overall == exp
        agree += int(match)
        if overall == "pass" and exp == "fail":
            false_pass += 1
        if overall == "fail" and exp == "pass":
            false_fail += 1
        rows.append(
            {
                "id": item["id"],
                "kind": item["kind"],
                "expected": exp,
                "got": overall,
                "match": match,
                "points": got.get("points"),
                "parse_error": got.get("parse_error", False),
            }
        )
    summary = {
        "judge_model": JUDGE_MODEL,
        "temperature": JUDGE_TEMPERATURE,
        "prompt_sha256": prompt_sha256(),
        "n": len(items),
        "agreement": agree,
        "false_pass": false_pass,
        "false_fail": false_fail,
        "planted_error_items": sum(1 for i in items if i["kind"].startswith("planted")),
        "correct_items": sum(1 for i in items if i["kind"].startswith("correct")),
        "rows": rows,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(summary, indent=2) + "\n"
    (out_dir / "calibration_result.json").write_text(blob, encoding="utf-8")
    (out_dir / "prompt_sha256.txt").write_text(prompt_sha256() + "\n", encoding="utf-8")
    summary["output_sha256"] = hashlib.sha256(blob.encode()).hexdigest()
    summary["output_path"] = str(out_dir / "calibration_result.json")
    (out_dir / "calibration_meta.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "out_dir",
        type=Path,
        nargs="?",
        default=Path("/Users/nowaki027/part-g-arm-state-out-judge"),
    )
    parser.add_argument("--calibration", action="store_true", default=True)
    args = parser.parse_args(argv)
    summary = run_calibration(args.out_dir)
    print(
        f"judge calibration n={summary['n']} agree={summary['agreement']} "
        f"false_pass={summary['false_pass']} false_fail={summary['false_fail']} "
        f"prompt={summary['prompt_sha256'][:16]}… out={summary['output_path']}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
