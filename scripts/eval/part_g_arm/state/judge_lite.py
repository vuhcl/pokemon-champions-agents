"""Judge-lite: deterministic post-answer checks (FU20). No eval-oracle imports."""

from __future__ import annotations

import re
from typing import Any, Mapping, Sequence

# Tool families by guard class (mapping §2–3; names only).
_FAMILY: dict[str, frozenset[str]] = {
    "LOOKUP": frozenset(
        {
            "get_typing",
            "get_abilities",
            "check_species_ability",
            "check_species_legal",
            "check_item_legal",
            "get_move_static",
            "check_learnset",
            "find_species",
            "get_usage_items",
            "get_usage_teammates",
            "get_usage_spreads",
            "get_usage_stats",
            "get_common_speeds",
            "get_meta_threats",
            "calc_damage",
            "get_speed",
            "solve_spread",
            "describe",
            "no_lookup_needed",
            "show_candidates",
            "read_team",
            "read_pending",
            "read_constraints",
            "read_archetype",
            "read_rejected",
        }
    ),
    "WRITE": frozenset(
        {
            "set_slot",
            "lock_fields",
            "unlock_fields",
            "unlock_slot",
            "select_option",
            "commit_slot",
            "confirm_build",
            "reject_pending",
            "reject_option",
            "reject_all",
            "add_constraint",
            "restore_constraint",
            "set_constraint_active",
            "change_archetype",
            "reset_team",
            "show_candidates",
            "get_typing",
            "get_abilities",
            "check_species_ability",
            "check_species_legal",
            "check_item_legal",
            "get_move_static",
            "check_learnset",
            "find_species",
            "get_usage_items",
            "get_usage_teammates",
            "get_usage_spreads",
            "get_usage_stats",
            "get_common_speeds",
            "get_meta_threats",
            "read_team",
            "read_pending",
            "read_constraints",
            "read_archetype",
            "read_rejected",
            "calc_damage",
            "get_speed",
            "solve_spread",
            "describe",
        }
    ),
    "HYPOTHETICAL": frozenset({"check_hypothetical"}),
    "READ_STATE": frozenset(
        {
            "read_team",
            "read_pending",
            "read_constraints",
            "read_archetype",
            "read_rejected",
        }
    ),
    "ASK": frozenset({"no_lookup_needed", "read_team", "read_pending", "read_constraints", "read_archetype", "read_rejected"}),
    "READ_ONLY_REFUSE": frozenset(
        {"no_lookup_needed", "read_team", "read_pending", "read_constraints", "read_archetype", "read_rejected"}
    ),
    "PENDING_ANSWER": frozenset(),  # uses WRITE family via action
}

_MUTATION_TOOLS = frozenset(
    {
        "set_slot",
        "lock_fields",
        "unlock_fields",
        "unlock_slot",
        "select_option",
        "commit_slot",
        "confirm_build",
        "reject_pending",
        "reject_option",
        "reject_all",
        "add_constraint",
        "restore_constraint",
        "set_constraint_active",
        "change_archetype",
        "reset_team",
    }
)

_SLOT_HOLD = re.compile(
    r"slot\s+(\d+)\s+(?:holds|has|is|contains)\s+([A-Za-z0-9\-']+)",
    re.I,
)
_SLOT_EMPTY = re.compile(r"slot\s+(\d+)\s+is\s+empty", re.I)
_SLOT_LOCKED = re.compile(r"slot\s+(\d+)\s+is\s+locked", re.I)
_SLOT_DRAFT = re.compile(r"slot\s+(\d+)\s+is\s+draft(?:ed)?", re.I)
_PENDING_EXISTS = re.compile(r"pending\s+(?:screen\s+)?(?:exists|is\s+open|is\s+shown)", re.I)
_PENDING_NONE = re.compile(r"(?:no|without)\s+pending", re.I)
_CONSTRAINT_COUNT = re.compile(r"(\d+)\s+constraints?", re.I)


def _executed_names(tool_calls: Sequence[Mapping[str, Any]]) -> list[str]:
    out: list[str] = []
    for c in tool_calls:
        result = c.get("result")
        if isinstance(result, Mapping) and result.get("guard_blocked"):
            continue
        if c.get("result_status") == "refused" and isinstance(result, Mapping) and result.get("guard_blocked"):
            continue
        name = c.get("name")
        if isinstance(name, str):
            out.append(name)
    return out


