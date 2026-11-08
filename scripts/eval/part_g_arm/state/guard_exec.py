"""Execution-time guard: re-check each tool call against the turn's allowed set."""

from __future__ import annotations

from typing import Any, Mapping, MutableMapping, Sequence

from scripts.eval.part_g_arm.state.guard_allowed import (
    allowed_tools,
    pending_fingerprint_matches,
    replace_allowed,
    user_requests_unlock,
)

MAX_TOOL_CALLS_PER_TURN = 16

# a393ae91 / flag-off: names the tool and request class in the user-visible message.
REFUSAL_MESSAGE_LEGACY = (
    "Refused {name}: not allowed for request class {cls}. "
    "Do not retry this call; answer from tools already returned or ask."
)
# FU74 --prompt-cut: no tool or class names in the user-visible string. Structured
# fields (tool, class, reason) still teach the arm what was refused.
REFUSAL_MESSAGE_PROMPT_CUT = (
    "That action was refused for this request. Do not retry it. "
    "Answer from what the tools already returned, or ask the user for the "
    "missing detail (which slot, which species, or confirmation to clear)."
)


def _refusal_message(*, name: str, cls: str) -> str:
    from scripts.eval.part_g_arm.state.tools import prompt_cut_enabled

    if prompt_cut_enabled():
        return REFUSAL_MESSAGE_PROMPT_CUT
    return REFUSAL_MESSAGE_LEGACY.format(name=name, cls=cls)


def model_facing_tool_result(result: Mapping[str, Any]) -> dict[str, Any]:
    """Payload serialized into ToolMessage for the model.

    Under --prompt-cut, strip tool name and class (and reasons that quote them)
    from guard refusals so (b) is complete in the model-facing channel. The run
    log / transcript entry keeps the full result separately.
    """
    from scripts.eval.part_g_arm.state.tools import prompt_cut_enabled

    out = dict(result)
    if not prompt_cut_enabled() or not out.get("guard_blocked"):
        return out
    out.pop("tool", None)
    out.pop("class", None)
    # reason historically embeds the class label; drop it from the model view.
    out.pop("reason", None)
    return out


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
    if name == "clear_slot":
        return bool(args.get("replace"))
    if name == "unlock_slot":
        from scripts.eval.part_g_arm.state.tools import unlock_keeps_values_enabled

        # FU67: unlock_slot keeps values — replace on it is ignored (not a wipe).
        if unlock_keeps_values_enabled():
            return False
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
    user_text: str | None = None,
) -> dict[str, Any] | None:
    """Return a refusal patch if the call must not execute; else None."""
    args = args or {}
    cls = guard_class or "ASK"
    # FU66 sticky unlock gate: before class-only allowed refusal so the message
    # names unlock_fields / unlock_slot (entry 38), not only the class.
    from scripts.eval.part_g_arm.state.tools import (
        sticky_locks_enabled,
        unlock_keeps_values_enabled,
    )

    if sticky_locks_enabled() and name in {"unlock_fields", "unlock_slot"}:
        if not user_requests_unlock(user_text, pending_asked):
            if unlock_keeps_values_enabled():
                path = (
                    "unlock_fields or unlock_slot (both keep values); "
                    "to wipe a slot call clear_slot with replace=true only after "
                    "the user confirms a clear"
                )
            else:
                path = (
                    "unlock_fields (keeps values) or unlock_slot "
                    "(wipe; needs replace=true only after they confirm)"
                )
            return {
                "status": "refused",
                "guard_blocked": True,
                "tool": name,
                "args": dict(args),
                "reason": "unlock without user request",
                "class": cls,
                "message": (
                    f"Refused {name}: unlocking needs an explicit user unlock "
                    f"request this turn. When the user asks to unlock, call {path}."
                ),
            }
    if (
        sticky_locks_enabled()
        and unlock_keeps_values_enabled()
        and name == "clear_slot"
    ):
        from scripts.eval.part_g_arm.state.guard_allowed import user_requests_clear

        if not user_requests_clear(user_text, pending_asked):
            return {
                "status": "refused",
                "guard_blocked": True,
                "tool": name,
                "args": dict(args),
                "reason": "clear without user request",
                "class": cls,
                "message": (
                    "Refused clear_slot: wiping a slot needs an explicit user clear "
                    "or wipe request this turn, then clear_slot with replace=true "
                    "after they confirm. Unlock (unlock_slot / unlock_fields) keeps "
                    "values and is a different action."
                ),
            }
    if name not in allowed:
        return {
            "status": "refused",
            "guard_blocked": True,
            "tool": name,
            "args": dict(args),
            "reason": f"tool not in allowed set for class {cls}",
            "class": cls,
            "message": _refusal_message(name=name, cls=cls),
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

    user_text = turn_ctx.get("user_text")
    pending_asked = turn_ctx.get("pending_asked")
    allowed = set(turn_ctx.get("allowed") or ())
    if not allowed:
        allowed = allowed_tools(
            turn_ctx.get("sub_requests") or [],
            state,
            pending_asked=pending_asked,
            user_text=user_text if isinstance(user_text, str) else None,
        )
        turn_ctx["allowed"] = allowed

    # Recompute state-aware gates each call (fingerprint / valued attrs may change).
    allowed = allowed_tools(
        turn_ctx.get("sub_requests") or [],
        state,
        pending_asked=pending_asked,
        user_text=user_text if isinstance(user_text, str) else None,
    )
    turn_ctx["allowed"] = allowed

    refusal = check_call(
        name,
        args,
        allowed=allowed,
        guard_class=turn_ctx.get("guard_class"),
        confirms_replacement=bool(turn_ctx.get("confirms_replacement")),
        pending_asked=pending_asked,
        state=state,
        user_text=user_text if isinstance(user_text, str) else None,
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
        pending_asked=pending_asked,
        user_text=user_text if isinstance(user_text, str) else None,
    )
    return state, patch


def init_turn_ctx(
    sub_requests: Sequence[Mapping[str, Any]] | None,
    state: Mapping[str, Any],
    *,
    pending_asked: Mapping[str, Any] | None = None,
    user_text: str | None = None,
) -> dict[str, Any]:
    subs = list(sub_requests or [])
    confirms = any(bool(s.get("confirms_replacement")) for s in subs)
    primary = None
    for s in subs:
        if s.get("class"):
            primary = str(s["class"]).upper()
            break
    allowed = allowed_tools(
        subs, state, pending_asked=pending_asked, user_text=user_text
    )
    return {
        "sub_requests": subs,
        "pending_asked": dict(pending_asked) if pending_asked else None,
        "confirms_replacement": confirms,
        "guard_class": primary,
        "user_text": user_text,
        "allowed": allowed,
        "blocked_calls": [],
        "tool_call_count": 0,
        "cap_hit": False,
    }
