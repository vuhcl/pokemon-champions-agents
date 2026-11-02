"""Execution-time guard: re-check each tool call against the turn's allowed set."""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping, Sequence

from scripts.eval.part_g_arm.state.guard_allowed import (
    allowed_tools,
    pending_fingerprint_matches,
    replace_allowed,
)

MAX_TOOL_CALLS_PER_TURN = 16


def _replace_flag(name: str, args: Mapping[str, Any]) -> bool:
    if name == "set_slot":
        if bool(args.get("replace")):
            return True
        slots = args.get("slots")
        if isinstance(slots, list):
            return any(
                bool(s.get("replace")) for s in slots if isinstance(s, dict)
            )
        return False
    if name == "unlock_slot":
        return bool(args.get("replace"))
    return False


def check_call(
    name: str,
    args: Mapping[str, Any] | None,
    *,
    allowed: set[str],
    guard_class: str | None,
    confirms_replacement: bool,
    pending_asked: Mapping[str, Any] | None,
    state: Mapping[str, Any],
) -> dict[str, Any] | None:
    """Return a refusal patch if the call must not execute; else None."""
    args = args or {}
    cls = guard_class or "ASK"
    if name not in allowed:
        return {
            "status": "refused",
            "guard_blocked": True,
            "tool": name,
            "args": dict(args),
            "reason": f"tool not in allowed set for class {cls}",
            "class": cls,
            "message": (
                f"Refused {name}: not allowed for request class {cls}. "
                "Do not retry this call; answer from tools already returned or ask."
            ),
        }
    if name == "select_option" and not pending_fingerprint_matches(state):
        return {
            "status": "refused",
            "guard_blocked": True,
            "tool": name,
            "args": dict(args),
            "reason": "OL10a: pending team_fingerprint mismatch",
            "class": cls,
            "message": (
                "Refused select_option: pending candidate list is stale for the "
                "current team. Re-run show_candidates."
            ),
        }
    if _replace_flag(name, args) and not replace_allowed(
        confirms_replacement=confirms_replacement,
        pending_asked=pending_asked,
    ):
        return {
            "status": "refused",
            "guard_blocked": True,
            "tool": name,
            "args": dict(args),
            "reason": "replace=true without confirmation",
            "class": cls,
            "message": (
                f"Refused {name} with replace=true: user has not confirmed "
                "replacement this turn."
            ),
        }
    return None


def guarded_dispatch(
    state: dict[str, Any],
    arm: Any,
    name: str,
    args: dict[str, Any] | None,
    *,
    turn_ctx: MutableMapping[str, Any],
    dispatch_fn: Any,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Wrap harness.dispatch with allowed-set / replace / OL10a / call-cap checks."""
    args = args or {}
    blocked: list[dict[str, Any]] = turn_ctx.setdefault("blocked_calls", [])
    call_count = int(turn_ctx.get("tool_call_count") or 0)
    if call_count >= MAX_TOOL_CALLS_PER_TURN:
        refusal = {
            "status": "refused",
            "guard_blocked": True,
            "tool": name,
            "args": dict(args),
            "reason": f"per-turn tool call cap ({MAX_TOOL_CALLS_PER_TURN})",
            "class": turn_ctx.get("guard_class"),
            "message": (
                f"Refused {name}: turn hit the {MAX_TOOL_CALLS_PER_TURN} tool-call cap."
            ),
        }
        blocked.append(
            {"name": name, "args": dict(args), "reason": refusal["reason"]}
        )
        turn_ctx["cap_hit"] = True
        return state, refusal

    allowed = set(turn_ctx.get("allowed") or ())
    if not allowed:
        allowed = allowed_tools(
            turn_ctx.get("sub_requests") or [],
            state,
            pending_asked=turn_ctx.get("pending_asked"),
        )
        turn_ctx["allowed"] = allowed

    # Recompute state-aware gates each call (fingerprint / valued attrs may change).
    allowed = allowed_tools(
        turn_ctx.get("sub_requests") or [],
        state,
        pending_asked=turn_ctx.get("pending_asked"),
    )
    turn_ctx["allowed"] = allowed

    refusal = check_call(
        name,
        args,
        allowed=allowed,
        guard_class=turn_ctx.get("guard_class"),
        confirms_replacement=bool(turn_ctx.get("confirms_replacement")),
        pending_asked=turn_ctx.get("pending_asked"),
        state=state,
    )
    if refusal is not None:
        blocked.append(
            {"name": name, "args": dict(args), "reason": refusal["reason"]}
        )
        return state, refusal

    turn_ctx["tool_call_count"] = call_count + 1
    state, patch = dispatch_fn(state, arm, name, args)
    # Recompute after execution so later calls in the same turn see draft writes
    # (e.g. set_slot then lock_fields — FU23 §2).
    turn_ctx["allowed"] = allowed_tools(
        turn_ctx.get("sub_requests") or [],
        state,
        pending_asked=turn_ctx.get("pending_asked"),
    )
    return state, patch


def init_turn_ctx(
    sub_requests: Sequence[Mapping[str, Any]] | None,
    state: Mapping[str, Any],
    *,
    pending_asked: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    subs = list(sub_requests or [])
    confirms = any(bool(s.get("confirms_replacement")) for s in subs)
    primary = None
    for s in subs:
        if s.get("class"):
            primary = str(s["class"]).upper()
            break
    allowed = allowed_tools(subs, state, pending_asked=pending_asked)
    return {
        "sub_requests": subs,
        "pending_asked": dict(pending_asked) if pending_asked else None,
        "confirms_replacement": confirms,
        "guard_class": primary,
        "allowed": allowed,
        "blocked_calls": [],
        "tool_call_count": 0,
        "cap_hit": False,
    }
