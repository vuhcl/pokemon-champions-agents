#!/usr/bin/env python3
"""Bare-LLM baseline: open-ended Reg M-C team build, no tools, scored for hallucination.

Usage:
  BOOTSTRAP_OLLAMA_MODEL=qwen2.5:7b uv run python scripts/eval/run_bare_llm_baseline.py
  BOOTSTRAP_OLLAMA_MODEL=qwen3.5:latest uv run python scripts/eval/run_bare_llm_baseline.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.eval.bare_llm_score import (  # noqa: E402
    _KO_CLAIM,
    _SPE_CLAIM,
    _assert_structural_self_check,
    extract_team,
    score_transcript,
)
from scripts.eval.oracle import load_oracle_snapshot  # noqa: E402
from scripts.eval.run_legality import build_oracle_snapshot, calc_healthy  # noqa: E402
from scripts.eval.scenarios_bare_llm import (  # noqa: E402
    CONTINUER,
    DEFAULT_RUNS,
    INITIAL_PROMPT,
    SOFT_MECH_NUDGE,
    TEMPERATURE,
    TURN_CAP,
)
from scripts.eval.species_fact_oracle import _assert_self_check  # noqa: E402

ARTIFACTS = Path(__file__).resolve().parent / "artifacts"


def _model_tag(model: str) -> str:
    m = model.lower()
    if "qwen3.5" in m or "qwen35" in m:
        return "qwen35"
    if "qwen2.5" in m or "qwen25" in m:
        return "qwen25"
    return re.sub(r"[^a-z0-9]+", "", m)[:24]


def _ollama_reachable(model: str, timeout: float = 3.0) -> bool:
    try:
        req = urllib.request.Request(
            "http://127.0.0.1:11434/api/tags", method="GET"
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode())
        names = {m.get("name") for m in (body.get("models") or [])}
        return model in names or any(
            str(n).startswith(model.split(":")[0]) for n in names
        )
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return False


def _build_chat(model: str, temperature: float):
    from langchain_ollama import ChatOllama

    return ChatOllama(model=model, temperature=temperature)


def _run_one_chat(
    chat: Any,
    *,
    turn_cap: int,
) -> tuple[str, list[dict[str, str]], bool]:
    """Return (full transcript text, messages meta, mech_nudge_used)."""
    from langchain_core.messages import AIMessage, HumanMessage

    history: list[Any] = [HumanMessage(content=INITIAL_PROMPT)]
    transcript_parts: list[str] = [f"USER: {INITIAL_PROMPT}"]
    nudge_used = False
    organic_mech = 0

    for turn in range(turn_cap):
        resp = chat.invoke(history)
        content = getattr(resp, "content", None) or str(resp)
        if not isinstance(content, str):
            content = str(content)
        history.append(AIMessage(content=content))
        transcript_parts.append(f"ASSISTANT: {content}")

        # Early score for nudge decision (spe/ko regex only; cheap)
        so_far = "\n".join(transcript_parts)
        organic_mech = len(_SPE_CLAIM.findall(so_far)) + len(_KO_CLAIM.findall(so_far))
        team = extract_team(so_far)
        if team.completed:
            if organic_mech == 0 and not nudge_used and len(team.slots) >= 4:
                nudge_used = True
                history.append(HumanMessage(content=SOFT_MECH_NUDGE))
                transcript_parts.append(f"USER: {SOFT_MECH_NUDGE}")
                resp2 = chat.invoke(history)
                c2 = getattr(resp2, "content", None) or str(resp2)
                if not isinstance(c2, str):
                    c2 = str(c2)
                history.append(AIMessage(content=c2))
                transcript_parts.append(f"ASSISTANT: {c2}")
            break

        # Continuer
        history.append(HumanMessage(content=CONTINUER))
        transcript_parts.append(f"USER: {CONTINUER}")

        # Soft nudge mid-run if near-complete and no mech claims
        if (
            not nudge_used
            and len(team.slots) >= 4
            and organic_mech == 0
            and turn >= 2
        ):
            # Replace last continuer with nudge once
            history[-1] = HumanMessage(content=SOFT_MECH_NUDGE)
            transcript_parts[-1] = f"USER: {SOFT_MECH_NUDGE}"
            nudge_used = True

    return "\n\n".join(transcript_parts), [], nudge_used


def _aggregate(runs: list[dict[str, Any]]) -> dict[str, Any]:
    pairs_checked = sum(r["score"]["legality"]["pairs_checked"] for r in runs)
    false_legal = sum(r["score"]["legality"]["false_legal"] for r in runs)
    false_illegal = sum(r["score"]["legality"]["false_illegal"] for r in runs)

    def sum_tally(path: str) -> dict[str, int]:
        keys = ("TRUE", "FALSE", "unverifiable_shape", "total")
        out = {k: 0 for k in keys}
        for r in runs:
            t = r["score"][path]["tally"]
            for k in keys:
                out[k] += int(t.get(k, 0))
        return out

    ev = sum(r["score"]["structural"]["spreads_ev_shaped"] for r in runs)
    sp = sum(r["score"]["structural"]["spreads_sp_shaped"] for r in runs)
    completed = [r for r in runs if r["score"]["team"]["completed"]]
    ic_viol = sum(
        1
        for r in completed
        if r["score"]["structural"]["item_clause_violation"] is True
    )
    false_quotes: list[str] = []
    for r in runs:
        for claim in r["score"]["species_facts"]["claims"]:
            if claim.get("verdict") == "FALSE":
                false_quotes.append(claim.get("display") or "")
        for claim in r["score"]["mechanical"]["claims"]:
            if claim.get("verdict") == "FALSE":
                false_quotes.append(claim.get("display") or "")
        for ex in r["score"]["legality"].get("false_illegal_examples") or []:
            false_quotes.append(ex.get("display") or "")
    return {
        "pairs_checked": pairs_checked,
        "false_legal": false_legal,
        "false_illegal": false_illegal,
        "species_facts": sum_tally("species_facts"),
        "mechanical": sum_tally("mechanical"),
        "spreads_ev_shaped": ev,
        "spreads_sp_shaped": sp,
        "spreads_parsed_denom": ev + sp,
        "completed_teams": len(completed),
        "item_clause_violations": ic_viol,
        "incomplete_runs": sum(1 for r in runs if r["score"]["team"]["incomplete"]),
        "false_claim_quotes": [q for q in false_quotes if q][:12],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    parser.add_argument("--turn-cap", type=int, default=TURN_CAP)
    parser.add_argument("--temperature", type=float, default=TEMPERATURE)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument(
        "--require-calc",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Exit non-zero if calc unhealthy (default: true)",
    )
    parser.add_argument(
        "--self-check-only",
        action="store_true",
        help="Run oracle/structural self-checks and exit (no Ollama)",
    )
    args = parser.parse_args()

    _assert_self_check()
    _assert_structural_self_check()
    if args.self_check_only:
        return 0

    os.environ.setdefault("BOOTSTRAP_OLLAMA_MODEL", "qwen2.5:7b")
    model = os.environ["BOOTSTRAP_OLLAMA_MODEL"]

    if not _ollama_reachable(model):
        print(
            f"ABORT: Ollama unreachable or model {model!r} not listed at :11434",
            file=sys.stderr,
        )
        return 2

    calc_ok = calc_healthy()
    if args.require_calc and not calc_ok:
        print("ABORT: calc service unhealthy at :4173 (--require-calc)", file=sys.stderr)
        return 2

    snap_path = build_oracle_snapshot(mod="champions")
    snap = load_oracle_snapshot(snap_path)

    chat = _build_chat(model, args.temperature)
    runs: list[dict[str, Any]] = []
    for i in range(args.runs):
        print(f"=== run {i + 1}/{args.runs} model={model} ===", file=sys.stderr)
        transcript, _, nudge = _run_one_chat(chat, turn_cap=args.turn_cap)
        score = score_transcript(transcript, snap, calc_ok=calc_ok)
        runs.append(
            {
                "run": i + 1,
                "mech_nudge_used": nudge,
                "transcript_truncated": transcript[:8000],
                "transcript_chars": len(transcript),
                "score": score,
            }
        )
        print(
            f"  slots={len(score['team']['slots'])} "
            f"incomplete={score['team']['incomplete']} "
            f"species_claims={score['species_facts']['tally']['total']} "
            f"mech={score['mechanical']['tally']['total']}",
            file=sys.stderr,
        )

    summary = {
        "label": "Bare-LLM baseline (no tools)",
        "measured": str(date.today()),
        "model": model,
        "temperature": args.temperature,
        "runs": args.runs,
        "prompt": INITIAL_PROMPT,
        "oracle_snapshot": str(snap_path),
        "calc_ok": calc_ok,
        "aggregate": _aggregate(runs),
        "runs_detail": runs,
        "notes": [
            "No LangGraph / no tools; ChatOllama free-form only.",
            "Legality oracle: same build_oracle_snapshot(mod=champions) as run_legality.",
            "Species facts: species_fact_oracle (incl. move learnability).",
            "Soft mech nudge at most once if ≥4 slots and zero organic mech claims.",
        ],
    }

    out = args.out or (ARTIFACTS / f"bare_llm_baseline_{_model_tag(model)}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(out), "aggregate": summary["aggregate"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