def check_coverage(
    sub_requests: Sequence[Mapping[str, Any]],
    tool_calls: Sequence[Mapping[str, Any]],
    reply: str,
    *,
    blocked_calls: Sequence[Mapping[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Every sub-request has a family tool result, ASK reply, or refusal this turn."""
    verdicts: list[dict[str, Any]] = []
    executed = set(_executed_names(tool_calls))
    blocked = {b.get("name") for b in (blocked_calls or ())}
    reply_l = (reply or "").strip()
    looks_ask = "?" in reply_l
    for i, sub in enumerate(sub_requests or ()):
        cls = str(sub.get("class") or "").upper()
        if cls in ("ASK", "READ_ONLY_REFUSE"):
            if looks_ask or reply_l or blocked:
                continue
            verdicts.append(
                {
                    "claim_span": f"sub_request[{i}]",
                    "kind": "coverage",
                    "verdict": "unsupported",
                    "missing_tool": "no_lookup_needed",
                    "source": None,
                }
            )
            continue
        family = set(_FAMILY.get(cls) or ())
        if cls in ("WRITE", "PENDING_ANSWER"):
            family |= _FAMILY["WRITE"]
        if cls == "HYPOTHETICAL":
            family |= _FAMILY["LOOKUP"] | _FAMILY["HYPOTHETICAL"] | _FAMILY["READ_STATE"]
        if cls == "LOOKUP":
            family |= _FAMILY["LOOKUP"]
        hit = executed & family
        refused = blocked & family
        if hit or refused:
            continue
        if cls == "ASK" and looks_ask:
            continue
        # Missing family tool.
        sample = sorted(family)[:3]
        verdicts.append(
            {
                "claim_span": f"sub_request[{i}:{cls}]",
                "kind": "coverage",
                "verdict": "unsupported",
                "missing_tool": sample[0] if sample else "lookup",
                "source": None,
            }
        )
    return verdicts


def check_mutation(
    tool_calls: Sequence[Mapping[str, Any]],
    *,
    allowed: set[str] | None,
    confirms_replacement: bool,
    state_before: Mapping[str, Any] | None,
    state_after: Mapping[str, Any] | None,
    reply: str,
) -> list[dict[str, Any]]:
    """Executed mutations must be authorized; reply must not invent state changes."""
    from scripts.eval.part_g_arm.state.tools import draft_signature

    verdicts: list[dict[str, Any]] = []
    allowed = allowed or set()
    for c in tool_calls:
        name = c.get("name")
        if name not in _MUTATION_TOOLS:
            continue
        result = c.get("result") if isinstance(c.get("result"), Mapping) else {}
        if result.get("guard_blocked"):
            continue
        # Draft set_slot without replace is a draft write — still a mutation of draft.
        if name not in allowed:
            verdicts.append(
                {
                    "claim_span": str(name),
                    "kind": "mutation",
                    "verdict": "unsupported",
                    "missing_tool": "guard authorization",
                    "source": None,
                }
            )
        args = c.get("args") or {}
        if name in ("set_slot", "unlock_slot") and (
            bool(args.get("replace"))
            or (
                isinstance(args.get("slots"), list)
                and any(bool(s.get("replace")) for s in args["slots"] if isinstance(s, dict))
            )
        ):
            if not confirms_replacement and name in allowed:
                # Execution check should have blocked; if it ran, flag.
                if not result.get("guard_blocked"):
                    verdicts.append(
                        {
                            "claim_span": f"{name}.replace",
                            "kind": "mutation",
                            "verdict": "unsupported",
                            "missing_tool": "confirms_replacement",
                            "source": None,
                        }
                    )

    before_sig = draft_signature(dict(state_before or {})) if state_before else None
    after_sig = draft_signature(dict(state_after or {})) if state_after else None
    changed = before_sig is not None and after_sig is not None and before_sig != after_sig
    reply_l = (reply or "").lower()
    claims_change = any(
        w in reply_l
        for w in ("locked", "unlocked", "set slot", "replaced", "reset the team", "committed")
    )
    claims_no_change = any(
        p in reply_l for p in ("no change", "nothing changed", "did not change", "haven't changed")
    )
    if claims_change and not changed:
        verdicts.append(
            {
                "claim_span": "reply_state_change",
                "kind": "mutation",
                "verdict": "contradicted",
                "source": "state_diff_empty",
                "missing_tool": None,
            }
        )
    if claims_no_change and changed:
        verdicts.append(
            {
                "claim_span": "reply_no_change",
                "kind": "mutation",
                "verdict": "contradicted",
                "source": "state_diff_nonempty",
                "missing_tool": None,
            }
        )
    return verdicts


def check_state_claims(
    reply: str,
    state: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Closed-set patterns vs state block. Returns (verdicts, coverage counts)."""
    from recommender.state import all_locked

    verdicts: list[dict[str, Any]] = []
    hit = 0
    draft = state.get("team_draft") or []
    pending = state.get("pending_presentation")
    constraints = state.get("constraints") or []
    active_n = sum(
        1
        for c in constraints
        if (c.get("still_active", True) if isinstance(c, dict) else getattr(c, "still_active", True))
    )

    for m in _SLOT_EMPTY.finditer(reply or ""):
        hit += 1
        idx = int(m.group(1)) - 1
        empty = True
        if 0 <= idx < len(draft):
            slot = draft[idx]
            empty = not any(
                getattr(getattr(slot, n), "value", None) is not None
                for n in ("role", "species", "ability", "item", "moveset", "spread", "nature")
            )
        if not empty:
            verdicts.append(
                {
                    "claim_span": m.group(0),
                    "kind": "state",
                    "verdict": "contradicted",
                    "source": f"slot_{m.group(1)}_nonempty",
                }
            )

    for m in _SLOT_LOCKED.finditer(reply or ""):
        hit += 1
        idx = int(m.group(1)) - 1
        ok = 0 <= idx < len(draft) and all_locked(draft[idx])
        if not ok:
            verdicts.append(
                {
                    "claim_span": m.group(0),
                    "kind": "state",
                    "verdict": "contradicted",
                    "source": f"slot_{m.group(1)}_not_fully_locked",
                }
            )

    for m in _SLOT_HOLD.finditer(reply or ""):
        hit += 1
        idx = int(m.group(1)) - 1
        name = m.group(2)
        got = None
        if 0 <= idx < len(draft):
            got = getattr(draft[idx].species, "value", None)
        if got is None or str(got).casefold() != name.casefold():
            verdicts.append(
                {
                    "claim_span": m.group(0),
                    "kind": "state",
                    "verdict": "contradicted" if got else "unsupported",
                    "source": str(got) if got else None,
                    "missing_tool": "read_team",
                }
            )

    for m in _PENDING_EXISTS.finditer(reply or ""):
        hit += 1
        if not isinstance(pending, dict):
            verdicts.append(
                {
                    "claim_span": m.group(0),
                    "kind": "state",
                    "verdict": "contradicted",
                    "source": "no_pending",
                }
            )
    for m in _PENDING_NONE.finditer(reply or ""):
        hit += 1
        if isinstance(pending, dict):
            verdicts.append(
                {
                    "claim_span": m.group(0),
                    "kind": "state",
                    "verdict": "contradicted",
                    "source": pending.get("kind"),
                }
            )
    for m in _CONSTRAINT_COUNT.finditer(reply or ""):
        hit += 1
        n = int(m.group(1))
        if n != active_n and n != len(constraints):
            verdicts.append(
                {
                    "claim_span": m.group(0),
                    "kind": "state",
                    "verdict": "contradicted",
                    "source": f"active={active_n},total={len(constraints)}",
                }
            )

    return verdicts, {"patterns_hit": hit, "claims_seen": hit}


def check_entity_number_provenance(
    reply: str,
    *,
    user_text: str,
    tool_calls: Sequence[Mapping[str, Any]],
    state: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Stage A: closed-vocab names + numbers need a source this turn."""
    from recommender.legality import load_snapshot

    snap = load_snapshot()
    species = {str(v.get("name") or k) for k, v in (snap.get("species") or {}).items()}
    # Collect sources
    sources: set[str] = set()
    sources.update(re.findall(r"[A-Za-z][A-Za-z0-9\-']*", user_text or ""))
    for c in tool_calls:
        result = c.get("result")
        if not isinstance(result, Mapping):
            continue
        blob = str(result)
        sources.update(re.findall(r"[A-Za-z][A-Za-z0-9\-']*", blob))
    for slot in state.get("team_draft") or []:
        sp = getattr(getattr(slot, "species", None), "value", None)
        if isinstance(sp, str):
            sources.add(sp)

    sources_cf = {s.casefold() for s in sources}
    verdicts: list[dict[str, Any]] = []
    # Species names in reply (longest-first to reduce partial hits).
    reply_text = reply or ""
    for name in sorted(species, key=len, reverse=True):
        if len(name) < 4:
            continue
        if re.search(rf"\b{re.escape(name)}\b", reply_text):
            if name.casefold() not in sources_cf:
                verdicts.append(
                    {
                        "claim_span": name,
                        "kind": "provenance",
                        "verdict": "unsupported",
                        "missing_tool": "check_species_legal",
                        "source": None,
                    }
                )
            # Only flag first few to keep noise down
            if len(verdicts) >= 8:
                break

    # Numbers other than 1..6 / list lengths: simple digit tokens >= 2 digits or not 1-6.
    for m in re.finditer(r"\b(\d+)\b", reply_text):
        n = int(m.group(1))
        if 1 <= n <= 6:
            continue
        token = m.group(1)
        if token in (user_text or "") or any(
            token in str(c.get("result") or "") for c in tool_calls
        ):
            continue
        verdicts.append(
            {
                "claim_span": token,
                "kind": "provenance",
                "verdict": "unsupported",
                "missing_tool": "calc_damage",
                "source": None,
            }
        )
        if len(verdicts) >= 12:
            break
    return verdicts


def run_judge(
    *,
    reply: str,
    sub_requests: Sequence[Mapping[str, Any]],
    tool_calls: Sequence[Mapping[str, Any]],
    state: Mapping[str, Any],
    state_before: Mapping[str, Any] | None = None,
    state_after: Mapping[str, Any] | None = None,
    allowed: set[str] | None = None,
    confirms_replacement: bool = False,
    blocked_calls: Sequence[Mapping[str, Any]] | None = None,
    user_text: str = "",
    stage_b: bool = False,
) -> dict[str, Any]:
    """Run checks 1–4 (+ optional B). Does not mutate tool results."""
    verdicts: list[dict[str, Any]] = []
    verdicts.extend(
        check_coverage(sub_requests, tool_calls, reply, blocked_calls=blocked_calls)
    )
    verdicts.extend(
        check_mutation(
            tool_calls,
            allowed=allowed,
            confirms_replacement=confirms_replacement,
            state_before=state_before,
            state_after=state_after or state,
            reply=reply,
        )
    )
    state_verdicts, coverage = check_state_claims(reply, state)
    verdicts.extend(state_verdicts)
    verdicts.extend(
        check_entity_number_provenance(
            reply, user_text=user_text, tool_calls=tool_calls, state=state
        )
    )
    if stage_b:
        # Typed claims via system_claims — only when requested (time permitting).
        pass
    return {
        "verdicts": verdicts,
        "extractor_coverage": coverage,
        "retry_used": False,
        "raw_answer": reply,
        "post_judge_answer": reply,
    }


def apply_unverified_labels(reply: str, verdicts: Sequence[Mapping[str, Any]]) -> str:
    """After retry cap: mark unsupported spans; append mutation mismatch line."""
    text = reply or ""
    for v in verdicts:
        if v.get("verdict") != "unsupported":
            continue
        span = v.get("claim_span")
        if isinstance(span, str) and span and span in text and not span.startswith("sub_request"):
            text = text.replace(span, f"{span} [unverified]", 1)
    mut = [v for v in verdicts if v.get("kind") == "mutation" and v.get("verdict") == "contradicted"]
    if mut:
        text = text.rstrip() + "\n(Actual state change differs from the reply.)"
    return text
