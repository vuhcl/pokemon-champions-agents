#!/usr/bin/env python3
"""Bare-LLM baseline: no tools, two elicitation conditions (never averaged).

Conditions (see scripts/eval/scenarios_bare_llm.py):
  chat — ungrounded chat baseline (whole-team ask)
  slot — ungrounded, matched decomposition (slot-by-slot)

Usage:
  BOOTSTRAP_OLLAMA_MODEL=qwen2.5:7b uv run python scripts/eval/run_bare_llm_baseline.py --condition chat
  BOOTSTRAP_OLLAMA_MODEL=qwen2.5:7b uv run python scripts/eval/run_bare_llm_baseline.py --condition slot
  BOOTSTRAP_OLLAMA_MODEL=qwen2.5:7b uv run python scripts/eval/run_bare_llm_baseline.py --condition both
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
    CHAT_CONTINUER,
    CONDITIONS,
    DEFAULT_RUNS,
    SLOT_CONTINUER,
    SLOT_STEERING,
    SOFT_MECH_NUDGE,
    TEMPERATURE,
    Condition,
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


def _build_chat(model: str, temperature: float) -> dict[str, Any]:
    """Return a lightweight chat handle (Ollama HTTP — urllib timeout works)."""
    # qwen3.5 defaults to a thinking channel; with a tight num_predict budget
    # content stays empty. Disable think so bare-LLM output matches qwen2.5 shape.
    think = False if "qwen3.5" in model.lower() or "qwen35" in model.lower() else None
    return {
        "model": model,
        "temperature": temperature,
        "num_predict": 256,
        "think": think,
    }


def _message_role(msg: Any) -> str:
    t = getattr(msg, "type", None) or ""
    if t in ("human", "user"):
        return "user"
    if t in ("ai", "assistant"):
        return "assistant"
    # fallback by class name
    name = type(msg).__name__.lower()
    if "human" in name:
        return "user"
    return "assistant"


def _invoke(chat: dict[str, Any], history: list[Any]) -> str:
    """POST /api/chat with socket timeout (LangChain+thread timeout is unreliable here)."""
    messages = []
    for m in history:
        content = getattr(m, "content", None)
        if not isinstance(content, str):
            content = str(content)
        messages.append({"role": _message_role(m), "content": content})
    body_obj: dict[str, Any] = {
        "model": chat["model"],
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": chat["temperature"],
            "num_predict": chat["num_predict"],
        },
    }
    if chat.get("think") is not None:
        body_obj["think"] = chat["think"]
    body = json.dumps(body_obj).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:11434/api/chat",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120.0) as resp:
            data = json.loads(resp.read().decode())
    except TimeoutError:
        return "[eval: model invoke timed out after 120s]"
    except urllib.error.URLError as exc:
        return f"[eval: ollama error: {exc}]"
    msg = data.get("message") or {}
    content = msg.get("content")
    if isinstance(content, str) and content.strip():
        return content
    # Fallback if a thinking model still returns empty content.
    thinking = msg.get("thinking")
    if isinstance(thinking, str) and thinking.strip():
        return thinking
    return content if isinstance(content, str) else str(content or data)


def _maybe_nudge(
    history: list[Any],
    transcript_parts: list[str],
    chat: Any,
    *,
    nudge_used: bool,
    team_slots: int,
    organic_mech: int,
) -> bool:
    """Return updated nudge_used. At most one soft mech nudge."""
    from langchain_core.messages import AIMessage, HumanMessage

    if nudge_used or organic_mech > 0 or team_slots < 4:
        return nudge_used
    history.append(HumanMessage(content=SOFT_MECH_NUDGE))
    transcript_parts.append(f"USER: {SOFT_MECH_NUDGE}")
    content = _invoke(chat, history)
    history.append(AIMessage(content=content))
    transcript_parts.append(f"ASSISTANT: {content}")
    return True


def _run_chat_condition(chat: Any, *, turn_cap: int) -> tuple[str, bool]:
    from langchain_core.messages import AIMessage, HumanMessage

    cond = CONDITIONS["chat"]
    history: list[Any] = [HumanMessage(content=cond.initial)]
    transcript_parts: list[str] = [f"USER: {cond.initial}"]
    nudge_used = False

    for turn in range(turn_cap):
        content = _invoke(chat, history)
        history.append(AIMessage(content=content))
        transcript_parts.append(f"ASSISTANT: {content}")

        so_far = "\n".join(transcript_parts)
        organic_mech = len(_SPE_CLAIM.findall(so_far)) + len(
            _KO_CLAIM.findall(so_far)
        )
        team = extract_team(so_far)
        if team.completed:
            nudge_used = _maybe_nudge(
                history,
                transcript_parts,
                chat,
                nudge_used=nudge_used,
                team_slots=len(team.slots),
                organic_mech=organic_mech,
            )
            break

        history.append(HumanMessage(content=CHAT_CONTINUER))
        transcript_parts.append(f"USER: {CHAT_CONTINUER}")
        if (
            not nudge_used
            and len(team.slots) >= 4
            and organic_mech == 0
            and turn >= 2
        ):
            history[-1] = HumanMessage(content=SOFT_MECH_NUDGE)
            transcript_parts[-1] = f"USER: {SOFT_MECH_NUDGE}"
            nudge_used = True

    return "\n\n".join(transcript_parts), nudge_used


def _run_slot_condition(chat: Any, *, turn_cap: int) -> tuple[str, bool]:
    """Theme → species/set steering through 6 slots; no tools.

    Always exhausts all SLOT_STEERING lines even if extract_team reports
    completed mid-script (avoids stopping before slots 4–6 were asked).
    """
    from langchain_core.messages import AIMessage, HumanMessage

    cond = CONDITIONS["slot"]
    history: list[Any] = [HumanMessage(content=cond.initial)]
    transcript_parts: list[str] = [f"USER: {cond.initial}"]
    nudge_used = False
    steer_i = 0
    continuer_after_steer = 0

    for _turn in range(turn_cap):
        print(f"  … slot turn {_turn + 1}/{turn_cap} steer={steer_i}", file=sys.stderr, flush=True)
        content = _invoke(chat, history)
        history.append(AIMessage(content=content))
        transcript_parts.append(f"ASSISTANT: {content}")
        if content.startswith("[eval:"):
            print(f"  ! {content}", file=sys.stderr, flush=True)

        so_far = "\n".join(transcript_parts)
        organic_mech = len(_SPE_CLAIM.findall(so_far)) + len(
            _KO_CLAIM.findall(so_far)
        )
        team = extract_team(so_far)
        # Exhaust all steers before accepting completion.
        if team.completed and steer_i >= len(SLOT_STEERING):
            nudge_used = _maybe_nudge(
                history,
                transcript_parts,
                chat,
                nudge_used=nudge_used,
                team_slots=len(team.slots),
                organic_mech=organic_mech,
            )
            break

        if steer_i < len(SLOT_STEERING):
            nxt = SLOT_STEERING[steer_i]
            steer_i += 1
        elif team.completed:
            nudge_used = _maybe_nudge(
                history,
                transcript_parts,
                chat,
                nudge_used=nudge_used,
                team_slots=len(team.slots),
                organic_mech=organic_mech,
            )
            break
        else:
            continuer_after_steer += 1
            if continuer_after_steer > 2:
                break
            nxt = SLOT_CONTINUER

        history.append(HumanMessage(content=nxt))
        transcript_parts.append(f"USER: {nxt}")

    return "\n\n".join(transcript_parts), nudge_used


def _run_one(chat: Any, condition: Condition, *, turn_cap: int) -> tuple[str, bool]:
    if condition.id == "chat":
        return _run_chat_condition(chat, turn_cap=turn_cap)
    if condition.id == "slot":
        return _run_slot_condition(chat, turn_cap=turn_cap)
    raise ValueError(f"unknown condition {condition.id!r}")


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


def _run_condition(
    *,
    condition: Condition,
    model: str,
    runs_n: int,
    temperature: float,
    turn_cap: int | None,
    calc_ok: bool,
    snap: dict[str, Any],
    snap_path: Path,
    out: Path | None,
) -> dict[str, Any]:
    cap = turn_cap if turn_cap is not None else condition.turn_cap
    chat = _build_chat(model, temperature)
    runs: list[dict[str, Any]] = []
    for i in range(runs_n):
        print(
            f"=== [{condition.id}] run {i + 1}/{runs_n} model={model} ===",
            file=sys.stderr,
        )
        transcript, nudge = _run_one(chat, condition, turn_cap=cap)
        score = score_transcript(transcript, snap, calc_ok=calc_ok)
        runs.append(
            {
                "run": i + 1,
                "mech_nudge_used": nudge,
                "transcript_truncated": transcript[:12000],
                "transcript_chars": len(transcript),
                "transcript_full": transcript,
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
        "label": f"Bare-LLM — {condition.label}",
        "condition_id": condition.id,
        "condition_label": condition.label,
        "measured": str(date.today()),
        "model": model,
        "temperature": temperature,
        "runs": runs_n,
        "turn_cap": cap,
        "prompt": condition.initial,
        "oracle_snapshot": str(snap_path),
        "calc_ok": calc_ok,
        "aggregate": _aggregate(runs),
        "runs_detail": runs,
        "notes": [
            "No LangGraph / no tools; ChatOllama free-form only.",
            f"Condition: {condition.label} ({condition.id}).",
            "Do not average or merge with the other bare-LLM condition.",
            "Slot: always exhausts all SLOT_STEERING lines before stop.",
            "Species-fact axis includes build-derived move/ability claims from sets.",
            "Legality oracle: same build_oracle_snapshot(mod=champions) as run_legality.",
            "Soft mech nudge at most once if ≥4 slots and zero organic mech claims.",
        ],
    }

    path = out or (
        ARTIFACTS
        / f"bare_llm_{condition.id}_{_model_tag(model)}.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "artifact": str(path),
                "condition": condition.id,
                "condition_label": condition.label,
                "aggregate": summary["aggregate"],
            },
            indent=2,
        )
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--condition",
        choices=("chat", "slot", "both"),
        default="both",
        help="chat=ungrounded chat baseline; slot=matched decomposition; "
        "both=run separately (default; never averaged)",
    )
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS)
    parser.add_argument(
        "--turn-cap",
        type=int,
        default=None,
        help="Override condition default turn cap",
    )
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

    if args.out is not None and args.condition == "both":
        print("ABORT: --out requires a single --condition (chat|slot)", file=sys.stderr)
        return 2

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

    try:
        snap_path = build_oracle_snapshot(mod="champions")
    except Exception as exc:
        # Sandbox/CI may block npx tsx IPC; fall back to committed snapshot.
        snap_path = ROOT / "data" / "legality" / "champions.v1.json"
        print(
            f"WARN: build_oracle_snapshot failed ({exc}); "
            f"using committed snapshot {snap_path}",
            file=sys.stderr,
            flush=True,
        )
        if not snap_path.exists():
            print("ABORT: no legality snapshot available", file=sys.stderr)
            return 2
    snap = load_oracle_snapshot(snap_path)

    ids = ("chat", "slot") if args.condition == "both" else (args.condition,)
    for cid in ids:
        _run_condition(
            condition=CONDITIONS[cid],
            model=model,
            runs_n=args.runs,
            temperature=args.temperature,
            turn_cap=args.turn_cap,
            calc_ok=calc_ok,
            snap=snap,
            snap_path=snap_path,
            out=args.out,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
