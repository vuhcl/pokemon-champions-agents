#!/usr/bin/env python3
"""Non-gating gemma4:12b consistency check on run_1 hand-audit sections.

Uses judge_prompt.md (expect sha 89b99005…). Calls Ollama /api/chat with think=false
(same pattern as part_g_arm/judge/extract.py) — ChatOllama hangs on gemma4 thinking.
Merges after Vu export. Does not change any verdict.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
WT = Path("/Users/nowaki027/part-g-arm-state-run-b98568d")
sys.path.insert(0, str(WT))

from scripts.eval.part_g_arm.state.hand_audit_form import (  # noqa: E402
    build_sections_from_transcript,
)
from scripts.eval.part_g_arm.state.hand_audit_judge import (  # noqa: E402
    JUDGE_MODEL,
    JUDGE_TEMPERATURE,
    PROMPT_PATH,
    _extract_json,
    build_user_payload,
    prompt_sha256,
)
from scripts.eval.part_g_arm.state.request_set_rows import load_request_rows  # noqa: E402

OLLAMA = "http://127.0.0.1:11434"
SCHEMA = {
    "type": "object",
    "properties": {
        "points": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "verdict": {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["id", "verdict"],
            },
        },
        "overall": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["overall"],
}


def _chat(messages: list[dict[str, str]], *, timeout: float = 180.0) -> str:
    body = {
        "model": JUDGE_MODEL,
        "stream": False,
        "think": False,
        "format": SCHEMA,
        "options": {"temperature": JUDGE_TEMPERATURE, "num_predict": 800},
        "keep_alive": "10m",
        "messages": messages,
    }
    req = urllib.request.Request(
        OLLAMA + "/api/chat",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        doc = json.load(r)
    return (doc.get("message") or {}).get("content") or ""


def judge_http(*, rubric: str, user_turns: Any, final_text: str, tool_results: Any) -> dict[str, Any]:
    system = PROMPT_PATH.read_text(encoding="utf-8")
    user = build_user_payload(
        rubric=rubric,
        user_turns=user_turns,
        final_text=final_text,
        tool_results=tool_results,
    )
    raw = _chat(
        [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
    )
    parsed = _extract_json(raw)
    parsed["raw_response"] = raw
    return parsed


def slim_tools(turn: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for c in turn.get("tool_calls") or []:
        res = c.get("result")
        slim: dict[str, Any]
        if isinstance(res, dict):
            slim = {
                k: res[k]
                for k in (
                    "status",
                    "ok",
                    "error",
                    "error_kind",
                    "message",
                    "slot_commit_error",
                    "damage_range",
                    "ko_text",
                    "priority",
                    "pp",
                    "category",
                    "base_power",
                    "type",
                    "move",
                    "speed",
                    "conflicts",
                )
                if k in res
            }
            if isinstance(res.get("options"), list):
                slim["n_options"] = len(res["options"])
            if isinstance(res.get("pending_flags"), list):
                slim["n_pending_flags"] = len(res["pending_flags"])
        else:
            slim = {"raw": str(res)[:200]}
        out.append(
            {
                "name": c.get("name"),
                "args": c.get("args") if "args" in c else c.get("arguments"),
                "result": slim,
            }
        )
    return out


def main() -> int:
    expected_prompt = "89b9900570368074fd45a1ce44981e57fcd6e3da8f3c46f4dbcbb0fc437e5d87"
    got = prompt_sha256()
    if got != expected_prompt:
        print(f"WARN: judge prompt sha {got} != expected {expected_prompt}", file=sys.stderr)

    hand_ids = set(json.loads((ROOT / "run_1_hand_ids.json").read_text())["ids"])
    rows = {r["id"]: r for r in load_request_rows()}
    acceptance = {rid: rows[rid].get("acceptance") or "" for rid in hand_ids if rid in rows}
    transcript = json.loads((ROOT / "run_1" / "transcript.json").read_text())
    sections = build_sections_from_transcript(
        transcript, acceptance_by_id=acceptance, ids=hand_ids
    )

    vu: dict[tuple[str, int], str] = {}
    for r in csv.DictReader((ROOT / "run_1_hand_audit" / "hand_audit_export_1.csv").open()):
        vu[(r["row_id"], int(r["turn"]))] = (r.get("overall") or "").strip()

    print(
        f"judge start n={len(sections)} model={JUDGE_MODEL} prompt={got[:16]}… think=false",
        flush=True,
    )

    results: list[dict[str, Any]] = []
    for sec in sections:
        rid = sec["row_id"]
        turn = int(sec["turn"])
        rubric = sec.get("key_text") or acceptance.get(rid, "")
        points = sec.get("points") or []
        rubric_full = (
            rubric + "\n" + "\n".join(f"- {p.get('id')}: {p.get('text')}" for p in points)
        )[:4000]
        entry = next((e for e in transcript if e.get("id") == rid), None)
        turns = (entry or {}).get("turns") or []
        t = turns[turn - 1] if 0 < turn <= len(turns) else {}
        final_text = (t.get("final_text") or "")[:4000]
        tool_results = slim_tools(t)
        user_turns = [t.get("prompt") or t.get("user") or ""]
        print(f"judging {rid} t{turn}…", flush=True)
        t0 = time.time()
        try:
            gotj = judge_http(
                rubric=rubric_full,
                user_turns=user_turns,
                final_text=final_text,
                tool_results=tool_results,
            )
        except Exception as exc:  # noqa: BLE001
            gotj = {
                "overall": "abstain_error",
                "parse_error": True,
                "reason": f"{type(exc).__name__}: {exc}",
                "raw_response": "",
            }
        elapsed = time.time() - t0
        judge_overall = (gotj.get("overall") or "").strip().lower()
        if gotj.get("parse_error"):
            judge_overall = "abstain_parse_error"
        vu_overall = vu.get((rid, turn), "")
        if judge_overall not in ("pass", "fail", "not_applicable") or not vu_overall:
            agreement = "judge abstained"
        elif judge_overall == vu_overall:
            agreement = "agree"
        else:
            agreement = "disagree"
        results.append(
            {
                "row_id": rid,
                "turn": turn,
                "vu_overall": vu_overall,
                "judge_overall": judge_overall,
                "agreement": agreement,
                "judge_reason": gotj.get("reason") or (gotj.get("raw_response") or "")[:500],
                "points": gotj.get("points"),
                "parse_error": bool(gotj.get("parse_error")),
                "elapsed_s": round(elapsed, 2),
            }
        )
        print(
            f"{rid} t{turn}: vu={vu_overall} judge={judge_overall} → {agreement} ({elapsed:.1f}s)",
            flush=True,
        )

    agree = sum(1 for r in results if r["agreement"] == "agree")
    disagree = sum(1 for r in results if r["agreement"] == "disagree")
    abstain = sum(1 for r in results if r["agreement"] == "judge abstained")
    out = {
        "judge_model": JUDGE_MODEL,
        "temperature": JUDGE_TEMPERATURE,
        "prompt_sha256": prompt_sha256(),
        "transport": "ollama /api/chat think=false",
        "n_sections": len(results),
        "agree": agree,
        "disagree": disagree,
        "judge_abstained": abstain,
        "disagreements": [
            {
                "row_id": r["row_id"],
                "turn": r["turn"],
                "vu_overall": r["vu_overall"],
                "judge_overall": r["judge_overall"],
                "judge_reason": r["judge_reason"],
            }
            for r in results
            if r["agreement"] == "disagree"
        ],
        "sections": results,
    }
    out_dir = ROOT / "run_1_hand_audit"
    path = out_dir / "gemma_merge.json"
    blob = json.dumps(out, indent=2, sort_keys=True) + "\n"
    path.write_text(blob)
    meta = {
        **{
            k: out[k]
            for k in (
                "judge_model",
                "temperature",
                "prompt_sha256",
                "transport",
                "n_sections",
                "agree",
                "disagree",
                "judge_abstained",
            )
        },
        "output_sha256": hashlib.sha256(blob.encode()).hexdigest(),
        "output_path": str(path),
    }
    (out_dir / "gemma_merge_meta.json").write_text(json.dumps(meta, indent=2) + "\n")
    print(json.dumps(meta, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
