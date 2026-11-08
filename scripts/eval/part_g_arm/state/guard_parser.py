"""Structured-output guard parser (same model as the arm; thinking off; once per turn)."""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Mapping

HERE = Path(__file__).resolve().parent
PARSER_PROMPT_PATH = HERE / "prompt_guard_parser.md"
PARSER_PROMPT_V2_PATH = HERE / "prompt_guard_parser_v2.md"


def _active_parser_prompt_path() -> Path:
    from scripts.eval.part_g_arm.state.tools import parser_v2_enabled

    return PARSER_PROMPT_V2_PATH if parser_v2_enabled() else PARSER_PROMPT_PATH

_ATTR_NAMES = (
    "role",
    "species",
    "ability",
    "item",
    "moveset",
    "spread",
    "nature",
)


def parser_prompt_sha256() -> str:
    return hashlib.sha256(_active_parser_prompt_path().read_bytes()).hexdigest()


def compact_state_summary(
    state: Mapping[str, Any],
    *,
    pending_asked: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    from scripts.eval.part_g_arm.state.guard_allowed import pending_fingerprint_matches

    slots_out: list[dict[str, Any]] = []
    for i, slot in enumerate(state.get("team_draft") or []):
        attrs: dict[str, str] = {}
        for name in _ATTR_NAMES:
            a = getattr(slot, name, None)
            if a is None:
                attrs[name] = "empty"
            elif getattr(a, "locked", False):
                attrs[name] = "locked"
            elif getattr(a, "value", None) is not None:
                attrs[name] = "draft"
            else:
                attrs[name] = "empty"
        slots_out.append({"slot": i + 1, "attrs": attrs})
    pending = state.get("pending_presentation")
    pending_kind = pending.get("kind") if isinstance(pending, dict) else None
    constraints = state.get("constraints") or []
    active_n = sum(
        1
        for c in constraints
        if (getattr(c, "still_active", True) if not isinstance(c, dict) else c.get("still_active", True))
    )
    return {
        "slots": slots_out,
        "pending_kind": pending_kind,
        "pending_fingerprint_matches": bool(
            isinstance(pending, dict) and pending_fingerprint_matches(state)
        ),
        "asked_action": dict(pending_asked) if pending_asked else None,
        "constraint_count_active": active_n,
        "constraint_count_total": len(constraints),
    }


_PARSER_SCHEMA: dict[str, Any] = {
    "title": "GuardParse",
    "description": "Ordered sub-requests for the tool guard.",
    "type": "object",
    "properties": {
        "uncertain": {"type": "boolean"},
        "sub_requests": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "class": {
                        "type": "string",
                        "enum": [
                            "LOOKUP",
                            "WRITE",
                            "ASK",
                            "HYPOTHETICAL",
                            "READ_STATE",
                            "PENDING_ANSWER",
                            "READ_ONLY_REFUSE",
                        ],
                    },
                    "action": {
                        "type": ["string", "null"],
                        "enum": [
                            None,
                            "set_slot",
                            "lock_fields",
                            "unlock_fields",
                            "unlock_slot",
                            "select_option",
                            "commit",
                            "reject",
                            "constraint",
                            "change_archetype",
                            "reset",
                        ],
                    },
                    "numeric_or_explain": {"type": "boolean"},
                    "confirms_replacement": {"type": "boolean"},
                },
                "required": [
                    "class",
                    "action",
                    "numeric_or_explain",
                    "confirms_replacement",
                ],
            },
        },
    },
    "required": ["uncertain", "sub_requests"],
}


def parse_user_turn(
    llm: Any,
    user_text: str,
    state: Mapping[str, Any],
    *,
    pending_asked: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """One structured-output call. Returns parser record (subs, flags, latency, sha)."""
    from langchain_core.messages import HumanMessage, SystemMessage

    summary = compact_state_summary(state, pending_asked=pending_asked)
    system = _active_parser_prompt_path().read_text(encoding="utf-8")
    human = (
        f"User message:\n{user_text}\n\n"
        f"State summary (JSON):\n{json.dumps(summary, sort_keys=True)}\n"
    )
    t0 = time.perf_counter()
    # Prefer with_structured_output when available; else JSON-mode invoke.
    structured = None
    try:
        structured = llm.with_structured_output(_PARSER_SCHEMA)
    except Exception:  # noqa: BLE001
        structured = None
    raw: Any
    if structured is not None:
        raw = structured.invoke(
            [SystemMessage(system), HumanMessage(human)]
        )
    else:
        ai = llm.invoke([SystemMessage(system), HumanMessage(human)])
        content = ai.content if hasattr(ai, "content") else ai
        if isinstance(content, list):
            content = "".join(
                p if isinstance(p, str) else str((p or {}).get("text") or "")
                for p in content
            )
        raw = json.loads(str(content))
    latency_ms = int((time.perf_counter() - t0) * 1000)
    if hasattr(raw, "model_dump"):
        data = raw.model_dump()
    elif isinstance(raw, dict):
        data = raw
    else:
        data = dict(raw)
    uncertain = bool(data.get("uncertain"))
    subs = list(data.get("sub_requests") or [])
    if uncertain:
        for s in subs:
            s["uncertain"] = True
    if not subs:
        subs = [
            {
                "class": "ASK",
                "action": None,
                "numeric_or_explain": False,
                "confirms_replacement": False,
                "uncertain": True,
            }
        ]
    return {
        "sub_requests": subs,
        "uncertain": uncertain,
        "parser_latency_ms": latency_ms,
        "parser_prompt_sha256": parser_prompt_sha256(),
        "state_summary": summary,
    }
